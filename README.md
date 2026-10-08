# Enterprise AI Assignment Suite (Django 5.x)

A unified, production-ready Django 5.x application housing three enterprise AI micro-systems:
1. **Task 1 (`/task1/`)**: Autonomous Inventory Data Analyst Agent (Dynamic Pandas execution, DuckDuckGo web search, ReAct feedback loop).
2. **Task 2 (`/task2/`)**: DocAware Multi-Turn Support Assistant (PyMuPDF document indexing, 10-turn session memory, anti-repetition protection, precise section citations).
3. **Task 3 (`/task3/`)**: Multimodal Document Scanner & Extractor (10 statutory ID and handwritten insurance forms, confidence scoring, 0.85 threshold human-in-the-loop flagging report).

---

## Local execution (development)

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv

   # Windows:
   .\.venv\Scripts\activate

   # Linux/macOS:
   source .venv/bin/activate
   ```

2. **Install project dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Navigate into the Django directory**:
   ```bash
   cd ai_assignment
   ```

4. **Run database migrations**:
   ```bash
   python manage.py migrate
   ```

5. **Start the development server**:
   ```bash
   python manage.py runserver 8000
   ```

6. Visit [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser.

---

## Environment variables reference

Create a `.env` file in the project root or configure the following environment variables:

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `DEBUG` | Optional | Set to `False` in production | `False` |
| `SECRET_KEY` | Recommended | Django security secret key | `random-string` |
| `GEMINI_API_KEY` | Recommended | Google Gemini API key for Task 1, Task 2 & Task 3 | `AIzaSy...` |
| `GROQ_API_KEY` | Optional | Groq API key for Llama 3.3 70B fallback | `gsk_...` |