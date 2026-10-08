"""URL configuration for Task 1: Autonomous Inventory Data Analyst Agent."""
from django.urls import path
from . import views

app_name = 'task1_agent'

urlpatterns = [
    path('', views.chat_ui, name='chat_ui'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/playground/', views.api_playground, name='api_playground'),
    path('api/data_info/', views.api_data_info, name='api_data_info'),
    path('api/records/', views.api_records, name='api_records'),
    path('api/insight/', views.api_insight, name='api_insight'),
]
