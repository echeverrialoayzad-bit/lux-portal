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

import secrets
from datetime import datetime, timedelta

from flask import (
    render_template, request, jsonify, redirect, url_for, session, flash
)

from lux_portal.agente_lux import agente_lux_bp
from lux_portal.agente_lux import graph, contexto, reglas
from lux_portal.agente_lux.aplicar import aplicar_hallazgo
from lux_portal.agente_lux.models import (
    AgenteCuenta, AgenteMail, AgenteAdjunto, AgenteHallazgo, AgenteScan,
)
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required

# Cuando nunca se ha hecho un scan, cuantos dias hacia atras mirar.
DIAS_PRIMER_SCAN = 7
# Solape al re-escanear, por si un correo entro con retraso en el buzon.
HORAS_SOLAPE = 6


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
        config_ok=graph.config_ok(),
        falta_config=graph.falta_config(),
        resumen=contexto.resumen_corto(),
    )


# ---------------------------------------------------------------------------
# Conexion con Microsoft 365
# ---------------------------------------------------------------------------

def _redirect_uri():
    return graph.redirect_uri(
        url_for('agente_lux.oauth_callback', _external=True)
    )


@agente_lux_bp.route('/oauth/iniciar')
@login_required
def oauth_iniciar():
    if not graph.config_ok():
        flash('Faltan variables de Microsoft en Railway: '
              + ', '.join(graph.falta_config()), 'danger')
        return redirect(url_for('agente_lux.index'))

    estado = secrets.token_urlsafe(24)
    session['agente_lux_oauth_state'] = estado
    return redirect(graph.url_autorizacion(_redirect_uri(), estado))


@agente_lux_bp.route('/oauth/callback')
@login_required
def oauth_callback():
    error = request.args.get('error')
    if error:
        detalle = request.args.get('error_description', error)
        flash(f'Microsoft rechazo la conexion: {detalle}', 'danger')
        return redirect(url_for('agente_lux.index'))

    esperado = session.pop('agente_lux_oauth_state', None)
    if not esperado or request.args.get('state') != esperado:
        flash('La respuesta de Microsoft no coincide con la solicitud. '
              'Intenta conectar de nuevo.', 'danger')
        return redirect(url_for('agente_lux.index'))

    codigo = request.args.get('code')
    if not codigo:
        flash('Microsoft no devolvio ningun codigo de autorizacion.', 'danger')
        return redirect(url_for('agente_lux.index'))

    try:
        payload = graph.canjear_codigo(codigo, _redirect_uri())
        cuenta = _cuenta() or AgenteCuenta()
        graph.guardar_token(cuenta, payload)
        datos = graph.perfil(cuenta.access_token)
        cuenta.email = datos['email']
        cuenta.conectada_en = datetime.utcnow()
        if cuenta.id is None:
            db.session.add(cuenta)
        db.session.commit()
        flash(f'Correo conectado: {cuenta.email}', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'No se pudo conectar el correo: {exc}', 'danger')

    return redirect(url_for('agente_lux.index'))


@agente_lux_bp.route('/api/desconectar', methods=['POST'])
@login_required
def desconectar():
    """Borra los tokens. Los correos ya descargados se conservan."""
    cuenta = _cuenta()
    if cuenta:
        db.session.delete(cuenta)
        db.session.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Refresh: bajar correos nuevos
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/refresh', methods=['POST'])
@login_required
def refresh():
    """Baja los correos nuevos del buzon. No analiza nada todavia."""
    cuenta = _cuenta()
    if not cuenta:
        return jsonify({'error': 'No hay ninguna cuenta de correo conectada.'}), 400

    if (cuenta.modo or 'graph') == 'local':
        # En modo local el portal no tiene como llegar al buzon: los correos
        # entran desde la PC de Daniela con el CLI.
        return jsonify({
            'error': 'Esta cuenta lee el correo desde tu Outlook local, no '
                     'desde el servidor. Corre en tu PC: '
                     'python agente_lux_cli.py leer-outlook'
        }), 400

    dias = int((request.json or {}).get('dias') or 0)

    scan = AgenteScan(iniciado_en=datetime.utcnow(), estado='en_curso')
    db.session.add(scan)
    db.session.commit()

    try:
        token = graph.token_valido(cuenta)
        db.session.commit()   # persistir el token renovado

        if dias > 0:
            desde = datetime.utcnow() - timedelta(days=dias)
        elif cuenta.ultimo_scan:
            desde = cuenta.ultimo_scan - timedelta(hours=HORAS_SOLAPE)
        else:
            desde = datetime.utcnow() - timedelta(days=DIAS_PRIMER_SCAN)

        mensajes = graph.listar_mensajes(token, desde)
        nuevos = 0

        for mensaje in mensajes:
            graph_id = mensaje.get('id')
            if not graph_id:
                continue
            if AgenteMail.query.filter_by(graph_id=graph_id).first():
                continue

            correo_remitente, nombre_remitente = graph.remitente_de(mensaje)
            correo = AgenteMail(
                graph_id=graph_id,
                fecha=graph.fecha_de(mensaje),
                remitente=correo_remitente[:250],
                remitente_nombre=nombre_remitente[:250],
                asunto=(mensaje.get('subject') or '(sin asunto)')[:500],
                cuerpo=graph.texto_de(mensaje),
                web_link=mensaje.get('webLink'),
                estado='pendiente',
            )
            db.session.add(correo)
            db.session.flush()   # necesitamos el id para los adjuntos

            if mensaje.get('hasAttachments'):
                for adj in graph.descargar_adjuntos(token, graph_id):
                    db.session.add(AgenteAdjunto(
                        mail_id=correo.id,
                        nombre=adj['nombre'][:400],
                        mime=adj['mime'][:150],
                        size=adj['size'],
                        contenido_b64=adj['contenido_b64'],
                    ))
            nuevos += 1

        cuenta.ultimo_scan = datetime.utcnow()
        scan.terminado_en = datetime.utcnow()
        scan.correos_nuevos = nuevos
        scan.correos_revisados = len(mensajes)
        scan.estado = 'ok'
        db.session.commit()

        pendientes = AgenteMail.query.filter_by(estado='pendiente').count()
        return jsonify({
            'ok': True,
            'correos_nuevos': nuevos,
            'correos_revisados': len(mensajes),
            'pendientes_de_analisis': pendientes,
            'ultimo_scan': cuenta.ultimo_scan.strftime('%Y-%m-%d %H:%M'),
        })

    except Exception as exc:
        db.session.rollback()
        scan = AgenteScan.query.get(scan.id)
        if scan:
            scan.estado = 'error'
            scan.terminado_en = datetime.utcnow()
            scan.mensaje = str(exc)[:1000]
            db.session.commit()
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Estado general
# ---------------------------------------------------------------------------

@agente_lux_bp.route('/api/estado')
@login_required
def estado():
    cuenta = _cuenta()
    ultimo = AgenteScan.query.order_by(AgenteScan.id.desc()).first()
    return jsonify({
        'cuenta': cuenta.to_dict() if cuenta else None,
        'config_ok': graph.config_ok(),
        'falta_config': graph.falta_config(),
        'pendientes_de_analisis': AgenteMail.query.filter_by(estado='pendiente').count(),
        'hallazgos_pendientes': AgenteHallazgo.query.filter_by(estado='pendiente').count(),
        'hallazgos_aprobados': AgenteHallazgo.query.filter_by(estado='aprobado').count(),
        'ultimo_scan': ultimo.to_dict() if ultimo else None,
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
    desde = datetime.utcnow() - timedelta(days=dias)

    correos = (AgenteMail.query
               .filter(AgenteMail.fecha >= desde)
               .order_by(AgenteMail.fecha.desc())
               .all())

    agrupado = {}
    for correo in correos:
        clave = correo.fecha.strftime('%Y-%m-%d') if correo.fecha else 'sin fecha'
        agrupado.setdefault(clave, []).append(correo.to_dict())

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
        'generado_en': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'estado_actual': contexto.snapshot(),
        'correos': [c.to_dict(con_adjuntos=False) for c in pendientes],
    })
