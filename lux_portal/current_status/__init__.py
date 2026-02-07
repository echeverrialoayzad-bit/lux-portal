from flask import Blueprint

current_status_bp = Blueprint(
    'current_status',
    __name__,
    template_folder='templates',
    url_prefix='/current-status'
)

from lux_portal.current_status import routes
