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


class AirlineFscGroup(db.Model):
    """Marca que una aerolinea esta gestionada en la tabla maestra de FSC,
    incluso si en este momento no tiene ninguna regla (0 reglas = FSC debe
    quedar en 0 al actualizar, en vez de dejarse intacto)."""
    __tablename__ = 'cotizacion_fsc_airlines'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False, unique=True)


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


class AirlineCargoGroup(db.Model):
    """Marca que una aerolinea esta gestionada en la tabla maestra de cargos
    adicionales (igual razon que AirlineFscGroup: 0 cargos = se debe limpiar
    al actualizar). Tambien guarda la nota general de la aerolinea, que se
    agrega (no reemplaza) a la nota especifica de cada cotizacion."""
    __tablename__ = 'cotizacion_cargo_airlines'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False, unique=True)
    notas = db.Column(db.Text, default='')

    def to_dict(self):
        return {'id': self.id, 'aerolinea': self.aerolinea, 'notas': self.notas or ''}


class AirlineDepartureDays(db.Model):
    """Dias de salida fijos por aerolinea desde UIO (no depende del destino).
    Una fila por aerolinea."""
    __tablename__ = 'cotizacion_departure_days'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False, unique=True)
    dias_json = db.Column(db.Text, default='[]')

    @property
    def dias(self):
        return json.loads(self.dias_json) if self.dias_json else []

    @dias.setter
    def dias(self, value):
        self.dias_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self):
        return {'id': self.id, 'aerolinea': self.aerolinea, 'dias': self.dias}


class AirlineCargoRule(db.Model):
    """Cargo adicional fijo por aerolinea (Due Carrier, CC, CG HAWB C/U, etc).
    No depende del destino, a diferencia de AirlineFscRule."""
    __tablename__ = 'cotizacion_cargo_rules'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False)
    concepto = db.Column(db.String(150), nullable=False)
    monto = db.Column(db.String(20), default='0.00')
    order = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'aerolinea': self.aerolinea,
            'concepto': self.concepto,
            'monto': self.monto,
            'order': self.order,
        }


class AirlineMailRequest(db.Model):
    """Correo de solicitud de tarifas por aerolinea (pestana Mails). Los
    destinos arrancan sembrados con lo que se identifica en las cotizaciones
    guardadas, pero de ahi en adelante son una lista editable a mano
    (agregar/quitar). El cuerpo del correo se genera solo a partir de los
    destinos, salvo que se guarde un override manual (cuerpo_editado=True)."""
    __tablename__ = 'cotizacion_mail_requests'

    id = db.Column(db.Integer, primary_key=True)
    aerolinea = db.Column(db.String(100), nullable=False, unique=True)
    destinos_json = db.Column(db.Text, default='[]')
    asunto = db.Column(db.String(200))
    cuerpo = db.Column(db.Text)
    cuerpo_editado = db.Column(db.Boolean, default=False)
    # A quien se manda (Agente Lux > Mails). Se llenan solos a partir de los
    # correos que Daniela ya mando a cada aerolinea, y se pueden corregir.
    destinatarios = db.Column(db.Text)   # direcciones separadas por ;
    cc = db.Column(db.Text)
    # Los destinos que Daniela marco para la proxima solicitud desde Agente
    # Lux. `destinos` es la lista completa que conoce la aerolinea; al correo
    # van solo estos. Arranca vacio: ella marca lo que quiere pedir.
    seleccionados_json = db.Column(db.Text, default='[]')
    # Destinos a los que esta aerolinea dijo por correo que NO llega, con la
    # frase que lo prueba: {"BUD": {"evidencia": "...", "mail_id": 85, ...}}.
    # Se guardan para no volver a pedir lo que ya negaron, y para poder
    # mostrarlo tachado en la tabla de destinos.
    no_sirve_json = db.Column(db.Text, default='{}')
    # Contactos que solo valen para ciertos destinos: {"MIA": "a@x.com; b@x.com"}.
    # Una aerolinea puede atenderse por una oficina distinta segun la ruta:
    # Atlas va por Prime Air, pero lo de USA lo lleva Fenix Ecuador, que es la
    # misma Atlas. En ese caso el correo REEMPLAZA al general, no se suma: se
    # le escribe a la oficina que maneja esa ruta y a nadie mas.
    destinatarios_destino_json = db.Column(db.Text, default='{}')

    @property
    def destinos(self):
        return json.loads(self.destinos_json) if self.destinos_json else []

    @destinos.setter
    def destinos(self, value):
        self.destinos_json = json.dumps(value, ensure_ascii=False)

    @property
    def seleccionados(self):
        try:
            lista = json.loads(self.seleccionados_json) if self.seleccionados_json else []
        except (ValueError, TypeError):
            lista = []
        # Solo los que siguen en la lista de la aerolinea.
        return [d for d in lista if d in self.destinos]

    @seleccionados.setter
    def seleccionados(self, value):
        self.seleccionados_json = json.dumps(value or [], ensure_ascii=False)

    @property
    def no_sirve(self):
        try:
            datos = json.loads(self.no_sirve_json) if self.no_sirve_json else {}
        except (ValueError, TypeError):
            datos = {}
        return datos if isinstance(datos, dict) else {}

    @no_sirve.setter
    def no_sirve(self, value):
        self.no_sirve_json = json.dumps(value or {}, ensure_ascii=False)

    @property
    def destinatarios_destino(self):
        try:
            datos = json.loads(self.destinatarios_destino_json or '{}')
        except (ValueError, TypeError):
            datos = {}
        return datos if isinstance(datos, dict) else {}

    @destinatarios_destino.setter
    def destinatarios_destino(self, value):
        self.destinatarios_destino_json = json.dumps(value or {}, ensure_ascii=False)

    def correos_para(self, destinos):
        """A quien se le escribe si se piden estos destinos.

        Un destino con contacto propio manda: esa ruta la atiende otra
        oficina de la misma aerolinea (Atlas va por Prime Air, pero lo de USA
        lo lleva Fenix), asi que el correo va a esa oficina y no al general.
        Los destinos sin contacto propio usan el de siempre. Si se piden los
        dos tipos a la vez, van ambos: cada uno tiene que ver lo suyo."""
        por_destino = self.destinatarios_destino
        propios, hay_general = [], False
        for d in (destinos or []):
            propio = por_destino.get(str(d).strip().upper())
            if propio:
                propios.append(propio)
            else:
                hay_general = True
        # Sin destinos, o todos sin contacto propio: el de siempre.
        partes = propios if propios else [self.destinatarios or '']
        if propios and (hay_general or not destinos):
            partes.append(self.destinatarios or '')

        vistas = []
        for parte in partes:
            for correo in str(parte).replace(',', ';').split(';'):
                correo = correo.strip()
                if correo and correo.lower() not in [v.lower() for v in vistas]:
                    vistas.append(correo)
        return '; '.join(vistas)

    def to_dict(self):
        return {
            'id': self.id,
            'aerolinea': self.aerolinea,
            'destinos': self.destinos,
            'asunto': self.asunto,
            'cuerpo': self.cuerpo,
            'cuerpo_editado': self.cuerpo_editado,
            'destinatarios': self.destinatarios,
            'cc': self.cc,
        }
