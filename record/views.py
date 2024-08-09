from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.contrib import messages
from record.models import Record
from django.db.models import Q, Sum
from django.contrib.auth.models import User
from datetime import datetime, date as dt_date, timedelta
from collections import defaultdict
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models.functions import TruncMonth, TruncYear
import json
from django.core.files.storage import default_storage
from django.db.models import Sum
from .models import SimplifiedData  # You'll need to create this model
from django.db.models import F
from django.db.models import F
from django.utils.dateformat import DateFormat
import calendar
from .models import SimplifiedData
from django.contrib.auth.models import User
from .models import SimplifiedData
import calendar
import json
from datetime import datetime
from django.http import JsonResponse

def can_view_dashboard(user):
    return user.is_superuser or user.is_staff or user.groups.filter(name='DashboardViewers').exists()


def summarized_monthly_data(request):
    return render(request, 'summarized_monthly_data.html')

@login_required
@user_passes_test(can_view_dashboard)
def simplified_data(request):
    simplified_data = SimplifiedData.objects.all().order_by('-period', 'user__username')
    context = {
        'simplified_data': simplified_data,
    }
    return render(request, 'simplified_data.html', context)

def simplified_data_view(request):
    simplified_data = SimplifiedData.objects.all().order_by('-period', 'user__username')
    context = {
        'simplified_data': simplified_data,
    }
    return render(request, 'simplified_data.html', context)

def get_simplified_data(request):
    data = SimplifiedData.objects.all().order_by('-period', 'user__username').values(
        'user__username', 'user__first_name', 'excel_total', 
        'working_days', 'period', 'month'
    )
    
    # Convert date objects to strings
    formatted_data = []
    for item in data:
        item['period'] = item['period'].strftime('%Y-%m-%d')
        formatted_data.append(item)
    
    return JsonResponse(formatted_data, safe=False)


@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def user_data(request):
    today = dt_date.today()
    users = User.objects.filter(is_staff=False, is_superuser=False).order_by('first_name')

    if request.method == 'POST':
        user_id = request.POST.get('user')
        selected_date = request.POST.get('date')
        is_leave = request.POST.get('is_leave') == 'on'
        fields = 0 if is_leave else int(request.POST.get('fields', 0))
        remarks = request.POST.get('remarks', '')

        user = User.objects.get(id=user_id)

        if Record.objects.filter(date=selected_date, user=user).exists():
            messages.error(request, f'Data for {user.first_name} on this date already exists.')
        else:
            record = Record(user=user, date=selected_date, field=fields, is_leave=is_leave, remarks=remarks)
            record.save()
            messages.success(request, f'Record saved successfully for {user.first_name}!')
        
        return redirect('user_data')  # Redirect to the same page after form submission

    context = {
        'users': users,
        'today': today,
    }
    return render(request, 'user_data.html', context)



@login_required
def index(request):
    today = dt_date.today()
    start_date = today - timedelta(days=7)  # default to the past 7 days
    end_date = today
    view_type = request.GET.get('view_type', 'daily')
    
    if request.method == 'POST':
        user = request.user
        selected_date = request.POST.get('date')
        is_leave = request.POST.get('is_leave') == 'on'
        fields = 0 if is_leave else int(request.POST.get('fields', 0))
        remarks = request.POST.get('remarks', '')

        if Record.objects.filter(date=selected_date, user=user).exists():
            messages.error(request, 'You have already entered data for this date.')
        else:
            record = Record(user=user, date=selected_date, field=fields, is_leave=is_leave, remarks=remarks)
            record.save()
            messages.success(request, 'Record saved successfully!')
        return redirect('index')
    
    if request.GET.get('start_date') and request.GET.get('end_date'):
        start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d').date()

    records = Record.objects.filter(user=request.user, date__range=[start_date, end_date]).order_by('date')
    
    # Prepare data for the chart
    if view_type == 'month':
        chart_data = records.annotate(period=TruncMonth('date')).values('period').annotate(total=Sum('field')).order_by('period')
    elif view_type == 'year':
        chart_data = records.annotate(period=TruncYear('date')).values('period').annotate(total=Sum('field')).order_by('period')
    else:  # daily view
        chart_data = records.values('date').annotate(total=Sum('field')).order_by('date')

    chart_labels = [item['period'].strftime('%Y-%m-%d') if view_type != 'daily' else item['date'].strftime('%Y-%m-%d') for item in chart_data]
    chart_values = [item['total'] for item in chart_data]
    
    context = {
        'user': request.user,
        'today': today,
        'records': records,
        'start_date': start_date,
        'end_date': end_date,
        'has_dashboard_access': can_view_dashboard(request.user),
        'chart_labels': json.dumps(chart_labels),
        'chart_values': json.dumps(chart_values),
        'is_admin': request.user.is_superuser or request.user.is_staff,

        'view_type': view_type,
    }
    return render(request, 'index.html', context)

@login_required
@user_passes_test(can_view_dashboard)
def validate_data(request):
    today = dt_date.today()
    start_date = today - timedelta(days=7)
    end_date = today

    if request.method == 'POST':
        start_date = datetime.strptime(request.POST.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.POST.get('end_date'), '%Y-%m-%d').date()

    user_data = get_user_data(start_date, end_date)
    simplified_data = SimplifiedData.objects.filter(user__is_staff=False, user__is_superuser=False).order_by('-period', 'user__username')

    context = {
        'user_data': user_data,
        'start_date': start_date,
        'end_date': end_date,
        'simplified_data': simplified_data,
    }

    return render(request, 'validate.html', context)

def get_user_data(start_date, end_date):
    user_data = []
    # Filter out admin users (superusers and staff)
    normal_users = User.objects.filter(is_staff=False, is_superuser=False)
    
    for user in normal_users:
        records = Record.objects.filter(user=user, date__range=[start_date, end_date])
        total = records.aggregate(Sum('field'))['field__sum'] or 0
        working_days = records.filter(is_leave=False).count()
        
        user_data.append({
            'user_id': user.username,
            'username': user.first_name,
            'total': total,
            'working_days': working_days
        })
    return user_data

@require_POST
@csrf_exempt
def update_simplified_data(request):
    data = json.loads(request.body)
    excel_data = data.get('excel_data', [])
    end_date = data.get('end_date')

    try:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        updated_count = 0
        for row in excel_data:
            user_id = row.get('User ID')
            excel_total = row.get('Total')
            working_days = row.get('Working Days')

            # Convert empty strings to 0
            excel_total = 0 if excel_total == '' else int(excel_total or 0)
            working_days = 0 if working_days == '' else int(working_days or 0)

            if user_id:
                try:
                    user = User.objects.get(username=user_id)
                    obj, created = SimplifiedData.objects.update_or_create(
                        user=user,
                        period=end_date,
                        defaults={
                            'excel_total': excel_total,
                            'working_days': working_days,
                            'month': calendar.month_name[end_date.month],
                        }
                    )
                    updated_count += 1
                except User.DoesNotExist:
                    print(f"User with ID {user_id} not found")
            else:
                print(f"Skipping row due to missing User ID: {row}")

        return JsonResponse({'success': True, 'updated_count': updated_count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

    
@login_required
@user_passes_test(can_view_dashboard)
def simplified_data(request):
    month = request.GET.get('month', '')
    simplified_data = SimplifiedData.objects.all()
    
    if month:
        simplified_data = simplified_data.filter(month=month)
    
    simplified_data = simplified_data.order_by('-period', 'user__username')
    
    context = {
        'simplified_data': simplified_data,
        'selected_month': month,
    }
    return render(request, 'simplified_data.html', context)

@require_POST
@csrf_exempt
def delete_simplified_data(request):
    try:
        data = json.loads(request.body)
        month = data.get('month', '')

        if month:
            SimplifiedData.objects.filter(month=month).delete()
        else:
            SimplifiedData.objects.all().delete()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


def login_user(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            user = User.objects.get(Q(username__iexact=username))
            user = authenticate(request, username=user.username, password=password)
            if user is not None:
                login(request, user)
                if user.is_staff:  # Check if the user is an admin
                    return redirect('dashboard')
                return redirect('index')
            else:
                messages.error(request, 'Wrong password entered.')
        except User.DoesNotExist:
            messages.error(request, 'You have entered a wrong username.')
        
        return redirect('login')
    else:
        return render(request, 'login.html')
@login_required
def logout_user(request):
    logout(request)
    # messages.success(request, 'Logged out successfully!')
    return redirect('login')

@login_required
@user_passes_test(can_view_dashboard)
def dashboard(request):
    today = dt_date.today()
    start_date = today - timedelta(days=7)  # default to the past 7 days
    end_date = today
    selected_users = []

    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        selected_user_ids = request.POST.getlist('selected_users')

        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            if selected_user_ids:
                selected_users = User.objects.filter(id__in=selected_user_ids)
        except ValueError:
            messages.error(request, 'Invalid input. Please try again.')

    records = Record.objects.filter(date__range=[start_date, end_date])
    if selected_users:
        records = records.filter(user__in=selected_users)
    records = records.order_by('date', 'user')

    dates = list(records.values_list('date', flat=True).distinct().order_by('date'))

    user_data = {}
    daily_totals = [0] * len(dates)
    grand_total = 0

    for record in records:
        username = record.user.username
        user_id = record.user.id
        first_name = record.user.first_name
        if username not in user_data:
            user_data[username] = {
                'user_id': user_id,
                'first_name': first_name,
                'daily_records': [{'value': 0, 'type': 'normal', 'id': None} for _ in dates],
                'total': 0
            }
        
        date_index = dates.index(record.date)
        if record.is_leave:
            user_data[username]['daily_records'][date_index] = {'value': 'Leave', 'type': 'leave', 'id': record.id}
        else:
            user_data[username]['daily_records'][date_index] = {'value': record.field, 'type': 'normal', 'id': record.id}
            user_data[username]['total'] += record.field
            daily_totals[date_index] += record.field
            grand_total += record.field

    # Sort user_data by user_id
    user_data_sorted = sorted(
        [(data['first_name'], username, data) for username, data in user_data.items()],
        key=lambda x: x[0].lower()  # Sort by first_name alphabetically
    )

    # Prepare data for the chart
    chart_labels = [date.strftime('%Y-%m-%d') for date in dates]
    chart_data = daily_totals

    context = {
        'user': request.user,
        'date_range': dates,
        'user_data_sorted': user_data_sorted,
        'daily_totals': daily_totals,
        'grand_total': grand_total,
        'start_date': start_date,
        'end_date': end_date,
        'today': today,
        'all_users': User.objects.all().order_by('first_name'),
        'selected_users': [user.id for user in selected_users],
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data)
    }

    return render(request, 'dashboard.html', context)

@login_required
@user_passes_test(can_view_dashboard)
def status_record(request):
    today = dt_date.today()
    status_date = today  # default status report date

    if request.method == 'POST':
        status_date_str = request.POST.get('status_date')
        try:
            if status_date_str:
                status_date = datetime.strptime(status_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, 'Invalid date. Please try again.')
            status_date = today  # Reset to today if there's an error

    # Status report for selected date
    # Exclude admin users (is_staff=False and is_superuser=False)
    normal_users = User.objects.filter(is_staff=False, is_superuser=False)
    status_report = {}
    for user in normal_users:
        record = Record.objects.filter(user=user, date=status_date).first()
        if record:
            if record.is_leave:
                status = "Leave"
            else:
                status = record.field
            status_report[user.first_name] = {
                'status': status,
                'remarks': record.remarks
            }
        else:
            status_report[user.first_name] = {
                'status': "Not entered yet",
                'remarks': "-"
            }

    # Sort the status_report by user first names (keys) in alphabetical order
    sorted_status_report = dict(sorted(status_report.items(), key=lambda item: item[0].lower()))

    context = {
        'status_date': status_date,
        'status_report': sorted_status_report,
    }

    return render(request, 'statusrecord.html', context)


@require_POST
@csrf_exempt
@login_required
@user_passes_test(lambda u: u.is_superuser or u.is_staff)
def update_record(request):
    data = json.loads(request.body)
    record_id = data.get('id')
    new_value = data.get('value')
    record_type = data.get('type')

    try:
        record = Record.objects.get(id=record_id)
        if record_type == 'leave':
            record.is_leave = new_value.lower() == 'leave'
            record.field = 0
        else:
            record.is_leave = False
            record.field = int(new_value)
        record.save()
        return JsonResponse({'success': True})
    except Record.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Record not found'})
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid value'})
    