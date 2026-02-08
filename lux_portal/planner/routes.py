#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Planner
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from lux_portal.planner import planner_bp
from lux_portal.planner.models import (
    MonthlyGoal, SubGoal, Task, Event, Habit, HabitLog, StickyNote,
    get_daily_quote
)
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required
from datetime import datetime, date, timedelta
from sqlalchemy import case
import calendar


# Ordenamiento de prioridad: high=1, medium=2, low=3 (menor numero = mayor prioridad)
def get_priority_order():
    return case(
        (Task.priority == 'high', 1),
        (Task.priority == 'medium', 2),
        (Task.priority == 'low', 3),
        else_=4
    )


@planner_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal del planner"""
    today = date.today()
    current_year = today.year
    current_month = today.month

    # Obtener meta del mes actual
    monthly_goal = MonthlyGoal.query.filter_by(
        year=current_year,
        month=current_month
    ).first()

    # Tareas pendientes para hoy y urgentes
    tasks_today = Task.query.filter(
        Task.status != 'completed',
        db.or_(
            Task.due_date == today,
            Task.priority == 'high'
        )
    ).order_by(get_priority_order(), Task.due_date).limit(10).all()

    # Todas las tareas pendientes
    all_pending_tasks = Task.query.filter(
        Task.status != 'completed'
    ).order_by(get_priority_order(), Task.due_date, Task.order).all()

    # Eventos de esta semana
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_events = Event.query.filter(
        Event.event_date >= week_start,
        Event.event_date <= week_end
    ).order_by(Event.event_date, Event.start_time).all()

    # Organizar eventos por dia de la semana
    events_by_day = {i: [] for i in range(7)}
    for event in week_events:
        day_idx = event.event_date.weekday()
        events_by_day[day_idx].append(event)

    # Habitos activos
    habits = Habit.query.filter_by(active=True).order_by(Habit.order).all()

    # Sticky notes
    sticky_notes = StickyNote.query.order_by(StickyNote.pinned.desc(), StickyNote.updated_at.desc()).limit(6).all()

    # Frase motivacional
    quote = get_daily_quote()

    # Generar dias de la semana
    week_days = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        week_days.append({
            'date': day,
            'name': ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM'][i],
            'is_today': day == today
        })

    return render_template(
        'planner/dashboard.html',
        monthly_goal=monthly_goal,
        tasks_today=tasks_today,
        all_pending_tasks=all_pending_tasks,
        week_days=week_days,
        events_by_day=events_by_day,
        habits=habits,
        sticky_notes=sticky_notes,
        quote=quote,
        today=today,
        month_name=calendar.month_name[current_month],
        year=current_year
    )


# ============================================================================
# MONTHLY GOAL ROUTES
# ============================================================================

@planner_bp.route('/goal', methods=['GET', 'POST'])
@planner_bp.route('/goal/<int:id>', methods=['GET', 'POST'])
@login_required
def goal(id=None):
    """Crear o editar meta del mes"""
    today = date.today()

    if id:
        goal = MonthlyGoal.query.get_or_404(id)
    else:
        # Buscar meta del mes actual o crear nueva
        goal = MonthlyGoal.query.filter_by(
            year=today.year,
            month=today.month
        ).first()

    if request.method == 'POST':
        try:
            if not goal:
                goal = MonthlyGoal(year=today.year, month=today.month)

            goal.title = request.form.get('title', '').strip()
            goal.description = request.form.get('description', '').strip()
            goal.target_value = int(request.form.get('target_value', 100) or 100)
            goal.current_value = int(request.form.get('current_value', 0) or 0)

            if not goal.id:
                db.session.add(goal)

            db.session.commit()
            flash('Meta guardada', 'success')
            return redirect(url_for('planner.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('planner/goal_form.html', goal=goal, today=today)


@planner_bp.route('/api/goal/<int:id>/progress', methods=['POST'])
@login_required
def update_goal_progress(id):
    """Actualizar progreso de meta"""
    try:
        goal = MonthlyGoal.query.get_or_404(id)
        data = request.get_json()
        goal.current_value = int(data.get('current_value', goal.current_value))
        db.session.commit()
        return jsonify({'success': True, 'progress': goal.progress_percent})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/subgoal', methods=['POST'])
@login_required
def add_subgoal():
    """Agregar sub-meta"""
    try:
        data = request.get_json()
        subgoal = SubGoal(
            goal_id=data['goal_id'],
            title=data['title'],
            order=data.get('order', 0)
        )
        db.session.add(subgoal)
        db.session.commit()
        return jsonify({'success': True, 'id': subgoal.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/subgoal/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_subgoal(id):
    """Marcar/desmarcar sub-meta"""
    try:
        subgoal = SubGoal.query.get_or_404(id)
        subgoal.completed = not subgoal.completed
        db.session.commit()
        return jsonify({'success': True, 'completed': subgoal.completed})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TASK ROUTES
# ============================================================================

@planner_bp.route('/tasks')
@login_required
def tasks():
    """Lista de todas las tareas"""
    filter_status = request.args.get('status', 'pending')
    filter_priority = request.args.get('priority', 'all')

    query = Task.query

    if filter_status != 'all':
        if filter_status == 'pending':
            query = query.filter(Task.status != 'completed')
        else:
            query = query.filter(Task.status == filter_status)

    if filter_priority != 'all':
        query = query.filter(Task.priority == filter_priority)

    tasks = query.order_by(get_priority_order(), Task.due_date, Task.order).all()

    return render_template(
        'planner/tasks.html',
        tasks=tasks,
        filter_status=filter_status,
        filter_priority=filter_priority
    )


@planner_bp.route('/task/new', methods=['GET', 'POST'])
@planner_bp.route('/task/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def task_form(id=None):
    """Crear o editar tarea"""
    task = Task.query.get(id) if id else None

    if request.method == 'POST':
        try:
            if not task:
                task = Task()

            task.title = request.form.get('title', '').strip()
            task.description = request.form.get('description', '').strip()
            task.priority = request.form.get('priority', 'medium')
            task.category = request.form.get('category', 'general')

            due_date_str = request.form.get('due_date', '')
            task.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else None

            if not task.id:
                db.session.add(task)

            db.session.commit()
            flash('Tarea guardada', 'success')
            return redirect(url_for('planner.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('planner/task_form.html', task=task)


@planner_bp.route('/api/task', methods=['POST'])
@login_required
def quick_add_task():
    """Agregar tarea rapida via AJAX"""
    try:
        data = request.get_json()
        task = Task(
            title=data['title'],
            priority=data.get('priority', 'medium'),
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None
        )
        db.session.add(task)
        db.session.commit()
        return jsonify({
            'success': True,
            'id': task.id,
            'priority_color': task.priority_color
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/task/<int:id>/status', methods=['POST'])
@login_required
def update_task_status(id):
    """Actualizar estado de tarea"""
    try:
        task = Task.query.get_or_404(id)
        data = request.get_json()
        new_status = data.get('status', 'completed')

        task.status = new_status
        if new_status == 'completed':
            task.completed_at = datetime.utcnow()
        else:
            task.completed_at = None

        db.session.commit()
        return jsonify({'success': True, 'status': task.status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/task/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    """Eliminar tarea"""
    try:
        task = Task.query.get_or_404(id)
        db.session.delete(task)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# EVENT ROUTES
# ============================================================================

@planner_bp.route('/agenda')
@login_required
def agenda():
    """Vista de agenda con calendario"""
    today = date.today()
    view = request.args.get('view', 'week')

    # Navegacion semanal
    week_offset = request.args.get('week_offset', 0, type=int)

    # Calcular rango de fechas para la lista de eventos
    if view == 'week':
        base_monday = today - timedelta(days=today.weekday())
        start_date = base_monday + timedelta(weeks=week_offset)
        end_date = start_date + timedelta(days=6)
        # Mes del calendario basado en la semana seleccionada
        cal_year = start_date.year
        cal_month = start_date.month
    else:  # month
        cal_year = request.args.get('cal_year', today.year, type=int)
        cal_month = request.args.get('cal_month', today.month, type=int)
        start_date = date(cal_year, cal_month, 1)
        _, last_day = calendar.monthrange(cal_year, cal_month)
        end_date = date(cal_year, cal_month, last_day)

    # Calendario: generar semanas
    cal = calendar.Calendar(firstweekday=0)  # Lunes primero
    cal_weeks_all = cal.monthdatescalendar(cal_year, cal_month)

    if view == 'week':
        cal_weeks = []
        for week in cal_weeks_all:
            if start_date in week:
                cal_weeks = [week]
                break
        if not cal_weeks:
            cal_weeks = [cal_weeks_all[0]]
        cal_range_start = cal_weeks[0][0]
        cal_range_end = cal_weeks[0][-1]
    else:
        cal_weeks = cal_weeks_all
        cal_range_start = date(cal_year, cal_month, 1)
        _, cal_last_day = calendar.monthrange(cal_year, cal_month)
        cal_range_end = date(cal_year, cal_month, cal_last_day)

    # Obtener tareas con due_date en el rango del calendario
    tasks = Task.query.filter(
        Task.due_date >= cal_range_start,
        Task.due_date <= cal_range_end
    ).order_by(Task.due_date, Task.priority).all()

    # Mapeo de fechas con detalles de tareas
    task_dates = {}
    for t in tasks:
        d = t.due_date.isoformat()
        if d not in task_dates:
            task_dates[d] = []
        task_dates[d].append({
            'title': t.title,
            'priority': t.priority,
            'status': t.status,
            'category': t.category,
        })

    # Mes anterior y siguiente para navegacion
    if cal_month == 1:
        prev_year, prev_month = cal_year - 1, 12
    else:
        prev_year, prev_month = cal_year, cal_month - 1
    if cal_month == 12:
        next_year, next_month = cal_year + 1, 1
    else:
        next_year, next_month = cal_year, cal_month + 1

    meses_es = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',
                7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}

    # Lista de tareas de la semana (para resumen en vista semanal)
    week_tasks = tasks if view == 'week' else []

    return render_template(
        'planner/agenda.html',
        view=view,
        today=today,
        cal_weeks=cal_weeks,
        cal_year=cal_year,
        cal_month=cal_month,
        cal_month_name=meses_es[cal_month],
        meses_es=meses_es,
        task_dates=task_dates,
        week_tasks=week_tasks,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        week_offset=week_offset,
    )


@planner_bp.route('/event/new', methods=['GET', 'POST'])
@planner_bp.route('/event/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def event_form(id=None):
    """Crear o editar evento"""
    event = Event.query.get(id) if id else None

    if request.method == 'POST':
        try:
            if not event:
                event = Event()

            event.title = request.form.get('title', '').strip()
            event.description = request.form.get('description', '').strip()
            event.event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date()
            event.event_type = request.form.get('event_type', 'work')
            event.location = request.form.get('location', '').strip()
            event.all_day = 'all_day' in request.form

            if not event.all_day:
                start_time = request.form.get('start_time', '')
                end_time = request.form.get('end_time', '')
                event.start_time = datetime.strptime(start_time, '%H:%M').time() if start_time else None
                event.end_time = datetime.strptime(end_time, '%H:%M').time() if end_time else None

            if not event.id:
                db.session.add(event)

            db.session.commit()
            flash('Evento guardado', 'success')
            return redirect(url_for('planner.agenda'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('planner/event_form.html', event=event, today=date.today())


@planner_bp.route('/api/event/<int:id>', methods=['DELETE'])
@login_required
def delete_event(id):
    """Eliminar evento"""
    try:
        event = Event.query.get_or_404(id)
        db.session.delete(event)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HABIT ROUTES
# ============================================================================

@planner_bp.route('/habits')
@login_required
def habits():
    """Vista de habitos"""
    today = date.today()
    week_offset = int(request.args.get('week_offset', 0))
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    habits = Habit.query.filter_by(active=True).order_by(Habit.order).all()

    return render_template(
        'planner/habits.html',
        habits=habits,
        week_start=week_start,
        week_end=week_end,
        today=today,
        timedelta=timedelta
    )


@planner_bp.route('/habit/new', methods=['GET', 'POST'])
@planner_bp.route('/habit/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def habit_form(id=None):
    """Crear o editar habito"""
    habit = Habit.query.get(id) if id else None

    if request.method == 'POST':
        try:
            if not habit:
                habit = Habit()

            habit.name = request.form.get('name', '').strip()
            habit.icon = request.form.get('icon', 'check-circle')
            habit.color = request.form.get('color', 'rose')
            habit.target_per_week = int(request.form.get('target_per_week', 7))

            if not habit.id:
                db.session.add(habit)

            db.session.commit()
            flash('Habito guardado', 'success')
            return redirect(url_for('planner.habits'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('planner/habit_form.html', habit=habit)


@planner_bp.route('/api/habit/toggle', methods=['POST'])
@planner_bp.route('/api/habit/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_habit(id=None):
    """Marcar/desmarcar habito para un dia"""
    try:
        data = request.get_json()
        habit_id = id or data.get('habit_id')
        habit = Habit.query.get_or_404(habit_id)
        log_date = datetime.strptime(data['date'], '%Y-%m-%d').date()

        log = HabitLog.query.filter_by(habit_id=habit_id, log_date=log_date).first()

        if log:
            log.completed = not log.completed
        else:
            log = HabitLog(habit_id=habit_id, log_date=log_date, completed=True)
            db.session.add(log)

        db.session.commit()
        return jsonify({
            'success': True,
            'completed': log.completed,
            'streak': habit.get_streak()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# STICKY NOTE ROUTES
# ============================================================================

@planner_bp.route('/api/note', methods=['POST'])
@login_required
def create_note():
    """Crear nota"""
    try:
        data = request.get_json()
        note = StickyNote(
            content=data['content'],
            color=data.get('color', 'pink')
        )
        db.session.add(note)
        db.session.commit()
        return jsonify({'success': True, 'id': note.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/note/<int:id>', methods=['PUT'])
@login_required
def update_note(id):
    """Actualizar nota"""
    try:
        note = StickyNote.query.get_or_404(id)
        data = request.get_json()

        if 'content' in data:
            note.content = data['content']
        if 'color' in data:
            note.color = data['color']
        if 'pinned' in data:
            note.pinned = data['pinned']

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@planner_bp.route('/api/note/<int:id>', methods=['DELETE'])
@login_required
def delete_note(id):
    """Eliminar nota"""
    try:
        note = StickyNote.query.get_or_404(id)
        db.session.delete(note)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
