#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blueprint de Cotizaciones FreightWise
"""

from flask import Blueprint

cotizaciones_bp = Blueprint(
    'cotizaciones',
    __name__,
    template_folder='templates'
)

from lux_portal.cotizaciones import routes
