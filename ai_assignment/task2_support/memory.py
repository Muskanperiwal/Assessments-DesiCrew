"""Session memory tracking for Task 2 Smart Support Assistant.
Maintains multi-turn context (10+ turns), tracks delivered facts and semantic embeddings
to prevent repetition, and logs topic switches via Django's session framework.
"""
import re
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

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


def compute_cosine_similarity(text1: str, text2: str) -> float:
    """Computes normalized term-frequency cosine similarity between two texts."""
    words1 = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', text1) if len(w) > 2 and w.lower() not in STOP_WORDS]
    words2 = [w.lower() for w in re.findall(r'\b[a-zA-Z0-9]+\b', text2) if len(w) > 2 and w.lower() not in STOP_WORDS]
    if not words1 or not words2:
        return 0.0
    vocab = list(set(words1 + words2))
    v1 = np.array([words1.count(w) for w in vocab], dtype=float)
    v2 = np.array([words2.count(w) for w in vocab], dtype=float)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


class SessionMemory:
    """
    Manages session state across multi-turn conversations:
    1. Tracks user queries and turn numbers (maintains 10+ turns).
    2. Maintains a log of delivered facts and computes semantic cosine similarity
       to prevent boilerplate duplication.
    3. Detects and tracks topic switches and conversation history.
    """
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        data = data or {}
        self.turns: List[Dict[str, Any]] = data.get("turns", [])
        self.delivered_facts: set = set(data.get("delivered_facts", []))
        self.topic_history: List[str] = data.get("topic_history", [])
        self.active_topic: Optional[str] = data.get("active_topic", None)
        self.topic_switches: List[Dict[str, Any]] = data.get("topic_switches", [])
        self.active_document: Optional[str] = data.get("active_document", None)
        self.covered_documents: List[str] = data.get("covered_documents", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turns": self.turns,
            "delivered_facts": list(self.delivered_facts),
            "topic_history": self.topic_history,
            "active_topic": self.active_topic,
            "topic_switches": self.topic_switches,
            "active_document": self.active_document,
            "covered_documents": self.covered_documents,
        }

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def compute_max_cosine_similarity(self, candidate_text: str) -> float:
        """Measures semantic cosine similarity against previously issued assistant replies."""
        if not self.turns or not candidate_text.strip():
            return 0.0
        max_sim = 0.0
        for turn in self.turns:
            reply = turn.get("assistant_reply", "")
            if reply:
                sim = compute_cosine_similarity(candidate_text, reply)
                if sim > max_sim:
                    max_sim = sim
        return max_sim

    def is_anti_repetition_triggered(
        self,
        candidate_text: str,
        candidate_fact_keys: List[str],
        cosine_threshold: float = 0.85
    ) -> Tuple[bool, float, int]:
        """
        Determines whether anti-repetition should be triggered:
        1. Semantic cosine similarity exceeding threshold (default 0.85).
        2. Exact overlap with previously logged facts.
        """
        max_cosine = self.compute_max_cosine_similarity(candidate_text)
        already_delivered_count = sum(1 for k in candidate_fact_keys if self.has_fact_been_delivered(k))
        triggered = (max_cosine >= cosine_threshold) or (already_delivered_count > 0)
        return triggered, max_cosine, already_delivered_count

    @staticmethod
    def parse_source_file(citation: str) -> str:
        if not citation:
            return ""
        match = re.search(r'\[Doc:\s*([^,\]]+)', citation)
        return match.group(1).strip() if match else ""

    def get_document_lock(self, user_message: str) -> Optional[str]:
        """On follow-ups, stay on the same source file unless the user changes subject."""
        low = user_message.lower()
        if re.search(r'\b(compare|versus|vs\.?|difference between|both documents)\b', low):
            return None
        if re.search(
            r'\b(billing|subscription|refund|security|mfa|password|warranty|shipment|sla|p[1-4])\b',
            low,
        ) and not self.is_likely_follow_up(user_message):
            return None
        if self.is_likely_follow_up(user_message) and self.turns:
            last = self.turns[-1]
            src = last.get("source_file") or self.parse_source_file(last.get("citation", ""))
            return src or None
        return None

    def record_turn(
        self,
        user_query: str,
        topic: str,
        delivered_facts: List[str],
        citation: str,
        assistant_reply: str,
        citations: Optional[List[str]] = None,
        source_file: str = "",
    ) -> Dict[str, Any]:
        """Records a completed dialogue turn into persistent session memory."""
        turn_num = len(self.turns) + 1
        is_topic_switch = False
        previous_topic = self.active_topic

        if previous_topic and topic and previous_topic != topic:
            is_topic_switch = True
            self.topic_switches.append({
                "turn": turn_num,
                "from_topic": previous_topic,
                "to_topic": topic
            })

        self.active_topic = topic
        if topic and topic not in self.topic_history:
            self.topic_history.append(topic)

        # Record new facts to prevent repetition
        new_facts = []
        for fact in delivered_facts:
            fact_key = fact.strip().lower()
            if fact_key and fact_key not in self.delivered_facts:
                self.delivered_facts.add(fact_key)
                new_facts.append(fact)

        resolved_source = source_file or self.parse_source_file(citation)
        if resolved_source:
            self.active_document = resolved_source
            if resolved_source not in self.covered_documents:
                self.covered_documents.append(resolved_source)

        turn_record = {
            "turn_number": turn_num,
            "user_query": user_query,
            "topic": topic,
            "source_file": resolved_source,
            "is_topic_switch": is_topic_switch,
            "previous_topic": previous_topic,
            "new_facts": new_facts,
            "citation": citation,
            "citations": citations or ([citation] if citation else []),
            "assistant_reply": assistant_reply
        }
        self.turns.append(turn_record)
        # Keep up to 20 turns in history
        if len(self.turns) > 20:
            self.turns = self.turns[-20:]
        return turn_record

    def has_fact_been_delivered(self, fact_key: str) -> bool:
        return fact_key.strip().lower() in self.delivered_facts

    def has_topic_been_visited(self, topic: str) -> bool:
        return topic in self.topic_history

    def get_chat_history(self, max_turns: int = 10) -> List[Dict[str, str]]:
        """Returns standard role/content messages list for LLM context injection."""
        messages = []
        for turn in self.turns[-max_turns:]:
            messages.append({"role": "user", "content": turn.get("user_query", "")})
            messages.append({"role": "model", "content": turn.get("assistant_reply", "")})
        return messages

    def get_last_user_query(self) -> str:
        if not self.turns:
            return ""
        return (self.turns[-1].get("user_query") or "").strip()

    def get_recent_topics(self, n: int = 3) -> List[str]:
        seen: List[str] = []
        for turn in reversed(self.turns):
            topic = (turn.get("topic") or "").strip()
            if topic and topic not in seen:
                seen.append(topic)
            if len(seen) >= n:
                break
        return seen

    def is_likely_follow_up(self, user_message: str) -> bool:
        """Heuristic: only truly underspecified anaphoric queries depend on prior turns for retrieval."""
        msg = user_message.strip()
        if not msg:
            return False
        low = msg.lower()

        # If query contains explicit domain nouns, it is a standalone query that retrieves on its own
        standalone_indicators = (
            'sla', 'outage', 'severity', 'p1', 'p2', 'p3', 'p4',
            'refund', 'cancel', 'subscription', 'billing', 'invoice', 'plan', 'pricing', 'tier',
            'mfa', '2fa', 'multi-factor', 'password', 'recovery', 'security', 'privacy',
            'warranty', 'damage', 'liquid', 'drop', 'shipment', 'transit', 'package',
            'pan', 'card', 'income tax', 'birth', 'holder', 'father', 'degree', 'resume'
        )
        if any(w in low for w in standalone_indicators):
            if low.startswith(('what about', 'how about', 'and what about', 'and for')):
                return True
            return False

        # Short anaphoric phrases lacking self-contained context
        if len(msg.split()) <= 6:
            if re.search(r'\b(it|that|those|they|them|same|also|previous|earlier|remind|again)\b', low):
                return True
            if low.startswith(('what about', 'how about', 'and ', 'also ', 'tell me more', 'how long', 'why', 'what else')):
                return True
        return False

    def build_retrieval_query(self, user_message: str) -> str:
        """Expand underspecified follow-ups cleanly without corrupting the search text."""
        parts = [user_message.strip()]
        if self.is_likely_follow_up(user_message) and self.turns:
            if len(user_message.strip().split()) <= 4 and self.active_topic:
                parts.append(self.active_topic)
            last_q = self.get_last_user_query()
            if last_q and len(user_message.strip().split()) <= 4 and last_q.lower() != user_message.strip().lower():
                parts.append(last_q)
        return " ".join(parts)

    def get_session_brief(self, max_turns: int = 6) -> str:
        """Compact narrative of recent dialogue for the LLM (topics + facts already covered)."""
        if not self.turns:
            return "No prior turns in this session."
        lines = []
        if self.active_topic:
            lines.append(f"Active topic: {self.active_topic}")
        if self.topic_history:
            lines.append(f"Topics visited: {', '.join(self.topic_history[-6:])}")
        for turn in self.turns[-max_turns:]:
            lines.append(
                f"Turn {turn.get('turn_number')}: User asked about '{turn.get('topic', 'General')}' — "
                f"\"{(turn.get('user_query') or '')[:120]}\""
            )
        if self.delivered_facts:
            lines.append(
                f"Facts already stated in session: {min(len(self.delivered_facts), 12)} tracked "
                "(do not repeat verbatim; add new detail or confirm briefly)."
            )
        return "\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_turns": len(self.turns),
            "topics_discussed": self.topic_history,
            "active_topic": self.active_topic,
            "switches_count": len(self.topic_switches),
            "facts_logged_count": len(self.delivered_facts)
        }

    def clear(self):
        """Clears all session memory."""
        self.turns = []
        self.delivered_facts = set()
        self.topic_history = []
        self.active_topic = None
        self.topic_switches = []
        self.active_document = None
        self.covered_documents = []


def get_session_memory(request, chat_id: Optional[str] = None) -> SessionMemory:
    """Retrieves or initializes SessionMemory stored in Django session."""
    session_key = f"support_memory_{chat_id}" if chat_id else "support_memory"
    session_data = request.session.get(session_key, None)
    if session_data:
        return SessionMemory(session_data)
    
    if not chat_id:
        # Backwards compatibility migration from legacy session keys
        legacy_history = request.session.get("support_chat_history", [])
        legacy_topics = request.session.get("support_topics", [])
        legacy_active = request.session.get("support_active_topic", None)
        legacy_facts = request.session.get("support_delivered_facts", [])

        if legacy_history:
            turns = []
            for i in range(0, len(legacy_history) - 1, 2):
                turn_idx = (i // 2) + 1
                turns.append({
                    "turn_number": turn_idx,
                    "user_query": legacy_history[i].get("content", ""),
                    "assistant_reply": legacy_history[i+1].get("content", ""),
                    "topic": legacy_active or "General Support",
                    "is_topic_switch": False,
                    "previous_topic": None,
                    "new_facts": [],
                    "citation": "",
                    "citations": []
                })
            migrated = SessionMemory({
                "turns": turns,
                "delivered_facts": legacy_facts,
                "topic_history": legacy_topics,
                "active_topic": legacy_active,
                "topic_switches": []
            })
            return migrated

    return SessionMemory()


def save_session_memory(request, memory: SessionMemory, chat_id: Optional[str] = None):
    """Persists SessionMemory in Django session and updates legacy keys."""
    session_key = f"support_memory_{chat_id}" if chat_id else "support_memory"
    request.session[session_key] = memory.to_dict()
    if not chat_id:
        request.session["support_chat_history"] = memory.get_chat_history()
        request.session["support_topics"] = memory.topic_history
        request.session["support_active_topic"] = memory.active_topic
        request.session["support_delivered_facts"] = list(memory.delivered_facts)
    request.session.modified = True


def clear_session_memory(request, chat_id: Optional[str] = None):
    """Clears memory for a specific chat or all support memory."""
    if chat_id:
        session_key = f"support_memory_{chat_id}"
        if session_key in request.session:
            del request.session[session_key]
    else:
        for k in list(request.session.keys()):
            if k.startswith("support_memory"):
                del request.session[k]
        for key in ['support_chat_history', 'support_topics', 'support_active_topic', 'support_delivered_facts']:
            if key in request.session:
                del request.session[key]
    request.session.modified = True

