#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modulo Clientes - Planillas de storage por cliente
"""

from flask import Blueprint

clientes_bp = Blueprint(
    'clientes',
    __name__,
    template_folder='templates',
    url_prefix='/clientes'
)

from lux_portal.clientes import routes
