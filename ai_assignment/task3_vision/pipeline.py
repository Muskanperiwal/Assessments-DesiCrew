"""Task 3 Document Intelligence Pipeline (Purely Dynamic Multimodal Vision).

Processes uploaded images and scanned PDFs using Google Gemini's native multimodal
vision transformer (gemini-3.5-flash-lite / gemini-3.5-flash / gemini-1.5-flash).

Performs:
1. Dynamic page extraction and image conversion (PDF to Image via pdf2image/PyMuPDF).
2. Purely dynamic visual classification across 10 document categories.
3. Purely dynamic field extraction and per-field confidence scoring directly from pixels.
4. Mandatory PII redaction: replaces 'Aadhaar Number' values with '[Aadhaar Redacted]'.
5. Quality Flagging Engine: flags any field with confidence strictly below 0.85 for Human Review.
"""

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

# Multimodal Gemini SDK
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    genai = None
    HAS_GENAI = False

# PDF preprocessing engines
try:
    from pdf2image import convert_from_bytes
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# ==============================================================================
# Pipeline Constants & Configurations
# ==============================================================================

CONFIDENCE_THRESHOLD = 0.85

THRESHOLD_RATIONALE = (
    "A confidence threshold of 0.85 balances straight-through processing with compliance risk. "
    "Under RBI, NPCI (NACH), and IRDAI standards, low-confidence extractions on statutory identifiers, "
    "handwritten bank accounts, IFSC codes, or legal declarations create operational and legal exposure. "
    "Any field with a confidence score strictly below 0.85 is flagged for mandatory Human-in-the-Loop (HITL) review."
)

STATUTORY_PRINTED_TYPES = frozenset({
    "Aadhaar Card",
    "PAN Card",
    "Driving Licence",
    "Passport",
})

METHODOLOGY_NOTE = (
    "Gemini 1.5's native vision transformer was used to bypass traditional OCR, "
    "relying on its end-to-end multimodal training on cursive and messy handwritten forms. "
    "Common failure cases observed in document processing pipelines include ambiguous digits "
    "(such as distinguishing 0 vs O in alphanumeric IFSC codes, 1 vs I/l), overlapping forward slashes "
    "in slanted handwritten dates, and cursive baseline drift across non-gridded form fields."
)

DOCUMENT_TYPES = [
    "Aadhaar Card",
    "PAN Card",
    "Driving Licence",
    "Passport",
    "NACH / ECS Mandate",
    "FATCA Annexure Form",
    "Benefit Illustration Declaration",
    "Moral Hazard Questionnaire",
    "Multiple Policies Consent Form",
    "Suitability Profiler Declaration",
]

TARGET_FIELDS_BY_TYPE = {
    "Aadhaar Card": ["Aadhaar Number", "Full Name", "Date of Birth", "Address"],
    "PAN Card": ["PAN Number", "Full Name", "Father's Name", "Date of Birth"],
    "Driving Licence": ["DL Number", "Name", "Date of Issue", "Valid Till date"],
    "Passport": ["Passport Number", "Date of Birth", "Date of Expiry", "MRZ Line 2"],
    "NACH / ECS Mandate": ["Bank Account Number", "IFSC Code", "Bank Name", "Amount (figures)", "Frequency"],
    "FATCA Annexure Form": ["Policy Number", "TIN / PAN", "Father's Name", "Place of Birth", "Nationality"],
    "Benefit Illustration Declaration": ["Application Number", "Policyholder Name", "Date", "Place"],
    "Moral Hazard Questionnaire": ["Application Number", "Name of Life Assured", "Nominee Relationship", "Date", "Place"],
    "Multiple Policies Consent Form": ["Proposer Name", "Reason for Multiple Policies", "Date", "Place"],
    "Suitability Profiler Declaration": ["Application Number", "Name of Life Assured", "Name of Agent/SP", "Date", "Place"],
}

SYSTEM_INSTRUCTION = (
    "You are an expert Document Processing AI trained to read messy handwritten forms and Indian KYC documents.\n"
    "Analyze the provided image and extract the data into a strict JSON format.\n\n"
    "Step 1: Classify the document into EXACTLY one of these types: Aadhaar Card, PAN Card, Driving Licence, "
    "Passport, NACH / ECS Mandate, FATCA Annexure Form, Benefit Illustration Declaration, "
    "Moral Hazard Questionnaire, Multiple Policies Consent Form, or Suitability Profiler Declaration.\n\n"
    "Step 2: Extract the specific fields based ONLY on the classified type:\n"
    "Aadhaar: Aadhaar Number, Full Name, Date of Birth, Address\n"
    "PAN: PAN Number, Full Name, Father's Name, Date of Birth\n"
    "DL: DL Number, Name, Date of Issue, Valid Till date\n"
    "Passport: Passport Number, Date of Birth, Date of Expiry, MRZ Line 2\n"
    "NACH/ECS: Bank Account Number, IFSC Code, Bank Name, Amount (figures), Frequency\n"
    "FATCA: Policy Number, TIN / PAN, Father's Name, Place of Birth, Nationality\n"
    "Benefit Illustration: Application Number, Policyholder Name, Date, Place\n"
    "Moral Hazard: Application Number, Name of Life Assured, Nominee Relationship, Date, Place\n"
    "Multiple Policies: Proposer Name, Reason for Multiple Policies, Date, Place\n"
    "Suitability Profiler: Application Number, Name of Life Assured, Name of Agent/SP, Date, Place\n\n"
    "Step 3: For EVERY extracted field, provide a confidence_score between 0.0 and 1.0. "
    "Pay extremely close attention to handwritten dates, bank account numbers, IFSC codes, and TINs, as these are critical. "
    "If handwriting is illegible, output null and give a confidence of 0.1."
)


# ==============================================================================
# Image Preprocessing & Conversion
# ==============================================================================

def preprocess_document_file(file_obj: Any, filename: Optional[str] = None) -> Tuple[Image.Image, str]:
    """Converts uploaded file (PDF or Image) into a PIL Image and base64 JPEG string.

    If it is a PDF, renders the first page using pdf2image with automatic
    PyMuPDF fallback for operating systems without poppler binaries.
    """
    file_bytes = b""
    orig_name = filename or ""

    if hasattr(file_obj, "seek"):
        try:
            file_obj.seek(0)
        except Exception:
            pass

    if hasattr(file_obj, "read"):
        file_bytes = file_obj.read()
        if hasattr(file_obj, "seek"):
            try:
                file_obj.seek(0)
            except Exception:
                pass
        if not orig_name and hasattr(file_obj, "name"):
            orig_name = file_obj.name
    elif isinstance(file_obj, (str, Path)):
        orig_name = str(file_obj)
        with open(file_obj, "rb") as f:
            file_bytes = f.read()
    elif isinstance(file_obj, bytes):
        file_bytes = file_obj

    if not file_bytes:
        raise ValueError("Uploaded file is empty or cannot be read.")

    is_pdf = orig_name.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF")
    pil_image = None

    if is_pdf:
        # 1. Try pdf2image (if poppler is installed)
        if HAS_PDF2IMAGE:
            try:
                images = convert_from_bytes(file_bytes, first_page=1, last_page=1)
                if images:
                    pil_image = images[0].convert("RGB")
            except Exception as pdf2img_err:
                logger.info("pdf2image unavailable (%s), using PyMuPDF engine", pdf2img_err)

        # 2. Resilient fallback to PyMuPDF (no poppler binary dependency needed)
        if pil_image is None and HAS_PYMUPDF:
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                if len(doc) > 0:
                    page = doc.load_page(0)
                    pix = page.get_pixmap(dpi=200)
                    pil_image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                    doc.close()
            except Exception as fitz_err:
                logger.error("PyMuPDF PDF conversion failed: %s", fitz_err)

        if pil_image is None:
            raise RuntimeError("Could not convert PDF page to image. Verify poppler or pymupdf is installed.")
    else:
        try:
            pil_image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception as img_err:
            raise ValueError(f"Invalid image format: {img_err}")

    # Generate base64 representation
    buffered = io.BytesIO()
    pil_image.save(buffered, format="JPEG", quality=92)
    base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return pil_image, base64_str


# ==============================================================================
# Purely Dynamic Multimodal Vision Processing (Zero Hardcoding / Zero Static Fallback)
# ==============================================================================

def call_gemini_vision(pil_image: Image.Image) -> Dict[str, Any]:
    """Dynamically invokes Google Gemini Multimodal Vision on the provided image pixels.

    Sends the raw image directly to the model with system instructions requiring
    structured JSON classification and entity extraction with confidence scores.
    Rotates through configured keys in settings.GEMINI_API_KEYS if any key encounters
    temporary rate-limiting.
    """
    if not HAS_GENAI:
        raise RuntimeError("google.generativeai package is not installed.")

    api_keys = getattr(settings, "GEMINI_API_KEYS", [])
    single_key = getattr(settings, "GEMINI_API_KEY", "")
    if single_key and single_key not in api_keys:
        api_keys.insert(0, single_key)

    if not api_keys:
        raise ValueError("No GEMINI_API_KEY or GEMINI_API_KEYS configured in settings.")

    # High-performance vision models available in Google Generative AI
    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ]

    extraction_prompt = (
        "Analyze this document image thoroughly. Examine the layout, headers, stamps, printed text, "
        "and handwriting. Return a strict JSON object with this exact structure:\n"
        "{\n"
        '  "document_type": "<Classified Type>",\n'
        '  "is_handwritten": true or false,\n'
        '  "extracted_data": {\n'
        '    "<Field Name>": {\n'
        '      "value": "<extracted text or null>",\n'
        '      "confidence_score": 0.95\n'
        "    }\n"
        "  }\n"
        "}\n"
        "Ensure all target fields specified for the classified document type are present in extracted_data."
    )

    last_error = None

    # Rotate through API keys if needed
    for key_idx, api_key in enumerate(api_keys):
        try:
            genai.configure(api_key=api_key)
        except Exception as conf_err:
            logger.warning("Error configuring Gemini API key #%d: %s", key_idx, conf_err)
            continue

        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=SYSTEM_INSTRUCTION,
                    generation_config={"response_mime_type": "application/json"}
                )
                response = model.generate_content(
                    [pil_image, extraction_prompt],
                    request_options={"timeout": 20}
                )

                if response and response.text:
                    raw_text = response.text.strip()
                    # Strip any markdown code fences if present
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                        raw_text = re.sub(r"\s*```$", "", raw_text)

                    parsed_json = json.loads(raw_text)
                    if isinstance(parsed_json, dict) and "document_type" in parsed_json:
                        logger.info("Successfully processed document via Gemini model '%s' (key #%d)", model_name, key_idx)
                        return parsed_json

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if "404" in err_str or "not found" in err_str.lower():
                    # Model not available in this region/tier, try next candidate model
                    continue
                elif "429" in err_str or "quota" in err_str.lower():
                    # Key quota exhausted, rotate to next API key
                    logger.warning("Gemini key #%d rate-limited (429). Rotating to next key...", key_idx)
                    break
                else:
                    logger.warning("Gemini model %s error: %s", model_name, exc)
                    continue

    # No static mock fallback: Raise explicit exception so client knows real AI status
    raise RuntimeError(f"Gemini Vision inference failed across all keys/models: {last_error}")


# ==============================================================================
# Pipeline Normalization, PII Redaction & Flagging Engine
# ==============================================================================

def process_document(file_obj: Any, filename: Optional[str] = None) -> Dict[str, Any]:
    """Executes the end-to-end multimodal document extraction pipeline.

    1. Preprocesses image or PDF.
    2. Sends raw image to Gemini Vision AI for zero-shot classification and extraction.
    3. Dynamically unpacks and normalizes field coordinates and confidence scores.
    4. Enforces Aadhaar PII Redaction: replaces Aadhaar Number values with '[Aadhaar Redacted]'.
    5. Evaluates confidence scores against the 0.85 cutoff to generate the Flagging Report.
    """
    orig_name = filename or getattr(file_obj, "name", "uploaded_document")
    pil_image, _ = preprocess_document_file(file_obj, filename=orig_name)

    # Purely dynamic visual inference
    raw_result = call_gemini_vision(pil_image)

    # 1. Classification
    doc_type = str(raw_result.get("document_type", "Unknown Document")).strip()

    # 2. Extract Fields Dictionary (handling variable top-level key names from LLM)
    raw_fields = (
        raw_result.get("extracted_data")
        or raw_result.get("extraction_results")
        or raw_result.get("fields")
        or raw_result.get("extracted_fields")
        or {}
    )

    has_field_container = any(
        k in raw_result for k in ("extracted_data", "extraction_results", "fields", "extracted_fields")
    )
    if not raw_fields and not has_field_container:
        skip_keys = {
            "document_type", "document_type_confidence", "confidence_score", "status",
            "is_handwritten", "overall_confidence", "needs_human_review",
        }
        raw_fields = {k: v for k, v in raw_result.items() if k not in skip_keys}

    # 3. Dynamic Normalization & Aadhaar PII Redaction
    normalized_data: Dict[str, Dict[str, Any]] = {}

    for field_key, field_content in raw_fields.items():
        if isinstance(field_content, dict):
            extracted_val = field_content.get("value")
            raw_score = field_content.get("confidence_score", field_content.get("confidence"))
        else:
            extracted_val = field_content
            raw_score = 0.95

        # Clean score
        try:
            score = float(raw_score) if raw_score is not None else 0.1
        except (ValueError, TypeError):
            score = 0.1
        score = max(0.0, min(1.0, score))

        # ----------------------------------------------------------------------
        # Crucial Security Rule: PII Redaction for Aadhaar Number
        # ----------------------------------------------------------------------
        clean_name = field_key.strip().lower().replace("_", " ")
        is_aadhaar_field = any(tok in clean_name for tok in ["aadhaar number", "aadhaar no", "uid number", "aadhaar_number"])

        if is_aadhaar_field or (doc_type == "Aadhaar Card" and "aadhaar" in clean_name):
            extracted_val = "[Aadhaar Redacted]"

        # Also mask any raw 12-digit numbers on Aadhaar cards if present in values
        elif doc_type == "Aadhaar Card" and isinstance(extracted_val, str):
            if re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b", extracted_val):
                extracted_val = "[Aadhaar Redacted]"

        normalized_data[field_key] = {
            "value": extracted_val,
            "confidence_score": round(score, 2)
        }

    def _norm_field_name(name: str) -> str:
        return re.sub(r"\s+", " ", name.strip().lower())

    expected_fields = TARGET_FIELDS_BY_TYPE.get(doc_type, [])
    extracted_norm = {_norm_field_name(k) for k in normalized_data}
    missing_fields = [
        label for label in expected_fields
        if _norm_field_name(label) not in extracted_norm
    ]

    is_handwritten = raw_result.get("is_handwritten")
    if isinstance(is_handwritten, str):
        is_handwritten = is_handwritten.strip().lower() in ("true", "1", "yes")
    elif is_handwritten is None:
        is_handwritten = doc_type not in STATUTORY_PRINTED_TYPES

    scores = [fd["confidence_score"] for fd in normalized_data.values()]
    overall_confidence = round(sum(scores) / len(scores), 3) if scores else 0.0

    # 4. Quality Flagging Engine (strictly below threshold)
    flagged_fields = []
    for field_name, field_dict in normalized_data.items():
        c_score = field_dict["confidence_score"]
        if c_score < CONFIDENCE_THRESHOLD:
            flagged_fields.append({
                "field_name": field_name,
                "value": field_dict["value"],
                "confidence_score": c_score,
                "rationale": f"Confidence score {c_score:.2f} is below the {CONFIDENCE_THRESHOLD:.2f} threshold"
            })

    for label in missing_fields:
        flagged_fields.append({
            "field_name": label,
            "value": None,
            "confidence_score": 0.0,
            "rationale": "Mandatory field not returned by extraction",
        })

    needs_human_review = bool(flagged_fields)

    flagging_report = {
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "threshold_rationale": THRESHOLD_RATIONALE,
        "total_fields": len(normalized_data),
        "expected_field_count": len(expected_fields),
        "missing_fields": missing_fields,
        "flagged_count": len(flagged_fields),
        "flagged_fields": flagged_fields,
        "needs_human_review": needs_human_review,
    }

    return {
        "filename": orig_name,
        "classification": doc_type,
        "json_data": {
            "document_type": doc_type,
            "is_handwritten": bool(is_handwritten),
            "overall_confidence": overall_confidence,
            "needs_human_review": needs_human_review,
            "extracted_data": normalized_data,
            "fields": {
                name: {
                    "value": payload["value"],
                    "confidence": payload["confidence_score"],
                }
                for name, payload in normalized_data.items()
            },
        },
        "flagging_report": flagging_report,
        "methodology_note": METHODOLOGY_NOTE,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
