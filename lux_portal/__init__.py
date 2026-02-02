#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lux Portal - Application Factory
Portal modular para herramientas FreightWise
"""

from flask import Flask
from lux_portal.extensions import db
from lux_portal.config import get_config


def create_app(config_name='default'):
    """Crea y configura la aplicacion Flask."""
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # Inicializar extensiones
    db.init_app(app)

    # Registrar blueprints
    from lux_portal.auth import auth_bp
    from lux_portal.main import main_bp
    from lux_portal.cotizaciones import cotizaciones_bp
    from lux_portal.clientes import clientes_bp
    from lux_portal.planner import planner_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(cotizaciones_bp, url_prefix='/cotizaciones')
    app.register_blueprint(clientes_bp)
    app.register_blueprint(planner_bp)

    # Crear tablas de base de datos
    with app.app_context():
        db.create_all()

    return app
