"""Views for Task 1: Autonomous Inventory Data Analyst Agent.
Powered by Google Gemini SDK (google.generativeai) with automatic function calling,
multi-key API rotation, Pandas execution, DuckDuckGo search, and executive summary synthesis.
"""
import io
import sys
import json
import logging
import re
from pathlib import Path
import pandas as pd
import numpy as np

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

# Model candidates ordered by preference for automatic resolution
MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-1.5-flash",
    "gemini-3.5-flash",
    "gemini-1.5-pro",
    "gemini-flash-latest"
]

# ==============================================================================
# GLOBAL DATAFRAME LOADING (Loaded once at server startup to prevent I/O bottlenecks)
# ==============================================================================
EXCEL_PATH = Path(settings.BASE_DIR) / 'Inventory-Records-Sample-Data.xlsx'
if not EXCEL_PATH.exists():
    EXCEL_PATH = Path(settings.BASE_DIR) / 'data' / 'Inventory-Records-Sample-Data.xlsx'

try:
    # Header row is at index 5 in the sample dataset
    df = pd.read_excel(EXCEL_PATH, header=5)
    
    # Clean column names: strip newlines and extraneous whitespace
    cleaned_cols = []
    for col in df.columns:
        c = re.sub(r'\s+', ' ', str(col).replace('-\n', '-').replace('\n', ' ')).strip()
        cleaned_cols.append(c)
    df.columns = cleaned_cols

    if 'Unnamed: 0' in df.columns:
        df = df.drop(columns=['Unnamed: 0'])

    # Clean empty rows
    df = df.dropna(subset=['Product ID', 'Product Name'], how='all')
    print(f"[Task 1] Loaded {len(df)} inventory records globally into memory from {EXCEL_PATH.name}")
except Exception as e:
    logger.error(f"Error loading inventory records: {e}")
    df = pd.DataFrame()

# Dynamic representation of dataset schema for LLM system prompt
DATASET_DTYPES_STR = df.dtypes.to_string() if not df.empty else "No columns loaded"

# Global tracking container for tools executed during the active request turn
current_turn_artifacts = {
    "code_executed": None,
    "search_query": None
}

# ==============================================================================
# TOOL DEFINITIONS (Function Calling for Gemini)
# ==============================================================================
def execute_pandas_code(code: str) -> str:
    """
    Safely executes LLM-generated Python pandas code against the loaded df using exec().
    Captures standard output (sys.stdout) and returns it as a string.
    Wrap in try/except to return runtime errors directly to the LLM for self-correction.
    """
    global current_turn_artifacts
    current_turn_artifacts["code_executed"] = code

    # Strip code block markdown ticks if passed
    code_lines = [line for line in code.strip().split('\n') if not line.strip().startswith('```')]
    clean_code = '\n'.join(code_lines).strip()

    # Capture standard output
    stdout_buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf

    local_env = {
        'df': df,
        'pd': pd,
        'np': np,
    }

    try:
        # If the last line is a bare expression without assignment or print, automatically capture it
        lines = clean_code.split('\n')
        if lines and not lines[-1].startswith(' ') and not lines[-1].startswith('\t'):
            last_line = lines[-1].strip()
            if not (last_line.startswith('print') or '=' in last_line or last_line.startswith('import') or last_line.startswith('def ')):
                lines[-1] = f"__res__ = ({last_line})\nif __res__ is not None: print(__res__)"
                clean_code = '\n'.join(lines)

        exec(clean_code, local_env, local_env)
        sys.stdout = old_stdout
        output = stdout_buf.getvalue().strip()
        if not output:
            output = "Execution completed successfully with no output."
        return output
    except Exception as e:
        sys.stdout = old_stdout
        err_msg = f"{type(e).__name__}: {str(e)}"
        return f"Python Execution Error: {err_msg}. Please review the DataFrame columns and syntax, and try again."


def search_web(query: str) -> str:
    """
    Uses the duckduckgo-search library to look up supply chain definitions,
    terminology, industry metrics (e.g. Safety Stock, EOQ), and external market context.
    """
    global current_turn_artifacts
    current_turn_artifacts["search_query"] = query

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))

        if not results:
            return f"No web search results found for query: '{query}'."

        snippets = []
        for idx, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "") or r.get("snippet", "")
            url = r.get("href", "") or r.get("link", "")
            snippets.append(f"[{idx}] {title}\nSummary: {body}\nSource: {url}")

        return "\n\n".join(snippets)
    except Exception as e:
        return f"Search engine lookup failed: {str(e)}."


# ==============================================================================
# SYSTEM INSTRUCTION
# ==============================================================================
SYSTEM_INSTRUCTION = f"""You are an expert Inventory Data Analyst assistant. You have direct access to an Excel dataset loaded into memory as a pandas DataFrame named df.
Dataset Columns and Types:
{DATASET_DTYPES_STR}

Operational Rules:
- For any numerical, statistical, or data-filtering question, you MUST call the execute_pandas_code tool. Write valid Python code. Always print your final result (e.g., print(df['Column'].sum())). NEVER hallucinate data.
- For definitions, supply chain metrics (e.g., Safety Stock, EOQ), or external industry context, you MUST call the search_web tool.
- Synthesize the tool outputs into a clear, professional plain-English summary. Do not explain the Python code to the user."""


# ==============================================================================
# DETERMINISTIC FALLBACK ENGINE
# ==============================================================================
def fallback_pandas_response(message: str) -> dict:
    q = message.lower()
    code = ""
    reply = ""

    if "low" in q or "reorder" in q or ("stock" in q and "alert" in q):
        code = "print(df[['Product ID', 'Product Name', 'Hand-In-Stock', 'Number of Units Sold']].sort_values(by='Hand-In-Stock').head(10))"
        out = execute_pandas_code(code)
        reply = (
            "### 🚨 Low Stock & Replenishment Priority\n\n"
            "Here are the items with the lowest current hand-in-stock levels requiring operational attention:\n\n"
            f"```text\n{out}\n```\n\n"
            "**Analyst Recommendations:**\n"
            "- Items with single-digit units on hand should be prioritized for immediate purchase order requisition.\n"
            "- Review historical lead times to establish safety stock buffers."
        )
    elif "top" in q or "best" in q or "most sold" in q or "sales" in q:
        code = "print(df[['Product ID', 'Product Name', 'Number of Units Sold', 'Cost Price Total (USD)']].sort_values(by='Number of Units Sold', ascending=False).head(5))"
        out = execute_pandas_code(code)
        reply = (
            "### 🏆 Top 5 Performing Products by Sales Volume\n\n"
            "The top sold products identified across your inventory catalog:\n\n"
            f"```text\n{out}\n```\n\n"
            "**Key Findings:** These high-velocity SKUs represent your core revenue drivers. Ensure supply chain continuity to prevent stockouts."
        )
    elif "value" in q or "total" in q or "worth" in q or "summary" in q or "overview" in q:
        code = (
            "total_val = df['Cost Price Total (USD)'].sum()\n"
            "total_stock = df['Hand-In-Stock'].sum()\n"
            "total_sold = df['Number of Units Sold'].sum()\n"
            "print(f'Total Inventory Valuation: ${total_val:,.2f}')\n"
            "print(f'Total Units on Hand: {total_stock:,}')\n"
            "print(f'Total Units Sold: {total_sold:,}')"
        )
        out = execute_pandas_code(code)
        reply = (
            "### 📊 Inventory Valuation & Catalog Summary\n\n"
            f"{out}\n\n"
            f"- **Catalog Size:** {len(df)} active inventory SKUs registered.\n"
            "- **Active Valuation:** Cumulative total cost value of inventory assets."
        )
    else:
        code = "print(df.describe().to_string())"
        out = execute_pandas_code(code)
        reply = (
            f"### 📈 Inventory Dataset Analysis\n\n"
            f"Found **{len(df)} products** in the loaded dataset.\n\n"
            f"```text\n{out}\n```\n\n"
            "> *Note: Add your Gemini API keys to `.env` to enable live Gemini AI function calling.*"
        )

    return {
        "reply": reply,
        "code_executed": code,
        "search_query": None
    }


# ==============================================================================
# DJANGO VIEWS
# ==============================================================================
@ensure_csrf_cookie
def chat_ui(request):
    """Template View: Renders task1_agent/index.html with rich dataset metrics."""
    column_details = []
    if not df.empty:
        for col in df.columns:
            column_details.append({
                "name": col,
                "dtype": str(df[col].dtype)
            })

    total_val = df['Cost Price Total (USD)'].sum() if 'Cost Price Total (USD)' in df.columns else 0
    total_stock = df['Hand-In-Stock'].sum() if 'Hand-In-Stock' in df.columns else 0

    context = {
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": column_details,
        "total_valuation": f"${total_val:,.2f}",
        "total_stock": f"{total_stock:,}",
        "has_gemini_key": bool(getattr(settings, 'GEMINI_API_KEYS', []) or getattr(settings, 'GEMINI_API_KEY', '')),
        "key_count": len(getattr(settings, 'GEMINI_API_KEYS', [])),
    }
    return render(request, 'task1_agent/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_chat(request):
    """
    API View: Accepts a JSON POST request containing 'message' (str) and 'history' (list).
    Runs Gemini model with automatic function calling & key rotation over tools:
    - execute_pandas_code
    - search_web
    Returns JsonResponse with reply, code_executed, and search_query.
    """
    global current_turn_artifacts
    current_turn_artifacts = {"code_executed": None, "search_query": None}

    try:
        body = json.loads(request.body.decode('utf-8'))
        user_message = body.get('message', '').strip()
        history = body.get('history', [])
    except Exception:
        return JsonResponse({"error": "Invalid JSON payload in request body"}, status=400)

    if not user_message:
        return JsonResponse({"error": "Empty message string provided"}, status=400)

    api_keys = getattr(settings, 'GEMINI_API_KEYS', [])
    if not api_keys:
        primary_k = getattr(settings, 'GEMINI_API_KEY', '')
        if primary_k:
            api_keys = [primary_k]

    if not api_keys:
        fallback = fallback_pandas_response(user_message)
        return JsonResponse(fallback)

    import google.generativeai as genai

    # Iterate through available API key pool for failover resilience
    last_exception = None
    for key_idx, current_key in enumerate(api_keys, 1):
        if not current_key.strip():
            continue

        genai.configure(api_key=current_key.strip())

        # Try supported candidate models for this key
        for model_name in MODEL_CANDIDATES:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=[execute_pandas_code, search_web]
                )

                gemini_history = []
                for h in history[-8:]:
                    role = "user" if h.get("role") == "user" else "model"
                    content = h.get("content", "")
                    if content:
                        gemini_history.append({"role": role, "parts": [content]})

                chat = model.start_chat(
                    history=gemini_history,
                    enable_automatic_function_calling=True
                )

                response = chat.send_message(user_message)
                reply_text = response.text if response and hasattr(response, 'text') else "Analysis completed."

                return JsonResponse({
                    "reply": reply_text,
                    "code_executed": current_turn_artifacts["code_executed"],
                    "search_query": current_turn_artifacts["search_query"]
                })

            except Exception as model_err:
                err_text = str(model_err).lower()
                if "404" in err_text or "not found" in err_text:
                    continue
                logger.warning(f"[Task 1] Key #{key_idx} ({model_name}) error: {model_err}. Rotating key...")
                last_exception = model_err
                break

    logger.error(f"[Task 1] All Gemini API keys failed. Last error: {last_exception}")
    fallback = fallback_pandas_response(user_message)
    fallback["reply"] += f"\n\n*(Notice: Gemini API key rotation exhausted. Reason: {str(last_exception)[:150]}. Executed via deterministic Pandas engine.)*"
    return JsonResponse(fallback)


@csrf_exempt
@require_http_methods(["POST"])
def api_playground(request):
    """
    Pandas Python Playground Endpoint:
    Executes raw custom Python Pandas code submitted by user in playground modal.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
        code = body.get('code', '').strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    if not code:
        return JsonResponse({"error": "No Python code provided"}, status=400)

    stdout_buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf

    local_env = {'df': df, 'pd': pd, 'np': np}

    try:
        lines = code.split('\n')
        if lines and not lines[-1].startswith(' ') and not lines[-1].startswith('\t'):
            last_line = lines[-1].strip()
            if not (last_line.startswith('print') or '=' in last_line or last_line.startswith('import') or last_line.startswith('def ')):
                lines[-1] = f"__res__ = ({last_line})\nif __res__ is not None: print(__res__)"
                code = '\n'.join(lines)

        exec(code, local_env, local_env)
        sys.stdout = old_stdout
        output = stdout_buf.getvalue().strip()
        if not output:
            output = "Code executed successfully with no printed output."
        return JsonResponse({"status": "success", "output": output})
    except Exception as e:
        sys.stdout = old_stdout
        return JsonResponse({"status": "error", "output": f"{type(e).__name__}: {str(e)}"})


@require_http_methods(["GET"])
def api_data_info(request):
    """Returns detailed dataset columns, data types, and preview records."""
    if df.empty:
        return JsonResponse({"error": "DataFrame is empty"}, status=404)

    preview_records = df.head(5).to_dict(orient='records')
    dtypes_dict = {col: str(df[col].dtype) for col in df.columns}

    return JsonResponse({
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(df),
        "column_count": len(df.columns),
        "columns": list(df.columns),
        "dtypes": dtypes_dict,
        "preview": preview_records
    })
