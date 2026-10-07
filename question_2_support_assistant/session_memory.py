class SessionMemory:
    """
    Manages session state across multi-turn conversations:
    1. Tracks user queries and turn numbers.
    2. Maintains a log of provided information and facts to prevent repetition.
    3. Detects and tracks topic switches and conversation stack.
    """
    def __init__(self):
        self.turns = []
        self.user_queries = []
        self.delivered_facts = set()
        self.topic_history = []
        self.active_topic = None
        self.topic_switches = []

    def record_turn(self, turn_num: int, user_query: str, topic: str, delivered_facts: list, citation: str, assistant_reply: str):
        # Check topic transition
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

        # Record facts
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
        self.user_queries.append({"turn": turn_num, "query": user_query, "topic": topic})
        return turn_record

    def has_fact_been_delivered(self, fact_key: str) -> bool:
        return fact_key.strip().lower() in self.delivered_facts

    def has_query_topic_been_asked(self, topic: str) -> bool:
        return topic in self.topic_history

    def get_turns_discussing(self, topic: str) -> list:
        return [t["turn_number"] for t in self.turns if t["topic"] == topic]

    def get_summary_state(self) -> dict:
        return {
            "total_turns": len(self.turns),
            "active_topic": self.active_topic,
            "topic_history": list(self.topic_history),
            "topic_switches_count": len(self.topic_switches),
            "topic_switches": self.topic_switches,
            "user_queries": self.user_queries,
            "total_facts_delivered": len(self.delivered_facts),
            "delivered_facts": list(self.delivered_facts)
        }

    def reset(self):
        self.turns = []
        self.user_queries = []
        self.delivered_facts = set()
        self.topic_history = []
        self.active_topic = None
        self.topic_switches = []
