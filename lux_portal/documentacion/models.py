#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos de Documentacion y Verificacion
"""

from datetime import datetime
from lux_portal.extensions import db


# Tipos de documento fijos que debe tener cada cliente. El orden aqui define
# el orden en que se muestran en la carpeta del cliente.
TIPOS_DOCUMENTO = [
    ('customer_associate_format', 'Customer Associate Format',
     'Formulario de FreightWise llenado por el cliente, con firma del representante legal.'),
    ('shipping_instructions', 'Shipping Instructions',
     'Formulario de instrucciones de envio llenado por el cliente.'),
    ('cedula_representante', 'Cedula del Representante Legal',
     'Para confirmar que la firma del Customer Associate Format es la misma.'),
    ('tax_id_ruc', 'Tax ID / RUC',
     'Identificacion tributaria del cliente, en PDF.'),
    ('certificado_bancario', 'Certificado Bancario', ''),
]
TIPOS_DOCUMENTO_KEYS = [t[0] for t in TIPOS_DOCUMENTO]
TIPOS_DOCUMENTO_NOMBRES = {t[0]: t[1] for t in TIPOS_DOCUMENTO}

# Tipo especial para documentos que no son ninguno de los 5 esenciales, pero
# que igual se guardan (con su propio titulo descriptivo en vez de un tipo fijo).
TIPO_EXTRA = 'extra'


class DocCliente(db.Model):
    """Una carpeta de cliente."""
    __tablename__ = 'doc_clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False, unique=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Resultado de la verificacion de firma asistida por IA (compara
    # customer_associate_format vs cedula_representante). None = todavia no
    # se ha corrido la verificacion.
    firma_verificada = db.Column(db.Boolean)
    firma_verificacion_detalle = db.Column(db.Text)
    firma_verificacion_fecha = db.Column(db.DateTime)

    archivos = db.relationship('DocArchivo', backref='cliente', cascade='all, delete-orphan',
                                order_by='DocArchivo.fecha_subida.desc()')

    def archivos_por_tipo(self):
        """Ultimo archivo vigente por cada uno de los 5 tipos esenciales
        (checklist), como dict tipo -> DocArchivo|None."""
        resultado = {tipo: None for tipo in TIPOS_DOCUMENTO_KEYS}
        for a in self.archivos:
            if a.tipo in resultado and resultado[a.tipo] is None:
                resultado[a.tipo] = a
        return resultado

    def archivos_extra(self):
        """Todos los documentos adicionales (no esenciales), los mas
        recientes primero. A diferencia de los 5 esenciales, aqui se
        acumulan todos, no se reemplazan."""
        return [a for a in self.archivos if a.tipo == TIPO_EXTRA]

    def completos(self):
        presentes = self.archivos_por_tipo()
        return sum(1 for v in presentes.values() if v is not None)

    def to_dict(self):
        presentes = self.archivos_por_tipo()
        return {
            'id': self.id,
            'nombre': self.nombre,
            'completos': self.completos(),
            'total': len(TIPOS_DOCUMENTO_KEYS),
            'firma_verificada': self.firma_verificada,
            'archivos': {tipo: (a.to_dict() if a else None) for tipo, a in presentes.items()},
            'archivos_extra': [a.to_dict() for a in self.archivos_extra()],
        }


class DocArchivo(db.Model):
    """Un archivo subido para un cliente/tipo de documento. El contenido se
    guarda como bytes en la base de datos (el filesystem de Railway no es
    persistente entre despliegues)."""
    __tablename__ = 'doc_archivos'

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('doc_clientes.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    titulo_extra = db.Column(db.String(200))  # solo se usa cuando tipo == TIPO_EXTRA
    nombre_archivo = db.Column(db.String(300))
    mimetype = db.Column(db.String(100))
    contenido = db.Column(db.LargeBinary, nullable=False)
    fecha_subida = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'titulo_extra': self.titulo_extra,
            'nombre_archivo': self.nombre_archivo,
            'mimetype': self.mimetype,
            'fecha_subida': self.fecha_subida.strftime('%Y-%m-%d %H:%M') if self.fecha_subida else None,
        }
