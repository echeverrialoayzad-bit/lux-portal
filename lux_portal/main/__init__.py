#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Blueprint Principal del Portal
"""

from flask import Blueprint

main_bp = Blueprint('main', __name__)

from lux_portal.main import routes
