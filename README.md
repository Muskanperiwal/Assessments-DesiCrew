# Enterprise AI Assignment Suite (Django 5.x)

A unified, production-ready Django 5.x application housing three enterprise AI micro-systems:
1. **Task 1 (`/task1/`)**: Autonomous Inventory Data Analyst Agent (Dynamic Pandas execution, DuckDuckGo web search, ReAct feedback loop).
2. **Task 2 (`/task2/`)**: DocAware Multi-Turn Support Assistant (PyMuPDF document indexing, 10-turn session memory, anti-repetition protection, precise section citations).
3. **Task 3 (`/task3/`)**: Multimodal Document Scanner & Extractor (10 statutory ID and handwritten insurance forms, confidence scoring, 0.85 threshold human-in-the-loop flagging report).

---

## Quick deployment guide

This project is pre-configured with **WhiteNoise**, **Gunicorn**, **Procfile**, **build.sh**, and **Dockerfile** for zero-friction cloud deployment.

### Option 1: Render.com (recommended — fast and free)

1. Push your code to a **GitHub** repository.
2. Sign in to [Render](https://render.com/) and click **New + > Web Service**.
3. Select your GitHub repository.
4. Fill in the following settings:
   - **Name**: `ai-assignment-suite` (or your choice)
   - **Language**: `Python 3`
   - **Branch**: `main`
   - **Region**: Any (e.g. Frankfurt / Oregon / Singapore)
   - **Build Command**:
     ```bash
     ./build.sh
     ```
     *(Or if deploying with Root Directory set to `ai_assignment`: `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`)*
   - **Start Command**:
     ```bash
     gunicorn ai_assignment.wsgi:application --bind 0.0.0.0:$PORT
     ```
5. In **Environment Variables**, add:
   - `DEBUG`: `False`
   - `SECRET_KEY`: *(Click "Generate" or provide a secure random key)*
   - `GEMINI_API_KEY`: `your_gemini_api_key_here`
   - `GROQ_API_KEY`: *(Optional) `your_groq_api_key_here`*
   - `ALLOWED_HOSTS`: `*`
6. Click **Deploy Web Service**. Your app will be live with a free `https://<service-name>.onrender.com` SSL URL.

---

### Option 2: Railway.app

1. Go to [Railway.app](https://railway.app/) and create a **New Project**.
2. Click **Deploy from GitHub repo** and select this repository.
3. Railway automatically detects the provided [Dockerfile](file:///C:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/Dockerfile) or [Procfile](file:///C:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/Procfile).
4. In the **Variables** tab, set:
   - `DEBUG` = `False`
   - `GEMINI_API_KEY` = `your_gemini_api_key`
   - `GROQ_API_KEY` = `your_groq_api_key`
5. In the **Settings** tab, generate a public domain (e.g. `your-app.up.railway.app`). Railway handles SSL automatically.

---

### Option 3: Docker and Docker Compose (VPS, AWS, GCP, Azure, DigitalOcean)

A multi-stage [Dockerfile](file:///C:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/Dockerfile) and [docker-compose.yml](file:///C:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/docker-compose.yml) are included.

#### Using Docker Compose:
```bash
# Clone the repository
git clone <your-repo-url>
cd <repo-folder>

# Launch the containerized application
docker compose up -d --build
```
Access the application at `http://localhost:8000`.

#### Using Docker CLI:
```bash
docker build -t ai-suite .
docker run -d -p 8000:8000 \
  -e DEBUG=False \
  -e GEMINI_API_KEY="your_gemini_key" \
  -e GROQ_API_KEY="your_groq_key" \
  ai-suite
```

---

### Option 4: PythonAnywhere (free Python hosting)

1. Sign up at [PythonAnywhere](https://www.pythonanywhere.com/).
2. Open a **Bash Console** and clone the repo:
   ```bash
   git clone <your-repo-url>
   cd "muskan periwal/ai_assignment"
   mkvirtualenv --python=/usr/bin/python3.11 ai_env
   pip install -r requirements.txt
   python manage.py collectstatic --no-input
   python manage.py migrate
   ```
3. Go to the **Web** tab:
   - Add a new web app (Manual configuration, Python 3.11).
   - Set **Source code**: `/home/<username>/.../ai_assignment`
   - Set **Virtualenv**: `/home/<username>/.virtualenvs/ai_env`
4. Edit the **WSGI configuration file**:
   ```python
   import os
   import sys

   path = '/home/<username>/.../ai_assignment'
   if path not in sys.path:
       sys.path.append(path)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'ai_assignment.settings'
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
5. Click **Reload <username>.pythonanywhere.com**.

---

### Option 5: Local execution (development)

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
| `ALLOWED_HOSTS` | Optional | Comma-separated list of allowed domains | `*,your-domain.com` |
| `GEMINI_API_KEY` | Optional | Google Gemini API key for Task 1 & Task 2 | `AIzaSy...` |
| `GROQ_API_KEY` | Optional | Groq API key for Llama 3.3 70B fallback | `gsk_...` |
| `CSRF_TRUSTED_ORIGINS` | Optional | Extra trusted origins for CSRF POST requests | `https://*.onrender.com,https://your-domain.com` |
