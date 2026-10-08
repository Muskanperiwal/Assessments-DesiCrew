"""URL configuration for Task 3: Document Scanner & Extractor."""

from django.urls import path
from . import views

app_name = "task3_vision"

urlpatterns = [
    # Primary requested routes
    path("", views.upload_ui, name="upload_ui"),
    path("api/process/", views.api_process_document, name="api_process_document"),
    path("api/sample/", views.api_sample_file, name="api_sample_file"),

    # Aliases for backward compatibility
    path("api/upload/", views.api_process_document, name="api_upload_file"),
    path("api/pipeline/", views.api_run_pipeline, name="api_run_pipeline"),
]
