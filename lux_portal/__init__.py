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
    from lux_portal.fw_fruta import fw_fruta_bp
    from lux_portal.excel_online import excel_online_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(cotizaciones_bp, url_prefix='/cotizaciones')
    app.register_blueprint(clientes_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(current_status_bp)
    app.register_blueprint(fw_fruta_bp, url_prefix='/fw-fruta')
    app.register_blueprint(excel_online_bp, url_prefix='/excel-online')

    # Crear tablas de base de datos y migrar columnas faltantes
    with app.app_context():
        db.create_all()
        _migrate_db(app)
        _seed_cotizaciones()
        _seed_excel_online()
        _seed_fsc_rules()
        _seed_cargo_rules()
        _migrate_fsc_cargo_groups()

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
        # Cotizaciones: cargos FreightWise editables + notas
        ('cotizaciones', 'cargos_freightwise_json', "TEXT"),
        ('cotizaciones', 'notas_freightwise', "TEXT"),
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


# ---------------------------------------------------------------------------
# Cotizaciones seed data — agregar aqui cada cotizacion recuperada de PDF
# La funcion inserta solo si no existe ya (origen+destino+valid_from unicos)
# ---------------------------------------------------------------------------
_COTIZACIONES_SEED = [
    {
        'origen': 'UIO', 'destino': 'RUH', 'valid_from': '03/18/2026',
        'contacto_nombre': 'Daniela Echeverria',
        'contacto_email': 'daniela.echeverria@freight-wise.com',
        'mercancia': 'FRESH CUT FLOWERS',
        'customer': '', 'attn': '',
        'aerolineas': [
            {
                "aerolinea": "LUFTHANSA PAX", "vuelo": "PAX",
                "itinerario": "UIO-MIA-MUC-RUH", "tiempo_transito": "3-4D",
                "granjas_entrega": "LUN\nJUE\n16:00",
                "salida": "MAR\nVIE\n16:00", "llegada": "SAB\nMAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "4.75", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "4.75"},
                    {"kg": "+500", "tarifa": "3.50", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.50"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "50"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "EMIRATES FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-BQN-DXB-RUH", "tiempo_transito": "3-4D",
                "granjas_entrega": "MIE\nSAB\n16:00",
                "salida": "JUE\nDOM\n16:00", "llegada": "LUN\nJUE\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "4.55", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "4.55"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "25"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "QATAR FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-PTY-AMS-DOH-RUH", "tiempo_transito": "2-3D",
                "granjas_entrega": "JUE\nSAB\n16:00",
                "salida": "VIE\nDOM\n16:00", "llegada": "LUN\nMIE\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "4.40", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "4.40"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "45"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "TURKISH PAX", "vuelo": "PAX",
                "itinerario": "UIO-MST-IST-RUH", "tiempo_transito": "3-4D",
                "granjas_entrega": "JUE\nDOM\n16:00",
                "salida": "VIE\nLUN\n16:00", "llegada": "MAR\nVIE\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "4.15", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "4.15"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "35"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "TURKISH PAX", "vuelo": "PAX",
                "itinerario": "UIO-MIA-IST-RUH", "tiempo_transito": "3-4D",
                "granjas_entrega": "MAR\nVIE\n16:00",
                "salida": "MIE\nSAB\n16:00", "llegada": "SAB\nMIE\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.99", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.99"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": True
            },
            {
                "aerolinea": "TURKISH PAX", "vuelo": "PAX",
                "itinerario": "UIO-PTY-IST-RUH", "tiempo_transito": "3-4D",
                "granjas_entrega": "MIE\nSAB\n16:00",
                "salida": "JUE\nDOM\n16:00", "llegada": "DOM\nJUE\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "5.34", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "5.34"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": True
            },
        ],
        'cargos_freightwise': [
            {"concepto": "Due Agent", "monto": "0"},
            {"concepto": "Certificado", "monto": "0"},
            {"concepto": "Fitosanitario", "monto": "0"},
        ],
        'notas_freightwise': ''
    },
    {
        'origen': 'UIO', 'destino': 'MAD', 'valid_from': '03/18/2026',
        'contacto_nombre': 'Daniela Echeverria',
        'contacto_email': 'daniela.echeverria@freight-wise.com',
        'mercancia': 'FRESH CUT FLOWERS',
        'customer': '', 'attn': '',
        'aerolineas': [
            {
                "aerolinea": "TURKISH FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-MIA-MST-IST-MAD", "tiempo_transito": "+3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.40", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.40"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "35"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "LUFTHANSA PAX", "vuelo": "PAX",
                "itinerario": "UIO-MIA-FRA-MAD", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.10", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.10"},
                    {"kg": "+500", "tarifa": "2.85", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.85"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "50"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "AVIANCA FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-BOG-MAD", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.00", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.00"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "FSC (Fuel Surcharge)", "monto": "0.10"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "ATLAS FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-MIA-MAD", "tiempo_transito": "2-3D",
                "granjas_entrega": "JUE\n16:00",
                "salida": "VIE\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "2.55", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.55"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "25"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "DELTA PAX", "vuelo": "PAX",
                "itinerario": "UIO-ATL-MAD", "tiempo_transito": "+1D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.10", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.10"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "25"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "AIR CANADA FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-YYZ-MAD", "tiempo_transito": "+2D",
                "granjas_entrega": "VIE\n16:00",
                "salida": "SAB\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "2.80", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.80"},
                    {"kg": "+300", "tarifa": "2.75", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.75"},
                    {"kg": "+500", "tarifa": "2.70", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.70"},
                    {"kg": "+1000", "tarifa": "2.65", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.65"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": False
            },
        ],
        'cargos_freightwise': [
            {"concepto": "Due Agent", "monto": "0"},
            {"concepto": "Certificado", "monto": "0"},
            {"concepto": "Fitosanitario", "monto": "0"},
        ],
        'notas_freightwise': ''
    },
    {
        'origen': 'UIO', 'destino': 'LHR', 'valid_from': '03/18/2026',
        'contacto_nombre': 'Daniela Echeverria',
        'contacto_email': 'daniela.echeverria@freight-wise.com',
        'mercancia': 'FRESH CUT FLOWERS',
        'customer': '', 'attn': '',
        'aerolineas': [
            {
                "aerolinea": "AVIANCA PAX", "vuelo": "PAX",
                "itinerario": "UIO-BOG-LHR", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "2.90", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.90"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "FSC (Fuel Surcharge)", "monto": "0.10"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "LUFTHANSA PAX", "vuelo": "PAX",
                "itinerario": "UIO-MIA-FRA-LHR", "tiempo_transito": "3-4D",
                "granjas_entrega": "16:00",
                "salida": "16:00", "llegada": "22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.20", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.20"},
                    {"kg": "+500", "tarifa": "2.70", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.70"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "AIR CANADA FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-YYZ-LHR", "tiempo_transito": "2-3D",
                "granjas_entrega": "VIE\n16:00",
                "salida": "SAB\n16:00", "llegada": "LUN\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.35", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.35"},
                    {"kg": "+300", "tarifa": "3.30", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.30"},
                    {"kg": "+500", "tarifa": "3.25", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.25"},
                    {"kg": "+1000", "tarifa": "3.20", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.20"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "DELTA PAX", "vuelo": "PAX",
                "itinerario": "UIO-ATL-LHR", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.10", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.10"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "25"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "TURKISH FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-MST-IST-LHR", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.80", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.80"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "35"}],
                "notas": "", "es_continuacion": False
            },
        ],
        'cargos_freightwise': [
            {"concepto": "Due Agent", "monto": "0"},
            {"concepto": "Certificado", "monto": "0"},
            {"concepto": "Fitosanitario", "monto": "0"},
        ],
        'notas_freightwise': ''
    },
    {
        'origen': 'UIO', 'destino': 'GRU', 'valid_from': '03/10/2026',
        'contacto_nombre': 'Daniela Echeverria',
        'contacto_email': 'daniela.echeverria@freight-wise.com',
        'mercancia': 'FRESH CUT FLOWERS',
        'customer': '', 'attn': '',
        'aerolineas': [
            {
                "aerolinea": "DELTA PAX", "vuelo": "PAX",
                "itinerario": "UIO-GRU", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.20", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.20"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "25"}],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "AVIANCA PAX", "vuelo": "PAX",
                "itinerario": "UIO-BOG-GRU", "tiempo_transito": "+1D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "2.40", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "2.40"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": False
            },
            {
                "aerolinea": "AVIANCA PAX", "vuelo": "PAX",
                "itinerario": "UIO-MIA-VCP", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "6.25", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "6.25"},
                ],
                "rate_increases": [], "cargos_adicionales": [],
                "notas": "", "es_continuacion": True
            },
            {
                "aerolinea": "DHL FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-MIA-VCP", "tiempo_transito": "+1D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+500", "tarifa": "3.40", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.40"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "FSC (Fuel Surcharge)", "monto": "0.10"}],
                "notas": "FSC: $0.12 / kg vol - MIN $15.00 - A PARTIR DEL 16 DE MARZO 2026",
                "es_continuacion": False
            },
        ],
        'cargos_freightwise': [
            {"concepto": "Due Agent", "monto": "50.00"},
            {"concepto": "Certificado", "monto": "15.00"},
            {"concepto": "Fitosanitario", "monto": "2.50"},
        ],
        'notas_freightwise': ''
    },
    {
        'origen': 'UIO', 'destino': 'EVN', 'valid_from': '02/25/2026',
        'contacto_nombre': 'Daniela Echeverria',
        'contacto_email': 'daniela.echeverria@freight-wise.com',
        'mercancia': 'FRESH CUT FLOWERS',
        'customer': '', 'attn': '',
        'aerolineas': [
            {
                "aerolinea": "TURKISH FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-MST-ICN-EVN", "tiempo_transito": "2-3D",
                "granjas_entrega": "SAB\n16:00",
                "salida": "DOM\n16:00", "llegada": "MAR\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "3.95", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "3.95"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [{"concepto": "Due Carrier", "monto": "35"}],
                "notas": "Esta ruta inicia a partir del 11 de marzo",
                "es_continuacion": False
            },
            {
                "aerolinea": "QATAR FREIGHTER", "vuelo": "FREIGHTER",
                "itinerario": "UIO-PTY-AMS-DOH-EVN", "tiempo_transito": "+3D",
                "granjas_entrega": "JUE\n16:00",
                "salida": "VIE\n16:00", "llegada": "DOM\n22:30",
                "kg_rates": [
                    {"kg": "+100", "tarifa": "4.64", "margen": "0.00", "costo_operativo": "0.00", "tarifa_cliente": "4.64"},
                ],
                "rate_increases": [],
                "cargos_adicionales": [
                    {"concepto": "Due Carrier", "monto": "45"},
                    {"concepto": "CC (Carrier Charges)", "monto": "12"},
                    {"concepto": "CG HAWB C/U", "monto": "3"},
                ],
                "notas": "The only departure day on the DOH-EVN route is D5, so UIO must depart on D2",
                "es_continuacion": False
            },
        ],
        'cargos_freightwise': [
            {"concepto": "Due Agent", "monto": "50.00"},
            {"concepto": "Certificado", "monto": "15.00"},
            {"concepto": "Fitosanitario", "monto": "2.50"},
        ],
        'notas_freightwise': ''
    },
]


def _seed_cotizaciones():
    """Inserta cotizaciones predefinidas si no existen todavia."""
    import json
    from datetime import datetime

    for seed in _COTIZACIONES_SEED:
        try:
            exists = db.session.execute(db.text(
                'SELECT id FROM cotizaciones WHERE origen=:o AND destino=:d AND valid_from=:v'
            ), {'o': seed['origen'], 'd': seed['destino'], 'v': seed['valid_from']}).fetchone()

            if not exists:
                now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                db.session.execute(db.text("""
                    INSERT INTO cotizaciones
                        (fecha_creacion, fecha_modificacion, contacto_nombre, contacto_email,
                         valid_from, mercancia, customer, attn, origen, destino,
                         aerolineas_json, cargos_freightwise_json, notas_freightwise, estado)
                    VALUES
                        (:fc, :fm, :cn, :ce, :vf, :mc, :cu, :at, :orig, :dest,
                         :aj, :cf, :nf, :es)
                """), {
                    'fc': now, 'fm': now,
                    'cn': seed['contacto_nombre'], 'ce': seed['contacto_email'],
                    'vf': seed['valid_from'], 'mc': seed['mercancia'],
                    'cu': seed['customer'], 'at': seed['attn'],
                    'orig': seed['origen'], 'dest': seed['destino'],
                    'aj': json.dumps(seed['aerolineas'], ensure_ascii=False),
                    'cf': json.dumps(seed['cargos_freightwise'], ensure_ascii=False),
                    'nf': seed['notas_freightwise'],
                    'es': 'borrador'
                })
                db.session.commit()
        except Exception:
            db.session.rollback()


# ---------------------------------------------------------------------------
# Excel Online: siembra las hojas iniciales (tarifas por destino) si la
# tabla esta vacia, leyendo lux_portal/excel_online/seed_data.json
# ---------------------------------------------------------------------------
def _seed_excel_online():
    """Inserta las hojas iniciales del modulo Excel Online si no hay ninguna."""
    import json
    import os
    from lux_portal.excel_online.models import ExcelSheet

    if ExcelSheet.query.first() is not None:
        return

    seed_path = os.path.join(os.path.dirname(__file__), 'excel_online', 'seed_data.json')
    if not os.path.exists(seed_path):
        return

    try:
        with open(seed_path, 'r', encoding='utf-8') as f:
            seed_sheets = json.load(f)
        for order, entry in enumerate(seed_sheets):
            sheet = ExcelSheet(name=entry['name'], order=order)
            sheet.headers = entry['headers']
            sheet.rows = entry['rows']
            db.session.add(sheet)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# FSC por aerolinea: valores conocidos al momento de crear la tabla maestra.
# destinos=[] significa "todos los destinos" (regla catch-all para esa aerolinea).
# Aerolineas sin regla fija (Avianca, Delta, Qatar, Air Caribe) se editan caso
# por caso dentro de cada cotizacion, no llevan default aqui.
# ---------------------------------------------------------------------------
_FSC_RULES_SEED = [
    {'aerolinea': 'AIR CANADA', 'nombre': 'Canada', 'destinos': [], 'fsc': '0.16', 'order': 1},
    {'aerolinea': 'AIR CANADA', 'nombre': 'US Northeast', 'destinos': [], 'fsc': '0.16', 'order': 2},
    {'aerolinea': 'AIR CANADA', 'nombre': 'US Midwest', 'destinos': [], 'fsc': '0.16', 'order': 3},
    {'aerolinea': 'AIR CANADA', 'nombre': 'Miami', 'destinos': ['MIA'], 'fsc': '0.12', 'order': 4},
    {'aerolinea': 'AIR CANADA', 'nombre': 'Otros destinos en el mundo', 'destinos': [], 'fsc': '0.30', 'order': 5},
    {'aerolinea': 'LATAM', 'nombre': 'AMS', 'destinos': ['AMS'], 'fsc': '0.08', 'order': 1},
    {'aerolinea': 'EMIRATES', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '0.51', 'order': 1},
    {'aerolinea': 'ATLAS', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '1.05', 'order': 1},
    {'aerolinea': 'AERO MEXICO', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '0.63', 'order': 1},
    {'aerolinea': 'TURKISH', 'nombre': 'AMS', 'destinos': ['AMS'], 'fsc': '0.12', 'order': 1},
    {'aerolinea': 'IBERIA', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '0.14', 'order': 1},
    {'aerolinea': 'LUFTHANSA', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '1.25', 'order': 1},
    {'aerolinea': 'CATHAY', 'nombre': 'Todos los destinos', 'destinos': [], 'fsc': '0.60', 'order': 1},
]


def _seed_fsc_rules():
    """Inserta las reglas de FSC iniciales si la tabla esta vacia."""
    from lux_portal.cotizaciones.models import AirlineFscRule
    import json as _json

    if AirlineFscRule.query.first() is not None:
        return

    try:
        for seed in _FSC_RULES_SEED:
            regla = AirlineFscRule(
                aerolinea=seed['aerolinea'],
                nombre=seed['nombre'],
                fsc=seed['fsc'],
                order=seed['order'],
            )
            regla.destinos_json = _json.dumps(seed['destinos'])
            db.session.add(regla)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# Cargos adicionales fijos por aerolinea, extraidos analizando los cargos
# realmente usados en las 49 cotizaciones de produccion (conceptos y montos
# dominantes). Aerolineas sin cargos detectados (Air Canada, Avianca) no
# llevan fila aqui a proposito.
# ---------------------------------------------------------------------------
_CARGO_RULES_SEED = [
    {'aerolinea': 'AERO MEXICO', 'items': [('CC (Carrier Charges)', '10'), ('Due Carrier', '25')]},
    {'aerolinea': 'AIR CARIBE', 'items': [('Due Carrier', '45')]},
    {'aerolinea': 'AIR EUROPA', 'items': [('CC (Carrier Charges)', '25'), ('CG HAWB C/U', '10'), ('Due Carrier', '25')]},
    {'aerolinea': 'ATLAS', 'items': [('Due Carrier', '25')]},
    {'aerolinea': 'AV/MSC', 'items': [('Due Carrier', '60'), ('Import Fee', '100')]},
    {'aerolinea': 'CATHAY', 'items': [('Due Carrier', '25'), ('Fee', '2.00')]},
    {'aerolinea': 'COPA AIRLINES', 'items': [('Due Carrier', '25'), ('CC (Carrier Charges)', '10'), ('CG HAWB C/U', '5'), ('CG', '5.00'), ('DD', '10.00')]},
    {'aerolinea': 'DELTA', 'items': [('Due Carrier', '25')]},
    {'aerolinea': 'DHL', 'items': [('Due Carrier', '43')]},
    {'aerolinea': 'EMIRATES', 'items': [('Due Carrier', '25'), ('Booking', '25'), ('CC (Carrier Charges)', '10'), ('CG HAWB C/U', '0.25')]},
    {'aerolinea': 'GAL', 'items': [('Due Carrier', '50'), ('Handling', '125')]},
    {'aerolinea': 'IBERIA', 'items': [('Due Carrier', '25'), ('CC (Carrier Charges)', '12'), ('CG HAWB C/U', '2.45')]},
    {'aerolinea': 'LAN', 'items': [('Due Carrier', '43')]},
    {'aerolinea': 'LATAM', 'items': [('Due Carrier', '43')]},
    {'aerolinea': 'LUFTHANSA', 'items': [('Due Carrier', '50'), ('CC (Carrier Charges)', '40')]},
    {'aerolinea': 'MAS AIR', 'items': [('Due Carrier', '43')]},
    {'aerolinea': 'QATAR', 'items': [('Due Carrier', '45'), ('CC (Carrier Charges)', '12'), ('CG HAWB C/U', '3')]},
    {'aerolinea': 'SINGAPORE', 'items': [('Due Carrier', '25')]},
    {'aerolinea': 'SOLENT', 'items': [('Due Carrier', '95'), ('CC (Carrier Charges)', '40'), ('Inspection', '40')]},
    {'aerolinea': 'TURKISH', 'items': [('Due Carrier', '35')]},
]


def _seed_cargo_rules():
    """Inserta los cargos adicionales iniciales si la tabla esta vacia."""
    from lux_portal.cotizaciones.models import AirlineCargoRule

    if AirlineCargoRule.query.first() is not None:
        return

    try:
        for seed in _CARGO_RULES_SEED:
            for order, (concepto, monto) in enumerate(seed['items'], start=1):
                db.session.add(AirlineCargoRule(
                    aerolinea=seed['aerolinea'],
                    concepto=concepto,
                    monto=monto,
                    order=order,
                ))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _migrate_fsc_cargo_groups():
    """Crea las filas de AirlineFscGroup/AirlineCargoGroup que falten para
    aerolineas que ya tienen reglas pero todavia no tienen su 'grupo' (esto
    pasa la primera vez que se despliega esta tabla, ya que es nueva)."""
    from lux_portal.cotizaciones.models import (
        AirlineFscRule, AirlineFscGroup, AirlineCargoRule, AirlineCargoGroup
    )

    try:
        existentes = {g.aerolinea for g in AirlineFscGroup.query.all()}
        for (aerolinea,) in db.session.query(AirlineFscRule.aerolinea).distinct():
            if aerolinea not in existentes:
                db.session.add(AirlineFscGroup(aerolinea=aerolinea))
                existentes.add(aerolinea)
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        existentes = {g.aerolinea for g in AirlineCargoGroup.query.all()}
        for (aerolinea,) in db.session.query(AirlineCargoRule.aerolinea).distinct():
            if aerolinea not in existentes:
                db.session.add(AirlineCargoGroup(aerolinea=aerolinea, notas=''))
                existentes.add(aerolinea)
        db.session.commit()
    except Exception:
        db.session.rollback()
