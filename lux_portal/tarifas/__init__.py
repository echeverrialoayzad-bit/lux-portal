from flask import Blueprint
tarifas_bp = Blueprint('tarifas', __name__, template_folder='templates')
from lux_portal.tarifas import routes  # noqa
