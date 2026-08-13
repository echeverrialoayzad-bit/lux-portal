from flask import Blueprint

proformas_bp = Blueprint('proformas', __name__, template_folder='templates')

from lux_portal.proformas import routes  # noqa
