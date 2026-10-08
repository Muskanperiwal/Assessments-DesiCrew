"""Views for Task 1: Autonomous Inventory Data Analyst Agent.
Powered by Google Gemini SDK (google.generativeai) with automatic function calling,
multi-key API rotation, Pandas execution, DuckDuckGo search, and executive summary synthesis.
"""
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

from .analysis import INSIGHT_BUILDERS, json_records, markdown_table, run_user_code

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
    "search_query": None,
    "charts": [],
}

# ==============================================================================
# TOOL DEFINITIONS (Function Calling for Gemini)
# ==============================================================================
def execute_pandas_code(code: str) -> str:
    """
    Executes LLM-generated Python against the loaded df.
    pandas, numpy, matplotlib.pyplot (plt), and seaborn (sns) are available.
    Charts are captured for the UI. Runtime errors are returned for self-correction.
    """
    global current_turn_artifacts
    current_turn_artifacts["code_executed"] = code
    result = run_user_code(df, code)
    current_turn_artifacts["charts"].extend(result.get("charts") or [])
    if result["ok"]:
        return result["output"]
    return result["output"] + " Please review the DataFrame columns and syntax, and try again."


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
- matplotlib.pyplot is available as plt and seaborn as sns. You may chart with them. Do not call plt.show(). Print a one-line description of what the chart shows.
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
        code = "df.nsmallest(8, 'Hand-In-Stock')[['Product ID', 'Product Name', 'Hand-In-Stock', 'Number of Units Sold']]"
        view = df.nsmallest(8, "Hand-In-Stock")
        execute_pandas_code(code)
        reply = (
            "### Low stock and replenishment priority\n\n"
            "Items with the lowest on-hand stock:\n\n"
            + markdown_table(view, ["Product ID", "Product Name", "Hand-In-Stock", "Number of Units Sold"])
            + "\n\nSingle-digit on-hand quantities should be first in the next purchase order."
        )
    elif "top" in q or "best" in q or "most sold" in q or "sales" in q:
        code = "df.nlargest(5, 'Number of Units Sold')[['Product ID', 'Product Name', 'Number of Units Sold', 'Cost Price Total (USD)']]"
        view = df.nlargest(5, "Number of Units Sold")
        execute_pandas_code(code)
        reply = (
            "### Top products by units sold\n\n"
            + markdown_table(view, ["Product ID", "Product Name", "Number of Units Sold", "Cost Price Total (USD)"])
            + "\n\nThese high-velocity SKUs need uninterrupted supply."
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
            "### Inventory valuation and catalog summary\n\n"
            f"{out}\n\n"
            f"- **Catalog Size:** {len(df)} active inventory SKUs registered.\n"
            "- **Active Valuation:** Cumulative total cost value of inventory assets."
        )
    else:
        code = "df.describe()"
        execute_pandas_code(code)
        reply = (
            f"### Inventory dataset\n\n"
            f"Found **{len(df)} products**.\n\n"
            + markdown_table(df, list(df.columns), limit=6)
            + "\n\nAsk about low stock, top sellers, valuation, or sell-through. "
            "The smart analyses on the left also draw charts."
        )

    return {
        "reply": reply,
        "code_executed": code,
        "search_query": None,
        "charts": current_turn_artifacts.get("charts") or [],
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
    current_turn_artifacts = {"code_executed": None, "search_query": None, "charts": []}

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
                    "search_query": current_turn_artifacts["search_query"],
                    "charts": current_turn_artifacts["charts"],
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

    result = run_user_code(df, code)
    return JsonResponse({
        "status": "success" if result["ok"] else "error",
        "output": result["output"],
        "charts": result["charts"],
    })


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


@require_http_methods(["GET"])
def api_records(request):
    """Full inventory sheet, read-only, for the data viewer."""
    if df.empty:
        return JsonResponse({"error": "Inventory sheet is empty"}, status=404)
    return JsonResponse({
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(df),
        "columns": list(df.columns),
        "rows": json_records(df),
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_insight(request):
    """Ready-made analysis: written findings plus a matplotlib/seaborn chart."""
    try:
        body = json.loads(request.body.decode("utf-8"))
        key = (body.get("insight") or "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    builder = INSIGHT_BUILDERS.get(key)
    if builder is None:
        return JsonResponse({"error": "Unknown analysis"}, status=400)
    if df.empty:
        return JsonResponse({"error": "Inventory sheet is empty"}, status=404)
    try:
        payload = builder(df)
    except Exception as exc:
        logger.exception("Insight %s failed", key)
        return JsonResponse({"error": str(exc)}, status=500)
    return JsonResponse(payload)
