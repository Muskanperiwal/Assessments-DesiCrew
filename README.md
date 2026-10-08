# Enterprise AI Assignment Suite (Django 5.x)

A unified, production-ready Django 5.x application housing three enterprise AI micro-systems:
1. **Task 1 (`/task1/`)**: Autonomous Inventory Data Analyst Agent (Dynamic Pandas execution, DuckDuckGo web search, ReAct feedback loop).
2. **Task 2 (`/task2/`)**: DocAware Multi-Turn Support Assistant (PyMuPDF document indexing, 10-turn session memory, anti-repetition protection, precise section citations).
3. **Task 3 (`/task3/`)**: Multimodal Document Scanner & Extractor (10 statutory ID and handwritten insurance forms, confidence scoring, 0.85 threshold human-in-the-loop flagging report).

---


Local execution (development)

1. Activate your virtual environment:
   ```bash
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Navigate into the Django directory:
   ```bash
   cd ai_assignment
   ```
3. Run migrations:
   ```bash
   python manage.py migrate
   ```
4. Start the development server:
   ```bash
   python manage.py runserver 8000
   ```
5. Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

---

## Environment variables reference

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `DEBUG` | Optional | Set to `False` in production | `False` |
| `SECRET_KEY` | Recommended | Django security secret key | `random-string` |
| `GEMINI_API_KEY` | Recommanded | Google Gemini API key for Task 1 & Task 2 | `AIzaSy...` |