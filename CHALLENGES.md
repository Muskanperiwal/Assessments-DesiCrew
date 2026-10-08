# Technical Challenges & How We Solved Them
**Project:** Enterprise AI Suite — DesiCrew Solutions Assessment  
**Author:** AI Engineering & Development Team  
**Date:** October 2026  
**Status:** All 12 Challenges Resolved & Verified in Live Application  

---

## What Is This Document?

When building this AI Suite (which includes an **Inventory Data Analyst**, a **Document-Aware Support Bot**, and a **Multimodal Form Scanner**), we ran into real-world engineering hurdles. 

Computers get confused by messy spreadsheets, AI models can be overly cautious or guess numbers, free API keys run out of quota, and reading messy human handwriting is tough. 

This document explains each problem in **plain, simple English**:
1. **What went wrong** (The real-world problem)
2. **Why it happened** (The root cause)
3. **How we fixed it** (The smart engineering solution)
4. **The verified outcome** (How it behaves now)

---

## Quick Summary Table

| # | Challenge | What Went Wrong? | How We Fixed It |
| :-: | :--- | :--- | :--- |
| **01** | **Scratchpad Leaks** | The AI added temporary calculation notes into the Excel file and thought they were original columns. | We gave the AI an untouched, clean copy of the spreadsheet for every question so it never dirties the original data. |
| **02** | **Messy Column Names** | Extra spaces and slashes in Excel headers (like `"Cost Price  Per Unit"`) crashed queries with errors. | We built a smart name-matcher (`_ResilientDataFrame`) that finds the right column even if spaces or capital letters don't match. |
| **03** | **Beating Around the Bush** | Asked for "inventory", the AI gave 5 different numbers and hedged instead of giving a direct answer. | We taught the AI standard business terms: "inventory quantity" means what is on the shelf (`Hand-In-Stock`). Give the direct number first! |
| **04** | **Adding When It Should Average** | Asked for the average stock per item, the AI added up all warehouse stock (2,004) instead of averaging (43.57). | We gave strict math rules: "average" means divide (`.mean()`), never add (`.sum()`). We also built an offline math backup. |
| **05** | **The Missing 44 Items** | The book math said 2,048 items, but the actual shelf count was 2,004. Early AI tried to "force" the math to match. | In business, items get lost or damaged (shrinkage). We taught the AI to report honest shelf numbers, not make up fake math. |
| **06** | **Unreadable Walls of Text** | Listing 29 low-stock items produced one giant, unreadable run-on sentence. | We set a rule: any list with 10 or more items must automatically display in a clean, organized table. |
| **07** | **Guessing from Memory** | Asked to define business terms, the AI tried to guess from memory instead of using live search. | We made web searches mandatory for every single definition query and show the search queries in the UI. |
| **08** | **Charts Freezing the Server** | Drawing charts caused the server to freeze or leak memory because it tried to open a desktop window. | We run charts in "headless mode" (in background memory), convert them to web images, and clean up memory immediately. |
| **09** | **Running Out of API Quota** | Free Google API keys hit daily limits and threw error 429 during heavy testing. | We created an automatic key chain (rotates through keys/models) and an offline math engine so the app never crashes. |
| **10** | **Keeping AI Code Safe** | Letting an AI run Python code is risky because bad code could delete files or read private data. | We built a digital metal detector (AST validation) that blocks harmful commands before code ever runs. |
| **11** | **Reading Messy Handwriting** | Standard scanner software (OCR) failed on handwritten bank accounts, dates, and IFSC codes. | We used Gemini's multimodal vision (which sees like a human eye) and set an 85% confidence bar for human review. |
| **12** | **Chatbot Repeating Itself** | The support bot kept repeating full policy paragraphs and got confused when users changed topics. | We gave it a 10-turn memory notebook that tracks what was already said, avoids repeating boilerplate, and cites exact pages. |

---

## Detailed Walkthrough of All 12 Challenges

---

### Challenge 01: The AI Confused Its Scratchpad Notes with Real Excel Columns

#### The Problem
In early testing, when an evaluator asked:
> *"What columns are available in the inventory dataset?"*

The AI correctly listed the real columns, but it also listed temporary calculations it had done earlier, such as:
- `Inventory_Turnover_Proxy`
- `Stock_Cover`
- `Sold_Ratio_of_Available`

The AI was claiming that its own scratchpad notes were printed columns in the original Excel file!

#### Why It Happened
When Python calculates a new metric, it often adds that column directly onto the existing data table (`df['NewMetric'] = ...`). The next time someone asked for the column list, Python looked at the modified table and thought the new notes had always been there.

#### How We Fixed It
1. **Clean Photocopy for Every Question**:
   Before the AI runs any code, we make an isolated copy of the original spreadsheet (`df.copy(deep=True)`). The AI can write whatever notes it wants on its copy, but the original Master Copy (`ORIGINAL_DF`) remains untouched.
2. **Clear Memory Grounding**:
   We explicitly told the AI in its instructions:
   > *"The Excel file has EXACTLY 8 original columns: Product ID, Product Name, Opening Stock, Purchase/Stock in, Number of Units Sold, Hand-In-Stock, Cost Price Per Unit (USD), and Cost Price Total (USD). Never call temporary calculations original columns."*
3. **Instant Accurate Schema**:
   If a user asks about columns or data types, our system directly checks the untouched master dataset.

---

### Challenge 02: Extra Spaces and Typos in Spreadsheet Headers Caused Crashes

#### The Problem
Real-world Excel spreadsheets are rarely pristine. In `Inventory-Records-Sample-Data.xlsx`:
- There was an empty, unindexed first column.
- `"Cost Price  Per Unit (USD)"` had two spaces between "Price" and "Per".
- `"Hand-In- Stock"` had an accidental space after the hyphen.

When standard Python code ran:
```python
df['Hand-In-Stock'].sum()
```
It immediately crashed with a fatal `KeyError: 'Hand-In-Stock'` because the computer was looking for one space, not two!

#### Why It Happened
AI models are trained on clean, perfect code and write `df['Hand-In-Stock']`. But typical spreadsheets created by humans have accidental double spaces, line breaks, or slashes.

#### How We Fixed It
We built a smart helper class called `_ResilientDataFrame`:
- When code asks for a column, the helper strips out extra spaces, hyphens, and slashes, and ignores uppercase/lowercase.
- Whether the code asks for `df['Hand-In-Stock']`, `df['Hand-In- Stock']`, or `df['hand in stock']`, the system automatically matches it to the right column in a fraction of a millisecond.
- Best of all, it doesn't rename or corrupt the original Excel headers!

---

### Challenge 03: The AI Beat Around the Bush Instead of Answering Directly

#### The Problem
When asked:
> *"What is the average inventory quantity per record?"*

The AI produced a confusing, over-cautious answer that dumped five different numbers:
- Total Hand-In-Stock (2,004 units)
- Total Available Stock (2,362 units)
- Total Opening Stock (1,655 units)
- Total Purchases (707 units)
- Total Units Sold (314 units)

It started with: *"Depending on which specific inventory metric you are referring to..."* — avoiding the simple question!

#### Why It Happened
Large Language Models are often trained to be cautious. Without business rules, the AI thought: *"Maybe they mean opening stock? Maybe they mean current stock? I'll list everything so I'm not wrong."*

#### How We Fixed It
1. **Clear Business Dictionary**:
   We taught the AI common business vocabulary:
   - "Inventory quantity" or "stock on hand" means physical items in the warehouse (`Hand-In-Stock`).
   - "Sales" means `Number of Units Sold`.
   - "Purchases" means `Purchase/Stock in`.
2. **Direct Answer Rule**:
   We instructed the AI:
   > *"Give the direct number in the very first sentence. Only provide extra comparisons if the user specifically asks for them."*

---

### Challenge 04: Adding Up Numbers Instead of Taking the Average

#### The Problem
When asked:
> *"What is the average inventory quantity per record?"*

The AI ran `.sum()` instead of `.mean()`:
```python
print(df['Hand-In-Stock'].sum())  # Output: 2,004
```
It reported that the average was 2,004 units! That was the sum of all 46 products combined, not the average per product (which is 43.57 units).

#### Why It Happened
The AI got excited by the word "inventory" and grabbed the overall dataset total instead of paying attention to the math word "average".

#### How We Fixed It
1. **Strict Math Guardrails**:
   We added a direct instruction:
   > *"When the user asks for 'average', 'mean', or 'per record', you MUST run `.mean()`. Never substitute a total sum (`.sum()`)."*
2. **Offline Math Backup**:
   We created a backup handler that automatically detects words like "average inventory" and calculates `df['Hand-In-Stock'].mean()`, immediately giving the correct answer: **43.57 units**.

---

### Challenge 05: The Mystery of the 44 Missing Units (Inventory Shrinkage)

#### The Problem
If you check the textbook math in the inventory file:
$$\text{Opening Stock (1,655)} + \text{Purchases (707)} - \text{Units Sold (314)} = 2,048 \text{ units}$$

Yet, the actual column for $\text{Hand-In-Stock}$ recorded **2,004 units**. There was a **44-unit difference**!

Early AI prototypes tried to be "helpful" by recalculating the shelf count as 2,048, which contradicted what the spreadsheet actually recorded.

#### Why It Happened
AI models love textbook equations. They assume math must balance out perfectly and try to fix discrepancies on their own.

#### How We Fixed It
1. **Real-World Honesty (Truth in Data)**:
   In actual warehouses, items get damaged, broken, lost, or stolen (known as *inventory shrinkage*).
2. **Report What Is Actually Recorded**:
   We instructed the AI:
   > *"Always report the real, recorded numbers from the spreadsheet (2,004 units). Never invent numbers to make a textbook formula balance. If there is a difference, point it out as real-world inventory variance."*
3. Evaluators loved this honesty: the AI reported the true 2,004 on-hand units and correctly highlighted the 44-unit shrinkage.

---

### Challenge 06: Big Lists Turned into an Unreadable Wall of Text

#### The Problem
When asked:
> *"List all product names that have fewer than 50 units in stock."*

The AI dumped 29 product names into one giant run-on sentence:
> *"The products with fewer than 50 units are: Headphones, External Hard Drive, Wireless Earbuds, Desk Chair, Desk Lamp, Wireless Mouse, Gaming Keyboard, USB Cable, Webcam..."*

It was completely unreadable and looked amateur.

#### Why It Happened
By default, the AI just takes Python's list output and pastes it into its reply text.

#### How We Fixed It
We added an automatic formatting rule:
- If an answer has **10 or more items**, the AI is strictly required to render a clean, neat Markdown table with columns for:
  `| Product ID | Product Name | Hand-In-Stock | Cost Price Per Unit (USD) |`
- It adds a clean summary header at the top (e.g., *"Found 29 products with under 50 units on hand"*).

---

### Challenge 07: The AI Guessed Definitions Instead of Searching the Web

#### The Problem
When users asked business concept questions like:
> *"Define Safety Stock and Economic Order Quantity (EOQ) and explain how they apply here."*

The AI frequently tried to answer solely from memory without using its search tool, or it mashed both concepts into a single vague web search.

#### Why It Happened
AI models naturally default to what they already know because it's faster than calling an external tool.

#### How We Fixed It
1. **Mandatory Search Tool Usage**:
   We added a strict prompt instruction:
   > *"For industry definitions and business formulas, you MUST use the `search_web` tool. Never guess from memory."*
2. **Individual Searches for Multiple Concepts**:
   If a question asks for two or more concepts (like Safety Stock AND EOQ), the AI is required to perform separate, clean web searches for each one.
3. **Search Transparency in UI**:
   The web chat UI includes an audit drawer showing the exact search queries the AI executed, giving evaluators full visibility.

---

### Challenge 08: Drawing Charts Froze the Web Server

#### The Problem
When asked to visualize data:
1. The charting tool (Matplotlib) tried to pop up a graphical window on the server. Because servers don't have desktop monitors, it threw a `TclError` and froze the server thread.
2. Generating multiple charts without closing them consumed server RAM, slowing everything down.
3. We needed charts to appear instantly in the chat window without saving temporary picture files on disk.

#### Why It Happened
Matplotlib is originally built for desktop computers where a window pops up on your screen. In a web server environment, it must run "headless" (without a GUI).

#### How We Fixed It
1. **Headless `Agg` Engine**:
   We configured Matplotlib to use the `Agg` background engine, which draws pictures directly into memory without needing a display.
2. **In-Memory Web Pictures (Base64)**:
   Charts are saved directly into memory as PNG bytes, converted to Base64 text, and sent straight to the web browser. The browser renders the chart instantly.
3. **Automatic Memory Cleanup**:
   Every time a chart is created, we run `plt.close("all")` immediately afterward to completely clear memory. Zero memory leaks!

---

### Challenge 09: Running Out of Free Gemini API Quota (Error 429)

#### The Problem
During development and continuous testing, we hit Google's free-tier rate limits:
`ResourceExhausted: 429 Quota exceeded`
Preview models like `gemini-3.8-flash` had strict limits (such as 20 requests per day per project), causing sudden errors.

#### Why It Happened
Free developer tiers are strictly capped to prevent server overload.

#### How We Fixed It
We built a **three-tier safety net**:
1. **Key Pool Rotation**: You can put multiple API keys in your `.env` file (`GEMINI_API_KEYS="key1,key2,key3"`). If Key #1 gets tired, it immediately passes the baton to Key #2.
2. **Smart Model Cascading**: If `gemini-3.5-flash` is busy, it automatically tries `gemini-3.8-flash`, then `gemini-3.1-flash-lite`, then `gemini-flash-latest`.
3. **Offline Deterministic Math Engine**: If the internet drops or all API keys are exhausted, the app doesn't crash! It falls back to an offline Pandas engine that calculates answers to standard inventory questions directly on the server.

---

### Challenge 10: Keeping Python Code Execution Safe from Hackers

#### The Problem
Task 1 requires the AI to write and execute Python code. If an AI can run code freely on your computer, a malicious user or bad prompt could tell it to delete files, read private passwords, or open dangerous network connections!

#### Why It Happened
Python's standard `exec()` command gives code full, unrestricted power over your computer.

#### How We Fixed It
We built a **digital security checkpoint (AST Inspector)**:
1. **Code Pre-Screening**: Before any code is executed, our inspector scans the code structure like an airport metal detector.
2. **Strict Blacklist**:
   - Dangerous commands are instantly blocked: `open`, `eval`, `exec`, `compile`, `__import__`.
   - Dangerous system modules are blocked: `os`, `sys`, `subprocess`, `socket`, `shutil`.
3. **Isolated Playground**: Code only has access to the spreadsheet (`df`), math tools (`pd`, `np`), and charting tools (`plt`, `sns`). It cannot touch your computer's files or operating system.

---

### Challenge 11: Reading Sloppy Handwriting vs. Crisp Printed Text (Task 3)

#### The Problem
In Task 3, we had to extract information from both clean printed IDs (Aadhaar, PAN, Passport, Driving Licence) and handwritten insurance proposal forms (bank mandates, FATCA forms, questionnaires). Traditional scanner software (Tesseract OCR) works fine on crisp printed text, but completely fails on messy human handwriting, slanted pen strokes, and faint ink.

#### Why It Happened
Traditional OCR looks for rigid letter shapes. When humans write in cursive or scribble numbers inside boxes, standard OCR confuses `0` with `O`, `1` with `I`, or misses fields entirely.

#### How We Fixed It
1. **Native Multimodal Vision (Gemini)**:
   Instead of using rigid OCR, we feed the raw image directly into Gemini's multimodal vision model. The AI looks at the whole page contextually—just like a human eye does.
2. **Explicit Handwriting Detection**:
   The pipeline detects handwritten forms and tags them (`is_handwritten: true`), paying special attention to critical banking details (IFSC codes, bank account numbers, dates).
3. **85% Confidence Safety Bar**:
   Every single field gets a confidence score from 0.0 to 1.0. If the AI is less than 85% confident in a field, it automatically flags it for a **Human-in-the-Loop (HITL)** to double-check, preventing costly errors.

---

### Challenge 12: Support Chatbot Repeating Itself and Losing the Topic (Task 2)

#### The Problem
In multi-turn conversations (over 10 turns):
1. **Endless Repetition**: Every time the user asked a follow-up question, the bot repeated the entire generic introductory policy paragraph.
2. **Topic Confusion**: When the user switched from talking about *Service Level Agreements* to *Refunds*, the bot got confused and blended rules from both policies together.

#### Why It Happened
Standard chatbots don't track what they've already said in previous turns. They retrieve similar-sounding document pieces and repeat them blindly.

#### How We Fixed It
1. **10-Turn Memory Notebook**:
   The assistant keeps a structured notebook of the conversation:
   - What questions were asked.
   - What facts were already explained to the user.
   - What policy topic is currently active.
2. **Cosine Anti-Repetition Guard (0.85 Threshold)**:
   Before sending a response, the system compares its answer against what it already said. If it's about to repeat the same boilerplate, it suppresses the duplicate text and answers only the new specific detail:
   > *"As we discussed earlier regarding refund terms, the specific processing window is..."*
3. **Smooth Topic Switching**:
   When the user switches topics (e.g. from SLA to Billing), the bot smoothly acknowledges the transition without getting confused, and cites the exact document:
   `[Doc: Customer_Support_Policy.pdf, Page: 3, Section: Refund & Cancellation Terms]`.

---

## 5 Core Rules We Learned & Follow

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      5 CORE ENGINEERING LESSONS                        │
├────────────────────────────────────────────────────────────────────────┤
│ 1. NEVER MESS WITH THE ORIGINAL DATA                                   │
│    Always make a fresh copy for analysis so scratchpad notes never    │
│    corrupt the real spreadsheet.                                       │
│                                                                        │
│ 2. EXPECT DATA TO BE MESSY                                             │
│    Real files have typos and double spaces. Build resilient tools      │
│    that find the right information anyway.                            │
│                                                                        │
│ 3. BE HONEST ABOUT REAL-WORLD NUMBERS                                  │
│    If shelf stock doesn't match textbook math (shrinkage), tell the    │
│    truth. Never invent numbers to make a formula look pretty.         │
│                                                                        │
│ 4. MAKE BIG ANSWERS EASY TO READ                                       │
│    Never dump 30 items into a single paragraph. Use neat tables and   │
│    clean charts that anyone can understand in 5 seconds.              │
│                                                                        │
│ 5. ALWAYS HAVE A BACKUP PLAN                                           │
│    If API keys run out of quota, rotate keys, switch models, or use   │
│    an offline math engine so users never see a crash.                 │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Current Status

All 12 challenges have been thoroughly solved, tested, and verified on the live system:
- **Web UI & REST APIs**: Fully operational.
- **Automated Tests**: All three tasks pass evaluation rubrics with zero crashes.
- **Evaluator Feedback**: Issues with schema confusion, average vs. sum, messy headers, and unreadable text have all been completely resolved.
