#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Blueprint

excel_online_bp = Blueprint('excel_online', __name__, template_folder='templates')

from lux_portal.excel_online import routes
