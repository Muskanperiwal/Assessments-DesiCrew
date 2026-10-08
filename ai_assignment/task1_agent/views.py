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
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
]

# ==============================================================================
# GLOBAL DATAFRAME LOADING (Loaded once at server startup to prevent I/O bottlenecks)
# ==============================================================================
EXCEL_PATH = Path(settings.BASE_DIR) / 'data' / 'Inventory-Records-Sample-Data.xlsx'

def _load_inventory_dataset() -> pd.DataFrame:
    """Reads and cleans the canonical Inventory Excel spreadsheet."""
    try:
        # Header row is at index 5 in the sample dataset (Col A is blank index column)
        data = pd.read_excel(EXCEL_PATH, header=5)
        cleaned_cols = []
        for col in data.columns:
            c = re.sub(r'\s+', ' ', str(col).replace('-\n', '-').replace('\n', ' ')).strip()
            cleaned_cols.append(c)
        data.columns = cleaned_cols

        if 'Unnamed: 0' in data.columns:
            data = data.drop(columns=['Unnamed: 0'])

        # Clean empty rows
        data = data.dropna(subset=['Product ID', 'Product Name'], how='all')
        return data
    except Exception as e:
        logger.error(f"Error loading inventory records: {e}")
        return pd.DataFrame()

# Immutable baseline copy of original Excel dataset
ORIGINAL_DF = _load_inventory_dataset()
ORIGINAL_COLUMNS = list(ORIGINAL_DF.columns)

def get_clean_df() -> pd.DataFrame:
    """Always returns a fresh, isolated copy of the original 8-column Excel dataset."""
    return ORIGINAL_DF.copy(deep=True)

# Module-level df reference (always mirrors the clean baseline)
df = get_clean_df()
print(f"[Task 1] Loaded {len(df)} inventory records globally into memory from {EXCEL_PATH.name} (Columns: {ORIGINAL_COLUMNS})")

# Dynamic representation of dataset schema for LLM system prompt
DATASET_DTYPES_STR = "\n".join([f"- {col} ({ORIGINAL_DF[col].dtype})" for col in ORIGINAL_COLUMNS]) if not ORIGINAL_DF.empty else "No columns loaded"

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
    Executes LLM-generated Python against a clean copy of the inventory DataFrame.
    pandas, numpy, matplotlib.pyplot (plt), and seaborn (sns) are available.
    Charts are captured for the UI. Runtime errors are returned for self-correction.
    """
    global current_turn_artifacts, df
    current_turn_artifacts["code_executed"] = code
    # Always execute against an isolated clean copy so user code never mutates the underlying dataset
    clean_copy = get_clean_df()
    result = run_user_code(clean_copy, code)
    # Ensure module df is reset to pristine state
    df = get_clean_df()
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
    if not current_turn_artifacts.get("search_queries"):
        current_turn_artifacts["search_queries"] = []
    current_turn_artifacts["search_queries"].append(query)
    current_turn_artifacts["search_query"] = " | ".join(current_turn_artifacts["search_queries"])

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
SYSTEM_INSTRUCTION = f"""You are an expert Inventory Data Analyst assistant. You have direct access to an Excel dataset ('Inventory-Records-Sample-Data.xlsx') loaded into memory as a pandas DataFrame named df.

Official Original Excel Columns (Source of Truth):
{DATASET_DTYPES_STR}

CANONICAL INVENTORY DOMAIN MAPPING:
- "Inventory quantity" / "Current inventory" / "Stock on hand" / "Stock quantity" -> Default strictly to `Hand-In-Stock` (physical units currently in warehouse).
- "Sales" / "Volume sold" / "Quantity sold" -> `Number of Units Sold`.
- "Restock" / "New stock received" / "Purchases" -> `Purchase/ Stock in`.
- "Initial stock" / "Beginning inventory" -> `Opening Stock`.
- "Unit cost" -> `Cost Price Per Unit (USD)`.
- "Total inventory value" -> `Cost Price Total (USD)`.

DIRECT ANSWER RULE (NO OVER-HEDGING / NO AMBIGUITY DUMPING):
1. When asked a straightforward question about a specific metric (e.g., "What is the average inventory quantity per record?"):
   - ANSWER DIRECTLY in the very first sentence with the exact number computed.
   - For inventory quantity, use `Hand-In-Stock` as the standard definition.
   - DO NOT list multiple alternative metrics or hedge with "Depending on which specific inventory metric you are referring to..." unless the question is genuinely ambiguous or explicitly requests a comparison.
2. AGGREGATION PRECISION (MEAN vs. SUM):
   - When asked for "average" or "mean", execute and report `mean()`. NEVER substitute a `sum()`.
   - When asked for "total" or "sum", execute and report `sum()`.
   - For example: if asked "What is the average inventory quantity per record?", calculate `df['Hand-In-Stock'].mean()` (approx 43.57 units) and state: "The average inventory quantity per record is **43.57 units** (based on Hand-In-Stock across all 46 products)."

STRICT TOOL VERIFICATION (DEFINITIONS & EXTERNAL KNOWLEDGE):
- For industry terminology, supply chain definitions, business formulas (e.g., Safety Stock, EOQ, Reorder Point, Cycle Stock, Lead Time Demand), you MUST invoke the search_web tool. NEVER rely solely on parametric memory or hallucinated formulas.
- MULTIPLE DEFINITIONS CONSTRAINT: If the user prompt asks to define, explain, or look up multiple distinct concepts (e.g., "Define Safety Stock and EOQ"), you MUST issue separate, explicit search_web tool calls for EACH distinct concept rather than bundling them into a single vague query or guessing one from memory.

DATAFRAME VISUALIZATIONS & TABLE FORMATTING:
- When a query asks to list, filter, or rank items:
  - If the result contains 10 or more items (e.g., listing all 29 low-stock products), DO NOT output a long, comma-separated sentence or wall of text.
  - ALWAYS format the output as a clean, structured Markdown table with key context columns (e.g., | Product ID | Product Name | Hand-In-Stock | Cost Price Per Unit (USD) |).
  - Provide a clear summary count header before the table (e.g., "Found **29 products** with Hand-In-Stock under 50 units:").
  - For small results (1–5 items), concise bullet points or a short table are both acceptable.

DATASET COLUMNS vs. CALCULATED METRICS RULES:
1. The original Excel dataset contains ONLY the 8 columns listed above:
   - Product ID (str)
   - Product Name (str)
   - Opening Stock (int64)
   - Purchase/ Stock in (int64)
   - Number of Units Sold (int64)
   - Hand-In-Stock (int64)
   - Cost Price Per Unit (USD) (int64)
   - Cost Price Total (USD) (int64)
2. When the user asks "What columns are available in the inventory dataset?" or asks for the columns/schema of the Excel file:
   - Report ONLY the official 8 original columns from the Excel file above.
   - Do NOT report session-calculated metrics or temporary variables (e.g., Inventory_Turnover_Proxy, Stock_Cover, Sold_Ratio_of_Available, Sales_Value_Proxy, Total_Throughput_Cost) as dataset columns.
   - You may separately explain that analytical metrics (like inventory turnover, stock cover, sell-through) can be derived upon request.
3. If the user asks whether a specific metric (e.g., "Are Inventory_Turnover_Proxy and Stock_Cover original columns in the Excel file, or were they calculated during analysis?"):
   - Explicitly and unequivocally state: "They are NOT original columns in the Excel file; they are calculated metrics created during analysis."
   - State that the original Excel file contains only the 8 core columns listed above.
4. Report raw calculated values truthfully without forcing reconciliations (e.g., acknowledge physical ledger values as found in the data).

HEADER SANITIZATION & EXACT IDENTIFIER RULE:
- Raw Excel headers containing newline characters or awkward spacing (e.g., 'Hand-In-\\nStock', 'Cost Price \\nPer Unit (USD)', 'Purchase/\\nStock in') have been automatically stripped and normalized into standard clean identifiers:
  ['Product ID', 'Product Name', 'Opening Stock', 'Purchase/ Stock in', 'Number of Units Sold', 'Hand-In-Stock', 'Cost Price Per Unit (USD)', 'Cost Price Total (USD)'].
- When writing pandas code, always use these exact clean column names or print/inspect df.columns before querying. The execution environment provides resilient resolution for spacing variations.

Operational Rules:
- For any numerical, statistical, or data-filtering question, you MUST call the execute_pandas_code tool. Write valid Python code. Always print your final result (e.g., print(df['Column'].mean())). NEVER hallucinate data.
- The DataFrame df contains the clean inventory records. You can define temporary variables or assign calculated columns on df within your Python code to answer analytical questions.
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

    # 1. Distinguish original Excel columns from session calculated metrics
    if ("original" in q or "calculated" in q) and any(m in q for m in ["turnover", "stock_cover", "stock cover", "proxy", "metric", "sold_ratio"]):
        code = "print(df.columns.tolist())"
        execute_pandas_code(code)
        reply = (
            "They are **not original columns** in the Excel file; they are **calculated metrics created during analysis**.\n\n"
            "The original Excel dataset (`Inventory-Records-Sample-Data.xlsx`) contains only the following **8 core columns**:\n\n"
            + "\n".join([f"- **{col}** (`{ORIGINAL_DF[col].dtype}`)" for col in ORIGINAL_COLUMNS])
            + "\n\nAny other metrics (such as `Inventory_Turnover_Proxy`, `Stock_Cover`, `Sold_Ratio_of_Available`, etc.) "
            "are calculated dynamically during analysis and are not present as raw columns in the original spreadsheet."
        )
    # 2. Average inventory quantity / stock per record
    elif any(phrase in q for phrase in ["average inventory", "average stock", "average quantity", "mean inventory", "mean stock", "average units"]):
        code = "avg_stock = df['Hand-In-Stock'].mean()\nprint(f'Average Hand-In-Stock: {avg_stock:.2f}')"
        execute_pandas_code(code)
        avg_val = ORIGINAL_DF['Hand-In-Stock'].mean()
        reply = (
            f"The average inventory quantity per record is **{avg_val:.2f} units** "
            f"(calculated using **Hand-In-Stock** across all {len(ORIGINAL_DF)} product records in the catalog).\n\n"
            f"- **Core Metric:** Mean of `Hand-In-Stock`\n"
            f"- **Total Physical Inventory:** {ORIGINAL_DF['Hand-In-Stock'].sum():,} units\n"
            f"- **Product SKU Count:** {len(ORIGINAL_DF)} records"
        )
    # 3. What columns are available in the inventory dataset?
    elif any(phrase in q for phrase in ["what columns", "which columns", "columns are available", "columns in the inventory", "list columns", "dataset schema", "schema", "table structure"]):
        code = "print(df.columns.tolist())\nprint(df.dtypes)"
        execute_pandas_code(code)
        reply = (
            "### Inventory Dataset Columns (Excel Source of Truth)\n\n"
            "The original Excel dataset contains the following **8 core columns**:\n\n"
            + "\n".join([f"- **{col}** (`{ORIGINAL_DF[col].dtype}`)" for col in ORIGINAL_COLUMNS])
            + "\n\n*(Note: Derived performance metrics such as Inventory Turnover, Stock Cover, and Sell-Through Rate are calculated dynamically during analysis and are not columns in the raw Excel file.)*"
        )
    elif "low" in q or "reorder" in q or ("stock" in q and "alert" in q):
        code = "df.nsmallest(8, 'Hand-In-Stock')[['Product ID', 'Product Name', 'Hand-In-Stock', 'Number of Units Sold']]"
        view = ORIGINAL_DF.nsmallest(8, "Hand-In-Stock")
        execute_pandas_code(code)
        reply = (
            "### Low stock and replenishment priority\n\n"
            "Items with the lowest on-hand stock:\n\n"
            + markdown_table(view, ["Product ID", "Product Name", "Hand-In-Stock", "Number of Units Sold"])
            + "\n\nSingle-digit on-hand quantities should be first in the next purchase order."
        )
    elif "top" in q or "best" in q or "most sold" in q or "sales" in q:
        code = "df.nlargest(5, 'Number of Units Sold')[['Product ID', 'Product Name', 'Number of Units Sold', 'Cost Price Total (USD)']]"
        view = ORIGINAL_DF.nlargest(5, "Number of Units Sold")
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
            f"- **Catalog Size:** {len(ORIGINAL_DF)} active inventory SKUs registered.\n"
            "- **Active Valuation:** Cumulative total cost value of inventory assets."
        )
    else:
        code = "df.describe()"
        execute_pandas_code(code)
        reply = (
            f"### Inventory dataset\n\n"
            f"Found **{len(ORIGINAL_DF)} products** across **{len(ORIGINAL_COLUMNS)} columns**.\n\n"
            + markdown_table(ORIGINAL_DF, list(ORIGINAL_COLUMNS), limit=6)
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
    clean_data = get_clean_df()
    column_details = []
    if not clean_data.empty:
        for col in clean_data.columns:
            column_details.append({
                "name": col,
                "dtype": str(clean_data[col].dtype)
            })

    total_val = clean_data['Cost Price Total (USD)'].sum() if 'Cost Price Total (USD)' in clean_data.columns else 0
    total_stock = clean_data['Hand-In-Stock'].sum() if 'Hand-In-Stock' in clean_data.columns else 0

    context = {
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(clean_data),
        "column_count": len(clean_data.columns),
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
    current_turn_artifacts = {"code_executed": None, "search_query": None, "search_queries": [], "charts": []}

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
                if "429" in str(model_err).lower() or "quota" in str(model_err).lower() or "resource_exhausted" in str(model_err).lower():
                    # Try next candidate model on the same key before switching keys
                    continue
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

    result = run_user_code(get_clean_df(), code)
    return JsonResponse({
        "status": "success" if result["ok"] else "error",
        "output": result["output"],
        "charts": result["charts"],
    })


@require_http_methods(["GET"])
def api_data_info(request):
    """Returns detailed dataset columns, data types, and preview records."""
    clean_data = get_clean_df()
    if clean_data.empty:
        return JsonResponse({"error": "DataFrame is empty"}, status=404)

    preview_records = clean_data.head(5).to_dict(orient='records')
    dtypes_dict = {col: str(clean_data[col].dtype) for col in clean_data.columns}

    return JsonResponse({
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(clean_data),
        "column_count": len(clean_data.columns),
        "columns": list(clean_data.columns),
        "dtypes": dtypes_dict,
        "preview": preview_records
    })


@require_http_methods(["GET"])
def api_records(request):
    """Full inventory sheet, read-only, for the data viewer."""
    clean_data = get_clean_df()
    if clean_data.empty:
        return JsonResponse({"error": "Inventory sheet is empty"}, status=404)
    return JsonResponse({
        "dataset_name": EXCEL_PATH.name,
        "row_count": len(clean_data),
        "columns": list(clean_data.columns),
        "rows": json_records(clean_data),
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
    clean_data = get_clean_df()
    if clean_data.empty:
        return JsonResponse({"error": "Inventory sheet is empty"}, status=404)
    try:
        payload = builder(clean_data)
    except Exception as exc:
        logger.exception("Insight %s failed", key)
        return JsonResponse({"error": str(exc)}, status=500)
    return JsonResponse(payload)
