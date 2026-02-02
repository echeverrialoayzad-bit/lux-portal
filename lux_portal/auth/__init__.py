#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blueprint de Autenticacion
"""

from flask import Blueprint

auth_bp = Blueprint('auth', __name__)

from lux_portal.auth import routes
