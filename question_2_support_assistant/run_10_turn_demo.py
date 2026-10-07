import os
import sys
from assistant import DocumentAwareAssistant

def run_demonstration():
    docs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'documents'))
    assistant = DocumentAwareAssistant(docs_dir)

    # 10 Multi-turn scenario explicitly testing all required capabilities:
    # - Remember previous questions
    # - Avoid repeating information
    # - Graceful topic switches
    # - Citing specific document section
    conversation_script = [
        # Turn 1: SLA Initial Query
        "What is your SLA response time for Critical P1 outages?",
        # Turn 2: Follow-up within same topic (SLA)
        "What about Standard P3 severity issues?",
        # Turn 3: Topic Switch 1 (From SLA to Refund Policy)
        "Can I get a refund if I cancel my annual subscription?",
        # Turn 4: Follow-up on Refund (Processing duration)
        "How many days does it take for the refund money to reach my account?",
        # Turn 5: Anti-Repetition Test (User asks about annual refund eligibility again)
        "Could you remind me of the refund terms for annual plans?",
        # Turn 6: Topic Switch 2 (From Refund to Account Security / MFA)
        "Is multi-factor authentication mandatory for admin accounts?",
        # Turn 7: Follow-up on Security (Emergency Password Reset)
        "What is the protocol if an administrator loses both password and 2FA recovery codes?",
        # Turn 8: Topic Switch 3 (From Security to Subscription Pricing)
        "What features and pricing are included in the Professional Plan?",
        # Turn 9: Topic Switch 4 (Return to Support Policy: Hardware Warranty)
        "Does warranty cover physical drop damage or liquid spills?",
        # Turn 10: Follow-up in Support Policy (Lost Shipment protocol)
        "How long before a missing package is officially declared Lost in Transit?"
    ]

    print("=" * 80)
    print("🤖 QUESTION 2: 10-TURN CONVERSATION DEMONSTRATION")
    print("=" * 80)

    for i, user_query in enumerate(conversation_script, 1):
        print(f"\n--- [TURN {i}/10] ---")
        print(f"👤 USER: {user_query}")
        
        result = assistant.process_turn(user_query)
        
        # Display turn analytics
        print(f"🎯 Topic Identified: {result['topic']}")
        if result['is_topic_switch']:
            if result['returning_to_previous_topic']:
                print("🔄 [Topic Switch]: Returning to previously visited topic!")
            else:
                print("🔀 [Topic Switch]: Graceful context shift detected!")
        if result['already_delivered_facts']:
            print(f"🛡️ [Anti-Repetition Active]: {len(result['already_delivered_facts'])} previously delivered facts avoided/referenced.")
        print(f"📖 Citation: {result['citation']}")
        print(f"\n🤖 ASSISTANT RESPONSE:\n{result['reply']}")
        print("-" * 80)

    state = assistant.memory.get_summary_state()
    print("\n" + "=" * 80)
    print("📊 10-TURN SESSION MEMORY AUDIT SUMMARY")
    print("=" * 80)
    print(f"Total Turns Completed: {state['total_turns']}")
    print(f"Total Topics Explored: {len(state['topic_history'])}")
    print(f"Topic Transitions Detected: {state['topic_switches_count']}")
    print(f"Total Distinct Policy Facts Delivered: {state['total_facts_delivered']}")
    print("Topics History:", " -> ".join(state['topic_history']))
    print("=" * 80)

if __name__ == '__main__':
    run_demonstration()
