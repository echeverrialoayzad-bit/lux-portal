#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas de autenticacion
"""

from flask import render_template, request, redirect, url_for, session, flash
from lux_portal.auth import auth_bp
from lux_portal.config import Config


@auth_bp.route('/health')
def health():
    """Health check endpoint para Railway."""
    return 'OK', 200


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Pagina de login."""
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        if username.lower() == Config.ADMIN_USERNAME.lower() and password == Config.ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = 'Daniela'
            return redirect(url_for('main.home'))
        else:
            error = 'Usuario o contrasena incorrectos'

    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
def logout():
    """Cerrar sesion."""
    session.clear()
    return redirect(url_for('auth.login'))
