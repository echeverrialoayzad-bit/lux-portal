#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from flask import Blueprint

fw_fruta_bp = Blueprint('fw_fruta', __name__, template_folder='templates')

from lux_portal.fw_fruta import routes
