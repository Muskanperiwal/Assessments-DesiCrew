import os
import re

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

class KnowledgeIndexer:
    """
    Parses and indexes knowledge base documents at the specific section level,
    enabling accurate retrieval and citation without stop-word skew.
    """
    def __init__(self, docs_dir: str):
        self.docs_dir = docs_dir
        self.sections = []
        self.build_index()

    def build_index(self):
        self.sections = []
        if not os.path.exists(self.docs_dir):
            return

        for filename in sorted(os.listdir(self.docs_dir)):
            if filename.endswith(('.md', '.txt')):
                filepath = os.path.join(self.docs_dir, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                parsed = self._parse_document(filename, text)
                self.sections.extend(parsed)

    def _parse_document(self, filename: str, content: str):
        lines = content.split('\n')
        doc_title = filename
        sections = []
        current_section = None
        current_lines = []

        for line in lines:
            line_str = line.strip()
            # Top level doc header
            if line_str.startswith('# ') and not current_section:
                doc_title = line_str[2:].strip()
                continue

            # Section header: ## § X. Title
            if line_str.startswith('## '):
                if current_section and current_lines:
                    current_section['content'] = '\n'.join(current_lines).strip()
                    sections.append(current_section)
                    current_lines = []

                header_text = line_str[3:].strip()
                match_sec = re.match(r'(§\s*\d+[\.\d]*)\s*[:\.\-]?\s*(.*)', header_text)
                if match_sec:
                    sec_num = match_sec.group(1)
                    sec_title = match_sec.group(2).strip()
                else:
                    sec_num = f"§ {len(sections) + 1}"
                    sec_title = header_text

                citation = f"{filename} {sec_num} - {sec_title}"
                current_section = {
                    "doc_name": filename,
                    "doc_title": doc_title,
                    "section_num": sec_num,
                    "section_title": sec_title,
                    "citation": citation,
                    "content": ""
                }
            elif current_section:
                current_lines.append(line)

        if current_section and current_lines:
            current_section['content'] = '\n'.join(current_lines).strip()
            sections.append(current_section)

        return sections

    def search(self, query: str, top_k: int = 2) -> list:
        if not self.sections:
            return []

        # Extract meaningful terms excluding stop words
        all_tokens = [w.lower() for w in re.findall(r'\b\w+\b', query)]
        q_terms = [w for w in all_tokens if len(w) > 2 and w not in STOP_WORDS]
        if not q_terms:
            q_terms = [w for w in all_tokens if len(w) > 2]

        scored_sections = []

        for sec in self.sections:
            score = 0
            title_lower = sec['section_title'].lower()
            content_lower = sec['content'].lower()
            doc_lower = sec['doc_name'].lower()
            full_text = f"{title_lower} {content_lower} {doc_lower}"

            # Term frequency & section prominence
            for term in q_terms:
                # Word boundary match in title: highest weight
                if re.search(r'\b' + re.escape(term) + r'\b', title_lower):
                    score += 20
                elif term in title_lower:
                    score += 10

                # Match in document filename
                if term in doc_lower:
                    score += 8

                # Match in content
                content_matches = len(re.findall(r'\b' + re.escape(term) + r'\b', content_lower))
                score += content_matches * 3

            # Exact phrase match in content or title
            clean_query = query.strip('?.,! ').lower()
            if len(clean_query) > 5 and clean_query in full_text:
                score += 30

            if score > 0:
                scored_sections.append((score, sec))

        scored_sections.sort(key=lambda x: x[0], reverse=True)
        return [sec for score, sec in scored_sections[:top_k]]
