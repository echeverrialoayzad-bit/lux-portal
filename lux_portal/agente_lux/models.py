#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modelos del modulo Agente Lux.

Flujo: la cuenta de Microsoft 365 se conecta una vez (AgenteCuenta), el
refresh del portal baja correos nuevos (AgenteMail + AgenteAdjunto), el
analisis local con Claude Code escribe los cambios propuestos
(AgenteHallazgo) y recien cuando Daniela aprueba se tocan las cotizaciones
o las reglas de FSC.
"""

from datetime import datetime
import json
from lux_portal.extensions import db


class AgenteCuenta(db.Model):
    """Cuenta de correo Microsoft 365 conectada. Se espera una sola fila.

    El refresh_token es lo unico que hay que conservar: el access_token se
    renueva solo a partir de el y dura ~1 hora."""
    __tablename__ = 'agente_cuenta'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250))
    refresh_token = db.Column(db.Text)
    access_token = db.Column(db.Text)
    token_expira = db.Column(db.DateTime)
    conectada_en = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_scan = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'conectada_en': self.conectada_en.strftime('%Y-%m-%d %H:%M') if self.conectada_en else None,
            'ultimo_scan': self.ultimo_scan.strftime('%Y-%m-%d %H:%M') if self.ultimo_scan else None,
        }


class AgenteMail(db.Model):
    """Un correo bajado de Microsoft Graph.

    estado: 'pendiente' (bajado, sin analizar) -> 'analizado' -> se queda ahi.
    'ignorado' es para correos que el analisis marco como irrelevantes."""
    __tablename__ = 'agente_mails'

    id = db.Column(db.Integer, primary_key=True)
    graph_id = db.Column(db.String(400), unique=True, index=True)
    fecha = db.Column(db.DateTime, index=True)
    remitente = db.Column(db.String(250))
    remitente_nombre = db.Column(db.String(250))
    asunto = db.Column(db.String(500))
    cuerpo = db.Column(db.Text)
    web_link = db.Column(db.Text)

    estado = db.Column(db.String(30), default='pendiente', index=True)

    # Resultado del analisis
    categoria = db.Column(db.String(50))          # tarifas | fsc | operativo | comercial | otro
    resumen = db.Column(db.Text)                  # de que se hablo, en una o dos frases
    temas_json = db.Column(db.Text, default='[]')  # ["Pendiente confirmar booking MAD", ...]
    requiere_accion = db.Column(db.Boolean, default=False)
    analizado_en = db.Column(db.DateTime)

    adjuntos = db.relationship('AgenteAdjunto', backref='mail',
                               cascade='all, delete-orphan', lazy='select')

    @property
    def temas(self):
        try:
            return json.loads(self.temas_json) if self.temas_json else []
        except (ValueError, TypeError):
            return []

    @temas.setter
    def temas(self, value):
        self.temas_json = json.dumps(value or [], ensure_ascii=False)

    def to_dict(self, con_adjuntos=False):
        d = {
            'id': self.id,
            'fecha': self.fecha.strftime('%Y-%m-%d %H:%M') if self.fecha else None,
            'dia': self.fecha.strftime('%Y-%m-%d') if self.fecha else None,
            'remitente': self.remitente,
            'remitente_nombre': self.remitente_nombre or self.remitente,
            'asunto': self.asunto,
            'estado': self.estado,
            'categoria': self.categoria,
            'resumen': self.resumen,
            'temas': self.temas,
            'requiere_accion': bool(self.requiere_accion),
            'web_link': self.web_link,
            'n_adjuntos': len(self.adjuntos),
        }
        if con_adjuntos:
            d['cuerpo'] = self.cuerpo
            d['adjuntos'] = [a.to_dict(con_contenido=True) for a in self.adjuntos]
        return d


class AgenteAdjunto(db.Model):
    """Adjunto de un correo. Solo se guarda el contenido de imagenes y PDF
    (que son los que traen tarifas); el resto queda como referencia."""
    __tablename__ = 'agente_adjuntos'

    id = db.Column(db.Integer, primary_key=True)
    mail_id = db.Column(db.Integer, db.ForeignKey('agente_mails.id'), index=True)
    nombre = db.Column(db.String(400))
    mime = db.Column(db.String(150))
    size = db.Column(db.Integer, default=0)
    contenido_b64 = db.Column(db.Text)

    def to_dict(self, con_contenido=False):
        d = {
            'id': self.id,
            'nombre': self.nombre,
            'mime': self.mime,
            'size': self.size,
            'tiene_contenido': bool(self.contenido_b64),
        }
        if con_contenido:
            d['contenido_b64'] = self.contenido_b64
        return d


class AgenteHallazgo(db.Model):
    """Un cambio propuesto por el analisis, pendiente de aprobacion.

    tipo:
      'tarifa' -> detalle {cot_id, kg, tarifa_actual, tarifa_nueva}
      'fsc'    -> detalle {regla_id|None, aerolinea, nombre, destinos[], fsc_actual, fsc_nuevo}
      'cargo'  -> detalle {aerolinea, concepto, monto_actual, monto_nuevo}
      'dias'   -> detalle {aerolinea, dias_actual[], dias_nuevo[]}  (nunca se auto-aplica)
      'info'   -> solo informativo, no se aplica

    destino == '' en un hallazgo de FSC significa la regla catch-all
    (todos los destinos de esa aerolinea)."""
    __tablename__ = 'agente_hallazgos'

    id = db.Column(db.Integer, primary_key=True)
    mail_id = db.Column(db.Integer, db.ForeignKey('agente_mails.id'), index=True)
    tipo = db.Column(db.String(20), default='tarifa', index=True)
    aerolinea = db.Column(db.String(100))
    destino = db.Column(db.String(20), default='')
    descripcion = db.Column(db.Text)
    valor_actual = db.Column(db.String(50))
    valor_nuevo = db.Column(db.String(50))
    detalle_json = db.Column(db.Text, default='{}')
    confianza = db.Column(db.String(20), default='media')   # alta | media | baja
    cita = db.Column(db.Text)          # fragmento del correo que lo respalda
    alerta = db.Column(db.Text)        # regla de negocio en riesgo, si aplica
    estado = db.Column(db.String(20), default='pendiente', index=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    aplicado_en = db.Column(db.DateTime)
    error = db.Column(db.Text)

    mail = db.relationship('AgenteMail', backref='hallazgos')

    @property
    def detalle(self):
        try:
            return json.loads(self.detalle_json) if self.detalle_json else {}
        except (ValueError, TypeError):
            return {}

    @detalle.setter
    def detalle(self, value):
        self.detalle_json = json.dumps(value or {}, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'mail_id': self.mail_id,
            'mail_asunto': self.mail.asunto if self.mail else None,
            'mail_remitente': (self.mail.remitente_nombre or self.mail.remitente) if self.mail else None,
            'mail_fecha': self.mail.fecha.strftime('%Y-%m-%d %H:%M') if (self.mail and self.mail.fecha) else None,
            'tipo': self.tipo,
            'aerolinea': self.aerolinea,
            'destino': self.destino or '',
            'descripcion': self.descripcion,
            'valor_actual': self.valor_actual,
            'valor_nuevo': self.valor_nuevo,
            'detalle': self.detalle,
            'confianza': self.confianza,
            'cita': self.cita,
            'alerta': self.alerta,
            'estado': self.estado,
            'error': self.error,
            'creado_en': self.creado_en.strftime('%Y-%m-%d %H:%M') if self.creado_en else None,
        }


class AgenteScan(db.Model):
    """Bitacora de cada refresh de correo."""
    __tablename__ = 'agente_scans'

    id = db.Column(db.Integer, primary_key=True)
    iniciado_en = db.Column(db.DateTime, default=datetime.utcnow)
    terminado_en = db.Column(db.DateTime)
    correos_nuevos = db.Column(db.Integer, default=0)
    correos_revisados = db.Column(db.Integer, default=0)
    estado = db.Column(db.String(20), default='en_curso')   # en_curso | ok | error
    mensaje = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'iniciado_en': self.iniciado_en.strftime('%Y-%m-%d %H:%M') if self.iniciado_en else None,
            'correos_nuevos': self.correos_nuevos,
            'correos_revisados': self.correos_revisados,
            'estado': self.estado,
            'mensaje': self.mensaje,
        }
