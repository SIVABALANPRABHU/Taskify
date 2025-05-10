from django.shortcuts import render, redirect
from django.http import HttpResponse
from googleapiclient.discovery import build
import pandas as pd
from datetime import datetime, timedelta
import calendar
import io
from .models import Task
import logging
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from urllib.parse import urlencode

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Google Sheets API setup
API_KEY = "AIzaSyAT0_w_CZbwc81tVZxV7ETX8yxPGFE6IDo"
SHEET_ID = "1nmEyQp0Li6qScZ_kUeeZp-c4jFjx6M2y_J9PhJgyp_I"
service = build("sheets", "v4", developerKey=API_KEY)
RANGE_NAME = "Sheet1!A1:G"

def sync_tasks():
    try:
        result = service.spreadsheets().values().get(spreadsheetId=SHEET_ID, range=RANGE_NAME).execute()
        values = result.get("values", [])
        if not values or len(values) < 2:
            logger.warning("No data found in Google Sheet")
            return
        headers = values[0]  # ['Task Name', 'Assignee', 'Start Date', 'End Date', 'Duration', 'Status', 'Priority']
        data = values[1:]
        Task.objects.all().delete()
        for row in data:
            if len(row) >= 7:
                try:
                    start_date = datetime.strptime(row[2], '%Y-%m-%d').date()
                    end_date = datetime.strptime(row[3], '%Y-%m-%d').date()
                    duration = float(row[4]) if row[4] else 0.0
                    if start_date <= end_date and duration >= 0:
                        Task.objects.create(
                            task_name=row[0],
                            assignee=row[1],
                            start_date=start_date,
                            end_date=end_date,
                            duration=duration,
                            status=row[5],
                            priority=row[6]
                        )
                    else:
                        logger.warning(f"Invalid data in row {row}: start_date > end_date or negative duration")
                except (ValueError, TypeError) as e:
                    logger.error(f"Invalid data format in row {row}: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to sync tasks from Google Sheet: {str(e)}")
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
    
    # Default to current month
    current_date = datetime.now().date()
    year = current_date.year
    month = current_date.month
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date > end_date:
                start_date, end_date = end_date, start_date
        except ValueError:
            start_date = datetime(year, month, 1).date()
            end_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1).date() - timedelta(days=1)
    else:
        start_date = datetime(year, month, 1).date()
        end_date = (datetime(year, month, 1) + timedelta(days=31)).replace(day=1).date() - timedelta(days=1)
    
    # Filter tasks
    tasks = Task.objects.filter(
        assignee=name,
        start_date__lte=end_date,
        end_date__gte=start_date
    )
    
    # Calculate daily workload
    daily_hours = {}
    for task in tasks:
        duration_days = (task.end_date - task.start_date).days + 1
        if duration_days <= 0:
            continue
        # Cap daily hours at 12
        hours_per_day = min(task.duration / duration_days, 12)
        current_date = task.start_date
        while current_date <= task.end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str not in daily_hours:
                daily_hours[date_str] = 0
            daily_hours[date_str] += hours_per_day
            current_date += timedelta(days=1)
    
    # Round to one decimal place
    daily_hours_sum = {date_str: round(hours, 1) for date_str, hours in daily_hours.items()}
    
    # Generate calendar
    calendar_data = []
    current_date = start_date
    while current_date <= end_date:
        week = [None] * 7
        week_start = current_date - timedelta(days=current_date.weekday())
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
        current_task_date = max(task.start_date, start_date)
        while current_task_date <= min(task.end_date, end_date):
            date_str = current_task_date.strftime('%Y-%m-%d')
            if date_str not in tasks_by_date:
                tasks_by_date[date_str] = []
            tasks_by_date[date_str].append(task)
            current_task_date += timedelta(days=1)
    
    # Navigation
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
        'daily_hours': daily_hours_sum,
        'start_date': start_date,
        'end_date': end_date,
        'prev_start_date': prev_start_date,
        'prev_end_date': prev_end_date,
        'next_start_date': next_start_date,
        'next_end_date': next_end_date
    })

def all_tasks(request, name):
    sync_tasks()
    tasks = Task.objects.filter(assignee=name)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    status = request.GET.get('status')
    priority = request.GET.get('priority')
    search_query = request.GET.get('search')
    sort_by = request.GET.get('sort_by', 'id')
    sort_order = request.GET.get('sort_order', 'asc')
    
    filter_params = {
        'start_date': start_date_str or '',
        'end_date': end_date_str or '',
        'status': status or 'all',
        'priority': priority or 'all',
        'search': search_query or '',
        'sort_by': sort_by,
        'sort_order': sort_order,
        'page': request.GET.get('page', '1')
    }
    
    if request.method == 'POST' and 'task_id' in request.POST:
        task_id = request.POST.get('task_id')
        new_status = request.POST.get('status')
        try:
            task = Task.objects.get(id=task_id, assignee=name)
            task.status = new_status
            task.save()
        except Task.DoesNotExist:
            logger.error(f"Task ID {task_id} not found for assignee {name}")
        return redirect(f"{request.path}?{urlencode(filter_params)}")
    
    if request.method == 'POST' and 'export' in request.POST:
        filtered_tasks = tasks
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                if start_date <= end_date:
                    filtered_tasks = filtered_tasks.filter(start_date__lte=end_date, end_date__gte=start_date)
                else:
                    start_date, end_date = end_date, start_date
                    filtered_tasks = filtered_tasks.filter(start_date__lte=end_date, end_date__gte=start_date)
            except ValueError:
                pass
        if status and status != 'all':
            filtered_tasks = filtered_tasks.filter(status=status)
        if priority and priority != 'all':
            filtered_tasks = filtered_tasks.filter(priority=priority)
        if search_query:
            filtered_tasks = filtered_tasks.filter(task_name__icontains=search_query)
        df = pd.DataFrame.from_records(filtered_tasks.values('task_name', 'start_date', 'end_date', 'duration', 'status', 'priority'))
        output = io.StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        response = HttpResponse(
            content_type='text/csv',
            headers={'Content-Disposition': 'attachment; filename="filtered_tasks.csv"'},
        )
        response.write(output.getvalue())
        return response
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if start_date <= end_date:
                tasks = tasks.filter(start_date__lte=end_date, end_date__gte=start_date)
            else:
                start_date, end_date = end_date, start_date
                tasks = tasks.filter(start_date__lte=end_date, end_date__gte=start_date)
        except ValueError:
            start_date_str, end_date_str = None, None
    
    if status and status != 'all':
        tasks = tasks.filter(status=status)
    
    if priority and priority != 'all':
        tasks = tasks.filter(priority=priority)
    
    if search_query:
        tasks = tasks.filter(task_name__icontains=search_query)
    
    if sort_by in ['task_name', 'start_date', 'end_date', 'duration', 'status', 'priority']:
        if sort_order == 'desc':
            tasks = tasks.order_by(f'-{sort_by}')
        else:
            tasks = tasks.order_by(sort_by)
    else:
        tasks = tasks.order_by('id')
    
    paginator = Paginator(tasks, 10)
    page = request.GET.get('page')
    try:
        tasks_paginated = paginator.page(page)
    except PageNotAnInteger:
        tasks_paginated = paginator.page(1)
    except EmptyPage:
        tasks_paginated = paginator.page(paginator.num_pages)
    
    status_choices = Task.objects.filter(assignee=name).values_list('status', flat=True).distinct()
    priority_choices = Task.objects.filter(assignee=name).values_list('priority', flat=True).distinct()
    
    return render(request, 'all_tasks.html', {
        'name': name,
        'tasks': tasks_paginated,
        'status_choices': status_choices,
        'priority_choices': priority_choices,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'status': status or 'all',
        'priority': priority or 'all',
        'search_query': search_query or '',
        'sort_by': sort_by,
        'sort_order': sort_order,
        'filter_params': urlencode(filter_params)
    })

def tasks_by_date(request, name, date):
    sync_tasks()
    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
    tasks = Task.objects.filter(
        assignee=name,
        start_date__lte=date_obj,
        end_date__gte=date_obj
    )
    if request.method == 'POST':
        task_id = request.POST['task_id']
        new_status = request.POST['status']
        task = Task.objects.get(id=task_id)
        task.status = new_status
        task.save()
        return redirect('tasks_by_date', name=name, date=date)
    return render(request, 'tasks.html', {'name': name, 'date': date, 'tasks': tasks})

def dashboard(request):
    sync_tasks()
    df = pd.DataFrame.from_records(Task.objects.values())
    if not df.empty:
        stats = df.groupby('assignee').agg({
            'status': lambda x: (x == 'Completed').mean() * 100,
            'task_name': 'count'
        }).rename(columns={'status': 'completion_rate', 'task_name': 'total_tasks'})
        stats_dict = stats.to_dict('index')
        stats_formatted = {
            assignee: {
                'completion_rate': data['completion_rate'],
                'total_tasks': data['total_tasks']
            } for assignee, data in stats_dict.items()
        }
    else:
        stats_formatted = {}
    return render(request, 'dashboard.html', {'stats': stats_formatted})

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