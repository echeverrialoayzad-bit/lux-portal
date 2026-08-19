#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Documentacion y Verificacion - Modulo de gestion de documentos legales por cliente
"""

from flask import Blueprint

documentacion_bp = Blueprint('documentacion', __name__, template_folder='templates')

from lux_portal.documentacion import routes  # noqa
