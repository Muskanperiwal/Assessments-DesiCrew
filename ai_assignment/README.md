# Enterprise AI Assignment Suite (Django 5.x)

A modular, production-ready Django project implementing three specialized AI systems:
1. **`task1_agent/`**: Autonomous Inventory Data Analyst Chatbot with dynamic Pandas execution, DuckDuckGo web search, and ReAct loop.
2. **`task2_support/`**: DocAware Multi-Turn Support Assistant with PyMuPDF chunking, 10-turn session memory, anti-repetition tracking, and document citations.
3. **`task3_vision/`**: Multimodal Document Scanner & Extractor covering 10 mixed identity proofs and handwritten proposal forms with confidence scoring and quality flagging.

---

## 📁 Directory Architecture

```text
ai_assignment/
├── manage.py
├── requirements.txt
├── .env                             # Store GROQ_API_KEY and other credentials here
├── README.md                        # Instructions on how to run the Django server
│
├── ai_assignment/                   # Main Django Project Configuration
│   ├── __init__.py
│   ├── settings.py                  # Global settings, installed apps, and API keys
│   ├── urls.py                      # Main URL router pointing to the 3 task apps
│   ├── asgi.py                      # ASGI config (recommended if using async views)
│   └── wsgi.py                      # WSGI config
│
├── data/                            # Shared directory for reference datasets
│   ├── Inventory-Records-Sample-Data.xlsx  # Required for Task 1
│   ├── ground_truth.json            # Reference labels for Task 3 validation
│   ├── support_documents/           # Policy documents for Task 2
│   └── sample_documents/            # 10 mixed identity and proposal forms for Task 3
│
├── task1_agent/                     # App 1: Data Analyst Chatbot
│   ├── __init__.py
│   ├── urls.py                      # Routes: /task1/ (UI) and /task1/api/chat/ (API)
│   ├── views.py                     # Global Pandas loading and API view for ReAct loop
│   ├── tools.py                     # execute_pandas_code and search_web tools
│   └── templates/
│       └── task1_agent/
│           └── index.html           # Tailwind CSS chat interface with collapsible details
│
├── task2_support/                   # App 2: Smart Support Assistant
│   ├── __init__.py
│   ├── urls.py                      # Routes: /task2/ (UI), /task2/api/chat/, /task2/api/reset/
│   ├── views.py                     # Multi-turn conversation handling
│   ├── engine.py                    # RAG pipeline: PyMuPDF chunking and section indexing
│   ├── memory.py                    # 10-turn session memory & anti-repetition tracking
│   └── templates/
│       └── task2_support/
│           └── index.html           # UI displaying chat and explicit document citations
│
└── task3_vision/                    # App 3: Document Scanner & Extractor
    ├── __init__.py
    ├── urls.py                      # Routes: /task3/ (UI), /task3/api/pipeline/, /task3/api/upload/
    ├── views.py                     # Dashboard, full pipeline trigger, and file uploads
    ├── pipeline.py                  # Classification, extraction, and confidence scoring
    ├── schemas.py                   # Pydantic models mapping fields for all 10 document types
    └── templates/
        └── task3_vision/
            └── index.html           # UI for scanning, JSON viewing, and flagging report
```

---

## ⚙️ Quick Start Guide

### 1. Prerequisites & Environment Setup
Ensure Python 3.10+ is installed and your virtual environment is active:
```bash
# Activate your virtual environment (if using .venv in root)
..\.venv\Scripts\activate  # Windows
# or
source ../.venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys (`.env`)
Create or edit `.env` in `ai_assignment/`:
```env
# Optional but recommended for full OpenAI/Groq ReAct capabilities:
GROQ_API_KEY=gsk_your_groq_api_key_here

# (Optional: If no Groq key is provided, Task 1 and Task 2 automatically operate in high-precision local deterministic fallback mode)
```

### 3. Initialize Database
Run initial Django migrations:
```bash
python manage.py migrate
```

### 4. Run the Development Server
```bash
python manage.py runserver 8000
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in your browser to access the central suite hub.

---

## 🧭 Application Modules & Routes

| Module | Route | Key Features |
| :--- | :--- | :--- |
| **Suite Dashboard** | `/` | Central launchpad linking to all 3 task applications |
| **Task 1: Inventory Analyst** | `/task1/` | ReAct reasoning, dynamic Pandas execution, DuckDuckGo search, collapsible `<details>` execution views |
| **Task 2: Support Assistant** | `/task2/` | 10-turn session tracking, PyMuPDF RAG, anti-repetition, topic shift awareness, section citations |
| **Task 3: Document Scanner** | `/task3/` | 10 document types, 100% field extraction, confidence scoring, 0.85 threshold flagging report |

---

## 📡 REST API Endpoints

### Task 1: Data Analyst
- **`POST /task1/api/chat/`**:
  ```json
  // Request
  {
    "message": "Which are the top 5 products by number of units sold?",
    "history": []
  }
  // Response
  {
    "reply": "Executive summary with formatted Markdown...",
    "code_executed": "df[['Product ID', 'Product Name', 'Number of Units Sold']].sort_values(...)",
    "code_output": "...",
    "search_query": null
  }
  ```

### Task 2: Support Assistant
- **`POST /task2/api/chat/`**:
  ```json
  // Request
  { "message": "What is the policy regarding refund eligibility?" }
  // Response
  {
    "reply": "...",
    "citation": "[Document: Subscription Billing Guide | Section: § 2.1 - Refund Windows]",
    "turn_number": 1,
    "topic": "Refund Windows"
  }
  ```
- **`POST /task2/api/reset/`**: Clears multi-turn session history.

### Task 3: Document Extraction
- **`GET/POST /task3/api/pipeline/`**: Runs the complete extraction pipeline over all 10 reference documents and returns both structured extractions and the flagging report.
- **`POST /task3/api/upload/`**: Uploads a single document file (`multipart/form-data`) and returns real-time classification, field extractions, and confidence scores.
