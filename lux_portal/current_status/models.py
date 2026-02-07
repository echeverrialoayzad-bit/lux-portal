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

    airlines = db.relationship('StatusAirline', backref='client', cascade='all, delete-orphan',
                               order_by='StatusAirline.id')
    payments = db.relationship('StatusPayment', backref='client', cascade='all, delete-orphan',
                               order_by='StatusPayment.id')


class StatusAirline(db.Model):
    """Fila de aerolinea en la tabla Current Status"""
    __tablename__ = 'status_airlines'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    current_status = db.Column(db.String(200), default='')
    proximo_vuelo = db.Column(db.String(200), default='')
    entrega_fincas = db.Column(db.String(200), default='')
    hora_maxima = db.Column(db.String(200), default='')
    aerolinea = db.Column(db.String(200), default='')
    awb = db.Column(db.String(200), default='')
    itinerario = db.Column(db.String(500), default='')
    eta = db.Column(db.String(200), default='')


class StatusPayment(db.Model):
    """Fila de pago en la tabla Payment"""
    __tablename__ = 'status_payments'

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('status_clients.id'), nullable=False)
    valor = db.Column(db.String(200), default='')
    fecha = db.Column(db.String(200), default='')
    credito = db.Column(db.String(200), default='')
