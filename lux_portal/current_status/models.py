import json
from datetime import datetime
from lux_portal.extensions import db


class StatusClient(db.Model):
    """Cliente para seguimiento de estado de envios"""
    __tablename__ = 'status_clients'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente / finalizado
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)
    custom_columns = db.Column(db.Text, default='{}')

    rates = db.relationship('AirlineRate', backref='client', cascade='all, delete-orphan',
                            order_by='AirlineRate.id')
    airlines = db.relationship('StatusAirline', backref='client', cascade='all, delete-orphan',
                               order_by='StatusAirline.id')
    payments = db.relationship('StatusPayment', backref='client', cascade='all, delete-orphan',
                               order_by='StatusPayment.id')
    shipments = db.relationship('ClientShipment', backref='client', cascade='all, delete-orphan',
                                order_by='ClientShipment.id')

    def get_custom_cols(self, table_type):
        try:
            return json.loads(self.custom_columns or '{}').get(table_type, [])
        except Exception:
            return []


class AirlineRate(db.Model):
    """Fila de tarifa de aerolinea (Tabla 1)"""
    __tablename__ = 'airline_rates'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    airline = db.Column(db.String(200), default='')
    route = db.Column(db.String(300), default='')
    transit_time = db.Column(db.String(100), default='')
    kg_availability = db.Column(db.String(100), default='')
    date = db.Column(db.String(200), default='')
    net_rate = db.Column(db.String(100), default='')
    operative = db.Column(db.String(100), default='')
    net_ops = db.Column(db.String(100), default='')
    profit = db.Column(db.String(100), default='')
    final_rate = db.Column(db.String(100), default='')
    additional_costs = db.Column(db.String(200), default='')
    additional_costs_value = db.Column(db.String(200), default='')
    notes = db.Column(db.String(500), default='')
    extra_data = db.Column(db.Text, default='{}')

    def get_extra(self):
        try:
            return json.loads(self.extra_data or '{}')
        except Exception:
            return {}


class StatusAirline(db.Model):
    """Fila de estado actual por aerolinea (Tabla 2)"""
    __tablename__ = 'status_airlines'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    current_status = db.Column(db.String(200), default='')
    proximo_vuelo = db.Column(db.String(200), default='')
    kg = db.Column(db.String(200), default='')
    entrega_fincas = db.Column(db.String(200), default='')
    hora_maxima = db.Column(db.String(200), default='')
    aerolinea = db.Column(db.String(200), default='')
    all_in_rate = db.Column(db.String(200), default='')
    extra_data = db.Column(db.Text, default='{}')

    def get_extra(self):
        try:
            return json.loads(self.extra_data or '{}')
        except Exception:
            return {}


class StatusPayment(db.Model):
    """Fila de pago / invoice (Tabla 3)"""
    __tablename__ = 'status_payments'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    # Legacy columns (kept for backward compat)
    valor = db.Column(db.String(200), default='')
    fecha = db.Column(db.String(200), default='')
    credito = db.Column(db.String(200), default='')
    # New invoice fields
    route = db.Column(db.String(200), default='')
    net_weight = db.Column(db.String(100), default='')
    volume_weight = db.Column(db.String(100), default='')
    rate = db.Column(db.String(100), default='')
    pay_due_agent = db.Column(db.String(100), default='50')
    pay_due_carrier = db.Column(db.String(100), default='25')
    certificate = db.Column(db.String(100), default='15')
    pay_phyto = db.Column(db.String(100), default='2.50')
    pay_notes = db.Column(db.Text, default='')
    extra_data = db.Column(db.Text, default='{}')

    def get_extra(self):
        try:
            return json.loads(self.extra_data or '{}')
        except Exception:
            return {}


class ClientShipment(db.Model):
    """Fila de embarque por cliente (Tabla 4 - datos de embarque)"""
    __tablename__ = 'client_shipments'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    # Shipment fields
    ship_date = db.Column(db.String(100), default='')
    mark = db.Column(db.String(100), default='')
    awb = db.Column(db.String(100), default='')
    client_name = db.Column(db.String(200), default='')
    origin = db.Column(db.String(100), default='')
    destination = db.Column(db.String(100), default='')
    airline = db.Column(db.String(200), default='')
    fulles = db.Column(db.String(100), default='')
    piezas = db.Column(db.String(100), default='')
    pieces_gross = db.Column(db.String(100), default='')
    volume = db.Column(db.String(100), default='')
    charge = db.Column(db.String(100), default='')
    phyto = db.Column(db.String(100), default='')
    dup_phyto = db.Column(db.String(100), default='')
    c_origin = db.Column(db.String(100), default='')
    dup_co = db.Column(db.String(100), default='')
    termografo = db.Column(db.String(100), default='')
    transmision = db.Column(db.String(100), default='')
    transport = db.Column(db.String(100), default='')
    # Facturacion fields
    flete = db.Column(db.String(100), default='')
    fsc = db.Column(db.String(100), default='')
    esc = db.Column(db.String(100), default='')
    due_agent = db.Column(db.String(100), default='')
    due_carrier = db.Column(db.String(100), default='')
    fito_venta = db.Column(db.String(100), default='')
    co_venta = db.Column(db.String(100), default='')
    termografo_venta = db.Column(db.String(100), default='')
    fitos_venta = db.Column(db.String(100), default='')
    dup_fito_venta = db.Column(db.String(100), default='')
    co_factura = db.Column(db.String(100), default='')
    dup_co_factura = db.Column(db.String(100), default='')
    transmision_factura = db.Column(db.String(100), default='')
    beneficio = db.Column(db.String(100), default='')
    beneficio_x_kg = db.Column(db.String(100), default='')
    facturacion = db.Column(db.String(100), default='')
    handling_juni = db.Column(db.String(100), default='')
    termografo_factura = db.Column(db.String(100), default='')
    # Costos fields
    costos = db.Column(db.String(100), default='')
    costo_bodega = db.Column(db.String(100), default='')
    costo_guia = db.Column(db.String(100), default='')
    flete_costo = db.Column(db.String(100), default='')
    due_carrier_costo = db.Column(db.String(100), default='')
    fsc_costo = db.Column(db.String(100), default='')
    esc_costo = db.Column(db.String(100), default='')
    costo_x_kg = db.Column(db.String(100), default='')
    costo_bod_unit = db.Column(db.String(100), default='')
    costo_guia_unit = db.Column(db.String(100), default='')
    fito_costo_unit = db.Column(db.String(100), default='')
    co_costo_unit = db.Column(db.String(100), default='')
    termografo_costo_unit = db.Column(db.String(100), default='')
    fitos_costo = db.Column(db.String(100), default='')
    dup_fitos_costo = db.Column(db.String(100), default='')
    termografo_costo = db.Column(db.String(100), default='')
    co_costo = db.Column(db.String(100), default='')
    dup_co_costo = db.Column(db.String(100), default='')
    transmision_costo = db.Column(db.String(100), default='')
    costos_fijos = db.Column(db.String(100), default='')
    utilidad = db.Column(db.String(100), default='')

    def __repr__(self):
        return f'<ClientShipment {self.id} client={self.client_id}>'


class ShipmentHistory(db.Model):
    """Historial de embarques enviados"""
    __tablename__ = 'shipment_history'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    client_name = db.Column(db.String(200), default='')
    shipment_count = db.Column(db.Integer, default=0)
    shipment_data = db.Column(db.Text, default='[]')  # JSON snapshot of shipments sent
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('StatusClient', backref=db.backref('shipment_history', lazy='dynamic'))

    def get_shipments(self):
        try:
            return json.loads(self.shipment_data or '[]')
        except Exception:
            return []

    def __repr__(self):
        return f'<ShipmentHistory {self.client_name} count={self.shipment_count}>'


class StatusTable(db.Model):
    """Tabla de status personalizada por cliente"""
    __tablename__ = 'status_tables'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    title = db.Column(db.String(300), default='STATUS')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('StatusClient', backref=db.backref('status_tables', cascade='all, delete-orphan', order_by='StatusTable.id'))
    rows = db.relationship('StatusTableRow', backref='table', cascade='all, delete-orphan', order_by='StatusTableRow.id')


class StatusTableRow(db.Model):
    """Fila de una tabla de status"""
    __tablename__ = 'status_table_rows'

    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('status_tables.id'), nullable=False)
    awb = db.Column(db.String(200), default='')
    vuelo = db.Column(db.String(200), default='')
    itinerary = db.Column(db.String(300), default='')
    etd_date = db.Column(db.String(100), default='')
    etd_time = db.Column(db.String(100), default='')
    eta_date = db.Column(db.String(100), default='')
    eta_time = db.Column(db.String(100), default='')
    pcs = db.Column(db.String(100), default='')
    kg = db.Column(db.String(100), default='')
    status = db.Column(db.String(300), default='')
    status_color = db.Column(db.String(20), default='green')
