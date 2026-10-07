"""URL configuration for task2_support app."""
from django.urls import path
from . import views

app_name = 'task2_support'

urlpatterns = [
    path('', views.chat_ui, name='chat_ui'),
    path('api/support_chat/', views.api_support_chat, name='api_support_chat'),
    path('api/chat/', views.api_support_chat, name='api_chat_alias'),
    path('api/reset/', views.api_reset, name='api_reset'),
]
