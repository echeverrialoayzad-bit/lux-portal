#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modulo Planner - Organizador personal aesthetic
"""

from flask import Blueprint

planner_bp = Blueprint(
    'planner',
    __name__,
    template_folder='templates',
    url_prefix='/planner'
)

from lux_portal.planner import routes
