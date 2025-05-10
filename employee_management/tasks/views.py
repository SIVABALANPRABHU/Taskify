from django.shortcuts import render, redirect
from django.http import HttpResponse
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
import calendar
import io
from .models import Task
import logging

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Google Sheets API setup
API_KEY = "AIzaSyAT0_w_CZbwc81tVZxV7ETX8yxPGFE6IDo"  # Your Google Sheets API key
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
                try:
                    Task.objects.create(
                        assignee=row[0],
                        date=datetime.strptime(row[1], '%Y-%m-%d').date(),
                        task_name=row[2],
                        status=row[3],
                        priority=row[4]
                    )
                except ValueError as e:
                    logger.error(f"Invalid date format in row {row}: {str(e)}")
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
    # Get start_date and end_date from query params
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # Default to current month if no dates provided
    current_date = datetime.now().date()  # Use .date() for consistency
    year = current_date.year
    month = current_date.month
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                start_date, end_date = end_date, start_date  # Swap if start > end
        except ValueError:
            start_date = datetime(year, month, 1).date()
            end_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1).date() - timedelta(days=1)
    else:
        start_date = datetime(year, month, 1).date()
        end_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1).date() - timedelta(days=1)
    
    # Filter tasks by assignee and date range
    tasks = Task.objects.filter(assignee=name, date__gte=start_date, date__lte=end_date)
    
    # Generate custom calendar for date range
    calendar_data = []
    current_date = start_date
    while current_date <= end_date:
        week = [None] * 7  # Initialize week with None
        week_start = current_date - timedelta(days=current_date.weekday())  # Start at Monday
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            if start_date <= day_date <= end_date:
                week[i] = day_date
        calendar_data.append(week)
        current_date = week_start + timedelta(days=7)
        if current_date > end_date:
            break
    
    # Organize tasks by date
    tasks_by_date = {}
    for task in tasks:
        date_str = task.date.strftime('%Y-%m-%d')
        if date_str not in tasks_by_date:
            tasks_by_date[date_str] = []
        tasks_by_date[date_str].append(task)
    
    # Compute previous and next date range for navigation
    range_days = (end_date - start_date).days + 1
    prev_start_date = start_date - timedelta(days=range_days)
    prev_end_date = start_date - timedelta(days=1)
    next_start_date = end_date + timedelta(days=1)
    next_end_date = end_date + timedelta(days=range_days)
    
    return render(request, 'profile.html', {
        'name': name,
        'year': year,
        'month': month,
        'calendar': calendar_data,
        'tasks_by_date': tasks_by_date,
        'start_date': start_date,
        'end_date': end_date,
        'prev_start_date': prev_start_date,
        'prev_end_date': prev_end_date,
        'next_start_date': next_start_date,
        'next_end_date': next_end_date
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