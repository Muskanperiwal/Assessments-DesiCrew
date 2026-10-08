"""RAG Engine for task2_support app.

Handles:
1. Document ingestion and chunking for PDFs using PyMuPDF (fitz) and markdown files.
2. Metadata preservation: source_file, page_number, and section_title.
3. Persistent local ChromaDB vector store initialization and indexing.
4. Top-K chunk semantic retrieval (get_relevant_context).
5. Clean context string formatting for LLM prompt injection with strict citations.
"""
import os
import re
import io
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image

try:
    import pymupdf  # PyMuPDF
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

import chromadb
from chromadb.config import Settings as ChromaSettings
from django.conf import settings

logger = logging.getLogger(__name__)

# Stop words for lightweight lexical fallback
STOP_WORDS = {
    'what', 'when', 'where', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or',
    'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about',
    'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above',
    'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under',
    'again', 'further', 'then', 'once', 'here', 'there', 'all', 'any', 'both', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'can', 'will', 'just', 'should', 'now',
    'could', 'how', 'many', 'much', 'your', 'our', 'my', 'their', 'its'
}


class DocumentChunk:
    def __init__(self, chunk_id: str, text: str, source_file: str, page_number: int, section_title: str):
        self.chunk_id = chunk_id
        self.text = text.strip()
        self.source_file = source_file
        self.page_number = page_number
        self.section_title = section_title

    @property
    def citation(self) -> str:
        return f"[Doc: {self.source_file}, Page: {self.page_number}, Section: {self.section_title}]"

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "page_number": int(self.page_number),
            "section_title": str(self.section_title),
            "citation": self.citation
        }


class SupportRAGEngine:
    """Manages document parsing, ChromaDB indexing, and context retrieval."""

    def __init__(self, docs_dir: Optional[Path] = None, chroma_dir: Optional[Path] = None):
        if settings.configured:
            base_dir = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)
            data_dir = getattr(settings, 'DATA_DIR', base_dir / 'data')
        else:
            base_dir = Path(__file__).resolve().parent.parent
            data_dir = base_dir / 'data'
        self.docs_dir = docs_dir or data_dir / 'support_documents'
        self.fallback_docs_dir = data_dir / 'support_documents'
        self.chroma_dir = chroma_dir or data_dir / 'chroma_db'
        
        self.collection_name = "support_knowledge_base"
        self._client = None
        self._collection = None
        self._in_memory_chunks: List[DocumentChunk] = []

        self._initialize_vector_store()

    def _initialize_vector_store(self):
        """Initializes ChromaDB persistent client and indexes knowledge base documents."""
        try:
            self.chroma_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            self._collection = self._client.get_or_create_collection(name=self.collection_name)
            
            # Check if collection is empty or requires population
            if self._collection.count() == 0:
                logger.info("Chroma collection empty. Indexing knowledge base documents...")
                self.index_documents()
            else:
                logger.info(f"Loaded existing Chroma collection with {self._collection.count()} chunks.")
                # Also load in-memory chunks for fast lexical fallback
                self._load_fallback_chunks()
                self._ensure_custom_uploads_indexed()
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}. Relying on in-memory parsed index.", exc_info=True)
            self._load_fallback_chunks()

    def _load_fallback_chunks(self):
        """Loads and parses documents into in-memory list for fallback search."""
        self._in_memory_chunks = self._parse_all_documents()

    def _parse_all_documents(self) -> List[DocumentChunk]:
        """Parses baseline PDFs/MD and any files under uploads/."""
        chunks: List[DocumentChunk] = []
        target_dir = self.docs_dir if self.docs_dir.exists() else self.fallback_docs_dir

        if not target_dir.exists():
            logger.warning(f"Support documents directory does not exist: {target_dir}")
            return chunks

        pdf_files = list(target_dir.glob('*.pdf'))
        if pdf_files and pymupdf is not None:
            for file_path in sorted(pdf_files):
                chunks.extend(self._parse_pdf(file_path))
        else:
            for file_path in sorted(target_dir.iterdir()):
                if not file_path.is_file():
                    continue
                suffix = file_path.suffix.lower()
                if suffix in ('.md', '.txt'):
                    chunks.extend(self._parse_markdown(file_path))

        uploads_dir = target_dir / 'uploads'
        if uploads_dir.exists():
            for file_path in sorted(uploads_dir.iterdir()):
                if not file_path.is_file():
                    continue
                suffix = file_path.suffix.lower()
                try:
                    raw = file_path.read_bytes()
                except OSError as e:
                    logger.warning(f"Could not read upload {file_path}: {e}")
                    continue
                if suffix == '.pdf' and pymupdf is not None:
                    chunks.extend(self._parse_pdf_from_bytes(raw, file_path.name))
                elif suffix in ('.md', '.txt'):
                    chunks.extend(self._parse_markdown(file_path))
                elif suffix == '.docx':
                    parsed = self._parse_docx_bytes(raw, file_path.name)
                    chunks.extend(parsed)

        return chunks

    def _parse_pdf_from_bytes(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        """Parse PDF bytes into chunks (used for uploads folder sync)."""
        chunks: List[DocumentChunk] = []
        if pymupdf is None:
            return chunks
        file_stem = Path(filename).stem.replace('_', ' ')
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                raw_text = (doc[page_idx].get_text() or "").strip()
                if not raw_text:
                    continue
                section_title = self._extract_section_title(raw_text, fallback=f"{file_stem} - Page {page_num}")
                paragraphs = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 30]
                if not paragraphs:
                    paragraphs = [raw_text]
                for p_idx, para in enumerate(paragraphs, 1):
                    chunk_id = f"custom_{Path(filename).stem}_p{page_num}_c{p_idx}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        text=para,
                        source_file=filename,
                        page_number=page_num,
                        section_title=section_title,
                    ))
            doc.close()
        except Exception as e:
            logger.error(f"Error parsing PDF bytes for {filename}: {e}")
        return chunks

    def _parse_docx_bytes(self, file_bytes: bytes, filename: str) -> List[DocumentChunk]:
        import zipfile
        import xml.etree.ElementTree as ET
        chunks: List[DocumentChunk] = []
        file_stem = Path(filename).stem.replace('_', ' ')
        paragraphs: List[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                if 'word/document.xml' in z.namelist():
                    root = ET.fromstring(z.read('word/document.xml'))
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    for p in root.findall('.//w:p', ns):
                        texts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                        if texts:
                            p_text = "".join(texts).strip()
                            if len(p_text) > 15:
                                paragraphs.append(p_text)
        except Exception as e:
            logger.error(f"Error parsing docx {filename}: {e}")
            return chunks
        if not paragraphs:
            return chunks
        section_title = self._extract_section_title("\n".join(paragraphs[:3]), fallback=f"{file_stem} Overview")
        for p_idx, para in enumerate(paragraphs, 1):
            chunk_id = f"custom_{Path(filename).stem}_p1_c{p_idx}"
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                text=para,
                source_file=filename,
                page_number=1,
                section_title=section_title,
            ))
        return chunks

    def _ensure_custom_uploads_indexed(self):
        """Upsert any files in uploads/ that are missing from the vector index."""
        uploads_dir = self.docs_dir / 'uploads'
        if not uploads_dir.exists() or self._collection is None:
            return
        indexed_sources = set()
        try:
            res = self._collection.get(include=['metadatas'])
            for meta in res.get('metadatas') or []:
                if meta and meta.get('source_file'):
                    indexed_sources.add(meta['source_file'])
        except Exception as e:
            logger.warning(f"Could not list indexed sources: {e}")
            return

        for file_path in sorted(uploads_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.name in indexed_sources:
                continue
            suffix = file_path.suffix.lower()
            if suffix not in ('.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp'):
                continue
            try:
                result = self.index_custom_document(file_path.read_bytes(), file_path.name)
                if result.get('success'):
                    logger.info(f"Auto-indexed upload: {file_path.name}")
            except Exception as e:
                logger.warning(f"Failed auto-index {file_path.name}: {e}")

    def _parse_pdf(self, file_path: Path) -> List[DocumentChunk]:
        """Extracts text per page from PDF using PyMuPDF (fitz) and segments into chunks."""
        chunks: List[DocumentChunk] = []
        if pymupdf is None:
            logger.warning("PyMuPDF not installed, cannot parse PDF.")
            return chunks

        try:
            doc = pymupdf.open(str(file_path))
            for page_idx in range(len(doc)):
                page_num = page_idx + 1
                page = doc[page_idx]
                raw_text = page.get_text() or ""
                if not raw_text.strip():
                    continue

                # Determine section heading
                section_title = self._extract_section_title(raw_text, fallback=f"Page {page_num}")
                
                # Split page text into meaningful paragraphs
                paragraphs = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 30]
                if not paragraphs:
                    paragraphs = [raw_text.strip()]

                for p_idx, para in enumerate(paragraphs, 1):
                    chunk_id = f"{file_path.stem}_p{page_num}_c{p_idx}"
                    chunks.append(DocumentChunk(
                        chunk_id=chunk_id,
                        text=para,
                        source_file=file_path.name,
                        page_number=page_num,
                        section_title=section_title
                    ))
            doc.close()
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {e}")

        return chunks

    def _parse_markdown(self, file_path: Path) -> List[DocumentChunk]:
        """Parses structured markdown or text policy document."""
        chunks: List[DocumentChunk] = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            sections = content.split('\n## ')
            doc_title = file_path.stem.replace('_', ' ')

            for sec_idx, sec_text in enumerate(sections, 1):
                clean_sec = sec_text.strip()
                if not clean_sec:
                    continue
                if sec_idx > 1:
                    clean_sec = '## ' + clean_sec

                section_title = self._extract_section_title(clean_sec, fallback=f"Section {sec_idx}")
                chunk_id = f"{file_path.stem}_sec{sec_idx}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=clean_sec,
                    source_file=file_path.name,
                    page_number=sec_idx,  # Logical page/section number
                    section_title=section_title
                ))
        except Exception as e:
            logger.error(f"Error parsing Markdown {file_path}: {e}")

        return chunks

    def _extract_section_title(self, text: str, fallback: str) -> str:
        """Extracts the first header or section identifier from text."""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for line in lines:
            if line.startswith('## '):
                heading = line[3:].strip()
                match = re.match(r'(?:(?:§|Section)\s*[\d\.]+)?\s*[:\.\-]?\s*(.*)', heading)
                if match and match.group(1).strip():
                    return match.group(1).strip()
                return heading
            elif line.startswith('# '):
                return line[2:].strip()
            elif re.match(r'^(?:§|Section)\s*[\d\.]+', line):
                return line.strip()

        # Check first line if short enough
        if lines and len(lines[0]) < 80 and not lines[0].startswith('-'):
            return lines[0]

        return fallback

    def index_documents(self, force_reload: bool = False):
        """Parses documents and stores them into the ChromaDB collection."""
        if self._collection is None:
            self._load_fallback_chunks()
            return

        if force_reload:
            try:
                self._client.delete_collection(name=self.collection_name)
                self._collection = self._client.create_collection(name=self.collection_name)
            except Exception as e:
                logger.warning(f"Error recreating collection: {e}")

        chunks = self._parse_all_documents()
        self._in_memory_chunks = chunks

        if not chunks:
            logger.warning("No document chunks parsed to index.")
            return

        ids = [c.chunk_id for c in chunks]
        docs = [c.text for c in chunks]
        metadatas = [c.to_metadata() for c in chunks]

        # Chroma upsert in batches
        batch_size = 50
        for i in range(0, len(ids), batch_size):
            b_ids = ids[i:i + batch_size]
            b_docs = docs[i:i + batch_size]
            b_metas = metadatas[i:i + batch_size]
            try:
                self._collection.upsert(
                    ids=b_ids,
                    documents=b_docs,
                    metadatas=b_metas
                )
            except Exception as e:
                logger.error(f"Chroma upsert error at batch {i}: {e}")

        logger.info(f"Successfully indexed {len(chunks)} chunks into ChromaDB.")

    def _chunk_dict_from_memory(self, chunk: DocumentChunk) -> Dict[str, Any]:
        return {
            "text": chunk.text,
            "source_file": chunk.source_file,
            "page_number": chunk.page_number,
            "section_title": chunk.section_title,
            "citation": chunk.citation,
        }

    def _intent_boost(self, query: str, chunk: Dict[str, Any]) -> float:
        """Lightweight domain routing so follow-ups like 'P3' stay on SLA chunks."""
        q = query.lower()
        blob = f"{chunk.get('section_title', '')} {chunk.get('text', '')}".lower()
        boost = 0.0
        if re.search(r'\b(p[1-4]|sla|severity|outage|response time|response window)\b', q):
            if any(t in blob for t in ('sla', 'severity', 'response', 'outage', 'p1', 'p2', 'p3', 'p4')):
                boost += 8.0
            if 'warranty' in blob and 'severity' not in q:
                boost -= 4.0
        if re.search(r'\b(refund|cancel|subscription|billing|annual|monthly)\b', q):
            if any(t in blob for t in ('refund', 'billing', 'subscription', 'cancel', 'proration')):
                boost += 8.0
        if re.search(r'\b(mfa|2fa|multi-factor|password|recovery|admin)\b', q):
            if any(t in blob for t in ('mfa', 'multi-factor', 'password', 'authentication', 'recovery', 'admin')):
                boost += 8.0
        if re.search(r'\b(warranty|drop|liquid|damage|hardware|rma)\b', q):
            if any(t in blob for t in ('warranty', 'drop', 'liquid', 'hardware', 'rma', 'exclusion')):
                boost += 8.0
        if re.search(r'\b(lost in transit|missing package|shipment|delivery)\b', q):
            if any(t in blob for t in ('lost in transit', 'shipment', 'delivery', 'tracking', 'parcel')):
                boost += 8.0
        if re.search(r'\b(professional|enterprise|plan|pricing|tier)\b', q):
            if any(t in blob for t in ('professional', 'enterprise', 'plan', 'pricing', 'tier', 'subscription')):
                boost += 6.0
        boost += self._file_affinity(query, chunk)
        return boost

    def _file_affinity(self, query: str, chunk: Dict[str, Any]) -> float:
        """Route queries to the correct baseline PDF; penalize cross-file keyword collisions."""
        q = query.lower()
        src = (chunk.get("source_file") or "").lower()
        section = (chunk.get("section_title") or "").lower()
        text = (chunk.get("text") or "").lower()
        score = 0.0

        is_sla = bool(re.search(r'\b(p[1-4]|sla|severity|outage|response)\b', q))
        is_billing_pricing = bool(
            re.search(r'\b(pricing|price|\$|/month|per month|tier|invoice|proration)\b', q)
            or re.search(r'\b(professional|enterprise)\s+plan\b', q)
            or ('features' in q and 'plan' in q)
        )
        is_refund = bool(re.search(r'\b(refund|money-back|cancel)\b', q))
        is_security = bool(re.search(r'\b(mfa|2fa|multi-factor|password|recovery|authentication|privacy|gdpr)\b', q))
        is_warranty_ship = bool(
            re.search(r'\b(warranty|drop|liquid|rma|lost in transit|missing package|shipment)\b', q)
        )

        if is_sla and "customer_support" in src:
            score += 22.0
        if is_sla and "subscription_billing" in src:
            score -= 18.0

        if is_billing_pricing and "subscription_billing" in src:
            score += 24.0
        if is_billing_pricing and "customer_support" in src:
            if not any(t in section for t in ("refund", "cancellation", "billing")):
                score -= 22.0

        if is_refund and not is_billing_pricing:
            if "customer_support" in src and "refund" in section:
                score += 18.0
            if "subscription_billing" in src and any(t in text for t in ("refund", "cancel", "money-back")):
                score += 16.0
            if "account_security" in src:
                score -= 12.0

        if is_security and "account_security" in src:
            score += 24.0
        if is_security and "customer_support" in src and "security" not in section:
            score -= 14.0

        if is_warranty_ship and "customer_support" in src:
            score += 20.0
        if is_warranty_ship and "subscription_billing" in src:
            score -= 16.0

        return score

    def _chunk_score(self, query: str, chunk: Dict[str, Any]) -> float:
        return (
            self._score_chunk_lexical(query, chunk)
            + self._intent_boost(query, chunk)
        )

    def _known_source_filenames(self) -> List[str]:
        names: List[str] = []
        target_dir = self.docs_dir if self.docs_dir.exists() else self.fallback_docs_dir
        if target_dir.exists():
            for p in target_dir.glob("*.pdf"):
                names.append(p.name)
            uploads = target_dir / "uploads"
            if uploads.exists():
                for p in uploads.iterdir():
                    if p.is_file():
                        names.append(p.name)
        return names

    def detect_filename_in_query(self, query: str) -> Optional[str]:
        q = query.lower()
        for name in self._known_source_filenames():
            stem = Path(name).stem.lower().replace("_", " ")
            if name.lower() in q or stem in q:
                return name
        return None

    def query_requests_compare(self, query: str) -> bool:
        return bool(re.search(r'\b(compare|versus|vs\.?|difference between|both documents)\b', query.lower()))

    def _resolve_entity_source_file(self, query: str, chunks: List[Dict[str, Any]]) -> Optional[str]:
        """If the user names a person/entity, pick the file whose text mentions it most."""
        tokens = [
            t for t in re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
            if t not in STOP_WORDS and t not in ('know', 'who', 'tell', 'about', 'person')
        ]
        if not tokens:
            return None
        best_src: Optional[str] = None
        best_hits = 0
        by_src: Dict[str, str] = {}
        for chunk in chunks:
            src = chunk.get("source_file") or ""
            by_src[src] = by_src.get(src, "") + " " + (chunk.get("text") or "")
        for src, blob in by_src.items():
            blob_low = blob.lower()
            hits = sum(1 for t in tokens if t in blob_low)
            if hits > best_hits:
                best_hits = hits
                best_src = src
        return best_src if best_hits > 0 else None

    def _focus_to_primary_document(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int,
        source_file_lock: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Keep retrieval within one source file to avoid mixed-document answers."""
        if not chunks or self.query_requests_compare(query):
            return chunks[:top_k]

        explicit = self.detect_filename_in_query(query)
        entity_src = self._resolve_entity_source_file(query, chunks)
        primary_src = explicit or entity_src or source_file_lock

        if not primary_src:
            file_totals: Dict[str, float] = {}
            for chunk in chunks[:12]:
                src = chunk.get("source_file") or ""
                file_totals[src] = file_totals.get(src, 0.0) + self._chunk_score(query, chunk)
            if file_totals:
                primary_src = max(file_totals, key=file_totals.get)

        if not primary_src:
            return chunks[:top_k]

        same_file = [c for c in chunks if c.get("source_file") == primary_src]
        if not same_file:
            return chunks[:top_k]

        same_file.sort(key=lambda c: self._chunk_score(query, c), reverse=True)
        return same_file[:top_k]

    def _rerank_chunks(self, query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        scored = []
        for rank, chunk in enumerate(candidates):
            scored.append((self._chunk_score(query, chunk) - rank * 0.15, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        seen_text = set()
        ordered: List[Dict[str, Any]] = []
        for _, chunk in scored:
            key = chunk.get("text", "")[:80]
            if key in seen_text:
                continue
            seen_text.add(key)
            ordered.append(chunk)
            if len(ordered) >= top_k:
                break
        return ordered

    def _score_chunk_lexical(self, query: str, chunk: Dict[str, Any]) -> float:
        tokens = re.findall(r'[a-zA-Z0-9_\-]+', query.lower())
        q_words = [w for w in tokens if w not in STOP_WORDS and len(w) > 2]
        text_lower = (chunk.get("text") or "").lower()
        title_lower = (chunk.get("section_title") or "").lower()
        score = 0.0
        for w in q_words:
            if re.search(r'\b' + re.escape(w) + r'\b', title_lower):
                score += 12.0
            if re.search(r'\b' + re.escape(w) + r'\b', text_lower):
                score += 4.0
        return score

    def get_relevant_context(
        self,
        query: str,
        top_k: int = 5,
        source_file_lock: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval: vector + lexical merge, intent rerank, single-file focus."""
        clean_query = query.strip()
        if not clean_query:
            return []

        candidate_pool: List[Dict[str, Any]] = []
        pool_ids = set()

        def add_candidate(item: Dict[str, Any]):
            cid = (item.get("source_file"), item.get("page_number"), (item.get("text") or "")[:60])
            if cid in pool_ids:
                return
            pool_ids.add(cid)
            candidate_pool.append(item)

        fetch_n = max(top_k * 4, 12)

        if self._collection and self._collection.count() > 0:
            try:
                chroma_res = self._collection.query(
                    query_texts=[clean_query],
                    n_results=min(fetch_n, self._collection.count()),
                )
                if chroma_res and chroma_res.get('documents') and chroma_res['documents'][0]:
                    for d, m in zip(chroma_res['documents'][0], chroma_res['metadatas'][0]):
                        add_candidate({
                            "text": d,
                            "source_file": m.get("source_file", "Policy.pdf"),
                            "page_number": int(m.get("page_number", 1)),
                            "section_title": m.get("section_title", "General Policy"),
                            "citation": m.get(
                                "citation",
                                f"[Doc: {m.get('source_file')}, Page: {m.get('page_number')}, Section: {m.get('section_title')}]",
                            ),
                        })
            except Exception as e:
                logger.warning(f"ChromaDB retrieval failed: {e}. Falling back to lexical retrieval.")

        for chunk in self._lexical_fallback_search(clean_query, top_k=fetch_n):
            add_candidate(chunk)

        if candidate_pool:
            ranked = self._rerank_chunks(clean_query, candidate_pool, max(top_k * 3, 12))
            return self._focus_to_primary_document(clean_query, ranked, top_k, source_file_lock)

        fallback = self._lexical_fallback_search(clean_query, top_k=max(top_k * 3, 12))
        return self._focus_to_primary_document(clean_query, fallback, top_k, source_file_lock)

    def _lexical_fallback_search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """High-precision keyword matching fallback if vector store is unavailable."""
        if not self._in_memory_chunks:
            self._load_fallback_chunks()

        tokens = re.findall(r'[a-zA-Z0-9_\-]+', query.lower())
        q_words = [w for w in tokens if w not in STOP_WORDS and len(w) > 2]
        if not q_words:
            q_words = [w for w in tokens if len(w) > 2]

        scored: List[tuple] = []
        for chunk in self._in_memory_chunks:
            score = 0
            text_lower = chunk.text.lower()
            title_lower = chunk.section_title.lower()

            for w in q_words:
                if re.search(r'\b' + re.escape(w) + r'\b', title_lower):
                    score += 15
                if re.search(r'\b' + re.escape(w) + r'\b', text_lower):
                    score += 5

            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        chosen = [item[1] for item in scored[:top_k]]

        if not chosen and self._in_memory_chunks:
            chosen = self._in_memory_chunks[:top_k]

        return [
            {
                "text": c.text,
                "source_file": c.source_file,
                "page_number": c.page_number,
                "section_title": c.section_title,
                "citation": c.citation
            }
            for c in chosen
        ]

    def format_context_for_prompt(self, chunks: List[Dict[str, Any]]) -> str:
        """Formats retrieved chunks into a structured context string for Gemini."""
        if not chunks:
            return "No relevant document context found."

        primary_file = chunks[0].get("source_file", "")
        context_blocks = [
            f"PRIMARY DOCUMENT FOR THIS ANSWER: {primary_file}\n"
            "Use only this file's excerpts unless the user explicitly asked to compare documents.\n"
        ]
        for idx, chunk in enumerate(chunks, 1):
            citation = chunk.get("citation", f"[Doc: {chunk.get('source_file')}, Page: {chunk.get('page_number')}, Section: {chunk.get('section_title')}]")
            content = chunk.get("text", "").strip()
            context_blocks.append(
                f"--- EXCERPT {idx} (same file: {chunk.get('source_file')}) ---\n"
                f"Source Citation: {citation}\n"
                f"Content:\n{content}\n"
            )
        return "\n".join(context_blocks)

    def get_uploaded_documents(self) -> List[Dict[str, Any]]:
        """Returns list of custom uploaded documents."""
        uploads_dir = self.docs_dir / 'uploads'
        if not uploads_dir.exists():
            return []
        docs = []
        for p in sorted(uploads_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in ('.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp'):
                ext = p.suffix.lower()
                doc_type = 'PDF' if ext == '.pdf' else ('DOCX' if ext == '.docx' else ('TXT' if ext in ('.txt', '.md') else 'IMG'))
                docs.append({
                    "name": p.name,
                    "ext": ext,
                    "type": doc_type,
                    "is_pdf": ext == '.pdf',
                    "size": p.stat().st_size
                })
        return docs

    def ocr_image(self, img_bytes: bytes) -> str:
        """Extracts text from image bytes using Gemini Vision models with key failover."""
        keys_pool = getattr(settings, 'GEMINI_API_KEYS', [])
        single_key = getattr(settings, 'GEMINI_API_KEY', '')
        if single_key and single_key not in keys_pool:
            keys_pool = [single_key] + keys_pool

        try:
            import google.generativeai as genai
            img = Image.open(io.BytesIO(img_bytes))
            prompt = (
                "You are an expert document OCR engine. Transcribe all text, headings, bullet points, "
                "numbers, and tables from this document image with high fidelity. "
                "Format main headings with markdown (e.g. ## Section Name). "
                "Preserve all specific names, dates, amounts, and figures verbatim."
            )

            models = ['gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-2.0-flash', 'gemini-flash-latest']
            for key in keys_pool:
                if not key:
                    continue
                try:
                    genai.configure(api_key=key)
                    for model_name in models:
                        try:
                            m = genai.GenerativeModel(model_name)
                            res = m.generate_content([prompt, img])
                            if res and res.text and len(res.text.strip()) > 5:
                                return res.text.strip()
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error during OCR image transcription: {e}")

        return ""

    def index_custom_document(self, file_bytes: bytes, filename: str, mime_type: str = '') -> Dict[str, Any]:
        """Scans, parses, chunks, and indexes a user-uploaded PDF, DOCX, TXT, MD, or Image into the knowledge base."""
        ext = Path(filename).suffix.lower()
        if ext not in ('.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg', '.webp'):
            return {
                "success": False,
                "error": f"Unsupported file type '{ext}'. Please upload a PDF, Word (.docx), Text (.txt, .md), or Image (.png, .jpg, .webp)."
            }

        # Save uploaded file to uploads directory
        uploads_dir = self.docs_dir / 'uploads'
        uploads_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[^\w\.\-]', '_', filename)
        save_path = uploads_dir / safe_name
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        chunks: List[DocumentChunk] = []
        file_stem = Path(safe_name).stem.replace('_', ' ')
        pages_count = 1

        if ext == '.pdf' and pymupdf is not None:
            try:
                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
                pages_count = len(doc)
                for page_idx in range(pages_count):
                    page_num = page_idx + 1
                    page = doc[page_idx]
                    raw_text = page.get_text() or ""
                    
                    # If page has virtually no text (e.g. scanned image PDF), OCR the rendered pixmap
                    if len(raw_text.strip()) < 30:
                        try:
                            pix = page.get_pixmap(dpi=150)
                            ocr_text = self.ocr_image(pix.tobytes("png"))
                            if ocr_text:
                                raw_text = ocr_text
                        except Exception as ocr_err:
                            logger.warning(f"OCR failed for PDF page {page_num}: {ocr_err}")

                    if not raw_text.strip():
                        continue

                    section_title = self._extract_section_title(raw_text, fallback=f"{file_stem} - Page {page_num}")
                    paragraphs = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 30]
                    if not paragraphs:
                        paragraphs = [raw_text.strip()]

                    for p_idx, para in enumerate(paragraphs, 1):
                        chunk_id = f"custom_{Path(safe_name).stem}_p{page_num}_c{p_idx}"
                        chunks.append(DocumentChunk(
                            chunk_id=chunk_id,
                            text=para,
                            source_file=safe_name,
                            page_number=page_num,
                            section_title=section_title
                        ))
                doc.close()
            except Exception as pdf_err:
                logger.error(f"Error parsing custom PDF {filename}: {pdf_err}")
                return {"success": False, "error": f"Failed to parse PDF: {pdf_err}"}

        elif ext == '.docx':
            import zipfile
            import xml.etree.ElementTree as ET
            pages_count = 1
            paragraphs = []
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
                    if 'word/document.xml' in z.namelist():
                        xml_content = z.read('word/document.xml')
                        root = ET.fromstring(xml_content)
                        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                        for p in root.findall('.//w:p', ns):
                            texts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                            if texts:
                                p_text = "".join(texts).strip()
                                if len(p_text) > 15:
                                    paragraphs.append(p_text)
            except Exception as docx_err:
                logger.error(f"Error parsing docx {filename}: {docx_err}")
                return {"success": False, "error": f"Failed to parse Word document: {docx_err}"}

            if not paragraphs:
                return {"success": False, "error": "No readable text found in Word document."}

            section_title = self._extract_section_title("\n".join(paragraphs[:3]), fallback=f"{file_stem} Overview")
            for p_idx, para in enumerate(paragraphs, 1):
                chunk_id = f"custom_{Path(safe_name).stem}_p1_c{p_idx}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=para,
                    source_file=safe_name,
                    page_number=1,
                    section_title=section_title
                ))

        elif ext in ('.txt', '.md'):
            pages_count = 1
            try:
                raw_text = file_bytes.decode('utf-8', errors='replace')
            except Exception as text_err:
                return {"success": False, "error": f"Failed to decode text: {text_err}"}

            section_title = self._extract_section_title(raw_text[:500], fallback=f"{file_stem} Document")
            paragraphs = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 20]
            if not paragraphs:
                paragraphs = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 20]

            for p_idx, para in enumerate(paragraphs, 1):
                chunk_id = f"custom_{Path(safe_name).stem}_p1_c{p_idx}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=para,
                    source_file=safe_name,
                    page_number=1,
                    section_title=section_title
                ))

        elif ext in ('.png', '.jpg', '.jpeg', '.webp'):
            pages_count = 1
            raw_text = self.ocr_image(file_bytes)
            if not raw_text.strip():
                raw_text = f"Document: {file_stem}. Scanned image document."

            section_title = self._extract_section_title(raw_text, fallback=f"{file_stem} Overview")
            paragraphs = [p.strip() for p in raw_text.split('\n\n') if len(p.strip()) > 30]
            if not paragraphs:
                paragraphs = [raw_text.strip()]

            for p_idx, para in enumerate(paragraphs, 1):
                chunk_id = f"custom_{Path(safe_name).stem}_p1_c{p_idx}"
                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    text=para,
                    source_file=safe_name,
                    page_number=1,
                    section_title=section_title
                ))

        if not chunks:
            return {
                "success": False,
                "error": "No readable text could be extracted from this document."
            }

        # Index new chunks into ChromaDB
        if self._collection is not None:
            try:
                ids = [c.chunk_id for c in chunks]
                docs = [c.text for c in chunks]
                metadatas = [c.to_metadata() for c in chunks]
                self._collection.upsert(ids=ids, documents=docs, metadatas=metadatas)
            except Exception as chroma_err:
                logger.error(f"Error upserting custom chunks to ChromaDB: {chroma_err}")

        # Also add to in-memory chunks for lexical fallback
        self._in_memory_chunks.extend(chunks)

        total_chunks = (
            self._collection.count()
            if self._collection and self._collection.count() > 0
            else len(self._in_memory_chunks)
        )

        return {
            "success": True,
            "filename": safe_name,
            "is_pdf": (ext == '.pdf'),
            "pages_scanned": pages_count,
            "chunks_added": len(chunks),
            "total_chunks": total_chunks,
            "initial_topic": chunks[0].section_title if chunks else file_stem
        }

    def delete_custom_document(self, filename: str) -> Dict[str, Any]:
        """Safely removes a user-uploaded custom document from disk, in-memory chunks, and ChromaDB."""
        safe_name = os.path.basename(filename).strip()
        safe_name = re.sub(r'[^\w\.\-]', '_', safe_name)

        # Disallow deletion of baseline grounding documents
        base_protected = {
            'Customer_Support_Policy.pdf',
            'Subscription_Billing_Guide.pdf',
            'Account_Security_Privacy.pdf',
            'customer_support_policy.md',
            'subscription_billing_guide.md',
            'account_security_privacy.md'
        }
        if safe_name.lower() in {p.lower() for p in base_protected}:
            return {
                "success": False,
                "error": f"Document '{safe_name}' is a core system policy document and cannot be removed."
            }

        uploads_dir = (self.docs_dir / 'uploads').resolve()
        target_file = (uploads_dir / safe_name).resolve()

        # Security check: must reside inside uploads_dir
        if not str(target_file).startswith(str(uploads_dir)):
            return {
                "success": False,
                "error": "Invalid file path target."
            }

        # 1. Remove physical file if present
        if target_file.exists() and target_file.is_file():
            try:
                target_file.unlink()
            except Exception as e:
                logger.warning(f"Could not unlink file {target_file}: {e}")

        # 2. Remove from in-memory chunks
        stem_prefix = f"custom_{Path(safe_name).stem}_"
        self._in_memory_chunks = [
            c for c in self._in_memory_chunks
            if c.source_file != safe_name and not c.chunk_id.startswith(stem_prefix)
        ]

        # 3. Remove from ChromaDB collection
        if self._collection is not None:
            try:
                # Find IDs by source_file metadata or ID prefix
                res = self._collection.get()
                matching_ids = []
                for item_id, meta in zip(res.get('ids', []), res.get('metadatas', [])):
                    if meta and meta.get('source_file') == safe_name:
                        matching_ids.append(item_id)
                    elif item_id.startswith(stem_prefix):
                        matching_ids.append(item_id)
                if matching_ids:
                    self._collection.delete(ids=matching_ids)
                    logger.info(f"Deleted {len(matching_ids)} chunks from ChromaDB for {safe_name}")
            except Exception as chroma_err:
                logger.error(f"Error deleting chunks from ChromaDB for {safe_name}: {chroma_err}")

        total_chunks = (
            self._collection.count()
            if self._collection and self._collection.count() > 0
            else len(self._in_memory_chunks)
        )

        return {
            "success": True,
            "filename": safe_name,
            "total_chunks": total_chunks,
            "message": f"Document '{safe_name}' has been removed successfully."
        }


# Singleton engine instance
RAG_ENGINE = SupportRAGEngine()
RAGEngine = SupportRAGEngine


def get_relevant_context(
    query: str,
    top_k: int = 5,
    source_file_lock: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Global utility accessor for retrieval."""
    return RAG_ENGINE.get_relevant_context(query, top_k=top_k, source_file_lock=source_file_lock)


def format_context(chunks: List[Dict[str, Any]]) -> str:
    """Global utility accessor for prompt context formatting."""
    return RAG_ENGINE.format_context_for_prompt(chunks)


def index_custom_document(file_bytes: bytes, filename: str, mime_type: str = '') -> Dict[str, Any]:
    """Global utility accessor to index custom documents."""
    return RAG_ENGINE.index_custom_document(file_bytes, filename, mime_type)


def delete_custom_document(filename: str) -> Dict[str, Any]:
    """Global utility accessor to delete custom documents."""
    return RAG_ENGINE.delete_custom_document(filename)


def get_uploaded_documents() -> List[Dict[str, Any]]:
    """Global utility accessor for uploaded documents list."""
    return RAG_ENGINE.get_uploaded_documents()


