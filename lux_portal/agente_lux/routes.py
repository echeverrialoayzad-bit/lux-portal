#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Agente Lux.

Dos pestanas, las dos gobernadas por el rango de fechas de la pantalla
(por defecto, hoy):
  1. Correos          -> los correos de esos dias, con su resumen.
  2. Actualizaciones  -> lo que el agente encontro en esos correos y propone
                         cambiar. Nada se aplica sin aprobacion explicita.
"""

import base64
from datetime import date, datetime, timedelta

from flask import render_template, request, jsonify, Response

from lux_portal.agente_lux import agente_lux_bp
from lux_portal.agente_lux import contexto, reglas
from lux_portal.agente_lux.aplicar import aplicar_hallazgo
from lux_portal.agente_lux.models import (
    AgenteCuenta, AgenteMail, AgenteHallazgo, AgenteAdjunto, AgenteEnvio,
    AgentePrioritario, ahora_ecuador, rango_del_dia,
)

# Tope del rango que se puede pedir de una vez: un mes de correo son varias
# horas de analisis, y mas que eso es casi seguro un error al elegir fechas.
MAX_DIAS_RANGO = 62


def _rango_pedido(fuente):
    """(desde, hasta) como fechas, a partir de un dict con 'desde'/'hasta' en
    ISO. Sin datos, el dia de hoy. Lanza ValueError si vienen mal."""
    hoy = ahora_ecuador().date()
    desde = date.fromisoformat(fuente['desde']) if fuente.get('desde') else hoy
    hasta = date.fromisoformat(fuente['hasta']) if fuente.get('hasta') else hoy
    if desde > hasta:
        desde, hasta = hasta, desde
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise ValueError(f'Maximo {MAX_DIAS_RANGO} dias por vez.')
    return desde, hasta
from lux_portal.agente_lux.texto import limpiar_banners, limpiar_para_ver, sin_enlaces
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required


def _cuenta():
    return AgenteCuenta.query.first()


# ---------------------------------------------------------------------------
# Pantalla principal
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/')
@login_required
def index():
    cuenta = _cuenta()
    return render_template(
        'agente_lux/index.html',
        cuenta=cuenta.to_dict() if cuenta else None,
        resumen=contexto.resumen_corto(),
    )


# ---------------------------------------------------------------------------
# Refresh: le pide a la PC que lea el Outlook
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/refresh', methods=['POST'])
@login_required
def refresh():
    """Deja pedida una lectura del buzon.

    Railway no puede alcanzar el Outlook de escritorio, asi que este boton no
    lee nada por si mismo: anota la solicitud y el vigia que corre en la PC
    (agente_lux_watcher.py) la atiende en los siguientes segundos. El portal
    se entera del resultado consultando /api/estado."""
    cuenta = _cuenta()
    if not cuenta:
        return jsonify({
            'error': 'Todavia no hay ninguna cuenta. Corre una vez en tu PC: '
                     'python agente_lux_cli.py leer-outlook'
        }), 400

    if not cuenta.vigia_activo():
        return jsonify({
            'error': 'El vigia no esta corriendo en tu PC, asi que nadie puede '
                     'abrir el Outlook. Abre una terminal en la carpeta del '
                     'proyecto y corre:  python agente_lux_watcher.py'
        }), 409

    if cuenta.refresh_estado in ('solicitado', 'corriendo', 'analizando'):
        # Pedir otra vez encima de un ciclo en curso solo lo pisaria: el vigia
        # atiende de a uno.
        return jsonify({
            'ok': True,
            'estado': cuenta.refresh_estado,
            'aviso': 'Ya hay una revision en curso.',
        })

    # El rango de fechas manda en todo el ciclo: solo se leen, analizan y
    # resumen los correos de esos dias. Por defecto, hoy.
    try:
        desde, hasta = _rango_pedido(request.json or {})
    except ValueError as exc:
        return jsonify({'error': f'Fechas invalidas: {exc}'}), 400

    cuenta.refresh_solicitado = datetime.utcnow()
    cuenta.refresh_estado = 'solicitado'
    cuenta.refresh_mensaje = 'Esperando a tu PC...'
    cuenta.refresh_desde = desde
    cuenta.refresh_hasta = hasta
    db.session.commit()

    return jsonify({'ok': True, 'estado': 'solicitado',
                    'desde': desde.isoformat(), 'hasta': hasta.isoformat()})


# ---------------------------------------------------------------------------
# Estado general
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/estado')
@login_required
def estado():
    cuenta = _cuenta()
    # "Hoy" es el de Daniela: a las 8 de la noche en Quito ya es manana en UTC
    # y la pestana de hoy se quedaba en cero.
    hoy = ahora_ecuador().date()

    # Contadores dentro del rango elegido en la pantalla, ademas de los
    # totales: lo de otras fechas no se procesa hasta que ella lo pida.
    try:
        desde, hasta = _rango_pedido(request.args)
    except ValueError:
        desde = hasta = hoy
    inicio, fin = rango_del_dia(desde, hasta)
    en_rango = AgenteMail.query.filter(AgenteMail.fecha >= inicio, AgenteMail.fecha <= fin)

    return jsonify({
        'cuenta': cuenta.to_dict() if cuenta else None,
        'rango': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()},
        'pendientes_en_rango': en_rango.filter(AgenteMail.estado == 'pendiente').count(),
        'por_resumir_en_rango': en_rango.filter(AgenteMail.estado == 'por_resumir').count(),
        'pendientes_de_analisis': AgenteMail.query.filter_by(estado='pendiente').count(),
        'por_resumir': AgenteMail.query.filter_by(estado='por_resumir').count(),
        'hallazgos_pendientes': AgenteHallazgo.query.filter_by(estado='pendiente').count(),
        'hallazgos_aprobados': AgenteHallazgo.query.filter_by(estado='aprobado').count(),
        'correos_hoy': AgenteMail.query.filter(
            AgenteMail.fecha >= datetime.combine(hoy, datetime.min.time())
        ).count(),
    })


# ---------------------------------------------------------------------------
# Correos del dia
# ---------------------------------------------------------------------------

def _vistazo(correo, largo=220):
    """Primeras lineas utiles del cuerpo, para leer de un vistazo sin abrir
    el correo. Sirve incluso antes de que el analisis lo haya resumido."""
    # Sin los avisos de Microsoft ni los <https://...>: el vistazo del correo
    # de la fumigadora mostraba "Algunos contactos que recibieron este
    # mensaje..." y nada del contenido.
    cuerpo = sin_enlaces(limpiar_banners(correo.cuerpo)).strip()
    if not cuerpo:
        return ''

    lineas = []
    for linea in cuerpo.splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        # Saltar las citas del hilo anterior y los encabezados reenviados.
        if limpia.startswith('>'):
            continue
        if limpia.lower().startswith(('de:', 'from:', 'enviado el:', 'sent:',
                                      'para:', 'to:', 'asunto:', 'subject:',
                                      'cc:', 'cco:')):
            continue
        lineas.append(limpia)
        if sum(len(x) for x in lineas) >= largo:
            break

    texto = ' '.join(lineas)[:largo]
    return texto + ('...' if len(' '.join(lineas)) > largo else '')


@agente_lux_bp.route('/api/hoy')
@login_required
def hoy():
    """Los correos del rango elegido (por defecto, hoy), con un vistazo rapido
    de cada uno.

    No espera al analisis: el vistazo sale del cuerpo del correo, asi que
    sirve apenas el vigia los sube. El resumen aparece cuando esta."""
    try:
        desde, hasta = _rango_pedido(request.args)
    except ValueError as exc:
        return jsonify({'error': f'Fechas invalidas: {exc}'}), 400
    inicio, fin = rango_del_dia(desde, hasta)

    correos = (AgenteMail.query
               .filter(AgenteMail.fecha >= inicio, AgenteMail.fecha <= fin)
               .order_by(AgenteMail.fecha.desc())
               .all())

    salida = []
    for correo in correos:
        datos = correo.to_dict()
        datos['vistazo'] = _vistazo(correo)
        datos['aerolinea'] = (
            (correo.carpeta or '').split('/')[-1]
            if (correo.carpeta or '').upper().startswith('INBOX/AEROLINEAS/')
            else ''
        )
        salida.append(datos)

    return jsonify({
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'correos': salida,
        'total': len(salida),
        # Sin analizar o esperando el resumen rapido: ambos se ven "a medias".
        'sin_analizar': sum(1 for c in salida if c['estado'] != 'analizado'),
    })


# ---------------------------------------------------------------------------
# Hallazgos: revisar, aprobar, aplicar
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/hallazgos')
@login_required
def hallazgos():
    estados = request.args.get('estado', 'pendiente,aprobado').split(',')
    query = (AgenteHallazgo.query
             .outerjoin(AgenteMail, AgenteHallazgo.mail_id == AgenteMail.id)
             .filter(AgenteHallazgo.estado.in_([e.strip() for e in estados if e.strip()])))

    # El rango de fechas de la pantalla manda tambien aca: solo las
    # propuestas que salen de correos de esos dias. Las de otras fechas
    # siguen guardadas y aparecen al ampliar el rango.
    if request.args.get('desde') or request.args.get('hasta'):
        try:
            desde, hasta = _rango_pedido(request.args)
        except ValueError as exc:
            return jsonify({'error': f'Fechas invalidas: {exc}'}), 400
        inicio, fin = rango_del_dia(desde, hasta)
        query = query.filter(AgenteMail.fecha >= inicio, AgenteMail.fecha <= fin)

    # Lo mas reciente primero: si algo viene de un correo viejo, que se vea
    # abajo y no se confunda con lo que acaba de llegar.
    filas = query.order_by(AgenteMail.fecha.desc().nullslast(),
                           AgenteHallazgo.aerolinea, AgenteHallazgo.destino).all()
    fuera = 0
    if request.args.get('desde') or request.args.get('hasta'):
        total = (AgenteHallazgo.query
                 .filter(AgenteHallazgo.estado.in_([e.strip() for e in estados if e.strip()]))
                 .count())
        fuera = max(total - len(filas), 0)
    return jsonify({'hallazgos': [h.to_dict() for h in filas], 'fuera_del_rango': fuera})


@agente_lux_bp.route('/api/hallazgos/decidir', methods=['POST'])
@login_required
def decidir():
    """Aprueba o rechaza hallazgos. Aprobar todavia no aplica nada."""
    data = request.json or {}
    ids = data.get('ids') or []
    decision = data.get('decision')

    if decision not in ('aprobado', 'rechazado', 'pendiente'):
        return jsonify({'error': 'Decision invalida.'}), 400
    if not ids:
        return jsonify({'error': 'No se recibio ningun hallazgo.'}), 400

    filas = AgenteHallazgo.query.filter(AgenteHallazgo.id.in_(ids)).all()
    for h in filas:
        if h.estado == 'aplicado':
            continue   # ya se aplico, no se puede deshacer desde aqui
        h.estado = decision
    db.session.commit()
    return jsonify({'ok': True, 'actualizados': len(filas)})


@agente_lux_bp.route('/api/hallazgos/editar', methods=['POST'])
@login_required
def editar():
    """Corrige a mano el valor propuesto antes de aplicarlo.

    Es la valvula de escape cuando el agente leyo mal un numero o cuando un
    FSC que vino como 'todos los destinos' en realidad aplica a algunos."""
    data = request.json or {}
    hallazgo = AgenteHallazgo.query.get(data.get('id'))
    if not hallazgo:
        return jsonify({'error': 'Hallazgo no encontrado.'}), 404
    if hallazgo.estado == 'aplicado':
        return jsonify({'error': 'Ese hallazgo ya se aplico.'}), 400

    detalle = hallazgo.detalle

    if 'valor_nuevo' in data:
        valor = str(data['valor_nuevo']).strip()
        hallazgo.valor_nuevo = valor
        if hallazgo.tipo == 'tarifa':
            detalle['tarifa_nueva'] = valor
        elif hallazgo.tipo == 'fsc':
            detalle['fsc_nuevo'] = valor
        elif hallazgo.tipo == 'cargo':
            detalle['monto_nuevo'] = valor

    if 'destinos' in data and hallazgo.tipo == 'fsc':
        destinos = [d.strip().upper() for d in (data['destinos'] or []) if d and d.strip()]
        detalle['destinos'] = destinos
        # Cambiar el alcance implica que ya no aplica la regla que se habia
        # emparejado: se vuelve a resolver al aplicar.
        detalle.pop('regla_id', None)
        hallazgo.destino = ', '.join(destinos)

    hallazgo.detalle = detalle
    hallazgo.alerta = reglas.revisar({
        'tipo': hallazgo.tipo,
        'destino': hallazgo.destino,
        'detalle': detalle,
    })
    db.session.commit()
    return jsonify({'ok': True, 'hallazgo': hallazgo.to_dict()})


@agente_lux_bp.route('/api/aplicar', methods=['POST'])
@login_required
def aplicar():
    """Aplica los hallazgos aprobados sobre cotizaciones y reglas de FSC."""
    data = request.json or {}
    ids = data.get('ids')

    query = AgenteHallazgo.query.filter_by(estado='aprobado')
    if ids:
        query = query.filter(AgenteHallazgo.id.in_(ids))
    filas = query.all()

    if not filas:
        return jsonify({'ok': True, 'aplicados': 0, 'detalle': [],
                        'mensaje': 'No hay hallazgos aprobados por aplicar.'})

    aplicados, fallidos, detalle = 0, 0, []

    for h in filas:
        try:
            ok, mensaje = aplicar_hallazgo(h)
        except Exception as exc:
            ok, mensaje = False, str(exc)

        if ok:
            h.estado = 'aplicado'
            h.aplicado_en = datetime.utcnow()
            h.error = None
            aplicados += 1
        else:
            h.error = mensaje[:1000]
            fallidos += 1
        detalle.append({'id': h.id, 'ok': ok, 'mensaje': mensaje})

    db.session.commit()
    return jsonify({'ok': True, 'aplicados': aplicados,
                    'fallidos': fallidos, 'detalle': detalle})


# La bitacora dia a dia se quito a pedido de Daniela: la pestana de correos
# con el rango de fechas cubre lo mismo.


@agente_lux_bp.route('/api/mail/<int:mail_id>')
@login_required
def ver_mail(mail_id):
    correo = AgenteMail.query.get(mail_id)
    if not correo:
        return jsonify({'error': 'Correo no encontrado.'}), 404
    datos = correo.to_dict(con_adjuntos=True)
    # No mandamos el base64 completo a la pantalla: solo la referencia. El
    # contenido se sirve aparte en /api/adjunto/<id>.
    for adj in datos.get('adjuntos', []):
        adj.pop('contenido_b64', None)
    datos['cuerpo'] = limpiar_para_ver(datos.get('cuerpo'))
    datos['hallazgos'] = [h.to_dict() for h in correo.hallazgos]
    # No hay enlace "abrir en Outlook": el esquema outlook:<EntryID> solo lo
    # entiende el Outlook clasico, y desde el navegador no abre nada cuando
    # el cliente por defecto es el Outlook nuevo. La pantalla ofrece
    # "Responder", que es un mailto: y funciona con cualquier cliente.
    return jsonify(datos)


@agente_lux_bp.route('/api/adjunto/<int:adj_id>')
@login_required
def ver_adjunto(adj_id):
    """Sirve un adjunto guardado (imagen o PDF) para verlo en el navegador."""
    adj = AgenteAdjunto.query.get(adj_id)
    if not adj or not adj.contenido_b64:
        return jsonify({'error': 'Ese adjunto no esta guardado.'}), 404
    contenido = base64.b64decode(adj.contenido_b64)
    nombre = (adj.nombre or 'adjunto').replace('"', '')
    return Response(
        contenido,
        mimetype=adj.mime or 'application/octet-stream',
        headers={'Content-Disposition': f'inline; filename="{nombre}"'},
    )


# ---------------------------------------------------------------------------
# Mails: solicitudes de tarifas por aerolinea, enviadas por su Outlook
# ---------------------------------------------------------------------------

import re as _re

# Nombre de la carpeta de Outlook (Inbox/AEROLINEAS/<X>) -> nombre en Mails,
# cuando no coinciden letra por letra.
_ALIAS_CARPETA = {'AERCARIBE': 'AIR CARIBE'}
_RE_HDR = _re.compile(r'^(?:Para|To|CC|Cc):\s*(.+)$', _re.M)
_RE_MAIL = _re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
ASUNTO_POR_DEFECTO = 'Tarifa Flor'


def _aerolinea_de_carpeta(carpeta):
    nombre = (carpeta or '').replace('Inbox/AEROLINEAS/', '').strip().upper()
    return _ALIAS_CARPETA.get(nombre, nombre)


def _descubrir_contactos(mi_correo):
    """Por aerolinea, a quien le mando Daniela sus solicitudes de tarifas.

    Sale de las respuestas guardadas: la aerolinea contesta sobre el correo
    de ella, y abajo queda citado "De: Daniela ... Para: ...". Esas son las
    direcciones que ella usa de verdad (los buzones de ventas). Si un hilo
    no trae la cita, se usa la direccion de quien contesto.

    Devuelve {aerolinea: [direcciones, la mas usada primero]}."""
    citados, respondieron = {}, {}
    mails = (AgenteMail.query
             .filter(AgenteMail.carpeta.ilike('Inbox/AEROLINEAS/%'),
                     AgenteMail.respuesta_mia.is_(True))
             .all())
    for m in mails:
        aero = _aerolinea_de_carpeta(m.carpeta)
        if m.remitente and mi_correo not in m.remitente.lower() \
                and 'freight-wise.com' not in m.remitente.lower():
            respondieron.setdefault(aero, {})
            respondieron[aero][m.remitente.lower()] = respondieron[aero].get(m.remitente.lower(), 0) + 1
        for bloque in _re.split(r'\n(?=(?:De|From):)', m.cuerpo or ''):
            if mi_correo not in bloque.split('\n', 1)[0].lower():
                continue
            for linea in _RE_HDR.findall(bloque[:1500]):
                for e in _RE_MAIL.findall(linea):
                    e = e.lower()
                    if 'freight-wise.com' in e:
                        continue
                    citados.setdefault(aero, {})
                    citados[aero][e] = citados[aero].get(e, 0) + 1

    salida = {}
    for aero in set(citados) | set(respondieron):
        fuente = citados.get(aero) or respondieron.get(aero) or {}
        salida[aero] = [e for e, _ in sorted(fuente.items(), key=lambda x: -x[1])]
    return salida


def _ultimas_respuestas():
    """{aerolinea: fecha de la ultima respuesta a una solicitud de Daniela}."""
    from sqlalchemy import func
    filas = (db.session.query(AgenteMail.carpeta, func.max(AgenteMail.fecha))
             .filter(AgenteMail.carpeta.ilike('Inbox/AEROLINEAS/%'),
                     AgenteMail.respuesta_mia.is_(True))
             .group_by(AgenteMail.carpeta).all())
    return {_aerolinea_de_carpeta(c): f for c, f in filas}


CC_SIEMPRE = 'fwquito@freight-wise.com'


def _cuerpo_solicitud(registro):
    """El texto que se manda desde Agente Lux: con los destinos MARCADOS.

    La lista completa de destinos vive en la pestana Mails del portal (y su
    texto "para copiar" los lleva todos); aca Daniela marca cuales pide en
    esta solicitud. Si el texto esta editado a mano, se conserva y solo se
    reemplaza la lista de vinetas."""
    from lux_portal.cotizaciones.routes import _generar_cuerpo_mail
    from lux_portal.agente_lux.texto import sincronizar_destinos
    seleccion = registro.seleccionados
    if registro.cuerpo_editado and registro.cuerpo:
        return sincronizar_destinos(registro.cuerpo, seleccion)
    return _generar_cuerpo_mail(registro.aerolinea, seleccion)


def _con_cc_fijo(cc):
    """fwquito va siempre en copia, lo haya escrito Daniela o no."""
    direcciones = _RE_MAIL.findall(cc or '')
    if CC_SIEMPRE.lower() not in [d.lower() for d in direcciones]:
        direcciones.append(CC_SIEMPRE)
    return '; '.join(direcciones)


@agente_lux_bp.route('/api/mails')
@login_required
def mails():
    """Las solicitudes de tarifas por aerolinea, listas para enviar."""
    from lux_portal.cotizaciones.models import AirlineMailRequest

    respuestas = _ultimas_respuestas()
    ultimos = {}
    for e in AgenteEnvio.query.order_by(AgenteEnvio.id.desc()).all():
        ultimos.setdefault(e.aerolinea, e)

    salida = []
    for r in AirlineMailRequest.query.order_by(AirlineMailRequest.aerolinea).all():
        ultimo = ultimos.get(r.aerolinea)
        resp = respuestas.get(r.aerolinea)
        salida.append({
            'id': r.id,
            'aerolinea': r.aerolinea,
            'destinos': r.destinos,
            'seleccionados': r.seleccionados,
            'asunto': r.asunto or ASUNTO_POR_DEFECTO,
            'cuerpo': _cuerpo_solicitud(r),
            'destinatarios': r.destinatarios or '',
            'cc': _con_cc_fijo(r.cc),
            'cuerpo_editado': bool(r.cuerpo_editado),
            'ultimo_envio': ultimo.to_dict() if ultimo else None,
            'ultima_respuesta': resp.strftime('%Y-%m-%d %H:%M') if resp else None,
        })
    return jsonify({'mails': salida})


@agente_lux_bp.route('/api/mails/<int:id>', methods=['POST'])
@login_required
def guardar_mail(id):
    """Guarda a quien se manda, el asunto, los destinos o el texto de una
    solicitud. Mismas reglas que la pestana Mails del portal: al cambiar los
    destinos el texto se regenera, salvo que Daniela lo haya editado a mano;
    restablecer_cuerpo vuelve al texto automatico."""
    from lux_portal.cotizaciones.models import AirlineMailRequest

    registro = AirlineMailRequest.query.get(id)
    if not registro:
        return jsonify({'error': 'Aerolinea no encontrada.'}), 404
    data = request.json or {}
    if 'destinatarios' in data:
        registro.destinatarios = _limpiar_direcciones(data.get('destinatarios'))
    if 'cc' in data:
        registro.cc = _limpiar_direcciones(data.get('cc'))
    if 'asunto' in data:
        registro.asunto = (data.get('asunto') or '').strip()[:200] or None
    if 'destinos' in data:
        # La lista completa que conoce la aerolinea (se agregan o quitan).
        destinos = sorted({(d or '').strip().upper()
                           for d in (data.get('destinos') or []) if (d or '').strip()})
        nuevos = [d for d in destinos if d not in registro.destinos]
        registro.destinos = destinos
        # Un destino recien agregado desde Agente Lux se marca solo: si lo
        # escribio es porque lo quiere pedir.
        registro.seleccionados = [d for d in registro.seleccionados if d in destinos] + nuevos
        if not registro.cuerpo_editado:
            registro.cuerpo = None
    if 'seleccionados' in data:
        marcados = [(d or '').strip().upper() for d in (data.get('seleccionados') or [])]
        registro.seleccionados = [d for d in registro.destinos if d in marcados]
    if 'cuerpo' in data:
        texto = (data.get('cuerpo') or '').strip()
        if texto:
            registro.cuerpo = texto
            registro.cuerpo_editado = True
    if data.get('restablecer_cuerpo'):
        registro.cuerpo = None
        registro.cuerpo_editado = False
    db.session.commit()
    return jsonify({'ok': True, 'destinos': registro.destinos,
                    'seleccionados': registro.seleccionados,
                    'cuerpo': _cuerpo_solicitud(registro),
                    'cuerpo_editado': bool(registro.cuerpo_editado)})


def _limpiar_direcciones(texto):
    """'a@x.com, b@y.com; c@z.com' -> 'a@x.com; b@y.com; c@z.com'."""
    direcciones = _RE_MAIL.findall(texto or '')
    vistas = []
    for d in direcciones:
        if d.lower() not in [v.lower() for v in vistas]:
            vistas.append(d)
    return '; '.join(vistas)


@agente_lux_bp.route('/api/mails/<int:id>/enviar', methods=['POST'])
@login_required
def enviar_mail(id):
    """Deja el correo en cola: el vigia lo manda por el Outlook de la PC."""
    from lux_portal.cotizaciones.models import AirlineMailRequest

    registro = AirlineMailRequest.query.get(id)
    if not registro:
        return jsonify({'error': 'Aerolinea no encontrada.'}), 404
    cuenta = _cuenta()
    if not cuenta or not cuenta.vigia_activo():
        return jsonify({'error': 'El vigia no esta corriendo en tu PC, y es el que '
                                 'manda el correo por tu Outlook.'}), 409
    if not registro.destinatarios:
        return jsonify({'error': 'Esa aerolinea no tiene destinatario. Escribe la '
                                 'direccion o usa "Detectar contactos".'}), 400
    if not registro.seleccionados:
        return jsonify({'error': 'Marca al menos un destino para pedir.'}), 400

    envio = AgenteEnvio(
        aerolinea=registro.aerolinea,
        para=registro.destinatarios,
        cc=_con_cc_fijo(registro.cc),
        asunto=(registro.asunto or ASUNTO_POR_DEFECTO)[:300],
        cuerpo=_cuerpo_solicitud(registro),
        estado='pendiente',
    )
    db.session.add(envio)
    db.session.commit()
    return jsonify({'ok': True, 'envio': envio.to_dict()})


@agente_lux_bp.route('/api/mails/envios')
@login_required
def envios():
    filas = AgenteEnvio.query.order_by(AgenteEnvio.id.desc()).limit(30).all()
    return jsonify({'envios': [e.to_dict() for e in filas]})


@agente_lux_bp.route('/api/mails/descubrir', methods=['POST'])
@login_required
def descubrir_contactos():
    """Llena los destinatarios a partir de los correos ya guardados.

    Solo rellena los que estan vacios, salvo que venga {"forzar": true}."""
    from lux_portal.cotizaciones.models import AirlineMailRequest

    cuenta = _cuenta()
    mi_correo = (cuenta.email if cuenta else '').lower()
    encontrados = _descubrir_contactos(mi_correo)
    forzar = bool((request.json or {}).get('forzar'))
    llenados = {}
    for r in AirlineMailRequest.query.all():
        direcciones = encontrados.get((r.aerolinea or '').upper())
        if not direcciones:
            continue
        if r.destinatarios and not forzar:
            continue
        r.destinatarios = '; '.join(direcciones[:3])
        llenados[r.aerolinea] = r.destinatarios
    db.session.commit()
    return jsonify({'ok': True, 'llenados': llenados,
                    'sin_contacto': sorted(
                        r.aerolinea for r in AirlineMailRequest.query.all()
                        if not r.destinatarios)})


# ---------------------------------------------------------------------------
# Prioritarios: los correos de las personas que Daniela quiere ver aparte
# ---------------------------------------------------------------------------

def _correo_a_item(correo):
    datos = correo.to_dict()
    datos['vistazo'] = _vistazo(correo)
    datos['aerolinea'] = (
        (correo.carpeta or '').split('/')[-1]
        if (correo.carpeta or '').upper().startswith('INBOX/AEROLINEAS/')
        else ''
    )
    return datos


@agente_lux_bp.route('/api/prioritarios')
@login_required
def prioritarios():
    """Las personas prioritarias y sus correos dentro del rango de la
    pantalla (por defecto, hoy). Mismo rango que las demas pestanas, para que
    "Refresh y analizar" los traiga sin repasar historicos."""
    from sqlalchemy import func
    try:
        desde, hasta = _rango_pedido(request.args)
    except ValueError as exc:
        return jsonify({'error': f'Fechas invalidas: {exc}'}), 400
    inicio, fin = rango_del_dia(desde, hasta)

    personas = AgentePrioritario.query.order_by(AgentePrioritario.nombre).all()
    emails = [p.email.lower() for p in personas]
    correos, fuera = [], 0
    if emails:
        base = AgenteMail.query.filter(func.lower(AgenteMail.remitente).in_(emails))
        filas = (base.filter(AgenteMail.fecha >= inicio, AgenteMail.fecha <= fin)
                 .order_by(AgenteMail.fecha.desc()).all())
        correos = [_correo_a_item(c) for c in filas]
        fuera = max(base.count() - len(filas), 0)
    return jsonify({'personas': [p.to_dict() for p in personas],
                    'correos': correos, 'en_rango': len(correos),
                    'fuera_del_rango': fuera,
                    'rango': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()}})


@agente_lux_bp.route('/api/prioritarios', methods=['POST'])
@login_required
def agregar_prioritario():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    nombre = (data.get('nombre') or '').strip()[:150]
    if not _RE_MAIL.fullmatch(email):
        return jsonify({'error': 'Escribe una direccion de correo valida.'}), 400
    if AgentePrioritario.query.filter(db.func.lower(AgentePrioritario.email) == email).first():
        return jsonify({'error': 'Esa persona ya esta en la lista.'}), 400
    persona = AgentePrioritario(nombre=nombre or email.split('@')[0], email=email)
    db.session.add(persona)
    db.session.commit()
    return jsonify({'ok': True, 'persona': persona.to_dict()})


@agente_lux_bp.route('/api/prioritarios/<int:id>', methods=['DELETE'])
@login_required
def quitar_prioritario(id):
    persona = AgentePrioritario.query.get(id)
    if not persona:
        return jsonify({'error': 'No encontrada.'}), 404
    db.session.delete(persona)
    db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Puente con el analisis local (Claude Code)
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/export')
@login_required
def exportar():
    """Correos pendientes de analisis + foto del estado actual.

    El CLI local normalmente lee esto directo de la base; este endpoint existe
    para poder inspeccionar desde el navegador que es lo que va a analizarse."""
    pendientes = (AgenteMail.query
                  .filter_by(estado='pendiente')
                  .order_by(AgenteMail.fecha.asc())
                  .all())
    return jsonify({
        'generado_en': ahora_ecuador().strftime('%Y-%m-%d %H:%M:%S'),
        'estado_actual': contexto.snapshot(),
        'correos': [c.to_dict(con_adjuntos=False) for c in pendientes],
    })
