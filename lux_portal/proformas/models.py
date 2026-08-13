import json
from datetime import datetime
from lux_portal.extensions import db


class Proforma(db.Model):
    __tablename__ = 'proformas'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), unique=True, nullable=False)
    customer = db.Column(db.String(200), default='')
    customer_id = db.Column(db.String(100), default='')
    fecha = db.Column(db.String(20))
    fecha_desde = db.Column(db.String(20))
    fecha_hasta = db.Column(db.String(20))
    peso = db.Column(db.Numeric(12, 2), default=0)
    tarifa = db.Column(db.Numeric(10, 4), default=0)
    aerolinea = db.Column(db.String(100), default='')
    moneda = db.Column(db.String(10), default='USD')
    origen = db.Column(db.String(10), default='UIO')
    destino = db.Column(db.String(10), default='')
    descripcion = db.Column(db.String(500), default='Fresh Flowers')
    comentarios = db.Column(db.Text, default='')
    cargos_json = db.Column(db.Text, default='[]')
    estado = db.Column(db.String(20), default='borrador')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def cargos(self):
        try:
            return json.loads(self.cargos_json or '[]')
        except Exception:
            return []

    @cargos.setter
    def cargos(self, value):
        self.cargos_json = json.dumps(value or [])

    @property
    def flete(self):
        return float(self.peso or 0) * float(self.tarifa or 0)

    @property
    def total_cargos(self):
        return sum(c.get('total', 0) for c in self.cargos if c.get('activo'))

    @property
    def total(self):
        return self.flete + self.total_cargos

    def to_dict(self):
        return {
            'id': self.id,
            'numero': self.numero,
            'customer': self.customer,
            'customer_id': self.customer_id,
            'fecha': self.fecha,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'peso': float(self.peso or 0),
            'tarifa': float(self.tarifa or 0),
            'aerolinea': self.aerolinea,
            'moneda': self.moneda,
            'origen': self.origen,
            'destino': self.destino,
            'descripcion': self.descripcion,
            'comentarios': self.comentarios,
            'cargos': self.cargos,
            'estado': self.estado,
            'flete': self.flete,
            'total': self.total,
        }
