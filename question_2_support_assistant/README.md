# Question 2: Document-Aware Multi-Turn Support Assistant

A document-aware conversational support assistant that maintains dialogue context across a multi-turn conversation, enforces anti-repetition rules, detects and manages topic switches, and provides precise section citations for every answer.

---

## 🌟 Key Capabilities & Requirements Addressed

1. **Context Retention Across Multi-Turn Dialogue**:
   - Maintains active session state tracking the conversation topic stack, user query history, and active entity references.

2. **Remembers What the User Has Already Asked**:
   - Preserves a structured `user_queries` log per session with turn numbers and discussed topics.

3. **Anti-Repetition Intelligence**:
   - Maintains a set of delivered facts and policy clauses across turns.
   - When the user asks about an already-explored policy area, the assistant explicitly acknowledges the prior turn (*"As noted earlier in Turn 3..."*) and provides specific incremental answers rather than duplicating boilerplate text.

4. **Graceful Topic Switching**:
   - Dynamically recognizes when the conversation shifts domains (e.g. from *Support SLAs* to *Refunds*, to *Security & 2FA*, to *Billing Plans*, or returning back to *Hardware Warranty*).
   - Generates clean conversational transition bridges (*"Acknowledging the topic switch from..."* and *"Returning to our earlier discussion on..."*).

5. **Precise Document Section Citations**:
   - Every single response cites the exact document filename and section identifier, e.g.:
     `[Customer_Support_Policy.md § 2. - Refund & Cancellation Terms]`
     `[Subscription_Billing_Guide.md § 1. - Subscription Tiers & Pricing Model]`
     `[Account_Security_Privacy.md § 1. - Multi-Factor Authentication Requirements]`

6. **Demonstrated Across a 10-Turn Conversation**:
   - Automated benchmark script (`run_10_turn_demo.py`) and live UI benchmark runner validating all 10 turns.

---

## 📚 Knowledge Base Documents

Located in `question_2_support_assistant/documents/`:
1. `Customer_Support_Policy.md`:
   - § 1. Service Level Agreements (SLAs) & Response Windows
   - § 2. Refund & Cancellation Terms
   - § 3. Warranty Coverage & Hardware Replacements
   - § 4. Damaged or Lost Shipments Protocols
   - § 5. Customer Escalation & Mediation Paths
2. `Subscription_Billing_Guide.md`:
   - § 1. Subscription Tiers & Pricing Model
   - § 2. Billing Cycles, Renewal & Proration Rules
   - § 3. Payment Methods & Dunning for Failed Transactions
   - § 4. Plan Upgrades, Downgrades & Pausing
   - § 5. Invoicing, Corporate VAT & Tax Receipts
3. `Account_Security_Privacy.md`:
   - § 1. Multi-Factor Authentication (MFA / 2FA) Requirements
   - § 2. Password Reset Protocols & Identity Verification
   - § 3. User Data Retention, Export & Deletion (GDPR/CCPA)
   - § 4. Role-Based Access Control (RBAC) & Team Delegation
   - § 5. Security Incident Reporting & Audit Logs

---

## 🚀 How to Run Locally

### 1. Run the 10-Turn Benchmark in Terminal
```bash
python question_2_support_assistant/run_10_turn_demo.py
```

### 2. Start the Interactive Web Server
```bash
python question_2_support_assistant/app.py
```
Open your browser to:
```
http://127.0.0.1:5001
```

Click **"Run 10-Turn Demonstration"** or chat interactively!
