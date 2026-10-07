# Technical Assessment Solutions - DesiCrew

**Author:** Muskan Periwal  
**GitHub:** [@Muskanperiwal](https://github.com/Muskanperiwal)  
**Repository:** [Assessments-DesiCrew](https://github.com/Muskanperiwal/Assessments-DesiCrew)

---

## 📌 Overview

This repository contains end-to-end, production-grade solutions for the technical assessment challenges:

1. **Question 1: Excel Inventory Intelligence Agent**
   - An intelligent agentic AI system designed to load, analyze, and query multi-sheet Excel inventory datasets.
   - Capabilities include automatic Python/Pandas code synthesis and sandboxed execution, domain-specific terminology search (Hand-in-Stock, Sell-Through Rate, Safety Stock, ABC Pareto Classification), and plain-English executive summarization.
   - Features a modern dark-mode interactive web dashboard with real-time prompt chips, custom file uploads, and an embedded Python playground.

2. **Question 2: Document-Aware Multi-Turn Support Assistant**
   - A contextual customer support agent maintaining conversational state across long multi-turn dialogues.
   - Enforces intelligent anti-repetition rules, recognizes and manages topic switching gracefully, and strictly grounds all responses with exact document section citations (`[Document.md § X. - Title]`).
   - Includes a full 10-turn automated benchmark test suite and an interactive dual-panel chat web application with real-time topic tracking.

3. **Question 3 & Reference Materials**
   - Reference files, proposal/assignment forms, KYC identity documents, and question specifications.

---

## 📂 Repository Structure

```
.
├── .gitignore                                # Git ignore rules (virtualenvs, temporary files, etc.)
├── README.md                                 # Main project documentation (this file)
├── requirements.txt                          # Python dependencies with pinned versions
├── Questions.docx                            # Original assessment problem statements
│
├── Question 1 & 3 (Files to use)/            # Input datasets and reference assets
│   ├── Question 1/
│   │   └── Inventory-Records-Sample-Data.xlsx # Sample inventory dataset
│   └── Question 3/                           # KYC, proposal, and assignment document assets
│
├── question_1_inventory_agent/               # Question 1: Inventory Intelligence Agent
│   ├── app.py                                # Flask web server & REST endpoints (Port 5000)
│   ├── agent.py                              # Core reasoning agent, query routing & code generation
│   ├── code_executor.py                      # Sandboxed Python execution engine
│   ├── inventory_loader.py                   # Excel parser with auto-header discovery & normalization
│   ├── search_engine.py                      # Domain glossary and external search fallback
│   ├── static/                               # Web dashboard assets (HTML5, CSS3, JavaScript)
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── README.md                             # Detailed documentation for Question 1
│
└── question_2_support_assistant/             # Question 2: Document-Aware Support Assistant
    ├── app.py                                # Flask conversational web server (Port 5001)
    ├── assistant.py                          # Multi-turn stateful assistant & grounding logic
    ├── knowledge_indexer.py                  # Knowledge base chunker, TF-IDF indexer & citation engine
    ├── session_memory.py                     # Dialogue history, entity stack & anti-repetition tracker
    ├── run_10_turn_demo.py                   # Automated 10-turn benchmark script
    ├── documents/                            # Knowledge base policies
    │   ├── Account_Security_Privacy.md
    │   ├── Customer_Support_Policy.md
    │   └── Subscription_Billing_Guide.md
    ├── static/                               # Modern chat interface assets
    │   ├── index.html
    │   ├── styles.css
    │   └── app.js
    └── README.md                             # Detailed documentation for Question 2
```

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/Muskanperiwal/Assessments-DesiCrew.git
cd Assessments-DesiCrew
```

### 2. Environment Setup

Create and activate a Python virtual environment (Python 3.10+ recommended):

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 💻 Running the Applications

### Question 1: Inventory Intelligence Agent

Start the Flask server for Question 1:
```bash
python question_1_inventory_agent/app.py
```
Open your browser at: **`http://127.0.0.1:5000`**

**Key Features:**
- Natural language queries translated directly into executable Pandas code.
- Immediate metrics calculations: Valuation, Sales Velocity, ABC Analysis, Stockout Risk.
- Domain glossary lookups for supply chain terminology.
- Custom Excel file uploader and live interactive code executor.

---

### Question 2: Support Assistant

#### A. Automated 10-Turn Benchmark Demo (CLI)
Run the automated verification script:
```bash
python question_2_support_assistant/run_10_turn_demo.py
```
This runs a simulated 10-turn dialogue demonstrating context retention, topic switching, anti-repetition memory, and section citations.

#### B. Interactive Web Chat Interface
Start the Flask server for Question 2:
```bash
python question_2_support_assistant/app.py
```
Open your browser at: **`http://127.0.0.1:5001`**

**Key Features:**
- Stateful dialogue across multi-turn sessions.
- Real-time topic badge updates and document citation pills.
- Dedicated "Run 10-Turn Demonstration" trigger button.
- Session memory reset and live policy reference viewer.

---

## 🛠️ Tech Stack & Libraries

- **Language:** Python 3.10+
- **Web Framework:** Flask, Werkzeug, Jinja2
- **Data Analytics:** Pandas, NumPy, OpenPyXL
- **Frontend:** Vanilla HTML5, CSS3 (Glassmorphic dark design system), Modern JavaScript (ES6+)
- **Algorithms:** TF-IDF keyword indexing, AST safe code parsing, conversational buffer memory

---

## 📄 License

This repository is created for the technical assessment evaluation by DesiCrew. All rights reserved.
