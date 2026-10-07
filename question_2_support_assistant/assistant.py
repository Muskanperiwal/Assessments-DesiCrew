import os
import re
from knowledge_indexer import KnowledgeIndexer
from session_memory import SessionMemory

class DocumentAwareAssistant:
    """
    Document-Aware Multi-Turn Support Assistant:
    1. Remembers prior user queries within the active session.
    2. Avoids repeating information it has already provided.
    3. Gracefully handles topic transitions and context switches.
    4. Explicitly cites the specific document section for every answer.
    """
    def __init__(self, docs_dir: str):
        self.indexer = KnowledgeIndexer(docs_dir)
        self.memory = SessionMemory()

    def process_turn(self, user_query: str) -> dict:
        turn_num = len(self.memory.turns) + 1
        q_lower = user_query.strip().lower()

        # Step 1: Document Section Retrieval
        matched_sections = self.indexer.search(user_query, top_k=2)
        if not matched_sections:
            # Fallback to active topic or default section
            matched_section = self.indexer.sections[0] if self.indexer.sections else None
        else:
            matched_section = matched_sections[0]

        doc_name = matched_section["doc_name"] if matched_section else "General Policy"
        sec_num = matched_section["section_num"] if matched_section else "§ 1"
        sec_title = matched_section["section_title"] if matched_section else "Support Policy"
        citation = f"{doc_name} {sec_num} - {sec_title}"
        topic = f"{doc_name.replace('.md', '')} ({sec_title})"

        # Step 2: Analyze Session Memory for Topic Switch
        prev_topic = self.memory.active_topic
        is_topic_switch = bool(prev_topic and prev_topic != topic)
        returning_to_previous_topic = False
        prior_turns_for_topic = []

        if is_topic_switch:
            prior_turns_for_topic = self.memory.get_turns_discussing(topic)
            if prior_turns_for_topic:
                returning_to_previous_topic = True

        # Step 3: Extract Section Key Facts & Detect Already Delivered Information
        section_content = matched_section["content"] if matched_section else ""
        extracted_facts = self._extract_facts(section_content)
        
        already_delivered = []
        new_facts_to_deliver = []

        for fact in extracted_facts:
            fact_key = self._normalize_fact(fact)
            if self.memory.has_fact_been_delivered(fact_key):
                already_delivered.append(fact)
            else:
                new_facts_to_deliver.append(fact)

        # Step 4: Synthesize Response with Context, Anti-Repetition & Explicit Citation
        reply_parts = []

        # 4a. Topic Switch / Continuity Bridge
        if is_topic_switch:
            if returning_to_previous_topic:
                reply_parts.append(f"*Returning to our earlier discussion on **{sec_title}** (previously explored in Turn {prior_turns_for_topic[0]}):*\n")
            else:
                reply_parts.append(f"*Acknowledging the topic switch from **{self._clean_topic_name(prev_topic)}** to **{sec_title}**:*\n")
        elif len(self.memory.turns) > 0 and not is_topic_switch:
            reply_parts.append(f"*Continuing within the context of **{sec_title}**:*\n")

        # 4b. Anti-Repetition Acknowledgment
        if already_delivered and prior_turns_for_topic:
            summary_ref = f"As noted earlier in Turn {prior_turns_for_topic[0]}, you already have the core baseline for this policy."
            reply_parts.append(f"> ℹ️ *{summary_ref} (Avoiding repeating already shared terms).* Here are the specific additional details for your question:\n")
        elif already_delivered and not prior_turns_for_topic:
            reply_parts.append("> ℹ️ *(Referencing previously established policy guidelines).* Specific points below:\n")

        # 4c. Direct Answer & Relevant Section Synthesis
        answer_body = self._synthesize_answer(user_query, matched_section, already_delivered, new_facts_to_deliver)
        reply_parts.append(answer_body)

        # 4d. Mandatory Explicit Section Citation
        citation_block = f"\n\n**📖 Source Citation:** `[{citation}]`"
        reply_parts.append(citation_block)

        final_reply = "".join(reply_parts)

        # Record in Session Memory
        facts_to_record = [self._normalize_fact(f) for f in extracted_facts]
        turn_data = self.memory.record_turn(
            turn_num=turn_num,
            user_query=user_query,
            topic=topic,
            delivered_facts=facts_to_record,
            citation=citation,
            assistant_reply=final_reply
        )

        return {
            "turn_number": turn_num,
            "user_query": user_query,
            "topic": topic,
            "is_topic_switch": is_topic_switch,
            "returning_to_previous_topic": returning_to_previous_topic,
            "already_delivered_facts": already_delivered,
            "new_facts_delivered": new_facts_to_deliver,
            "citation": citation,
            "reply": final_reply,
            "session_state": self.memory.get_summary_state()
        }

    def _clean_topic_name(self, full_topic: str) -> str:
        if not full_topic:
            return ""
        match = re.search(r'\((.*?)\)', full_topic)
        return match.group(1) if match else full_topic

    def _normalize_fact(self, fact_str: str) -> str:
        return re.sub(r'[^a-zA-Z0-9]', '', fact_str.lower()[:40])

    def _extract_facts(self, content: str) -> list:
        """Splits section bullet points or sentences into identifiable fact nuggets."""
        facts = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('- ') or line.startswith('* '):
                facts.append(line[2:].strip())
            elif line and not line.startswith('#'):
                # Split sentences
                sentences = re.split(r'\.\s+', line)
                for s in sentences:
                    if len(s.strip()) > 15:
                        facts.append(s.strip())
        return facts[:5]

    def _synthesize_answer(self, query: str, section: dict, already_delivered: list, new_facts: list) -> str:
        """Builds a targeted, direct answer while respecting anti-repetition constraints."""
        q_lower = query.lower()
        content = section["content"]

        # Find lines most directly answering the question
        matching_lines = []
        q_words = [w for w in re.findall(r'\b\w+\b', q_lower) if len(w) > 3]

        for line in content.split('\n'):
            line_str = line.strip()
            if not line_str or line_str.startswith('#'):
                continue
            # If line contains facts already delivered, skip or compress if we have new facts
            if any(self._normalize_fact(line_str) == self._normalize_fact(f) for f in already_delivered) and new_facts:
                continue

            score = sum(1 for w in q_words if w in line_str.lower())
            if score > 0:
                matching_lines.append((score, line_str))

        if matching_lines:
            matching_lines.sort(key=lambda x: x[0], reverse=True)
            chosen_lines = [item[1] for item in matching_lines[:3]]
            return "\n\n".join(chosen_lines)
        else:
            # Fallback to key facts in the section
            sample_facts = new_facts if new_facts else already_delivered
            if sample_facts:
                return "\n\n".join([f"- {f}" for f in sample_facts[:3]])
            return content[:300] + "..."
