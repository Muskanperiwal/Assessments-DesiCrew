"""Pandas execution, chart capture, and ready-made inventory analyses for Task 1."""
import base64
import io
import sys

import numpy as np
import pandas as pd


def _plot_modules():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns
    return plt, sns


def _fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor="white")
    plt, _sns = _plot_modules()
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _collect_charts() -> list:
    try:
        plt, _sns = _plot_modules()
    except ImportError:
        return []
    images = []
    for num in list(plt.get_fignums()):
        fig = plt.figure(num)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor="white")
        images.append(base64.b64encode(buf.getvalue()).decode("ascii"))
    plt.close("all")
    return images


def json_records(frame: pd.DataFrame) -> list:
    records = []
    for row in frame.itertuples(index=False):
        item = {}
        for col, val in zip(frame.columns, row):
            if pd.isna(val):
                item[col] = None
            elif isinstance(val, (np.integer,)):
                item[col] = int(val)
            elif isinstance(val, (np.floating,)):
                item[col] = None if np.isnan(val) else float(val)
            elif isinstance(val, (int, float, str)):
                item[col] = val
            else:
                item[col] = str(val)
        records.append(item)
    return records


def markdown_table(frame: pd.DataFrame, columns: list, limit: int = 8) -> str:
    present = [c for c in columns if c in frame.columns]
    sub = frame[present].head(limit)
    labels = {
        "stock_to_sales": "Stock / sales",
        "sell_through": "Sell-through %",
        "abc": "Class",
        "share_pct": "Share %",
    }
    headers = [labels.get(c, c) for c in present]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in sub.itertuples(index=False):
        cells = []
        for col, val in zip(present, row):
            if pd.isna(val):
                cells.append("—")
            elif col in ("Cost Price Total (USD)", "Cost Price Per Unit (USD)") and isinstance(val, (int, float, np.number)):
                cells.append(f"${float(val):,.0f}")
            elif isinstance(val, float):
                cells.append(f"{val:,.2f}")
            else:
                cells.append(str(val).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def run_user_code(df: pd.DataFrame, code: str) -> dict:
    """Run analyst code with df, pd, np, and plotting libraries when installed."""
    code_lines = [line for line in code.strip().split("\n") if not line.strip().startswith("```")]
    clean_code = "\n".join(code_lines).strip()
    if not clean_code:
        return {"ok": False, "output": "No Python code provided.", "charts": [], "code": ""}

    local_env = {"df": df, "pd": pd, "np": np}
    try:
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        local_env["plt"] = plt
        local_env["sns"] = sns
    except ImportError:
        plt = None

    stdout_buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        lines = clean_code.split("\n")
        if lines and not lines[-1].startswith((" ", "\t")):
            last_line = lines[-1].strip()
            if last_line and not (
                last_line.startswith("print")
                or "=" in last_line
                or last_line.startswith(("import", "def ", "for ", "if ", "while ", "with ", "class "))
            ):
                lines[-1] = f"__res__ = ({last_line})\nif __res__ is not None: print(__res__)"
                clean_code = "\n".join(lines)
        exec(clean_code, local_env, local_env)
        output = stdout_buf.getvalue().strip()
        charts = _collect_charts()
        if not output and charts:
            output = f"Rendered {len(charts)} chart(s)."
        elif not output:
            output = "Execution completed successfully with no output."
        return {"ok": True, "output": output, "charts": charts, "code": clean_code}
    except Exception as exc:
        try:
            if plt is not None:
                plt.close("all")
        except Exception:
            pass
        return {
            "ok": False,
            "output": f"Python Execution Error: {type(exc).__name__}: {exc}",
            "charts": [],
            "code": clean_code,
        }
    finally:
        sys.stdout = old_stdout


def _chart_or_none(builder):
    try:
        return builder()
    except Exception:
        return None


def insight_low_stock(df: pd.DataFrame) -> dict:
    work = df.copy()
    sold = work["Number of Units Sold"].replace(0, np.nan)
    work["stock_to_sales"] = (work["Hand-In-Stock"] / sold).round(2)
    view = work.nsmallest(8, "Hand-In-Stock")
    urgent = int((work["stock_to_sales"] < 1).sum())
    lowest = work.loc[work["Hand-In-Stock"].idxmin()]

    def draw():
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        long = view.melt(
            id_vars=["Product Name"],
            value_vars=["Hand-In-Stock", "Number of Units Sold"],
            var_name="Measure",
            value_name="Units",
        )
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        sns.barplot(data=long, y="Product Name", x="Units", hue="Measure", ax=ax, palette=["#0f766e", "#d97706"])
        ax.set_title("Thinnest on-hand stock versus units sold")
        ax.set_xlabel("Units")
        fig.tight_layout()
        return _fig_b64(fig)

    reply = (
        "### Replenishment priority\n\n"
        f"**{lowest['Product Name']}** ({lowest['Product ID']}) is the thinnest position: "
        f"**{int(lowest['Hand-In-Stock'])}** units on hand after **{int(lowest['Number of Units Sold'])}** sold.\n\n"
        f"**{urgent}** SKUs have already sold more units than they have left on hand.\n\n"
        + markdown_table(view, ["Product ID", "Product Name", "Hand-In-Stock", "Number of Units Sold", "stock_to_sales"])
        + "\n\nTeal bars are units still on hand. Amber bars are units sold. "
        "Where amber is longer, raise a purchase order before the next cycle."
    )
    return {
        "question": "Which items need replenishment first?",
        "reply": reply,
        "charts": [c for c in [_chart_or_none(draw)] if c],
        "code_executed": "view = df.nsmallest(8, 'Hand-In-Stock')\nsns.barplot(... Hand-In-Stock vs Number of Units Sold ...)",
    }


def insight_top_sellers(df: pd.DataFrame) -> dict:
    view = df.nlargest(8, "Number of Units Sold")
    leader = view.iloc[0]
    total_sold = int(df["Number of Units Sold"].sum())
    top_share = 100 * float(view["Number of Units Sold"].sum()) / total_sold if total_sold else 0

    def draw():
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        sns.barplot(data=view, y="Product Name", x="Number of Units Sold", color="#0f766e", ax=ax)
        ax.set_title("Top products by units sold")
        fig.tight_layout()
        return _fig_b64(fig)

    reply = (
        "### Top sellers\n\n"
        f"**{leader['Product Name']}** leads with **{int(leader['Number of Units Sold'])}** units sold. "
        f"The top 8 SKUs account for **{top_share:.0f}%** of units sold in this catalog "
        f"({total_sold:,} units overall).\n\n"
        + markdown_table(view, ["Product ID", "Product Name", "Number of Units Sold", "Hand-In-Stock", "Cost Price Total (USD)"])
        + "\n\nKeep supply continuous on these SKUs. A stockout here moves more revenue than a stockout on the long tail."
    )
    return {
        "question": "Which products sell the most units?",
        "reply": reply,
        "charts": [c for c in [_chart_or_none(draw)] if c],
        "code_executed": "top = df.nlargest(8, 'Number of Units Sold')\nsns.barplot(data=top, y='Product Name', x='Number of Units Sold')",
    }


def insight_abc(df: pd.DataFrame) -> dict:
    work = df.sort_values("Cost Price Total (USD)", ascending=False).copy()
    total = float(work["Cost Price Total (USD)"].sum()) or 1.0
    work["share_pct"] = (work["Cost Price Total (USD)"] / total * 100).round(1)
    work["cum"] = work["share_pct"].cumsum()

    def classify(cum):
        if cum <= 80:
            return "A"
        if cum <= 95:
            return "B"
        return "C"

    work["abc"] = work["cum"].apply(classify)
    counts = work["abc"].value_counts().to_dict()
    a_value = float(work.loc[work["abc"] == "A", "Cost Price Total (USD)"].sum())
    view = work.head(8)

    def draw():
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        plot_df = work.head(12).reset_index(drop=True)
        fig, ax1 = plt.subplots(figsize=(8.2, 4.6))
        sns.barplot(data=plot_df, x=plot_df.index, y="Cost Price Total (USD)", color="#0f766e", ax=ax1)
        ax1.set_xticks(range(len(plot_df)))
        ax1.set_xticklabels(plot_df["Product Name"], rotation=35, ha="right")
        ax1.set_xlabel("")
        ax1.set_ylabel("Inventory value (USD)")
        ax2 = ax1.twinx()
        ax2.plot(range(len(plot_df)), plot_df["cum"], color="#b45309", marker="o", linewidth=2)
        ax2.set_ylabel("Cumulative share %")
        ax2.set_ylim(0, 105)
        ax1.set_title("ABC value concentration")
        fig.tight_layout()
        return _fig_b64(fig)

    reply = (
        "### ABC valuation\n\n"
        f"Catalog value is **${total:,.0f}**. Class A (about 80% of value) is "
        f"**{counts.get('A', 0)}** SKUs worth **${a_value:,.0f}**. "
        f"Class B is **{counts.get('B', 0)}** SKUs and class C is **{counts.get('C', 0)}**.\n\n"
        + markdown_table(view, ["Product Name", "Cost Price Total (USD)", "share_pct", "abc"])
        + "\n\nCount class A more often and review its suppliers first. Class C can sit on a lighter reorder cycle."
    )
    return {
        "question": "How is inventory value concentrated (ABC)?",
        "reply": reply,
        "charts": [c for c in [_chart_or_none(draw)] if c],
        "code_executed": "share = df['Cost Price Total (USD)'] / df['Cost Price Total (USD)'].sum()\n# A until 80% cumulative, B until 95%, else C",
    }


def insight_sell_through(df: pd.DataFrame) -> dict:
    work = df.copy()
    inbound = (work["Opening Stock"] + work["Purchase/ Stock in"]).replace(0, np.nan)
    work["sell_through"] = (work["Number of Units Sold"] / inbound * 100).round(1)
    view = work.sort_values("sell_through", ascending=False).head(8)
    fastest = view.iloc[0]
    slow = work.sort_values("sell_through", ascending=True).iloc[0]

    def draw():
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        sns.barplot(data=view, y="Product Name", x="sell_through", color="#0f766e", ax=ax)
        ax.set_xlabel("Sell-through %")
        ax.set_title("Highest sell-through rates")
        fig.tight_layout()
        return _fig_b64(fig)

    reply = (
        "### Sell-through\n\n"
        "Sell-through is units sold divided by opening stock plus purchases.\n\n"
        f"**{fastest['Product Name']}** is the fastest at **{fastest['sell_through']:.1f}%**. "
        f"**{slow['Product Name']}** is the slowest at **{float(slow['sell_through']):.1f}%**.\n\n"
        + markdown_table(view, ["Product Name", "Opening Stock", "Purchase/ Stock in", "Number of Units Sold", "sell_through"])
        + "\n\nHigh sell-through with low stock is a replenishment signal. Low sell-through with high stock is cash sitting on the shelf."
    )
    return {
        "question": "Which SKUs sell through fastest?",
        "reply": reply,
        "charts": [c for c in [_chart_or_none(draw)] if c],
        "code_executed": "sell_through = df['Number of Units Sold'] / (df['Opening Stock'] + df['Purchase/ Stock in']) * 100",
    }


def insight_price_velocity(df: pd.DataFrame) -> dict:
    corr = float(df["Cost Price Per Unit (USD)"].corr(df["Number of Units Sold"]))
    direction = "higher-priced SKUs tend to sell fewer units" if corr < -0.15 else (
        "higher-priced SKUs tend to sell more units" if corr > 0.15 else "unit price and units sold move independently"
    )

    def draw():
        plt, sns = _plot_modules()
        plt.close("all")
        sns.set_theme(style="whitegrid")
        fig, ax = plt.subplots(figsize=(8.2, 4.6))
        sns.scatterplot(
            data=df,
            x="Cost Price Per Unit (USD)",
            y="Number of Units Sold",
            size="Cost Price Total (USD)",
            hue="Cost Price Total (USD)",
            palette="viridis",
            ax=ax,
            legend=False,
        )
        ax.set_title("Unit price versus units sold")
        fig.tight_layout()
        return _fig_b64(fig)

    pricey = df.nlargest(5, "Cost Price Per Unit (USD)")
    reply = (
        "### Price versus velocity\n\n"
        f"Correlation between unit cost and units sold is **{corr:.2f}**, so {direction}. "
        "Bubble size follows total inventory value.\n\n"
        + markdown_table(pricey, ["Product Name", "Cost Price Per Unit (USD)", "Number of Units Sold", "Hand-In-Stock"])
        + "\n\nExpensive slow movers deserve a tighter buy plan. Cheap fast movers deserve a higher safety stock."
    )
    return {
        "question": "How does unit price relate to units sold?",
        "reply": reply,
        "charts": [c for c in [_chart_or_none(draw)] if c],
        "code_executed": "sns.scatterplot(data=df, x='Cost Price Per Unit (USD)', y='Number of Units Sold', size='Cost Price Total (USD)')",
    }


INSIGHT_BUILDERS = {
    "low_stock": insight_low_stock,
    "top_sellers": insight_top_sellers,
    "abc": insight_abc,
    "sell_through": insight_sell_through,
    "price_velocity": insight_price_velocity,
}
