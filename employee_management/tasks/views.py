from django.shortcuts import render, redirect
from django.http import HttpResponse
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime
import calendar
import io
from .models import Task
import logging

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Google Sheets API setup
API_KEY = "AIzaSyAT0_w_CZbwc81tVZxV7ETX8yxPGFE6IDo"  # Replace with your Google Sheets API key
SHEET_ID = "1nmEyQp0Li6qScZ_kUeeZp-c4jFjx6M2y_J9PhJgyp_I"  # Your sheet ID
service = build("sheets", "v4", developerKey=API_KEY)
RANGE_NAME = "Sheet1!A1:E"  # Adjust if your sheet tab name differs

def sync_tasks():
    try:
        result = service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])
        if not values or len(values) < 2:  # Check for empty sheet or header-only
            logger.warning("No data found in Google Sheet")
            return
        headers = values[0]  # ['Assignee', 'Date', 'Task Name', 'Status', 'Priority']
        data = values[1:]    # Data rows
        Task.objects.all().delete()
        for row in data:
            if len(row) >= 5:  # Ensure row has all columns
                Task.objects.create(
                    assignee=row[0],
                    date=datetime.strptime(row[1], '%Y-%m-%d').date(),
                    task_name=row[2],
                    status=row[3],
                    priority=row[4]
                )
    except Exception as e:
        logger.error(f"Failed to sync tasks from Google Sheet: {str(e)}")
        # Continue with existing local data
        pass

def index(request):
    sync_tasks()
    assignees = Task.objects.values('assignee').distinct()
    return render(request, 'index.html', {'assignees': assignees})

def assignee_profile(request, name):
    sync_tasks()
    year = int(request.GET.get('year', datetime.now().year))
    month = int(request.GET.get('month', datetime.now().month))
    tasks = Task.objects.filter(assignee=name, date__year=year, date__month=month)
    
    cal = calendar.monthcalendar(year, month)
    tasks_by_date = {}
    for task in tasks:
        date_str = task.date.strftime('%Y-%m-%d')
        if date_str not in tasks_by_date:
            tasks_by_date[date_str] = []
        tasks_by_date[date_str].append(task)
    
    # Compute previous and next month/year for navigation
    prev_month, prev_year = (month - 1, year) if month > 1 else (12, year - 1)
    next_month, next_year = (month + 1, year) if month < 12 else (1, year + 1)
    
    return render(request, 'profile.html', {
        'name': name,
        'year': year,
        'month': month,
        'calendar': cal,
        'tasks_by_date': tasks_by_date,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month
    })

def tasks_by_date(request, name, date):
    sync_tasks()
    tasks = Task.objects.filter(assignee=name, date=date)
    if request.method == 'POST':
        task_id = request.POST['task_id']
        new_status = request.POST['status']
        task = Task.objects.get(id=task_id)
        task.status = new_status
        task.save()
        # Note: Cannot update Google Sheet (read-only API key)
        return redirect('tasks_by_date', name=name, date=date)
    return render(request, 'tasks.html', {'name': name, 'date': date, 'tasks': tasks})

def dashboard(request):
    sync_tasks()
    df = pd.DataFrame.from_records(Task.objects.values())
    if not df.empty:
        stats = df.groupby('assignee').agg({
            'status': lambda x: (x == 'Completed').mean() * 100,
            'task_name': 'count'
        }).rename(columns={'status': 'Completion Rate (%)', 'task_name': 'Total Tasks'})
    else:
        stats = pd.DataFrame()
    return render(request, 'dashboard.html', {'stats': stats.to_dict()})

def export(request):
    sync_tasks()
    df = pd.DataFrame.from_records(Task.objects.values())
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="tasks.csv"'},
    )
    response.write(output.getvalue())
    return response