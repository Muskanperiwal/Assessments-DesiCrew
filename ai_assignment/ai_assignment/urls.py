"""Main URL configuration for ai_assignment."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home_view(request):
    """Landing dashboard linking to all three assignment applications."""
    try:
        sample_docs = len([p for p in (settings.DATA_DIR / 'sample_documents').glob('*') if p.is_file()])
    except Exception:
        sample_docs = 13
    try:
        support_docs = len([p for p in (settings.DATA_DIR / 'support_documents').glob('*') if p.is_file()])
    except Exception:
        support_docs = 3
    dataset_file = (settings.DATA_DIR / 'Inventory-Records-Sample-Data.xlsx').exists()
    
    context = {
        'gemini_active': bool(getattr(settings, 'GEMINI_API_KEY', '')),
        'dataset_exists': dataset_file,
        'knowledge_docs_count': support_docs,
        'sample_docs_count': sample_docs,
        'total_records': 46,
    }
    return render(request, 'home.html', context)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('task1/', include('task1_agent.urls')),
    path('task2/', include('task2_support.urls')),
    path('task3/', include('task3_vision.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
