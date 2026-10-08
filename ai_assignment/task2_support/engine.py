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
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}. Relying on in-memory parsed index.", exc_info=True)
            self._load_fallback_chunks()

    def _load_fallback_chunks(self):
        """Loads and parses documents into in-memory list for fallback search."""
        self._in_memory_chunks = self._parse_all_documents()

    def _parse_all_documents(self) -> List[DocumentChunk]:
        """Parses documents from support_documents directory prioritizing PDF versions."""
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
                suffix = file_path.suffix.lower()
                if suffix in ('.md', '.txt'):
                    chunks.extend(self._parse_markdown(file_path))

        return chunks

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

    def get_relevant_context(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieves top-K relevant chunks with exact metadata and citations.

        Returns:
            List of dicts: [
                {
                    "text": str,
                    "source_file": str,
                    "page_number": int,
                    "section_title": str,
                    "citation": str
                }, ...
            ]
        """
        results = []
        clean_query = query.strip()
        if not clean_query:
            return results

        # 1. Query ChromaDB Vector Store
        if self._collection and self._collection.count() > 0:
            try:
                chroma_res = self._collection.query(
                    query_texts=[clean_query],
                    n_results=min(top_k, self._collection.count())
                )
                if chroma_res and chroma_res.get('documents') and chroma_res['documents'][0]:
                    docs = chroma_res['documents'][0]
                    metas = chroma_res['metadatas'][0]
                    for d, m in zip(docs, metas):
                        results.append({
                            "text": d,
                            "source_file": m.get("source_file", "Policy.pdf"),
                            "page_number": int(m.get("page_number", 1)),
                            "section_title": m.get("section_title", "General Policy"),
                            "citation": m.get("citation", f"[Doc: {m.get('source_file')}, Page: {m.get('page_number')}, Section: {m.get('section_title')}]")
                        })
                    return results
            except Exception as e:
                logger.warning(f"ChromaDB retrieval failed: {e}. Falling back to lexical retrieval.")

        # 2. Lexical Keyword Overlap Fallback
        return self._lexical_fallback_search(clean_query, top_k=top_k)

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

        context_blocks = []
        for idx, chunk in enumerate(chunks, 1):
            citation = chunk.get("citation", f"[Doc: {chunk.get('source_file')}, Page: {chunk.get('page_number')}, Section: {chunk.get('section_title')}]")
            content = chunk.get("text", "").strip()
            context_blocks.append(
                f"--- DOCUMENT EXCERPT {idx} ---\n"
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
            if p.is_file() and p.suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.webp'):
                docs.append({
                    "name": p.name,
                    "is_pdf": p.suffix.lower() == '.pdf',
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
        """Scans, parses, chunks, and indexes a user-uploaded PDF or Image into the knowledge base."""
        ext = Path(filename).suffix.lower()
        if ext not in ('.pdf', '.png', '.jpg', '.jpeg', '.webp'):
            return {
                "success": False,
                "error": f"Unsupported file type '{ext}'. Please upload a PDF or image (.png, .jpg, .webp)."
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


def get_relevant_context(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Global utility accessor for retrieval."""
    return RAG_ENGINE.get_relevant_context(query, top_k=top_k)


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


