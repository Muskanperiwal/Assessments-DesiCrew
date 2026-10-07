"""Main URL configuration for ai_assignment."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home_view(request):
    """Landing dashboard linking to all three assignment applications."""
    return render(request, 'home.html')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('task1/', include('task1_agent.urls')),
    path('task2/', include('task2_support.urls')),
    path('task3/', include('task3_vision.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
