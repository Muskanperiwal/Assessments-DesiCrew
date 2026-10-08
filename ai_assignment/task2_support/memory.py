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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turns": self.turns,
            "delivered_facts": list(self.delivered_facts),
            "topic_history": self.topic_history,
            "active_topic": self.active_topic,
            "topic_switches": self.topic_switches,
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

    def record_turn(
        self,
        user_query: str,
        topic: str,
        delivered_facts: List[str],
        citation: str,
        assistant_reply: str,
        citations: Optional[List[str]] = None
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

        turn_record = {
            "turn_number": turn_num,
            "user_query": user_query,
            "topic": topic,
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


def get_session_memory(request) -> SessionMemory:
    """Retrieves or initializes SessionMemory stored in Django session."""
    session_data = request.session.get("support_memory", None)
    if session_data:
        return SessionMemory(session_data)
    
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


def save_session_memory(request, memory: SessionMemory):
    """Persists SessionMemory in Django session and updates legacy keys."""
    request.session["support_memory"] = memory.to_dict()
    request.session["support_chat_history"] = memory.get_chat_history()
    request.session["support_topics"] = memory.topic_history
    request.session["support_active_topic"] = memory.active_topic
    request.session["support_delivered_facts"] = list(memory.delivered_facts)
    request.session.modified = True
