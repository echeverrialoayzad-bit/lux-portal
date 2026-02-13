#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos para el modulo de Clientes
"""

from datetime import datetime
from lux_portal.extensions import db
import json


# ============================================================================
# FORMULARIO CUSTOMER ASSOCIATE (FW CUSTOMER ASSOCIATE FORMAT)
# ============================================================================
class CustomerAssociateForm(db.Model):
    """Formulario Customer Associate - Perfil de Cliente/Proveedor"""
    __tablename__ = 'customer_associate_forms'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estado = db.Column(db.String(20), default='borrador')  # borrador, completo

    # GENERAL INFORMATION
    legal_name = db.Column(db.String(300), default='')
    tax_id = db.Column(db.String(100))
    company_type = db.Column(db.String(100))  # public, private, non profit, other
    address = db.Column(db.String(500))
    city_country = db.Column(db.String(200))
    telephone = db.Column(db.String(100))
    email = db.Column(db.String(300))
    website = db.Column(db.String(200))
    business_activity = db.Column(db.Text)
    annual_revenue = db.Column(db.String(100))

    # LEGAL REPRESENTATIVE
    legal_rep_name = db.Column(db.String(200))
    legal_rep_id = db.Column(db.String(100))
    legal_rep_telephone = db.Column(db.String(100))
    legal_rep_email = db.Column(db.String(200))

    # SHAREHOLDERS (JSON array: [{name, id_number}, ...])
    shareholders_data = db.Column(db.Text, default='[]')

    # FINANCIAL AND BANKING
    financial_contact = db.Column(db.Text, default='{}')
    bank_name = db.Column(db.String(200))
    bank_account = db.Column(db.String(100))
    bank_address = db.Column(db.String(300))
    swift_aba = db.Column(db.String(50))

    # ETHICS AND COMPLIANCE (JSON object for checkboxes)
    ethics_data = db.Column(db.Text, default='{}')

    def get_shareholders(self):
        try:
            return json.loads(self.shareholders_data) if self.shareholders_data else []
        except:
            return []

    def set_shareholders(self, shareholders_list):
        self.shareholders_data = json.dumps(shareholders_list, ensure_ascii=False)

    def get_financial_contact(self):
        try:
            data = json.loads(self.financial_contact) if self.financial_contact else {}
            if isinstance(data, dict):
                return data
            # Legacy: old string value, put it as name
            return {'name': str(data), 'emails': [], 'phones': []}
        except:
            # Legacy: plain text value
            return {'name': self.financial_contact or '', 'emails': [], 'phones': []}

    def set_financial_contact(self, contact_dict):
        self.financial_contact = json.dumps(contact_dict, ensure_ascii=False)

    def get_ethics(self):
        try:
            return json.loads(self.ethics_data) if self.ethics_data else {}
        except:
            return {}

    def set_ethics(self, ethics_dict):
        self.ethics_data = json.dumps(ethics_dict, ensure_ascii=False)

    def __repr__(self):
        return f'<CustomerAssociateForm {self.id} - {self.legal_name}>'


# ============================================================================
# FORMULARIO SHIPPING INSTRUCTIONS (FWCustomer Shipping Instructions)
# ============================================================================
class ShippingInstructionsForm(db.Model):
    """Formulario Shipping Instructions"""
    __tablename__ = 'shipping_instructions_forms'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estado = db.Column(db.String(20), default='borrador')

    # CONTACT INFORMATION
    contact_full_name = db.Column(db.String(200), default='')
    contact_job_title = db.Column(db.String(100))
    contact_email = db.Column(db.String(200))
    contact_phone = db.Column(db.String(100))
    contact_whatsapp = db.Column(db.String(100))

    # BILLING & PAYMENT
    billing_address = db.Column(db.Text)
    billing_emails = db.Column(db.Text)  # Multiple emails, one per line

    # ADDITIONAL INFORMATION
    uses_customs_broker = db.Column(db.String(200))
    customs_broker_info = db.Column(db.String(300))
    customs_broker_emails = db.Column(db.Text)
    api_required = db.Column(db.String(100))

    # REQUESTED DOCUMENTS (JSON: {invoice: bool, coa: bool, phyto: bool, ...})
    documents_data = db.Column(db.Text, default='{}')

    # SUPPLIERS (JSON array)
    suppliers_data = db.Column(db.Text, default='[]')

    def get_documents(self):
        try:
            return json.loads(self.documents_data) if self.documents_data else {}
        except:
            return {}

    def set_documents(self, docs_dict):
        self.documents_data = json.dumps(docs_dict, ensure_ascii=False)

    def get_suppliers(self):
        try:
            return json.loads(self.suppliers_data) if self.suppliers_data else []
        except:
            return []

    def set_suppliers(self, suppliers_list):
        self.suppliers_data = json.dumps(suppliers_list, ensure_ascii=False)

    def __repr__(self):
        return f'<ShippingInstructionsForm {self.id} - {self.contact_full_name}>'


class Cliente(db.Model):
    """Modelo para clientes"""
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)  # Ej: AKK
    nombre = db.Column(db.String(200), nullable=False)
    ruta_principal = db.Column(db.String(50), default='')  # Ej: UIO-AMS
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)

    # Relacion con la planilla
    planilla = db.relationship('ClientePlanilla', backref='cliente', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Cliente {self.codigo}>'


class ClientePlanilla(db.Model):
    """Planilla de datos del cliente (storage tracking)"""
    __tablename__ = 'cliente_planillas'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)

    # Datos de la tabla de rutas/tarifas (JSON array)
    rutas_data = db.Column(db.Text, default='[]')

    # Datos de calculos (JSON object)
    calculos_data = db.Column(db.Text, default='{}')

    # Notas
    notas = db.Column(db.Text, default='')

    # Info bancaria (compartida pero editable por cliente)
    banco = db.Column(db.String(100), default='Banco Pichincha')
    swift = db.Column(db.String(50), default='PICHECEQXXX')
    cuenta = db.Column(db.String(50), default='2100339784')
    empresa = db.Column(db.String(200), default='FREIGHTWISE FORWARDING S.A')
    tax_id = db.Column(db.String(50), default='1793230131001')
    direccion = db.Column(db.String(300), default='Pedro de Alfaro y Francisco Ruiz')

    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_rutas(self):
        """Retorna las rutas como lista de diccionarios"""
        try:
            return json.loads(self.rutas_data) if self.rutas_data else []
        except:
            return []

    def set_rutas(self, rutas_list):
        """Guarda las rutas desde una lista de diccionarios"""
        self.rutas_data = json.dumps(rutas_list, ensure_ascii=False)

    def get_calculos(self):
        """Retorna los calculos como diccionario"""
        try:
            return json.loads(self.calculos_data) if self.calculos_data else {}
        except:
            return {}

    def set_calculos(self, calculos_dict):
        """Guarda los calculos desde un diccionario"""
        self.calculos_data = json.dumps(calculos_dict, ensure_ascii=False)

    def __repr__(self):
        return f'<ClientePlanilla cliente_id={self.cliente_id}>'


# ============================================================================
# FORMULARIO FREIGHT QUOTE (Cotizacion de Flete)
# ============================================================================
class FreightQuoteForm(db.Model):
    """Formulario de Cotizacion de Flete FreightWise"""
    __tablename__ = 'freight_quote_forms'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estado = db.Column(db.String(20), default='borrador')

    # RUTA Y PESOS
    ruta = db.Column(db.String(50))  # Ej: UIO-BKK
    net_weight = db.Column(db.Float, default=0)
    volume_weight = db.Column(db.Float, default=0)
    rate = db.Column(db.Float, default=0)
    weight_x_rate = db.Column(db.Float, default=0)

    # CARGOS
    due_agent = db.Column(db.Float, default=0)
    due_carrier = db.Column(db.Float, default=0)
    certificate = db.Column(db.Float, default=0)
    phyto = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

    # NOTAS
    notes = db.Column(db.Text, default='')

    # CUENTA BANCARIA
    bank_name = db.Column(db.String(100), default='Banco Pichincha')
    bank_swift = db.Column(db.String(50), default='PICHECEQXXX')
    bank_account = db.Column(db.String(50), default='2100339784')
    company_name = db.Column(db.String(200), default='FREIGHTWISE FORWARDING S.A')
    tax_id = db.Column(db.String(50), default='1793230131001')
    company_address = db.Column(db.String(300), default='Pedro de Alfaro y Francisco Ruiz')

    def calculate_totals(self):
        """Calcula weight_x_rate y total"""
        # Usar el mayor entre net_weight y volume_weight
        chargeable_weight = max(self.net_weight or 0, self.volume_weight or 0)
        self.weight_x_rate = round(chargeable_weight * (self.rate or 0), 2)
        self.total = round(
            self.weight_x_rate +
            (self.due_agent or 0) +
            (self.due_carrier or 0) +
            (self.certificate or 0) +
            (self.phyto or 0),
            2
        )

    def __repr__(self):
        return f'<FreightQuoteForm {self.id} - {self.ruta}>'


# ============================================================================
# FORMULARIO PAYMENT / INVOICE
# ============================================================================
class PaymentInfoForm(db.Model):
    """Invoice - Factura FreightWise"""
    __tablename__ = 'payment_info_forms'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    estado = db.Column(db.String(20), default='borrador')
    label = db.Column(db.String(200), default='')

    # HEADER
    invoice_date = db.Column(db.String(50), default='')
    expiration_date = db.Column(db.String(50), default='')
    invoice_number = db.Column(db.String(50), default='')
    customer_id_code = db.Column(db.String(50), default='')
    date_from = db.Column(db.String(50), default='')
    date_to = db.Column(db.String(50), default='')

    # CUSTOMER
    customer_name = db.Column(db.String(300), default='')
    customer_address = db.Column(db.Text, default='')

    # SHIPMENT INFO
    peso = db.Column(db.String(50), default='')
    moneda = db.Column(db.String(10), default='USD')
    aerolinea = db.Column(db.String(100), default='')
    tarifa = db.Column(db.String(50), default='')
    origen = db.Column(db.String(10), default='UIO')
    destino = db.Column(db.String(50), default='')
    tarifa_iva = db.Column(db.String(10), default='0%')

    # LINE ITEMS (JSON array: [{date, units, description, rate, amount, total}, ...])
    line_items = db.Column(db.Text, default='[]')

    # TERMS
    full_count = db.Column(db.String(20), default='0')
    pieces_count = db.Column(db.String(20), default='0')
    awb = db.Column(db.String(50), default='')
    gross_weight = db.Column(db.String(20), default='')

    # BANK INFO (FreightWise - pre-filled)
    fw_bank = db.Column(db.String(200), default='BANCO DEL PICHINCHA')
    fw_swift = db.Column(db.String(50), default='PICHECEQXXX')
    fw_account = db.Column(db.String(50), default='2100339784')
    fw_tax_id = db.Column(db.String(50), default='1793230131001')
    fw_company = db.Column(db.String(200), default='FREIGHTWISE FORWARDING S.A.')

    # TOTALS (right side)
    subtotal = db.Column(db.String(50), default='')
    taxable = db.Column(db.String(50), default='')
    tax_rate_vat = db.Column(db.String(20), default='0.000%')
    tax = db.Column(db.String(50), default='')
    other_charges = db.Column(db.String(50), default='')
    insurance = db.Column(db.String(50), default='')
    legal_consular = db.Column(db.String(50), default='')
    inspection_cert = db.Column(db.String(50), default='')
    other_specify = db.Column(db.String(50), default='')
    total = db.Column(db.String(50), default='')
    currency = db.Column(db.String(10), default='USD')

    # ADDITIONAL
    reason_for_export = db.Column(db.String(200), default='Fresh Flowers')

    def get_line_items(self):
        try:
            return json.loads(self.line_items) if self.line_items else []
        except:
            return []

    def set_line_items(self, items):
        self.line_items = json.dumps(items, ensure_ascii=False)

    def __repr__(self):
        return f'<PaymentInfoForm {self.id} - {self.invoice_number}>'


# Estructura por defecto de una fila de ruta
RUTA_TEMPLATE = {
    'airline': '',
    'awc': '',
    'date': '',
    'origin': '',
    'destiny': '',
    'total_kg_per_day': '',
    'pieces': '',
    'kg': '',
    'additional_kg': '',
    'net_rate': '',
    'valentine_increase': '',
    'operative_cost': '',
    'net_plus_costs': '',
    'profit': '',
    'selling_rate': '',
    'update_status': '',
    'client_approval': '',
    'departure': '',
    'en_route_status': '',
    'arrival': '',
    'important_notes': '',
    'alert': ''
}

# Estructura por defecto de calculos
CALCULOS_TEMPLATE = {
    'ruta_calculo': '',  # Ej: UIO-BKK
    'net_weight': '',
    'volume_weight': '',
    'rate': '',
    'weight_x_rate': '',
    'due_agent': '',
    'due_carrier': '',
    'certificate': '',
    'phyto': '',
    'total': ''
}
