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
    """Fila de pago (Tabla 3)"""
    __tablename__ = 'status_payments'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    valor = db.Column(db.String(200), default='')
    fecha = db.Column(db.String(200), default='')
    credito = db.Column(db.String(200), default='')
    extra_data = db.Column(db.Text, default='{}')

    def get_extra(self):
        try:
            return json.loads(self.extra_data or '{}')
        except Exception:
            return {}
