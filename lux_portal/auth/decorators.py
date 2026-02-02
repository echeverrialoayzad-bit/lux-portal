#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Decoradores de autenticacion
"""

from functools import wraps
from flask import session, redirect, url_for


def login_required(f):
    """Decorador para proteger rutas que requieren autenticacion."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
