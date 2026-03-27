#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime
import json
from lux_portal.extensions import db


class CotizacionFruta(db.Model):
    __tablename__ = 'cotizaciones_fruta'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacto_nombre = db.Column(db.String(200), default='Daniela Echeverria')
    contacto_email  = db.Column(db.String(200), default='daniela.echeverria@freight-wise.com')
    valid_from  = db.Column(db.String(50))
    mercancia   = db.Column(db.String(200), default='FRESH FRUIT')
    customer    = db.Column(db.String(200))
    attn        = db.Column(db.String(200))
    origen      = db.Column(db.String(10))
    destino     = db.Column(db.String(10))

    aerolineas_json          = db.Column(db.Text)
    cargos_freightwise_json  = db.Column(db.Text)
    notas_freightwise        = db.Column(db.Text)
    estado = db.Column(db.String(50), default='borrador')

    @property
    def ruta(self):
        return f"{self.origen or ''}-{self.destino or ''}"

    @property
    def aerolineas(self):
        return json.loads(self.aerolineas_json) if self.aerolineas_json else []

    @aerolineas.setter
    def aerolineas(self, value):
        self.aerolineas_json = json.dumps(value, ensure_ascii=False)

    @property
    def cargos_freightwise(self):
        return json.loads(self.cargos_freightwise_json) if self.cargos_freightwise_json else None

    @cargos_freightwise.setter
    def cargos_freightwise(self, value):
        self.cargos_freightwise_json = json.dumps(value, ensure_ascii=False) if value else None

    def to_dict(self):
        return {
            'id': self.id,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else None,
            'fecha_modificacion': self.fecha_modificacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_modificacion else None,
            'contacto_nombre': self.contacto_nombre,
            'contacto_email':  self.contacto_email,
            'valid_from': self.valid_from,
            'mercancia':  self.mercancia,
            'customer':   self.customer,
            'attn':       self.attn,
            'origen':     self.origen,
            'destino':    self.destino,
            'ruta':       self.ruta,
            'aerolineas': self.aerolineas,
            'cargos_freightwise':  self.cargos_freightwise,
            'notas_freightwise':   self.notas_freightwise,
            'estado': self.estado,
        }
