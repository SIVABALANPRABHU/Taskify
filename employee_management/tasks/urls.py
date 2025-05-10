from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('assignee/<str:name>/', views.assignee_profile, name='assignee_profile'),
    path('assignee/<str:name>/tasks/', views.all_tasks, name='all_tasks'),
    path('assignee/<str:name>/<str:date>/', views.tasks_by_date, name='tasks_by_date'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('export/', views.export, name='export'),
]
