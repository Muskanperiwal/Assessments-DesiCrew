# Enterprise AI Assignment Suite (Django 5.x)

A unified Django 5.x application with three enterprise AI micro-systems:

1. **Task 1 (`/task1/`)** — Inventory Data Analyst Agent (Pandas execution, DuckDuckGo search, ReAct loop)
2. **Task 2 (`/task2/`)** — DocAware Support Assistant (PyMuPDF RAG, 10-turn memory, citations)
3. **Task 3 (`/task3/`)** — Multimodal Document Scanner (ID / proposal forms, confidence scoring, flagging)

---

## Layout

```text
.
├── requirements.txt / .env.example / .env
├── README.md / SUBMISSION_REPORT.md
└── ai_assignment/                    # Django project
    ├── manage.py
    ├── ai_assignment/                # settings, urls, wsgi
    ├── data/                         # datasets & sample docs
    ├── task1_agent/
    ├── task2_support/
    ├── task3_vision/
    └── templates/
```

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # add GEMINI_API_KEY
cd ai_assignment
python manage.py migrate
python manage.py runserver 8000
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).


---

## Environment variables

| Variable | Required | Description |
| :--- | :---: | :--- |
| `GEMINI_API_KEY` | Recommended | Gemini for Tasks 1–3 |
| `GEMINI_API_KEYS` | Optional | Comma-separated Gemini key pool |
| `SECRET_KEY` | Recommended | Django secret |
| `DEBUG` | Optional | Default `True`; use `False` in production |
| `ALLOWED_HOSTS` | Optional | Comma-separated hosts (`*` by default) |

---

## Routes

| Module | Route |
| :--- | :--- |
| Suite dashboard | `/` |
| Inventory analyst | `/task1/` |
| Support assistant | `/task2/` |
| Document scanner | `/task3/` |

See `SUBMISSION_REPORT.md` for full API details and evaluation notes.
