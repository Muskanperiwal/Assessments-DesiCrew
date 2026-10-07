import re
import requests
import json

# Comprehensive domain knowledge base for inventory, supply chain, and retail analytics
INVENTORY_GLOSSARY = {
    "hand-in-stock": {
        "term": "Hand-In-Stock (On-Hand Inventory)",
        "definition": "The exact physical quantity of product units currently available in the warehouse or store ready for immediate order fulfillment or sale. In inventory balancing, Hand-In-Stock = Opening Stock + Stock In - Units Sold.",
        "formula": "Hand-In-Stock = Opening Stock + Purchase/Stock In - Units Sold",
        "business_impact": "Critical for calculating immediate order fulfillment capability and working capital tied up in stock."
    },
    "opening stock": {
        "term": "Opening Stock (Beginning Inventory)",
        "definition": "The quantity of goods available in stock at the beginning of an accounting or reporting cycle. It equals the closing stock of the preceding period.",
        "formula": "Opening Stock = Closing Stock of Previous Period",
        "business_impact": "Establishes the starting baseline for cost of goods and period-over-period inventory turnover."
    },
    "purchase/stock in": {
        "term": "Purchase / Stock In (Inbound Shipments)",
        "definition": "The total volume of newly procured or received inventory added to stock from manufacturers or suppliers during the active reporting period.",
        "formula": "Stock In = Total Units Received from Purchase Orders",
        "business_impact": "Indicates procurement activity and supplier delivery replenishment volume."
    },
    "number of units sold": {
        "term": "Number of Units Sold (Sales Volume)",
        "definition": "The total quantity of units successfully dispatched, purchased, or invoiced by customers across the reporting timeframe.",
        "formula": "Units Sold = Total Customer Demand Fulfilled",
        "business_impact": "Direct measure of sales velocity and consumer demand for specific SKU items."
    },
    "cost price per unit": {
        "term": "Cost Price Per Unit (COGS Unit Cost)",
        "definition": "The direct expense incurred by the business to produce or procure a single unit of the product, including purchase price and associated direct delivery costs.",
        "formula": "Unit Cost = Total Procurement Cost / Quantity Purchased",
        "business_impact": "Determines gross margin potential when evaluated against retail selling price."
    },
    "cost price total": {
        "term": "Cost Price Total (Inventory Valuation)",
        "definition": "The total monetary capital represented by current on-hand inventory, calculated by multiplying current Hand-In-Stock by Cost Price Per Unit.",
        "formula": "Cost Price Total = Hand-In-Stock × Cost Price Per Unit (USD)",
        "business_impact": "Directly reflects working capital trapped in unsold warehouse goods on the balance sheet."
    },
    "sell-through rate": {
        "term": "Sell-Through Rate (STR)",
        "definition": "A key retail metric comparing the amount of inventory sold against the amount of inventory available for sale during the same period.",
        "formula": "Sell-Through Rate (%) = [Number of Units Sold / (Opening Stock + Stock In)] × 100",
        "business_impact": "A high STR (>60-70%) signals strong product-market fit, whereas low STR (<20%) suggests poor demand or overstocking."
    },
    "inventory turnover": {
        "term": "Inventory Turnover Ratio (ITR)",
        "definition": "A ratio showing how many times a company has sold and replaced inventory during a given time period.",
        "formula": "Inventory Turnover = Cost of Goods Sold / Average Inventory Value",
        "business_impact": "Higher turnover signals efficient capital utilization and lower risk of inventory obsolescence."
    },
    "stockout": {
        "term": "Stockout / Stockout Risk",
        "definition": "A condition where available inventory on hand drops to zero or near zero while customer demand continues, leading to lost sales, damaged customer loyalty, and penalty fees.",
        "formula": "Stockout Risk = (Daily Sales Velocity × Supplier Lead Time) > Hand-In-Stock",
        "business_impact": "Can lead to lost revenue and customer churn. High-velocity items with low on-hand stock require immediate safety replenishment."
    },
    "safety stock": {
        "term": "Safety Stock (Buffer Stock)",
        "definition": "A surplus quantity of stock maintained as a cushion to protect against unpredictable spikes in customer demand or unexpected supplier lead time delays.",
        "formula": "Safety Stock = (Max Daily Usage × Max Lead Time) - (Avg Daily Usage × Avg Lead Time)",
        "business_impact": "Prevents catastrophic stockouts while balancing warehouse holding costs."
    },
    "abc analysis": {
        "term": "ABC Inventory Classification (Pareto Analysis)",
        "definition": "An inventory categorisation method based on Pareto's 80/20 rule: Class A represents top ~80% of total valuation (tight control needed), Class B represents ~15%, and Class C represents the remaining ~5% (bulk/low-value items).",
        "formula": "Rank SKUs by Total Value descending; Classify top 80% as A, next 15% as B, remaining 5% as C",
        "business_impact": "Allows warehouse and procurement teams to focus capital and tracking resources on high-value SKUs."
    },
    "reorder point": {
        "term": "Reorder Point (ROP)",
        "definition": "The threshold inventory level that signals the procurement team to initiate a new purchase order before current stock runs out.",
        "formula": "Reorder Point = (Average Daily Demand × Lead Time) + Safety Stock",
        "business_impact": "Automates replenishment triggers and eliminates supply shortages."
    },
    "dead stock": {
        "term": "Dead Stock / Obsolete Inventory",
        "definition": "Goods stored in the warehouse that have experienced zero sales velocity over a prolonged period and are unlikely to be sold at full price.",
        "formula": "Units Sold = 0 while Hand-In-Stock > 0 across reporting intervals",
        "business_impact": "Consumes valuable storage space, incurs ongoing holding costs, and should be liquidated or discounted."
    }
}

class InventorySearchTool:
    """
    Search Tool providing definitions, business context, formulas,
    and external supply chain domain lookups for the Agent.
    """
    def __init__(self):
        self.glossary = INVENTORY_GLOSSARY

    def search(self, query: str) -> dict:
        query_clean = query.strip().lower()
        
        # 1. Direct exact or substring match in glossary
        matched_items = []
        for key, entry in self.glossary.items():
            if key in query_clean or query_clean in key or any(w in query_clean for w in key.split()):
                matched_items.append(entry)

        if matched_items:
            best_match = matched_items[0]
            return {
                "source": "Inventory & Supply Chain Knowledge Base",
                "query": query,
                "term": best_match["term"],
                "definition": best_match["definition"],
                "formula": best_match.get("formula", "N/A"),
                "business_impact": best_match.get("business_impact", "N/A"),
                "all_matches": [m["term"] for m in matched_items]
            }

        # 2. Try DuckDuckGo Instant Answer API for general definitions or context
        try:
            url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1&skip_disambig=1"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                abstract = data.get("AbstractText") or data.get("Definition")
                if abstract:
                    return {
                        "source": "Web Search (DuckDuckGo Instant Answer)",
                        "query": query,
                        "term": data.get("Heading", query),
                        "definition": abstract,
                        "url": data.get("AbstractURL", "")
                    }
        except Exception:
            pass

        # 3. Fallback generic supply chain context
        return {
            "source": "Supply Chain Context Engine",
            "query": query,
            "term": query.title(),
            "definition": f"General operational metric or business parameter related to '{query}' in retail and warehouse inventory management.",
            "note": "For precise SKU-specific figures, see data query analysis."
        }
