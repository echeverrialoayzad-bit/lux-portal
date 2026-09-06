#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingesta de correos desde el Outlook de escritorio hacia la base del portal.

Lo usan dos cosas distintas y por eso vive aparte:
  - agente_lux_cli.py leer-outlook  (cuando Daniela lo corre a mano)
  - agente_lux_watcher.py           (cuando lo pide el boton del portal)

Solo corre en la PC, nunca en Railway: importa outlook_local, que necesita
Windows y Outlook instalado. El import va adentro de la funcion a proposito.
"""

import base64
from datetime import datetime, timedelta

from lux_portal.extensions import db
from lux_portal.agente_lux.models import AgenteCuenta, AgenteMail, AgenteAdjunto
from lux_portal.agente_lux.texto import limpiar_banners

# Cada lectura mira siempre estos dias hacia atras, no "desde la ultima
# lectura". Outlook no baja el correo en orden: cuando estuvo cerrado varios
# dias, al abrirlo sincroniza el atraso de a poco, y un correo del martes
# puede aparecer recien el sabado. Con la marca de la ultima lectura ese
# correo quedaba fuera para siempre: asi se perdieron 170 correos entre el
# 19 de agosto y el 5 de septiembre. Lo ya guardado se salta por su id, asi
# que releer la ventana cuesta poco.
DIAS_VENTANA = 10


def cuenta_local(crear=True):
    """La cuenta guardada, creandola en modo local si todavia no existe."""
    from lux_portal.agente_lux import outlook_local

    cuenta = AgenteCuenta.query.first()
    if cuenta is not None:
        return cuenta
    if not crear:
        return None

    cuenta = AgenteCuenta(
        email=outlook_local.cuenta_principal() or 'Outlook local',
        modo='local',
        conectada_en=datetime.utcnow(),
    )
    db.session.add(cuenta)
    db.session.commit()
    return cuenta


def ingerir(cuenta, dias=0, carpeta='Inbox', limite=500, recursivo=True):
    """Lee el buzon y guarda los correos que todavia no estaban.

    Se llama dentro de un app_context. Devuelve un dict con el resumen para
    poder mostrarlo tanto en la terminal como en el portal."""
    from lux_portal.agente_lux import outlook_local

    desde = datetime.now() - timedelta(days=dias or DIAS_VENTANA)

    # Lo que ya esta guardado se salta antes de bajar el cuerpo. El margen de
    # un dia es por si la fecha del correo y la del corte no calzan exacto.
    conocidos = {
        g for (g,) in db.session.query(AgenteMail.graph_id)
        .filter(AgenteMail.fecha >= desde - timedelta(days=1)).all()
    }

    # La direccion de Daniela decide que correos cuentan como respuesta a una
    # solicitud suya, y de eso depende que una tarifa pueda aplicarse. Va la
    # guardada en la cuenta para no depender de que Outlook la resuelva bien
    # en cada lectura; si la cuenta no tiene una direccion real, se deja que
    # outlook_local la busque como siempre.
    email = cuenta.email if '@' in (cuenta.email or '') else None
    correos, omitidos = outlook_local.leer(
        desde, carpeta=carpeta, limite=limite, recursivo=recursivo,
        mi_correo=email, omitir=conocidos)
    truncado = len(correos) >= limite

    nuevos, adjuntos = 0, 0
    for datos in correos:
        if AgenteMail.query.filter_by(graph_id=datos['id_unico']).first():
            continue

        correo = AgenteMail(
            graph_id=datos['id_unico'],
            fecha=datos['fecha'],
            carpeta=(datos.get('carpeta') or '')[:300],
            respuesta_mia=datos.get('respuesta_mia'),
            operativo=bool(datos.get('operativo')),
            remitente=(datos['remitente'] or '')[:250],
            remitente_nombre=(datos['remitente_nombre'] or '')[:250],
            asunto=(datos['asunto'] or '(sin asunto)')[:500],
            # Sin los avisos que Microsoft pega arriba: no aportan al
            # analisis y en el portal tapaban el contenido real.
            cuerpo=limpiar_banners(datos['cuerpo']),
            estado='pendiente',
        )
        db.session.add(correo)
        db.session.flush()

        for adj in datos['adjuntos']:
            contenido_b64 = None
            if adj['contenido']:
                contenido_b64 = base64.b64encode(adj['contenido']).decode('ascii')
                adjuntos += 1
            db.session.add(AgenteAdjunto(
                mail_id=correo.id,
                nombre=(adj['nombre'] or 'adjunto')[:400],
                mime=(adj['mime'] or '')[:150],
                size=adj['size'],
                contenido_b64=contenido_b64,
            ))
        nuevos += 1

    # Si se llego al tope quedaron correos dentro del rango sin leer: mover la
    # marca de agua los daria por vistos para siempre.
    if not truncado:
        cuenta.ultimo_scan = datetime.utcnow()
    db.session.commit()

    return {
        'revisados': len(correos) + omitidos,
        'nuevos': nuevos,
        'adjuntos': adjuntos,
        'truncado': truncado,
        'desde': desde,
        'pendientes': AgenteMail.query.filter_by(estado='pendiente').count(),
    }


def resumen_texto(stats):
    """Una linea para mostrarle a Daniela en el portal."""
    if stats['nuevos'] == 0:
        return f"Sin correos nuevos ({stats['revisados']} revisados)."
    texto = f"{stats['nuevos']} correo(s) nuevos."
    if stats['truncado']:
        texto += ' Se llego al tope: corre de nuevo para traer el resto.'
    return texto
