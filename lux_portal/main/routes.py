#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del portal principal
"""

from datetime import datetime
from flask import render_template
from lux_portal.main import main_bp
from lux_portal.auth.decorators import login_required


# Registro de modulos disponibles - facil de agregar nuevos
AVAILABLE_MODULES = [
    {
        'id': 'cotizaciones',
        'name': 'FreightWise',
        'description': 'Cotizaciones de flete aereo internacional',
        'icon': 'bi-airplane',
        'url': 'cotizaciones.dashboard',
        'color': '#924A4A'  # Burgundy para FreightWise
    },
    {
        'id': 'clientes',
        'name': 'Clientes',
        'description': 'Planillas de storage por cliente',
        'icon': 'bi-people-fill',
        'url': 'clientes.dashboard',
        'color': '#1A2456'  # Navy para Clientes
    },
    {
        'id': 'planner',
        'name': 'Planner',
        'description': 'Organizador personal con metas, tareas y habitos',
        'icon': 'bi-journal-bookmark-fill',
        'url': 'planner.dashboard',
        'color': '#8B5CF6'  # Lavender para Planner
    },
    {
        'id': 'current_status',
        'name': 'Current Status',
        'description': 'Seguimiento de estado de envios por cliente',
        'icon': 'bi-speedometer2',
        'url': 'current_status.dashboard',
        'color': '#7c3aed'  # Purple para Current Status
    },
]


def get_greeting():
    """Retorna saludo basado en la hora del dia."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "Buenos dias,"
    elif 12 <= hour < 19:
        return "Buenas tardes,"
    else:
        return "Buenas noches,"


@main_bp.route('/')
@login_required
def home():
    """Dashboard principal del portal con tarjetas de modulos."""
    return render_template(
        'main/home.html',
        modules=AVAILABLE_MODULES,
        greeting=get_greeting()
    )
