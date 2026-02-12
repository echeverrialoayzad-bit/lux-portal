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
    from lux_portal.current_status import current_status_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(cotizaciones_bp, url_prefix='/cotizaciones')
    app.register_blueprint(clientes_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(current_status_bp)

    # Crear tablas de base de datos y migrar columnas faltantes
    with app.app_context():
        db.create_all()
        _migrate_db(app)

    return app


def _migrate_db(app):
    """Agrega columnas faltantes a tablas existentes."""
    migrations = [
        ('airline_rates', 'net_rate', 'VARCHAR(100) DEFAULT \'\''),
        ('airline_rates', 'operative', 'VARCHAR(100) DEFAULT \'\''),
        ('airline_rates', 'net_ops', 'VARCHAR(100) DEFAULT \'\''),
        ('airline_rates', 'profit', 'VARCHAR(100) DEFAULT \'\''),
        ('airline_rates', 'additional_costs_value', 'VARCHAR(200) DEFAULT \'\''),
        ('status_clients', 'custom_columns', "TEXT DEFAULT '{}'"),
        ('airline_rates', 'extra_data', "TEXT DEFAULT '{}'"),
        ('status_airlines', 'extra_data', "TEXT DEFAULT '{}'"),
        ('status_payments', 'extra_data', "TEXT DEFAULT '{}'"),
        ('planner_tasks', 'start_time', 'TIME'),
        ('planner_tasks', 'end_time', 'TIME'),
        ('status_airlines', 'kg', 'VARCHAR(200) DEFAULT \'\''),
        ('status_airlines', 'all_in_rate', 'VARCHAR(200) DEFAULT \'\''),
        ('client_shipments', 'piezas', 'VARCHAR(100) DEFAULT \'\''),
    ]
    for table, column, col_type in migrations:
        try:
            db.session.execute(db.text(
                f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
