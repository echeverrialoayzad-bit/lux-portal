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

from datetime import datetime, timedelta, timezone
import json
from lux_portal.extensions import db

# Todo lo que guarda el modulo va en UTC (Railway corre en UTC), pero Daniela
# esta en Ecuador, que va cinco horas atras y no cambia con el verano. Las
# fechas de los correos ya llegan en hora local desde su Outlook; lo que hay
# que convertir al mostrar son las marcas de tiempo que pone el sistema.
ECUADOR = timezone(timedelta(hours=-5))


def a_ecuador(dt):
    """UTC sin zona -> hora de Ecuador sin zona, para mostrar o comparar
    contra las fechas de los correos."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(ECUADOR).replace(tzinfo=None)


def ahora_ecuador():
    """La hora que Daniela ve en su reloj. Sin tzinfo a proposito, para poder
    compararla con las fechas de los correos, que vienen igual de Outlook."""
    return datetime.now(ECUADOR).replace(tzinfo=None)


def _fmt(dt):
    return dt.strftime('%Y-%m-%d %H:%M') if dt else None


class AgenteCuenta(db.Model):
    """Cuenta de correo conectada. Se espera una sola fila.

    modo 'graph'  -> el portal baja los correos por Microsoft Graph. Requiere
                     que un administrador del tenant apruebe la app.
    modo 'local'  -> los correos se leen desde el Outlook de escritorio con
                     `agente_lux_cli.py leer-outlook`. No necesita Azure ni
                     aprobacion del administrador.

    En modo local no hay tokens: refresh_token queda en None y el unico campo
    que importa es ultimo_scan, que marca hasta donde se leyo."""
    __tablename__ = 'agente_cuenta'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(250))
    modo = db.Column(db.String(20), default='local')
    refresh_token = db.Column(db.Text)
    access_token = db.Column(db.Text)
    token_expira = db.Column(db.DateTime)
    conectada_en = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_scan = db.Column(db.DateTime)

    # --- Puente entre el boton del portal y la PC -------------------------
    # Railway no puede alcanzar el Outlook de escritorio, asi que el boton
    # solo deja una solicitud aca y el vigia local (agente_lux_watcher.py) la
    # atiende. Estos campos son el buzon de ida y vuelta entre los dos.
    refresh_solicitado = db.Column(db.DateTime)   # cuando se apreto el boton
    refresh_estado = db.Column(db.String(20), default='libre')
    # libre | solicitado | corriendo | ok | error
    refresh_mensaje = db.Column(db.Text)
    vigia_visto = db.Column(db.DateTime)          # ultimo latido del vigia

    def vigia_activo(self, segundos=90):
        """True si el vigia dio senales de vida hace poco."""
        if not self.vigia_visto:
            return False
        return (datetime.utcnow() - self.vigia_visto).total_seconds() < segundos

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'modo': self.modo or 'local',
            'conectada_en': _fmt(a_ecuador(self.conectada_en)),
            'ultimo_scan': _fmt(a_ecuador(self.ultimo_scan)),
            'refresh_estado': self.refresh_estado or 'libre',
            'refresh_mensaje': self.refresh_mensaje,
            'vigia_activo': self.vigia_activo(),
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
    # Ruta de la carpeta de Outlook, ej "Inbox/AEROLINEAS/AVIANCA". El buzon
    # esta archivado por aerolinea, asi que esto identifica la aerolinea sin
    # tener que deducirla del texto.
    carpeta = db.Column(db.String(300))
    # True si el correo llego como respuesta a un hilo que arranco Daniela.
    # Las tarifas buenas son siempre asi: ella pide y la aerolinea contesta
    # sobre el mismo correo. Lo que no es respuesta suya es reserva, guia o
    # aviso, y de ahi no se sacan tarifas. None = no se pudo determinar.
    respuesta_mia = db.Column(db.Boolean)
    # Reserva, cierre, AWB o guia. Estan llenos de cifras por kilo que son el
    # precio de un embarque puntual, no la tarifa vigente: de aca nunca se
    # sacan tarifas netas.
    operativo = db.Column(db.Boolean, default=False)

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
            'carpeta': self.carpeta,
            'respuesta_mia': self.respuesta_mia,
            'operativo': bool(self.operativo),
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
        # Antiguedad del correo que lo origino: una tarifa de hace un mes no
        # sirve de nada, asi que la pantalla lo tiene que dejar ver.
        dias = None
        if self.mail and self.mail.fecha:
            dias = max((ahora_ecuador() - self.mail.fecha).days, 0)

        return {
            'id': self.id,
            'mail_id': self.mail_id,
            'mail_asunto': self.mail.asunto if self.mail else None,
            'mail_remitente': (self.mail.remitente_nombre or self.mail.remitente) if self.mail else None,
            'mail_fecha': self.mail.fecha.strftime('%Y-%m-%d %H:%M') if (self.mail and self.mail.fecha) else None,
            'mail_carpeta': self.mail.carpeta if self.mail else None,
            'mail_dias': dias,
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
            'creado_en': _fmt(a_ecuador(self.creado_en)),
        }


# La bitacora de escaneos (AgenteScan) se quito junto con la via de Microsoft
# Graph: ahora el estado de la ultima lectura vive en la propia cuenta
# (refresh_estado / refresh_mensaje), que es lo que muestra el portal.
