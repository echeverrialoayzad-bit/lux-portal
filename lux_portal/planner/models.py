#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos para el modulo Planner
"""

from datetime import datetime, date
from lux_portal.extensions import db
import json


# ============================================================================
# MONTHLY GOAL - Meta del mes
# ============================================================================
class MonthlyGoal(db.Model):
    """Meta principal del mes"""
    __tablename__ = 'planner_monthly_goals'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default='')
    target_value = db.Column(db.Integer, default=100)  # Meta numerica (ej: 5 clientes)
    current_value = db.Column(db.Integer, default=0)   # Progreso actual
    color = db.Column(db.String(20), default='rose')   # Color del tema
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacion con sub-metas
    subgoals = db.relationship('SubGoal', backref='goal', cascade='all, delete-orphan', lazy='dynamic')

    @property
    def progress_percent(self):
        if self.target_value == 0:
            return 0
        return min(100, int((self.current_value / self.target_value) * 100))

    def __repr__(self):
        return f'<MonthlyGoal {self.year}/{self.month}: {self.title}>'


class SubGoal(db.Model):
    """Sub-metas de una meta principal"""
    __tablename__ = 'planner_subgoals'

    id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('planner_monthly_goals.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SubGoal {self.title}>'


# ============================================================================
# TASK - To-Do List
# ============================================================================
class Task(db.Model):
    """Tarea del to-do list"""
    __tablename__ = 'planner_tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default='')
    priority = db.Column(db.String(20), default='medium')  # high, medium, low
    status = db.Column(db.String(20), default='pending')   # pending, in_progress, completed
    category = db.Column(db.String(50), default='general') # trabajo, personal, urgente, etc
    due_date = db.Column(db.Date, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def is_overdue(self):
        if self.due_date and self.status != 'completed':
            return self.due_date < date.today()
        return False

    @property
    def priority_color(self):
        colors = {
            'high': '#EF4444',    # Rojo
            'medium': '#F59E0B',  # Amarillo
            'low': '#10B981'      # Verde
        }
        return colors.get(self.priority, '#6B7280')

    def __repr__(self):
        return f'<Task {self.title}>'


# ============================================================================
# EVENT - Agenda/Calendario
# ============================================================================
class Event(db.Model):
    """Evento de la agenda"""
    __tablename__ = 'planner_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    event_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    all_day = db.Column(db.Boolean, default=False)
    event_type = db.Column(db.String(30), default='work')  # work, meeting, personal, reminder, urgent
    color = db.Column(db.String(20), default='purple')
    location = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def type_color(self):
        colors = {
            'work': '#F59E0B',      # Amarillo
            'meeting': '#8B5CF6',   # Morado
            'personal': '#10B981',  # Verde
            'reminder': '#3B82F6',  # Azul
            'urgent': '#EF4444'     # Rojo
        }
        return colors.get(self.event_type, '#EC4899')

    def __repr__(self):
        return f'<Event {self.title} on {self.event_date}>'


# ============================================================================
# HABIT - Seguimiento de habitos
# ============================================================================
class Habit(db.Model):
    """Habito a trackear"""
    __tablename__ = 'planner_habits'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), default='check-circle')  # Bootstrap icon
    color = db.Column(db.String(20), default='rose')
    frequency = db.Column(db.String(20), default='daily')  # daily, weekly
    target_per_week = db.Column(db.Integer, default=7)     # Dias por semana objetivo
    active = db.Column(db.Boolean, default=True)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relacion con logs
    logs = db.relationship('HabitLog', backref='habit', cascade='all, delete-orphan', lazy='dynamic')

    def get_streak(self):
        """Calcula la racha actual de dias consecutivos"""
        from datetime import timedelta
        streak = 0
        check_date = date.today()

        while True:
            log = HabitLog.query.filter_by(
                habit_id=self.id,
                log_date=check_date,
                completed=True
            ).first()

            if log:
                streak += 1
                check_date -= timedelta(days=1)
            else:
                break

        return streak

    def get_week_completion(self, week_start):
        """Obtiene los dias completados en una semana"""
        from datetime import timedelta
        completions = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            log = HabitLog.query.filter_by(
                habit_id=self.id,
                log_date=day
            ).first()
            completions.append(log.completed if log else False)
        return completions

    def __repr__(self):
        return f'<Habit {self.name}>'


class HabitLog(db.Model):
    """Registro diario de un habito"""
    __tablename__ = 'planner_habit_logs'

    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('planner_habits.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    notes = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('habit_id', 'log_date', name='unique_habit_date'),
    )

    def __repr__(self):
        return f'<HabitLog {self.habit_id} on {self.log_date}>'


# ============================================================================
# STICKY NOTE - Notas adhesivas
# ============================================================================
class StickyNote(db.Model):
    """Nota adhesiva"""
    __tablename__ = 'planner_sticky_notes'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(20), default='pink')  # pink, lavender, yellow, mint, blue
    position_x = db.Column(db.Integer, default=0)
    position_y = db.Column(db.Integer, default=0)
    pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def color_class(self):
        colors = {
            'pink': '#FDF2F8',
            'lavender': '#F3E8FF',
            'yellow': '#FEF9C3',
            'mint': '#D1FAE5',
            'blue': '#DBEAFE'
        }
        return colors.get(self.color, '#FDF2F8')

    def __repr__(self):
        return f'<StickyNote {self.id}>'


# ============================================================================
# MOTIVATIONAL QUOTE - Frase del dia
# ============================================================================
MOTIVATIONAL_QUOTES = [
    {"quote": "El exito es la suma de pequenos esfuerzos repetidos dia tras dia.", "author": "Robert Collier"},
    {"quote": "No cuentes los dias, haz que los dias cuenten.", "author": "Muhammad Ali"},
    {"quote": "El unico modo de hacer un gran trabajo es amar lo que haces.", "author": "Steve Jobs"},
    {"quote": "Cree que puedes y ya estaras a mitad de camino.", "author": "Theodore Roosevelt"},
    {"quote": "La disciplina es el puente entre metas y logros.", "author": "Jim Rohn"},
    {"quote": "Cada dia es una nueva oportunidad para cambiar tu vida.", "author": "Anonimo"},
    {"quote": "El futuro pertenece a quienes creen en la belleza de sus suenos.", "author": "Eleanor Roosevelt"},
    {"quote": "No esperes. El tiempo nunca sera el correcto.", "author": "Napoleon Hill"},
    {"quote": "La unica forma de lograr lo imposible es creer que es posible.", "author": "Charles Kingsleigh"},
    {"quote": "Tu actitud determina tu direccion.", "author": "Anonimo"},
    {"quote": "Haz hoy lo que otros no quieren, manana tendras lo que otros no tienen.", "author": "Anonimo"},
    {"quote": "El exito no es definitivo, el fracaso no es fatal: lo que cuenta es el valor de continuar.", "author": "Winston Churchill"},
]

def get_daily_quote():
    """Obtiene una frase motivacional basada en el dia del ano"""
    day_of_year = datetime.now().timetuple().tm_yday
    index = day_of_year % len(MOTIVATIONAL_QUOTES)
    return MOTIVATIONAL_QUOTES[index]
