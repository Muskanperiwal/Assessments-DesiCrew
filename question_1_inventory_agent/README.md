# Question 1: Excel Inventory Intelligence Agent

An agentic AI assistant built to query, analyze, and interpret Excel inventory datasets with automated code execution, domain knowledge search, and plain-English executive summarization.

---

## 🌟 Key Features & Capabilities

1. **Automated Python / Pandas Code Execution**:
   - Understands natural language queries and automatically synthesizes Python code targeting the active dataset DataFrame (`df`).
   - Safely executes scripts in a dedicated execution sandbox, extracting metrics, aggregates, and filtering tables.
   - Transparently presents the exact code executed alongside output data tables.

2. **Domain Search Tool & Terminology Lookup**:
   - Integrates a specialized supply chain & inventory knowledge engine with definitions, formulas, and business impact for terms like:
     - *Hand-In-Stock (On-Hand Inventory)*
     - *Sell-Through Rate (STR)*
     - *Inventory Turnover Ratio*
     - *Safety Stock & Buffer Stock*
     - *ABC Pareto Classification (80/20 Rule)*
     - *Stockout Risk & Reorder Points*
   - Includes fallback live web search (DuckDuckGo Instant Answer API) for broad queries.

3. **Plain-English Executive Summaries**:
   - Distills raw quantitative outputs into concise, executive-ready insights.
   - Provides strategic recommendations (e.g., procurement alerts, stockout warnings, capital concentration risks).

4. **Interactive Chat Interface**:
   - Modern, responsive web UI with dark mode, interactive data tables, code inspector, and typing animations.
   - Pre-configured prompt chips for rapid testing.
   - Custom Excel dataset upload support (`.xlsx`, `.xls`) with automatic header discovery and schema normalization.
   - Interactive Python playground modal for running custom queries directly.

---

## 🏗️ Architecture & Project Structure

```
question_1_inventory_agent/
│
├── app.py                 # Flask REST backend and static file server
├── agent.py               # InventoryAgent orchestrator (reasoning, code gen, search dispatch)
├── inventory_loader.py    # Excel parser with auto-header discovery & column normalization
├── search_engine.py       # Domain knowledge search engine and glossary
├── code_executor.py       # Sandboxed Python/Pandas execution engine with table formatting
├── static/
│   ├── index.html         # Modern web application UI
│   ├── styles.css         # Design system & dark theme styling
│   └── app.js             # Reactive frontend controller
└── README.md              # Project documentation
```

---

## 🚀 How to Run Locally

### 1. Prerequisites
- Python 3.10+ installed
- Virtual environment (`.venv`) activated

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the Agent Web Server
```bash
python question_1_inventory_agent/app.py
```

### 4. Open in Browser
Navigate to:
```
http://127.0.0.1:5000
```

---

## 💡 Example Queries to Test

- **Valuation:** `"What is the total value of current inventory on hand?"`
- **Sales Velocity:** `"Which are our top 5 best-selling products by units sold?"`
- **Definition & Formula:** `"What does Hand-In-Stock mean and how is it calculated?"`
- **Risk Analysis:** `"Which products have the lowest on-hand stock and risk a stockout?"`
- **Advanced Metric:** `"Calculate the Sell-Through Rate (STR) for all products and show the top 10."`
- **Pareto Classification:** `"Perform an ABC Pareto classification based on inventory total cost."`
- **Specific SKU Search:** `"Tell me about the Laptop record."`
