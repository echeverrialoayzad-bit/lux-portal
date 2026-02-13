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
        ('client_shipments', 'transport', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'facturacion', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'handling_juni', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'termografo_factura', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costos', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costo_bodega', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costo_guia', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'flete_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'due_carrier_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'fsc_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'esc_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costo_x_kg', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costo_bod_unit', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costo_guia_unit', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'fito_costo_unit', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'co_costo_unit', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'termografo_costo_unit', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'fitos_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'dup_fitos_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'termografo_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'co_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'dup_co_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'transmision_costo', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'costos_fijos', "VARCHAR(100) DEFAULT ''"),
        ('client_shipments', 'utilidad', "VARCHAR(100) DEFAULT ''"),
        # PaymentInfoForm columns
        ('payment_info_forms', 'label', 'VARCHAR(200) DEFAULT \'\''),
        ('payment_info_forms', 'invoice_date', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'expiration_date', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'invoice_number', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'customer_id_code', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'date_from', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'date_to', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'customer_name', 'VARCHAR(300) DEFAULT \'\''),
        ('payment_info_forms', 'customer_address', "TEXT DEFAULT ''"),
        ('payment_info_forms', 'peso', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'moneda', 'VARCHAR(10) DEFAULT \'USD\''),
        ('payment_info_forms', 'aerolinea', 'VARCHAR(100) DEFAULT \'\''),
        ('payment_info_forms', 'tarifa', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'origen', 'VARCHAR(10) DEFAULT \'UIO\''),
        ('payment_info_forms', 'destino', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'tarifa_iva', 'VARCHAR(10) DEFAULT \'0%\''),
        ('payment_info_forms', 'line_items', "TEXT DEFAULT '[]'"),
        ('payment_info_forms', 'full_count', 'VARCHAR(20) DEFAULT \'0\''),
        ('payment_info_forms', 'pieces_count', 'VARCHAR(20) DEFAULT \'0\''),
        ('payment_info_forms', 'awb', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'gross_weight', 'VARCHAR(20) DEFAULT \'\''),
        ('payment_info_forms', 'fw_bank', 'VARCHAR(200) DEFAULT \'BANCO DEL PICHINCHA\''),
        ('payment_info_forms', 'fw_swift', 'VARCHAR(50) DEFAULT \'PICHECEQXXX\''),
        ('payment_info_forms', 'fw_account', 'VARCHAR(50) DEFAULT \'2100339784\''),
        ('payment_info_forms', 'fw_tax_id', 'VARCHAR(50) DEFAULT \'1793230131001\''),
        ('payment_info_forms', 'fw_company', 'VARCHAR(200) DEFAULT \'FREIGHTWISE FORWARDING S.A.\''),
        ('payment_info_forms', 'subtotal', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'taxable', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'tax_rate_vat', 'VARCHAR(20) DEFAULT \'0.000%\''),
        ('payment_info_forms', 'tax', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'other_charges', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'insurance', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'legal_consular', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'inspection_cert', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'other_specify', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'total', 'VARCHAR(50) DEFAULT \'\''),
        ('payment_info_forms', 'currency', 'VARCHAR(10) DEFAULT \'USD\''),
        ('payment_info_forms', 'reason_for_export', 'VARCHAR(200) DEFAULT \'Fresh Flowers\''),
    ]
    for table, column, col_type in migrations:
        try:
            db.session.execute(db.text(
                f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Drop NOT NULL constraints that were set initially
    nullable_fixes = [
        ('customer_associate_forms', 'legal_name'),
        ('shipping_instructions_forms', 'contact_full_name'),
    ]
    for table, column in nullable_fixes:
        try:
            db.session.execute(db.text(
                f'ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL'
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
