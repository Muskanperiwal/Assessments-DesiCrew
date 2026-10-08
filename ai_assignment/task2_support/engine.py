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
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

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
        base_dir = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)
        self.docs_dir = docs_dir or getattr(settings, 'DATA_DIR', base_dir / 'data') / 'support_documents'
        self.fallback_docs_dir = getattr(settings, 'DATA_DIR', base_dir / 'data') / 'support_documents'
        self.chroma_dir = chroma_dir or getattr(settings, 'DATA_DIR', base_dir / 'data') / 'chroma_db'
        
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


# Singleton engine instance
RAG_ENGINE = SupportRAGEngine()
RAGEngine = SupportRAGEngine


def get_relevant_context(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Global utility accessor for retrieval."""
    return RAG_ENGINE.get_relevant_context(query, top_k=top_k)


def format_context(chunks: List[Dict[str, Any]]) -> str:
    """Global utility accessor for prompt context formatting."""
    return RAG_ENGINE.format_context_for_prompt(chunks)


class RAGEngine:
    """Combines Markdown section indexing and PyMuPDF chunking for support documents."""
    def __init__(self, doc_paths: Optional[List[Any]] = None):
        base_dir = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)
        if doc_paths is None:
            self.doc_paths = [getattr(settings, 'DATA_DIR', base_dir / 'data') / 'support_documents']
        elif isinstance(doc_paths, (str, Path)):
            self.doc_paths = [Path(doc_paths)]
        else:
            self.doc_paths = [Path(p) for p in doc_paths]

        self.sections: List[Dict[str, Any]] = []
        self.build_index()

    def build_index(self):
        self.sections = []
        for path in self.doc_paths:
            if not path.exists():
                continue
            if path.is_dir():
                for file_p in sorted(path.glob("*")):
                    if file_p.suffix.lower() in [".md", ".txt", ".pdf"]:
                        self._index_file(file_p)
            elif path.is_file():
                self._index_file(path)

    def _index_file(self, file_path: Path):
        try:
            if file_path.suffix.lower() == '.pdf' and pymupdf is not None:
                doc = pymupdf.open(str(file_path))
                for page_idx, page in enumerate(doc):
                    text = page.get_text()
                    if text.strip():
                        self.sections.append({
                            "doc_name": file_path.name,
                            "doc_title": file_path.stem.replace('_', ' '),
                            "section_id": f"P{page_idx+1}",
                            "section_title": f"Page {page_idx+1}",
                            "citation": f"{file_path.name} Page {page_idx+1}",
                            "content": text.strip(),
                            "key_facts": [line.strip('- *') for line in text.split('\n') if len(line.strip()) > 20][:3]
                        })
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                self._parse_markdown(file_path.name, content)
        except Exception as e:
            logger.error(f"Error indexing {file_path}: {e}")

    def _parse_markdown(self, filename: str, content: str):
        lines = content.split('\n')
        doc_title = filename.replace('.md', '').replace('_', ' ')
        current_section = None
        current_lines = []

        for line in lines:
            line_str = line.strip()
            if line_str.startswith('# ') and not current_section:
                doc_title = line_str[2:].strip()
                continue

            if line_str.startswith('## '):
                if current_section and current_lines:
                    current_section['content'] = '\n'.join(current_lines).strip()
                    current_section['key_facts'] = [l.strip('- *') for l in current_lines if l.strip().startswith(('-', '*')) and len(l.strip()) > 10][:4]
                    self.sections.append(current_section)
                    current_lines = []

                header_text = line_str[3:].strip()
                match_sec = re.match(r'(§\s*\d+[\.\d]*)\s*[:\.\-]?\s*(.*)', header_text)
                if match_sec:
                    sec_id = match_sec.group(1).replace('§', '').strip()
                    sec_title = match_sec.group(2).strip()
                else:
                    sec_id = f"{len(self.sections) + 1}.0"
                    sec_title = header_text

                current_section = {
                    "doc_name": filename,
                    "doc_title": doc_title,
                    "section_id": sec_id,
                    "section_title": sec_title,
                    "citation": f"{doc_title} § {sec_id} - {sec_title}",
                    "content": "",
                    "key_facts": []
                }
            elif current_section:
                current_lines.append(line)

        if current_section and current_lines:
            current_section['content'] = '\n'.join(current_lines).strip()
            current_section['key_facts'] = [l.strip('- *') for l in current_lines if l.strip().startswith(('-', '*')) and len(l.strip()) > 10][:4]
            self.sections.append(current_section)

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        if not self.sections:
            return []

        all_tokens = [w.lower() for w in re.findall(r'\b\w+\b', query)]
        q_terms = [w for w in all_tokens if len(w) > 2 and w not in STOP_WORDS]
        if not q_terms:
            q_terms = [w for w in all_tokens if len(w) > 2]

        scored = []
        for sec in self.sections:
            score = 0
            t_low = sec['section_title'].lower()
            c_low = sec['content'].lower()
            d_low = sec['doc_title'].lower()

            for term in q_terms:
                if re.search(r'\b' + re.escape(term) + r'\b', t_low):
                    score += 20
                elif term in t_low:
                    score += 10
                if term in d_low:
                    score += 8
                matches = len(re.findall(r'\b' + re.escape(term) + r'\b', c_low))
                score += min(matches * 2, 12)

            if score > 0:
                scored.append((score, sec))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return [s[1] for s in scored[:top_k]]
        return self.sections[:top_k]
