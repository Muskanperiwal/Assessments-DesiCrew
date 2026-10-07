# Question 3: Document Classification & Field Extraction Pipeline

A machine-learning and heuristic pipeline designed for **10 mixed identity proofs and insurance proposal forms**, extracting required statutory and handwritten fields, computing field-level confidence scores, and flagging low-confidence values for Human-in-the-Loop (HITL) review.

---

## 📋 Required Extraction Targets & Pipeline Results

| Document Name | Classified Type | Nature | Target Fields Extracted | Status |
|---|---|---|---|---|
| `Aadhar.png` | **Aadhaar Card** | Printed | Aadhaar Number, Full Name, DOB, Address | ✅ 100% Accepted |
| `ID.png` | **PAN Card** | Printed | PAN Number, Full Name, Father's Name, DOB | ✅ 100% Accepted |
| `ChatGPT Image May 2, 2026, 03_43_11 PM.png` | **Driving Licence** | Printed | DL Number, Name, Date of Issue, Valid Till | ✅ 100% Accepted |
| `ChatGPT Image May 2, 2026, 03_52_54 PM.png` | **Passport** | Printed | Passport Number, DOB, Date of Expiry, MRZ Line 2 | ✅ 100% Accepted |
| `ECS.jpeg` | **NACH / ECS Mandate** | Handwritten | Bank Account Number, IFSC Code, Bank Name, Amount, Frequency | ✅ High Conf / Verified |
| `Fatca.jpeg` | **FATCA Annexure Form** | Handwritten | Policy Number, TIN / PAN, Father's Name, Place of Birth, Nationality | ⚠️ Place Flagged (<0.85) |
| `Illustration.jpeg` | **Benefit Illustration Declaration** | Handwritten | Application Number, Policyholder Name, Date, Place | ⚠️ Date & Place Flagged (<0.85) |
| `Moral.jpeg` | **Moral Hazard Questionnaire** | Handwritten | Application Number, Name of Life Assured, Nominee Relationship, Date, Place | ⚠️ Date & Place Flagged (<0.85) |
| `split.jpeg` | **Multiple Policies Consent Form** | Handwritten | Proposer Name, Reason for Multiple Policies, Date, Place | ⚠️ Place Flagged (<0.85) |
| `suitability.jpeg` | **Suitability Profiler Declaration** | Handwritten | Application Number, Name of Life Assured, Name of Agent/SP, Date, Place | ⚠️ Date & Place Flagged (<0.85) |

---

## 🎯 Deliverables Produced

1. **Structured JSON Output:**
   - Saved at: [`outputs/extractions.json`](file:///c:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/question_3_document_pipeline/outputs/extractions.json)
   - Contains classified document types, classification confidences, and granular field extraction dictionaries with values, methods, and individual field confidence scores.

2. **Confidence Score Per Field:**
   - Granular scoring (`0.00` to `1.00`) per individual field based on character contour legibility, syntax regularities, checksum validity (Aadhaar Verhoeff, PAN regex, MRZ line parity), and box stroke segmentation.

3. **Human Review Flagging Report:**
   - Saved at: [`outputs/flagging_report.json`](file:///c:/Users/nikhil.singh01_livsp/Desktop/muskan%20periwal/question_3_document_pipeline/outputs/flagging_report.json)
   - Lists the **8 fields** falling below the **0.85** confidence threshold with specific flagging reasons and recommended reviewer actions.

4. **Technical Note: Handwritten vs. Printed Text Handling & Failure Analysis:**
   - Detailed below and embedded directly within the interactive dashboard.

---

## ⚖️ Confidence Threshold Rationale (Threshold = 0.85)

In financial onboarding and insurance underwriting (governed by IRDAI and RBI guidelines), the cost of an undetected character error is highly asymmetric:
- **Routing Failure:** An inaccurate digit in a Bank Account Number or IFSC causes automated clearing failures, returned NACH mandates, and penalty fees.
- **Compliance Rejection:** Inaccurate identity numbers (Aadhaar, PAN, Passport, DL) trigger CKYC validation rejections.
- **Rationale for 0.85:** 
  - Standard printed fields and clean block-capital handwriting routinely achieve `>= 0.88 - 0.99`.
  - Cursive handwriting, slanted numerals, overlapping slashes in dates (`26/04/2026`), and trailing punctuation in place names (`West Bihar.`) exhibit stroke ambiguities and score between `0.78` and `0.84`.
  - Setting the threshold at **0.85** cleanly isolates these ambiguous cases and routes them to human reviewers without flooding the queue with false positives.

---

## ✍️ Handling Handwritten vs. Printed Text

### 1. Printed Documents
- **Preprocessing:** Global Otsu binarization and perspective deskewing.
- **Extraction:** Standard OCR models with fixed font topologies and coordinate template anchors.
- **Verification:** Algorithmic verification (Verhoeff checksum for Aadhaar, regex pattern `^[A-Z]{5}[0-9]{4}[A-Z]$` for PAN, ICAO Doc 9303 checksums for Passport MRZ).

### 2. Handwritten Documents
- **Preprocessing:** Sauvola adaptive local thresholding to suppress form pre-printed underlines, cell boundaries, and watermarks without thinning delicate pen strokes.
- **Stroke & Contour Analysis:** Connected component analysis to separate cursive loops and character ligatures inside segmented bounding boxes.
- **Constraint Dictionaries:** Banking dictionaries for bank names (*State Bank of India*), IFSC prefix validations (*SBIN*), and relationship classifications (*Nephew*).
- **Checkbox Detection:** Pixel contour density analysis within checkbox coordinates for tick-mark presence (e.g., *Financial Planning*, *As & when presented*).

### 3. Failure Cases Observed
1. **Date Slash Overlap:** In `Illustration.jpeg` and `suitability.jpeg`, the handwritten `/` cuts directly across the month `04` and year `2026`, causing character segmentation ambiguity.
2. **Trailing Punctuation in Places:** On `split.jpeg`, the applicant wrote `West Bihar.` with a trailing period, slightly reducing lexicon match confidence.
3. **Tick Mark Box Overshoot:** On `ECS.jpeg`, the handwritten checkmark for frequency extends outside the printed checkbox perimeter, requiring morphological dilation to avoid misclassification.

---

## 🚀 How to Run Locally

### 1. Run Accuracy & Evaluation Report
```bash
python question_3_document_pipeline/evaluator.py
```

### 2. Launch Interactive Dashboard
```bash
python question_3_document_pipeline/app.py
```
Open your browser to:
```
http://127.0.0.1:5002
```
