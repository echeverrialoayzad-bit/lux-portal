#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Agente Lux.

Dos pantallas en una:
  1. Actualizaciones  -> lo que el agente encontro en el correo y propone
                         cambiar. Nada se aplica sin aprobacion explicita.
  2. Bitacora         -> resumen dia a dia de los correos nuevos: de que se
                         hablo y que quedo pendiente.
"""

from datetime import datetime, timedelta

from flask import render_template, request, jsonify

from lux_portal.agente_lux import agente_lux_bp
from lux_portal.agente_lux import contexto, reglas
from lux_portal.agente_lux.aplicar import aplicar_hallazgo
from lux_portal.agente_lux.models import (
    AgenteCuenta, AgenteMail, AgenteHallazgo, ahora_ecuador,
)
from lux_portal.agente_lux.texto import limpiar_banners, sin_enlaces
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

    cuenta.refresh_solicitado = datetime.utcnow()
    cuenta.refresh_estado = 'solicitado'
    cuenta.refresh_mensaje = 'Esperando a tu PC...'
    db.session.commit()

    return jsonify({'ok': True, 'estado': 'solicitado'})


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
    return jsonify({
        'cuenta': cuenta.to_dict() if cuenta else None,
        'pendientes_de_analisis': AgenteMail.query.filter_by(estado='pendiente').count(),
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
    """Los correos que llegaron hoy, con un vistazo rapido de cada uno.

    A diferencia de la bitacora, esto no espera al analisis: el vistazo sale
    del cuerpo del correo, asi que sirve apenas el vigia los sube."""
    dias = int(request.args.get('dias', 0))
    ahora = ahora_ecuador()
    if dias > 0:
        desde = ahora - timedelta(days=dias)
    else:
        desde = datetime.combine(ahora.date(), datetime.min.time())

    correos = (AgenteMail.query
               .filter(AgenteMail.fecha >= desde)
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
        'desde': desde.strftime('%Y-%m-%d %H:%M'),
        'correos': salida,
        'total': len(salida),
        'sin_analizar': sum(1 for c in salida if c['estado'] == 'pendiente'),
    })


# ---------------------------------------------------------------------------
# Hallazgos: revisar, aprobar, aplicar
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/hallazgos')
@login_required
def hallazgos():
    estados = request.args.get('estado', 'pendiente,aprobado').split(',')
    # Lo mas reciente primero: si algo viene de un correo viejo, que se vea
    # abajo y no se confunda con lo que acaba de llegar.
    filas = (AgenteHallazgo.query
             .outerjoin(AgenteMail, AgenteHallazgo.mail_id == AgenteMail.id)
             .filter(AgenteHallazgo.estado.in_([e.strip() for e in estados if e.strip()]))
             .order_by(AgenteMail.fecha.desc().nullslast(),
                       AgenteHallazgo.aerolinea, AgenteHallazgo.destino)
             .all())
    return jsonify({'hallazgos': [h.to_dict() for h in filas]})


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


# ---------------------------------------------------------------------------
# Bitacora dia a dia
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/bitacora')
@login_required
def bitacora():
    """Correos analizados agrupados por dia, mas nuevos primero."""
    dias = int(request.args.get('dias', 14))
    desde = ahora_ecuador() - timedelta(days=dias)

    correos = (AgenteMail.query
               .filter(AgenteMail.fecha >= desde)
               .order_by(AgenteMail.fecha.desc())
               .all())

    agrupado = {}
    for correo in correos:
        clave = correo.fecha.strftime('%Y-%m-%d') if correo.fecha else 'sin fecha'
        datos = correo.to_dict()
        # Las reservas y los correos operativos ya no pasan por Claude: se
        # clasifican por el asunto y quedan sin resumen. El vistazo del
        # cuerpo es lo que se muestra en su lugar.
        datos['vistazo'] = _vistazo(correo)
        agrupado.setdefault(clave, []).append(datos)

    return jsonify({
        'dias': [
            {
                'dia': dia,
                'correos': items,
                'con_accion': sum(1 for c in items if c['requiere_accion']),
            }
            for dia, items in sorted(agrupado.items(), reverse=True)
        ],
        'sin_analizar': AgenteMail.query.filter_by(estado='pendiente').count(),
    })


@agente_lux_bp.route('/api/mail/<int:mail_id>')
@login_required
def ver_mail(mail_id):
    correo = AgenteMail.query.get(mail_id)
    if not correo:
        return jsonify({'error': 'Correo no encontrado.'}), 404
    datos = correo.to_dict(con_adjuntos=True)
    # No mandamos el base64 completo a la pantalla: solo la referencia.
    for adj in datos.get('adjuntos', []):
        adj.pop('contenido_b64', None)
    datos['hallazgos'] = [h.to_dict() for h in correo.hallazgos]
    return jsonify(datos)


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
