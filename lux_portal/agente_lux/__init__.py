from flask import Blueprint
agente_lux_bp = Blueprint('agente_lux', __name__, template_folder='templates')
from lux_portal.agente_lux import routes  # noqa
