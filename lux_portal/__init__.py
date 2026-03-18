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
        _seed_cotizaciones()

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
