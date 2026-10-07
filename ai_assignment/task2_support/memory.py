"""Session memory tracking for Task 2 Smart Support Assistant.
Maintains multi-turn context (10+ turns), tracks delivered facts to prevent repetition,
and logs topic switches via Django's session framework.
"""

class SessionMemory:
    """
    Manages session state across multi-turn conversations:
    1. Tracks user queries and turn numbers (up to 10+ turns).
    2. Maintains a log of provided information and facts to prevent repetition.
    3. Detects and tracks topic switches and conversation history.
    """
    def __init__(self, data: dict = None):
        data = data or {}
        self.turns = data.get("turns", [])
        self.delivered_facts = set(data.get("delivered_facts", []))
        self.topic_history = data.get("topic_history", [])
        self.active_topic = data.get("active_topic", None)
        self.topic_switches = data.get("topic_switches", [])

    def to_dict(self) -> dict:
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

    def record_turn(self, user_query: str, topic: str, delivered_facts: list, citation: str, assistant_reply: str):
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
            if fact_key not in self.delivered_facts:
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
            "assistant_reply": assistant_reply
        }
        self.turns.append(turn_record)
        return turn_record

    def has_fact_been_delivered(self, fact_key: str) -> bool:
        return fact_key.strip().lower() in self.delivered_facts

    def has_topic_been_visited(self, topic: str) -> bool:
        return topic in self.topic_history

    def get_summary(self) -> dict:
        return {
            "total_turns": len(self.turns),
            "topics_discussed": self.topic_history,
            "active_topic": self.active_topic,
            "switches_count": len(self.topic_switches),
            "facts_logged_count": len(self.delivered_facts)
        }

def get_session_memory(request) -> SessionMemory:
    """Retrieves or initializes SessionMemory stored in Django session."""
    session_data = request.session.get("support_memory", None)
    return SessionMemory(session_data)

def save_session_memory(request, memory: SessionMemory):
    """Persists SessionMemory in Django session."""
    request.session["support_memory"] = memory.to_dict()
    request.session.modified = True
