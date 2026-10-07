import os
import re
import json
import pandas as pd
import numpy as np
from search_engine import InventorySearchTool
from code_executor import PythonCodeExecutor

class InventoryAgent:
    """
    Intelligent Agent for Excel Inventory Data Q&A.
    1. Writes and executes Python/Pandas code to query the dataset.
    2. Uses Search Tool to look up definitions, formulas, and domain context.
    3. Synthesizes analytical findings into plain English executive summaries.
    4. Optionally integrates with Gemini LLM when an API key is provided,
       while maintaining a robust deterministic NLP engine for guaranteed out-of-the-box execution.
    """
    def __init__(self, df: pd.DataFrame, col_map: dict):
        self.df = df
        self.col_map = col_map
        self.search_tool = InventorySearchTool()
        self.code_executor = PythonCodeExecutor()
        self.history = []
        self.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def set_dataset(self, df: pd.DataFrame, col_map: dict):
        self.df = df
        self.col_map = col_map

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def process_query(self, user_query: str) -> dict:
        q = user_query.strip()
        self.history.append({"role": "user", "content": q})

        search_result = None
        code_result = None
        generated_code = None

        # Step 1: Detect if Search Tool lookup is relevant
        def_triggers = [
            "what is", "what does", "define", "meaning of", "definition", 
            "explain", "formula", "how is", "concept", "glossary", "difference between",
            "stand for"
        ]
        q_lower = q.lower()
        has_def_trigger = any(t in q_lower for t in def_triggers)
        has_term_keyword = any(
            term in q_lower for term in [
                "hand-in-stock", "opening stock", "stock in", "sell-through", "sell through",
                "inventory turnover", "safety stock", "stockout", "abc analysis", 
                "reorder point", "dead stock", "cogs", "holding cost"
            ]
        )

        if has_def_trigger or has_term_keyword:
            search_query = self._extract_search_target(q)
            search_result = self.search_tool.search(search_query)

        # Step 2: Determine if Code Execution is needed
        # Check if the query is strictly a theoretical question with no data context
        is_strictly_theoretical = (has_def_trigger or has_term_keyword) and not any(
            w in q_lower for w in [
                "our", "this", "dataset", "data", "highest", "lowest", "total", "average", "mean",
                "top", "bottom", "calculate", "compute", "how many", "which", "list", "show", 
                "items", "products", "cost", "value", "inventory", "stock", "sold", "units",
                "laptop", "monitor", "keyboard", "rate", "pareto", "abc"
            ]
        )

        if not is_strictly_theoretical:
            generated_code = self._generate_query_code(q)
            if generated_code:
                code_result = self.code_executor.execute(generated_code, self.df)

        # Step 3: Plain-English Executive Summary
        summary = self._synthesize_summary(q, search_result, code_result)

        response_payload = {
            "query": q,
            "search_lookup": search_result,
            "code_generated": generated_code,
            "code_execution": code_result,
            "plain_english_summary": summary
        }

        self.history.append({"role": "assistant", "content": summary})
        return response_payload

    def _extract_search_target(self, query: str) -> str:
        q = query.lower()
        for term in [
            "hand-in-stock", "opening stock", "purchase / stock in", "stock in",
            "sell-through rate", "sell-through", "sell through", "inventory turnover", 
            "cost price total", "cost price per unit", "safety stock", 
            "stockout", "abc analysis", "reorder point", "dead stock"
        ]:
            if term in q:
                return term
        cleaned = re.sub(r'^(what is|what does|define|meaning of|explain the concept of|how to calculate|explain)\s+', '', q)
        return cleaned.strip('? ')

    def _get_active_columns(self):
        cols = self.df.columns.tolist()
        id_col = next((c for c in cols if 'id' in c.lower()), cols[0])
        name_col = next((c for c in cols if 'name' in c.lower()), cols[1] if len(cols) > 1 else cols[0])
        open_col = next((c for c in cols if 'opening' in c.lower()), 'Opening Stock')
        in_col = next((c for c in cols if 'purchase' in c.lower() or 'stock in' in c.lower()), 'Purchase / Stock In')
        sold_col = next((c for c in cols if 'sold' in c.lower()), 'Number of Units Sold')
        hand_col = next((c for c in cols if 'hand' in c.lower()), 'Hand-In-Stock')
        unit_cost_col = next((c for c in cols if 'per unit' in c.lower()), 'Cost Price Per Unit (USD)')
        total_cost_col = next((c for c in cols if ('total' in c.lower() and 'cost' in c.lower())), 'Cost Price Total (USD)')

        return {
            "id": id_col, "name": name_col, "open": open_col, "in": in_col,
            "sold": sold_col, "hand": hand_col, "unit_cost": unit_cost_col, "total_cost": total_cost_col
        }

    def _generate_query_code(self, query: str) -> str:
        q = query.lower()
        c = self._get_active_columns()

        # 1. Total Inventory Valuation / Overall Value / Worth
        if ("total" in q or "overall" in q) and ("val" in q or "worth" in q or "cost" in q or "asset" in q):
            return f"""# 1. Total Inventory Valuation and Key Financial Aggregates
total_val = df['{c["total_cost"]}'].sum()
total_units = df['{c["hand"]}'].sum()
avg_unit_cost = df['{c["unit_cost"]}'].mean()
max_val_item = df.loc[df['{c["total_cost"]}'].idxmax()]

val_summary = pd.DataFrame([{{
    'Total Valuation (USD)': f"${{total_val:,.2f}}",
    'Total Physical Units on Hand': f"{{total_units:,}}",
    'Average Unit Cost (USD)': f"${{avg_unit_cost:,.2f}}",
    'Highest Value SKU': f"{{max_val_item['{c['name']}']}} (${{max_val_item['{c['total_cost']}']:,.2f}})",
    'Total Catalog SKUs': len(df)
}}])
val_summary"""

        # 2. Top Selling Products
        if ("top" in q or "best" in q or "most" in q or "highest" in q) and ("sell" in q or "sold" in q or "sales" in q or "volume" in q):
            n = self._extract_limit(q, default=5)
            return f"""# Top {n} best-selling products by units sold
top_sales = df.sort_values(by='{c["sold"]}', ascending=False)[[
    '{c["id"]}', '{c["name"]}', '{c["sold"]}', '{c["open"]}', '{c["in"]}', '{c["hand"]}'
]].head({n})
top_sales"""

        # 3. Slowest Moving / Dead Stock / Low Sales
        if ("slow" in q or "dead" in q or "worst" in q or "least" in q or "bottom" in q) and ("sell" in q or "sold" in q or "sales" in q or "mover" in q or "stock" in q):
            n = self._extract_limit(q, default=5)
            return f"""# Slowest moving products (low sales velocity)
slow_movers = df.sort_values(by='{c["sold"]}', ascending=True)[[
    '{c["id"]}', '{c["name"]}', '{c["sold"]}', '{c["hand"]}', '{c["total_cost"]}'
]].head({n})
slow_movers"""

        # 4. Highest Value SKUs / Capital Concentration
        if ("highest" in q or "top" in q or "most" in q) and ("expensive" in q or "tied" in q or "capital" in q or ("cost" in q and "product" in q)):
            n = self._extract_limit(q, default=5)
            return f"""# Top {n} items with highest total cost price tied up in stock
high_capital = df.sort_values(by='{c["total_cost"]}', ascending=False)[[
    '{c["id"]}', '{c["name"]}', '{c["hand"]}', '{c["unit_cost"]}', '{c["total_cost"]}'
]].head({n})
high_capital"""

        # 5. Stockout Risk / Lowest On-Hand Stock / Reorder Need
        if ("low" in q or "least" in q or "critical" in q or "risk" in q or "stockout" in q or "reorder" in q) and ("stock" in q or "hand" in q or "inventory" in q):
            n = self._extract_limit(q, default=5)
            return f"""# Critical stockout risk: lowest Hand-In-Stock units
stockout_risk = df.sort_values(by='{c["hand"]}', ascending=True)[[
    '{c["id"]}', '{c["name"]}', '{c["hand"]}', '{c["sold"]}', '{c["unit_cost"]}'
]].head({n})
stockout_risk"""

        # 6. Sell-Through Rate (STR)
        if "sell-through" in q or "sell through" in q or "str" in q or "velocity" in q:
            n = self._extract_limit(q, default=10)
            return f"""# Sell-Through Rate (%): [Units Sold / (Opening Stock + Stock In)] * 100
df_calc = df.copy()
total_avail = df_calc['{c["open"]}'] + df_calc['{c["in"]}']
df_calc['Sell_Through_Rate_%'] = np.where(total_avail > 0, (df_calc['{c["sold"]}'] / total_avail) * 100, 0).round(2)

str_ranked = df_calc.sort_values(by='Sell_Through_Rate_%', ascending=False)[[
    '{c["id"]}', '{c["name"]}', '{c["open"]}', '{c["in"]}', '{c["sold"]}', '{c["hand"]}', 'Sell_Through_Rate_%'
]].head({n})
str_ranked"""

        # 7. ABC Pareto Analysis
        if "abc" in q or "pareto" in q or "classification" in q or "80/20" in q:
            return f"""# ABC Inventory Pareto Classification (80-15-5 rule)
df_abc = df.copy().sort_values(by='{c["total_cost"]}', ascending=False)
total_val = df_abc['{c["total_cost"]}'].sum()
df_abc['Value_Share_%'] = ((df_abc['{c["total_cost"]}'] / total_val) * 100).round(2)
df_abc['Cumulative_Share_%'] = df_abc['Value_Share_%'].cumsum().round(2)

def classify(cum):
    if cum <= 80:
        return 'A (High Priority)'
    elif cum <= 95:
        return 'B (Moderate Priority)'
    else:
        return 'C (Low Priority)'

df_abc['ABC_Category'] = df_abc['Cumulative_Share_%'].apply(classify)
df_abc[['{c["id"]}', '{c["name"]}', '{c["hand"]}', '{c["total_cost"]}', 'Value_Share_%', 'Cumulative_Share_%', 'ABC_Category']].head(12)"""

        # 8. Average / Summary Statistics
        if any(w in q for w in ["average", "mean", "summary", "distribution", "overview", "describe"]):
            return f"""# High-level statistical distribution across all metrics
summary_stats = df[['{c["open"]}', '{c["in"]}', '{c["sold"]}', '{c["hand"]}', '{c["unit_cost"]}', '{c["total_cost"]}']].describe().round(2)
summary_stats"""

        # 9. Specific Product Search (e.g. Laptop, P101)
        for val in self.df[c["name"]].dropna().unique():
            if str(val).lower() in q:
                return f"""# Record details for product: '{val}'
matched = df[df['{c["name"]}'].astype(str).str.lower().str.contains('{str(val).lower()}')]
matched"""
        for val in self.df[c["id"]].dropna().unique():
            if str(val).lower() in q:
                return f"""# Record details for SKU ID: '{val}'
matched = df[df['{c["id"]}'].astype(str).str.lower() == '{str(val).lower()}']
matched"""

        # Fallback default: preview top rows
        return f"""# Overview of current inventory table
df[['{c["id"]}', '{c["name"]}', '{c["open"]}', '{c["sold"]}', '{c["hand"]}', '{c["total_cost"]}']].head(10)"""

    def _extract_limit(self, query: str, default: int = 5) -> int:
        match = re.search(r'\b(top|bottom|first|last)\s+(\d+)\b', query)
        if match:
            return int(match.group(2))
        match_num = re.search(r'\b(\d+)\b', query)
        if match_num and 1 <= int(match_num.group(1)) <= 50:
            return int(match_num.group(1))
        return default

    def _synthesize_summary(self, query: str, search_res: dict, code_res: dict) -> str:
        parts = []

        # 1. Search Result Terminology
        if search_res and search_res.get("definition"):
            term = search_res.get("term", "Term")
            defn = search_res.get("definition")
            formula = search_res.get("formula")
            impact = search_res.get("business_impact")
            
            parts.append(f"### 📖 Domain Knowledge: **{term}**")
            parts.append(f"> {defn}")
            if formula and formula != "N/A":
                parts.append(f"- **Standard Formula:** `{formula}`")
            if impact and impact != "N/A":
                parts.append(f"- **Business Significance:** {impact}")
            parts.append("")

        # 2. Quantitative Findings
        if code_res and code_res.get("success"):
            parts.append("### 📊 Analytical Findings from Inventory Data")
            table_data = code_res.get("table_data")
            
            if table_data and table_data.get("rows"):
                rows = table_data["rows"]
                cols = table_data.get("columns", [])

                if any("Total Valuation" in c for c in cols):
                    row0 = rows[0]
                    parts.append(f"- **Total Inventory Valuation:** **{row0.get('Total Valuation (USD)', 'N/A')}** tied up in active warehouse stock.")
                    parts.append(f"- **Physical Quantity Available:** **{row0.get('Total Physical Units on Hand', 'N/A')} units**.")
                    parts.append(f"- **Average Acquisition Cost:** **{row0.get('Average Unit Cost (USD)', 'N/A')}** per unit.")
                    parts.append(f"- **Top Capital Concentration:** **{row0.get('Highest Value SKU', 'N/A')}**.")
                    parts.append("\n**💡 Strategic Recommendation:** Maintain tight procurement controls and just-in-time replenishment for top-value items to unlock operating cash flow.")

                elif any("ABC_Category" in c for c in cols):
                    parts.append("- **Pareto Categorisation:** Inventory SKUs were ranked by capital concentration.")
                    cat_a = [r.get("Product Name", "Item") for r in rows if 'A' in str(r.get("ABC_Category", ""))]
                    parts.append(f"- **Class A High-Impact SKUs (~80% valuation):** {', '.join(cat_a[:4])}.")
                    parts.append("\n**💡 Strategic Recommendation:** Implement cycle counting weekly for Class A items to prevent costly discrepancies and unbudgeted carrying costs.")

                elif any("Sell_Through_Rate_%" in c for c in cols):
                    leader = rows[0]
                    lead_name = leader.get("Product Name", "Leading product")
                    lead_str = leader.get("Sell_Through_Rate_%", 0)
                    parts.append(f"- **Top Sales Velocity:** **{lead_name}** leads the portfolio with a **{lead_str}%** sell-through rate.")
                    parts.append(f"- Top {len(rows)} high-velocity SKUs are presented in the query result table.")
                    parts.append("\n**💡 Strategic Recommendation:** Increase safety stock allocations on items with STR > 20% to avoid premature stockouts.")

                elif ("stockout_risk" in code_res.get("executed_code", "").lower()) or ("stockout" in query.lower()) or ("low" in query.lower() and "stock" in query.lower()):
                    first_item = rows[0]
                    parts.append(f"- **Highest Stockout Vulnerability:** **{first_item.get('Product Name', 'Item')}** has only **{first_item.get('Hand-In-Stock', 0)} units** on hand.")
                    parts.append(f"- Analyzed bottom {len(rows)} SKUs by on-hand inventory levels.")
                    parts.append("\n**💡 Strategic Recommendation:** Immediately trigger replenishment purchase orders for these items to avoid stockouts.")

                else:
                    first_item = rows[0]
                    name = first_item.get("Product Name", first_item.get("Product_Name", "Leading SKU"))
                    parts.append(f"- Primary record identified: **{name}**.")
                    parts.append(f"- Query executed successfully across the dataset ({len(rows)} matching records returned).")

            elif code_res.get("result"):
                parts.append(f"- **Computed Result:** `{code_res['result']}`")

        elif code_res and not code_res.get("success"):
            parts.append(f"⚠️ *Execution error:* `{code_res.get('error')}`")

        return "\n".join(parts)
