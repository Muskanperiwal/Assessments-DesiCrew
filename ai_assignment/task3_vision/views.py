"""Views for Task 3: Multimodal Document Scanner & Extractor.

Provides the frontend dashboard template view and the REST API endpoint
for uploading documents, running the Gemini vision pipeline, and generating
compliance flagging reports.
"""

import logging
import mimetypes
from pathlib import Path
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods

from .pipeline import (
    process_document,
    CONFIDENCE_THRESHOLD,
    THRESHOLD_RATIONALE,
    DECISION_RULES,
    METHODOLOGY_NOTE,
    DOCUMENT_TYPES,
)

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
def upload_ui(request):
    """Renders the Task 3 Document Scanner & Quality Flagging Dashboard."""
    # List sample documents available in the data directory for quick testing
    sample_docs_dir = getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'data') / 'sample_documents'
    sample_files = []
    if sample_docs_dir.exists():
        for f in sample_docs_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.pdf']:
                sample_files.append(f.name)

    context = {
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "threshold_rationale": THRESHOLD_RATIONALE,
        "methodology_note": METHODOLOGY_NOTE,
        "document_types": DOCUMENT_TYPES,
        "sample_files": sorted(sample_files),
    }
    return render(request, "task3_vision/index.html", context)


# Alias for backwards compatibility
index_ui = upload_ui


@csrf_exempt
@require_http_methods(["POST"])
def api_process_document(request):
    """API endpoint accepting multipart/form-data file upload (image or PDF).

    Executes preprocessing, Gemini vision classification & field extraction,
    Aadhaar PII redaction, and confidence score threshold flagging.
    """
    uploaded_file = None
    if "file" in request.FILES:
        uploaded_file = request.FILES["file"]
    elif "document" in request.FILES:
        uploaded_file = request.FILES["document"]

    # Support testing via sample_filename parameter
    sample_name = request.POST.get("sample_filename")
    if not uploaded_file and sample_name:
        sample_path = getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'data') / 'sample_documents' / sample_name
        if sample_path.exists():
            try:
                result = process_document(str(sample_path), filename=sample_name)
                return JsonResponse(result)
            except Exception as e:
                logger.error("Error processing sample file %s: %s", sample_name, e)
                return JsonResponse({"error": f"Failed processing sample: {str(e)}"}, status=500)

    if not uploaded_file:
        return JsonResponse(
            {"error": "No file uploaded. Please send a file in 'file' or 'document' field."},
            status=400
        )

    try:
        # Optionally save file to media directory for record keeping
        media_dir = getattr(settings, "MEDIA_ROOT", Path(settings.BASE_DIR) / "media")
        media_dir.mkdir(parents=True, exist_ok=True)
        dest_path = media_dir / uploaded_file.name
        with open(dest_path, "wb+") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        # Run pipeline using saved dest_path
        result = process_document(dest_path, filename=uploaded_file.name)
        return JsonResponse(result)

    except Exception as exc:
        logger.exception("Error processing uploaded document: %s", exc)
        return JsonResponse({
            "error": "Pipeline processing failure",
            "details": str(exc)
        }, status=500)


# Aliases for backwards compatibility with previous test suites
api_upload_file = api_process_document


def _sample_dir() -> Path:
    return getattr(settings, "DATA_DIR", Path(settings.BASE_DIR) / "data") / "sample_documents"


@require_http_methods(["GET"])
def api_sample_file(request):
    """Serve one sample image or PDF for the side-by-side preview."""
    name = Path(request.GET.get("name") or "").name
    root = _sample_dir().resolve()
    path = (root / name).resolve()
    if not name or root not in path.parents or not path.is_file():
        raise Http404("Sample not found")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path.open("rb"), content_type=content_type)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_run_pipeline(request):
    """Full corpus batch endpoint for compatibility."""
    sample_docs_dir = getattr(settings, 'DATA_DIR', Path(settings.BASE_DIR) / 'data') / 'sample_documents'
    results = {}
    failures = []
    all_flagged = []

    if sample_docs_dir.exists():
        for f in sorted(sample_docs_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.pdf']:
                try:
                    res = process_document(str(f), filename=f.name)
                    results[f.name] = res
                    all_flagged.extend(res["flagging_report"]["flagged_fields"])
                except Exception as e:
                    logger.warning("Failed running sample %s: %s", f.name, e)
                    failures.append({"filename": f.name, "error": str(e)})

    return JsonResponse({
        "documents": results,
        "failures": failures,
        "flagging_report": {
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "threshold_rationale": THRESHOLD_RATIONALE,
            "total_documents": len(results),
            "failed_documents": len(failures),
            "total_flagged_fields": len(all_flagged),
            "flagged_fields": all_flagged,
            "needs_human_review": bool(all_flagged),
            "decision_rules": DECISION_RULES
        },
        "methodology_note": METHODOLOGY_NOTE,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    })
