#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelo de Cotizacion
"""

from datetime import datetime
import json
from lux_portal.extensions import db


class Cotizacion(db.Model):
    """Modelo para almacenar cotizaciones."""
    __tablename__ = 'cotizaciones'

    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Informacion general
    contacto_nombre = db.Column(db.String(200), default='Daniela Echeverria')
    contacto_email = db.Column(db.String(200), default='daniela.echeverria@freight-wise.com')
    valid_from = db.Column(db.String(50))
    mercancia = db.Column(db.String(200), default='FRESH CUT FLOWERS')
    customer = db.Column(db.String(200))
    attn = db.Column(db.String(200))
    origen = db.Column(db.String(10))
    destino = db.Column(db.String(10))

    # Datos JSON para aerolineas (guardamos todo en JSON para flexibilidad)
    aerolineas_json = db.Column(db.Text)

    # Cargos fijos FreightWise (editables) y notas
    cargos_freightwise_json = db.Column(db.Text)
    notas_freightwise = db.Column(db.Text)

    # Estado
    estado = db.Column(db.String(50), default='borrador')  # borrador, enviada, aceptada, rechazada

    @property
    def ruta(self):
        return f"{self.origen or ''}-{self.destino or ''}"

    @property
    def aerolineas(self):
        if self.aerolineas_json:
            return json.loads(self.aerolineas_json)
        return []

    @aerolineas.setter
    def aerolineas(self, value):
        self.aerolineas_json = json.dumps(value, ensure_ascii=False)

    @property
    def cargos_freightwise(self):
        if self.cargos_freightwise_json:
            return json.loads(self.cargos_freightwise_json)
        return None

    @cargos_freightwise.setter
    def cargos_freightwise(self, value):
        self.cargos_freightwise_json = json.dumps(value, ensure_ascii=False) if value else None

    def to_dict(self):
        """Convierte la cotizacion a diccionario."""
        return {
            'id': self.id,
            'fecha_creacion': self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_creacion else None,
            'fecha_modificacion': self.fecha_modificacion.strftime('%Y-%m-%d %H:%M:%S') if self.fecha_modificacion else None,
            'contacto_nombre': self.contacto_nombre,
            'contacto_email': self.contacto_email,
            'valid_from': self.valid_from,
            'mercancia': self.mercancia,
            'customer': self.customer,
            'attn': self.attn,
            'origen': self.origen,
            'destino': self.destino,
            'ruta': self.ruta,
            'aerolineas': self.aerolineas,
            'cargos_freightwise': self.cargos_freightwise,
            'notas_freightwise': self.notas_freightwise,
            'estado': self.estado
        }


class AirlineFscRule(db.Model):
    """Regla de FSC por aerolinea. Una aerolinea puede tener varias reglas:
    una por destino/region especifica (destinos_json no vacio) y opcionalmente
    una regla 'catch-all' (destinos_json == []) que aplica a cualquier destino
    que no calce con ninguna regla especifica."""
    __tablename__ = 'cotizacion_fsc_rules'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    destinos_json = db.Column(db.Text, default='[]')
    fsc = db.Column(db.String(20), default='0.00')
    order = db.Column(db.Integer, default=0)

    @property
    def destinos(self):
        return json.loads(self.destinos_json) if self.destinos_json else []

    @destinos.setter
    def destinos(self, value):
        self.destinos_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'aerolinea': self.aerolinea,
            'nombre': self.nombre,
            'destinos': self.destinos,
            'fsc': self.fsc,
            'order': self.order,
        }
