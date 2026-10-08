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

from django.http import FileResponse, HttpResponse

def favicon_ico_view(request):
    icon_path = settings.BASE_DIR / 'static' / 'favicon.ico'
    if icon_path.exists():
        response = FileResponse(open(icon_path, 'rb'), content_type='image/x-icon')
        response['Cache-Control'] = 'public, max-age=86400'
        return response
    return HttpResponse(status=204)

def favicon_svg_view(request):
    svg_path = settings.BASE_DIR / 'static' / 'favicon.svg'
    if svg_path.exists():
        response = FileResponse(open(svg_path, 'rb'), content_type='image/svg+xml')
        response['Cache-Control'] = 'public, max-age=86400'
        return response
    return HttpResponse(status=404)

urlpatterns = [
    path('favicon.ico', favicon_ico_view, name='favicon_ico'),
    path('favicon.svg', favicon_svg_view, name='favicon_svg'),
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('task1/', include('task1_agent.urls')),
    path('task2/', include('task2_support.urls')),
    path('task3/', include('task3_vision.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
