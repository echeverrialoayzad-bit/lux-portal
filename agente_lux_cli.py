#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente Lux - puente entre el portal y el analisis local con Claude Code.

El portal (Railway) baja los correos; el analisis lo hace Claude Code aca en
la maquina, usando la suscripcion en vez de creditos de API. Este script mueve
los datos en las dos direcciones.

USO
---
    python agente_lux_cli.py leer-outlook  # buzon local -> portal
    python agente_lux_cli.py carpetas      # lista las carpetas de Outlook
    python agente_lux_cli.py exportar      # correos pendientes -> _agente_lux/
    python agente_lux_cli.py cargar        # _agente_lux/hallazgos.json -> portal
    python agente_lux_cli.py exportar-resumen  # correos sin tarifas -> por_resumir.json
    python agente_lux_cli.py cargar-resumen    # resumenes.json -> portal (bitacora)
    python agente_lux_cli.py estado        # contadores rapidos

Los correos que no traen tarifas (reservas, fincas, avisos) no pasan por el
analisis de tarifas: quedan en estado "por_resumir" y una pasada aparte, mas
liviana y sin adjuntos, les escribe el resumen que Daniela ve en el portal.

La conexion sale de DATABASE_URL (la de Railway) o de --db.

FLUJO COMPLETO
--------------
 1. Bajar los correos, de una de estas dos formas:
      a) python agente_lux_cli.py leer-outlook   (Outlook de escritorio; no
         necesita Azure ni aprobacion del administrador del tenant)
      b) boton "Refresh correos" en el portal    (Microsoft Graph; requiere
         que un admin haya aprobado la app)
 2. Aca:  python agente_lux_cli.py exportar
 3. En Claude Code: "analiza _agente_lux/pendientes.json y escribe
    _agente_lux/hallazgos.json"  (ver FORMATO abajo)
 4. Aca:  python agente_lux_cli.py cargar
 5. En el portal: revisar, corregir si hace falta, aprobar y aplicar.

El modo local necesita pywin32:  pip install pywin32

FORMATO DE _agente_lux/hallazgos.json
-------------------------------------
{
  "correos": [
    {
      "mail_id": 12,
      "categoria": "tarifas",          // tarifas | fsc | operativo | comercial | otro
      "resumen": "Avianca manda tarifas nuevas para MAD y LHR vigentes 01-abr.",
      "temas": ["Confirmar si aplica a carga ya reservada"],
      "requiere_accion": true
    }
  ],
  "hallazgos": [
    {
      "mail_id": 12,
      "tipo": "tarifa",                // tarifa | fsc | cargo | dias | info
      "aerolinea": "AVIANCA",
      "destino": "MAD",
      "descripcion": "Tarifa +100 baja de 3.00 a 2.85",
      "valor_actual": "3.00",
      "valor_nuevo": "2.85",
      "confianza": "alta",             // alta | media | baja
      "cita": "MAD +100kg USD 2.85 effective April 1st",
      "detalle": {
        "cot_id": 7,                   // OBLIGATORIO en tipo=tarifa
        "kg": "+100",                  // OBLIGATORIO en tipo=tarifa
        "tarifa_nueva": 2.85,
        "kg_rate_actual": {"tarifa":"3.00","margen":"0.00","costo_operativo":"0.09","fsc":"0.10"}
      }
    },
    {
      "mail_id": 12,
      "tipo": "fsc",
      "aerolinea": "AVIANCA",
      "descripcion": "FSC sube a 0.18 solo para Europa",
      "valor_actual": "0.10",
      "valor_nuevo": "0.18",
      "confianza": "media",
      "detalle": {
        "regla_id": 14,                // id de la regla existente, o null si es nueva
        "destinos": ["MAD","LHR"],     // [] = TODOS los destinos de la aerolinea
        "nombre": "Europa",
        "fsc_actual": "0.10",
        "fsc_nuevo": 0.18
      }
    }
  ]
}

Notas importantes para quien genere ese JSON:
  - "destinos": [] en un hallazgo de FSC significa TODOS los destinos de esa
    aerolinea. Si el correo solo menciona algunos trayectos, hay que listarlos
    explicitamente. Es el error mas caro que se puede cometer aca.
  - tipo "dias" y tipo "info" nunca se aplican solos: quedan como aviso.
  - tipo "tarifa" solo vale si el correo es respuesta a una solicitud de
    Daniela (respuesta_a_mi_solicitud: true) y no es reserva ni guia. Ella
    pide la tarifa por correo y la aerolinea le contesta en el mismo hilo;
    esa respuesta es la unica fuente. Si no se cumple, `cargar` lo guarda
    como tipo "info" con alerta: se ve en el portal, pero no se aplica.
  - El FSC es la excepcion: las aerolineas lo mandan directo, sin solicitud.
  - cot_id y kg se sacan de estado_actual.cotizaciones en pendientes.json.
"""

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta

CARPETA = '_agente_lux'
ARCHIVO_PENDIENTES = os.path.join(CARPETA, 'pendientes.json')
ARCHIVO_HALLAZGOS = os.path.join(CARPETA, 'hallazgos.json')
CARPETA_ADJUNTOS = os.path.join(CARPETA, 'adjuntos')
# Resumen rapido de los correos que no pasan por el analisis de tarifas.
ARCHIVO_POR_RESUMIR = os.path.join(CARPETA, 'por_resumir.json')
ARCHIVO_RESUMENES = os.path.join(CARPETA, 'resumenes.json')

CATEGORIAS_VALIDAS = {'tarifas', 'fsc', 'operativo', 'comercial', 'otro'}

TIPOS_VALIDOS = {'tarifa', 'fsc', 'cargo', 'dias', 'info'}
CONFIANZAS_VALIDAS = {'alta', 'media', 'baja'}

# Correos que probablemente traen tarifas, FSC o recargos. En un mes tipico,
# de ~200 correos archivados solo ~45 son de esto: marcarlos evita que el
# analisis se gaste el tiempo abriendo adjuntos de reservas y manifiestos.
# Es una pista, no un filtro duro: el correo igual queda guardado y aparece
# en la bitacora.
PATRON_TARIFAS = re.compile(
    r'tarifa|rate|surcharge|fsc|fuel|gri|increase|incremento|quotation|'
    r'cotizaci|vigencia|valid\s+from|actualiza|update',
    re.I)


def parece_tarifas(correo):
    texto = f"{correo.asunto or ''}\n{(correo.cuerpo or '')[:1500]}"
    return bool(PATRON_TARIFAS.search(texto))


# ---------------------------------------------------------------------------
# Conexion
# ---------------------------------------------------------------------------

def crear_app(db_url):
    """App Flask minima: solo la base de datos.

    A proposito NO usa create_app(): esa corre create_all() y todos los seeds,
    y esto se conecta contra produccion."""
    from flask import Flask
    from lux_portal.extensions import db

    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # El vigia corre horas y Railway corta las conexiones ociosas. Sin esto,
    # la primera consulta despues de un rato quieto revienta con
    # "server closed the connection unexpectedly".
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }
    db.init_app(app)
    return app


def resolver_db(args):
    if args.db:
        return args.db

    # El .env de la carpeta del proyecto guarda la conexion a Railway, para no
    # tener que exportarla en cada terminal. Esta en .gitignore.
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
    except ImportError:
        pass

    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        sys.exit(
            'Falta la conexion a la base.\n'
            '  - Crea un archivo .env en la carpeta del proyecto con:\n'
            '      DATABASE_URL=postgresql://usuario:clave@host:puerto/base\n'
            '  - O pasa --db "postgresql://..."\n'
            'La URL publica sale de Railway: servicio Postgres -> Variables -> '
            'DATABASE_PUBLIC_URL.'
        )
    return url


def nombre_seguro(texto):
    """Nombre de archivo sin sorpresas (el nombre viene de un correo externo)."""
    limpio = re.sub(r'[^A-Za-z0-9._-]', '_', texto or 'adjunto')
    return limpio[:120] or 'adjunto'


def _fechas_rango(args):
    """(desde, hasta) como date a partir de --desde/--hasta, o (None, None)."""
    from datetime import date as _date
    desde = getattr(args, 'desde', None)
    hasta = getattr(args, 'hasta', None)
    if not desde and not hasta:
        return None, None
    d = _date.fromisoformat(desde or hasta)
    h = _date.fromisoformat(hasta or desde)
    return (d, h) if d <= h else (h, d)


def _filtrar_rango(query, args):
    """Limita una consulta de AgenteMail al rango --desde/--hasta, si lo hay.

    El rango es lo que decide Daniela en el portal: solo esos dias se leen,
    analizan y resumen. Lo demas espera a que ella lo pida."""
    from lux_portal.agente_lux.models import AgenteMail, rango_del_dia
    desde, hasta = _fechas_rango(args)
    if desde is None:
        return query
    inicio, fin = rango_del_dia(desde, hasta)
    return query.filter(AgenteMail.fecha >= inicio, AgenteMail.fecha <= fin)


def _agregar_rango(parser):
    parser.add_argument('--desde', help='Fecha inicial (AAAA-MM-DD) del rango.')
    parser.add_argument('--hasta', help='Fecha final (AAAA-MM-DD) del rango.')


# ---------------------------------------------------------------------------
# exportar
# ---------------------------------------------------------------------------

def cmd_exportar(args):
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux.models import AgenteMail
    from lux_portal.agente_lux import contexto

    with app.app_context():
        pendientes = (_filtrar_rango(AgenteMail.query.filter_by(estado='pendiente'), args)
                      .order_by(AgenteMail.fecha.asc())
                      .all())

        # Lo que vale la pena que mire Claude: correos con pinta de tarifas o
        # recargos, y todas las respuestas a las solicitudes de Daniela. Las
        # reservas, cierres y guias quedan fuera aunque digan "tarifa": de
        # ahi nunca sale una.
        relevantes = {
            c.id for c in pendientes
            if not c.operativo and (parece_tarifas(c) or c.respuesta_mia)
        }
        archivados = 0
        if args.solo_tarifas:
            # El resto no pasa por el analisis de tarifas: queda en cola para
            # el resumen rapido (exportar-resumen), porque Daniela quiere
            # saber de que es cada correo sin tener que abrirlo. Es lo que
            # hace que el analisis tarde una fraccion: en un mes tipico dos
            # de cada tres correos son reservas y temas operativos.
            #
            # En dos UPDATE masivos y no fila por fila: la base esta a 350 ms
            # de ida y vuelta, y marcar 224 correos uno por uno tomaba minuto
            # y medio.
            from lux_portal.extensions import db
            ids_operativos = [c.id for c in pendientes
                              if c.id not in relevantes and c.operativo]
            ids_otros = [c.id for c in pendientes
                         if c.id not in relevantes and not c.operativo]
            for ids, categoria in ((ids_operativos, 'operativo'), (ids_otros, 'otro')):
                if ids:
                    (AgenteMail.query.filter(AgenteMail.id.in_(ids))
                     .update({'estado': 'por_resumir', 'categoria': categoria,
                              'resumen': ''}, synchronize_session=False))
            archivados = len(ids_operativos) + len(ids_otros)
            db.session.commit()
            pendientes = [c for c in pendientes if c.id in relevantes]

        # Por tandas: un lote enorme (la primera corrida trae un mes entero)
        # se puede caer a la mitad y perder todo el trabajo. Mejor tandas
        # chicas que se cargan y quedan guardadas antes de seguir.
        quedan = 0
        if args.max_correos and len(pendientes) > args.max_correos:
            quedan = len(pendientes) - args.max_correos
            pendientes = pendientes[:args.max_correos]

        os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)
        correos = []
        n_adjuntos = 0

        for correo in pendientes:
            archivos = []
            # Los adjuntos de correos que no son de tarifas (reservas,
            # manifiestos, guias) se listan pero no se vuelcan a disco: son
            # la mayor parte del peso y no aportan al analisis.
            volcar = correo.id in relevantes
            for adj in correo.adjuntos:
                registro = {'nombre': adj.nombre, 'mime': adj.mime, 'size': adj.size}
                if adj.contenido_b64 and volcar:
                    ruta = os.path.join(
                        CARPETA_ADJUNTOS,
                        f'{correo.id}_{nombre_seguro(adj.nombre)}'
                    )
                    try:
                        with open(ruta, 'wb') as fh:
                            fh.write(base64.b64decode(adj.contenido_b64))
                        registro['archivo'] = ruta.replace('\\', '/')
                        n_adjuntos += 1
                    except Exception as exc:
                        registro['error'] = f'No se pudo guardar: {exc}'
                archivos.append(registro)

            correos.append({
                'mail_id': correo.id,
                'fecha': correo.fecha.strftime('%Y-%m-%d %H:%M') if correo.fecha else None,
                # La carpeta identifica la aerolinea: el buzon esta archivado
                # en Inbox/AEROLINEAS/<AEROLINEA>.
                'carpeta': correo.carpeta or '',
                # True = la aerolinea contesto sobre el hilo que abrio Daniela
                # pidiendo tarifas. Es la fuente mas confiable.
                'respuesta_a_mi_solicitud': correo.respuesta_mia,
                # True = reserva, cierre o guia. De aca no salen tarifas netas.
                'es_reserva_o_guia': bool(correo.operativo),
                # Pista: si es False, casi seguro es una reserva o un tema
                # operativo. Resumelo para la bitacora, pero no gastes tiempo
                # buscandole tarifas (sus adjuntos ni siquiera se volcaron).
                'parece_tarifas': volcar,
                'remitente': correo.remitente,
                'remitente_nombre': correo.remitente_nombre,
                'asunto': correo.asunto,
                'cuerpo': correo.cuerpo,
                'adjuntos': archivos,
            })

        salida = {
            'generado_en': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'estado_actual': contexto.snapshot(),
            'correos': correos,
        }

    os.makedirs(CARPETA, exist_ok=True)
    with open(ARCHIVO_PENDIENTES, 'w', encoding='utf-8') as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=2)

    n_relevantes = sum(1 for c in correos if c['parece_tarifas'])
    print(f'{len(correos)} correo(s) pendientes exportados a {ARCHIVO_PENDIENTES}')
    print(f'  de esos, {n_relevantes} parecen traer tarifas o recargos')
    if archivados:
        print(f'  {archivados} correo(s) sin tarifas quedaron en cola para el '
              f'resumen rapido (exportar-resumen)')
    if quedan:
        print(f'  quedan {quedan} para la siguiente tanda')
    if n_adjuntos:
        print(f'{n_adjuntos} adjunto(s) guardados en {CARPETA_ADJUNTOS}/ '
              f'(solo los de correos de tarifas)')
    if not correos:
        print('No hay nada por analizar. Dale "Refresh correos" en el portal primero.')
        return

    print()
    print('Siguiente paso, pidele esto a Claude Code:')
    print(f'  Lee {ARCHIVO_PENDIENTES} (y los adjuntos referenciados), compara')
    print('  contra estado_actual y escribe _agente_lux/hallazgos.json siguiendo')
    print('  el formato del docstring de agente_lux_cli.py.')


# ---------------------------------------------------------------------------
# cargar
# ---------------------------------------------------------------------------

def _validar_hallazgo(h, indice, correos):
    """Devuelve lista de errores para un hallazgo. Vacia = esta bien.

    `correos` mapea mail_id -> AgenteMail de los pendientes de esta tanda."""
    errores = []
    prefijo = f'hallazgos[{indice}]'

    tipo = h.get('tipo')
    if tipo not in TIPOS_VALIDOS:
        errores.append(f'{prefijo}: tipo "{tipo}" invalido '
                       f'(esperaba {sorted(TIPOS_VALIDOS)}).')
        return errores

    mail_id = h.get('mail_id')
    if mail_id is not None and mail_id not in correos:
        errores.append(f'{prefijo}: mail_id {mail_id} no esta entre los correos pendientes.')

    if h.get('confianza') and h['confianza'] not in CONFIANZAS_VALIDAS:
        errores.append(f'{prefijo}: confianza "{h["confianza"]}" invalida.')

    detalle = h.get('detalle') or {}

    if tipo == 'tarifa':
        if not detalle.get('cot_id'):
            errores.append(f'{prefijo}: falta detalle.cot_id.')
        if not detalle.get('kg'):
            errores.append(f'{prefijo}: falta detalle.kg.')
        if detalle.get('tarifa_nueva') in (None, ''):
            errores.append(f'{prefijo}: falta detalle.tarifa_nueva.')

    if tipo == 'fsc':
        if detalle.get('fsc_nuevo') in (None, ''):
            errores.append(f'{prefijo}: falta detalle.fsc_nuevo.')
        if 'destinos' not in detalle:
            errores.append(f'{prefijo}: falta detalle.destinos '
                           f'([] = todos los destinos; se exige explicito).')
        if not h.get('aerolinea') and not detalle.get('aerolinea'):
            errores.append(f'{prefijo}: falta aerolinea.')

    if tipo == 'cargo':
        if not detalle.get('concepto'):
            errores.append(f'{prefijo}: falta detalle.concepto.')
        if detalle.get('monto_nuevo') in (None, ''):
            errores.append(f'{prefijo}: falta detalle.monto_nuevo.')

    return errores


def _motivo_no_aplicable(h, correos):
    """Por que un hallazgo de tarifa NO puede aplicarse, o None si puede.

    Las tarifas netas se toman unicamente de las respuestas de la aerolinea a
    una solicitud de Daniela: ella pide ("Tarifa Flor") y le contestan sobre
    el mismo hilo. Un comunicado que la aerolinea mando por su cuenta no se
    aplica aunque traiga una tabla, y una reserva o guia menos todavia: sus
    cifras por kilo son el precio de ese embarque, no la tarifa vigente.
    El FSC es la excepcion y si llega directo, por eso aca solo entra tarifa.

    Esto se hace cumplir aca y no solo en el skill porque se aplica sobre
    datos de produccion: la instruccion sola no basta."""
    if h.get('tipo') != 'tarifa':
        return None
    correo = correos.get(h.get('mail_id'))
    if correo is None:
        return None
    asunto = (correo.asunto or '')[:50]
    if correo.operativo:
        return (f'No se aplica: el correo "{asunto}" es una reserva o guia, y '
                f'las cifras por kilo son el precio de ese embarque, no la '
                f'tarifa vigente.')
    if not correo.respuesta_mia:
        return (f'No se aplica: el correo "{asunto}" no es respuesta a una '
                f'solicitud tuya de tarifas. Si te interesa, pidele la tarifa '
                f'a la aerolinea y se actualiza con su respuesta.')
    return None


def _sin_indice(error):
    """'hallazgos[10]: falta detalle.concepto.' -> 'falta detalle.concepto.'"""
    return re.sub(r'^hallazgos\[\d+\]:\s*', '', error)


def _dejar_como_aviso(h, motivo):
    """Convierte un hallazgo en tipo "info": se ve en el portal, no se aplica.

    La cifra se conserva en la descripcion para que Daniela sepa que numero
    llego, aunque no se pueda aplicar desde aca."""
    detalle = h.get('detalle') or {}
    valor = str(h.get('valor_nuevo') or detalle.get('tarifa_nueva') or '').strip()
    descripcion = (h.get('descripcion') or '').strip()
    if valor and valor not in descripcion:
        descripcion = f'{descripcion} Cifra del correo: {valor}.'.strip()
    h['tipo'] = 'info'
    h['descripcion'] = descripcion
    h['_aviso'] = motivo


def _norm_kg(kg):
    kg = str(kg or '').strip()
    return kg if kg.startswith('+') else '+' + kg


def clave_hallazgo(tipo, aerolinea, detalle):
    """Identidad de "la misma cosa" para efectos de vigencia.

    Dos hallazgos con la misma clave hablan de la misma tarifa / FSC / cargo,
    asi que solo vale el que venga del correo mas reciente: una tarifa de hace
    un mes no sirve si llego una nueva la semana pasada."""
    detalle = detalle or {}
    aero = (aerolinea or detalle.get('aerolinea') or '').upper().strip()

    if tipo == 'tarifa':
        return ('tarifa', aero, str(detalle.get('cot_id') or ''),
                _norm_kg(detalle.get('kg')))
    if tipo == 'fsc':
        destinos = tuple(sorted(
            str(d).upper().strip() for d in (detalle.get('destinos') or [])
        ))
        return ('fsc', aero, destinos)
    if tipo == 'cargo':
        return ('cargo', aero, str(detalle.get('concepto') or '').upper().strip())
    if tipo == 'dias':
        return ('dias', aero)
    return None   # los informativos no se deduplican


def _quedarse_con_lo_mas_nuevo(hallazgos, fecha_de_mail):
    """De cada grupo de hallazgos equivalentes, deja solo el del correo mas
    reciente. Devuelve (vigentes, descartados)."""
    mejor = {}
    sueltos = []

    for h in hallazgos:
        clave = clave_hallazgo(h.get('tipo'), h.get('aerolinea'), h.get('detalle'))
        if clave is None:
            sueltos.append(h)
            continue
        fecha = fecha_de_mail(h.get('mail_id')) or datetime.min
        anterior = mejor.get(clave)
        if anterior is None or fecha > anterior[0]:
            mejor[clave] = (fecha, h)

    vigentes = sueltos + [par[1] for par in mejor.values()]
    descartados = len(hallazgos) - len(vigentes)
    return vigentes, descartados


def _ids_de_la_tanda():
    """Los mail_id que se exportaron en la ultima tanda.

    Es lo que delimita hasta donde llego el analisis. Devuelve None si no se
    puede leer el archivo, y en ese caso el caller no marca nada de mas."""
    if not os.path.exists(ARCHIVO_PENDIENTES):
        return None
    try:
        with open(ARCHIVO_PENDIENTES, 'r', encoding='utf-8-sig') as fh:
            datos = json.load(fh)
    except (ValueError, OSError):
        return None
    return {c.get('mail_id') for c in (datos.get('correos') or [])}


def cmd_cargar(args):
    if not os.path.exists(ARCHIVO_HALLAZGOS):
        sys.exit(f'No existe {ARCHIVO_HALLAZGOS}. Genera ese archivo con Claude Code primero.')

    # utf-8-sig: en Windows muchos editores guardan con BOM y utf-8 a secas
    # falla con un error que no dice nada util.
    with open(ARCHIVO_HALLAZGOS, 'r', encoding='utf-8-sig') as fh:
        try:
            datos = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f'{ARCHIVO_HALLAZGOS} no es JSON valido: {exc}')

    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux.models import AgenteMail, AgenteHallazgo
    from lux_portal.agente_lux import reglas

    with app.app_context():
        pendientes = {m.id: m for m in AgenteMail.query.filter_by(estado='pendiente').all()}
        hallazgos_entrada = datos.get('hallazgos') or []

        # Primero la regla de negocio y despues el formato: una tarifa que no
        # puede aplicarse pasa a ser aviso, y a un aviso no se le exige cot_id.
        # Va antes de la deduplicacion a proposito: si no, un comunicado mas
        # nuevo le ganaria a la respuesta valida que si se puede aplicar.
        no_aplicables = 0
        for h in hallazgos_entrada:
            motivo = _motivo_no_aplicable(h, pendientes)
            if motivo:
                _dejar_como_aviso(h, motivo)
                no_aplicables += 1

        # Formato: lo que venga incompleto queda como aviso en vez de tumbar
        # la carga entera. Tumbarla dejaba la tanda atascada para siempre: el
        # vigia la volvia a exportar, Claude volvia a producir lo mismo y el
        # portal repetia el error, con 15 minutos de analisis perdidos cada
        # vez. Solo se descarta lo que no se puede ni ubicar: tipo desconocido
        # o correo que no esta en la cola.
        incompletos, descartados_formato = 0, 0
        validos = []
        for i, h in enumerate(hallazgos_entrada):
            errores = _validar_hallazgo(h, i, pendientes)
            if not errores:
                validos.append(h)
                continue
            mail_id = h.get('mail_id')
            if (h.get('tipo') not in TIPOS_VALIDOS
                    or (mail_id is not None and mail_id not in pendientes)):
                descartados_formato += 1
                print('  - descartado: ' + ' '.join(errores))
                continue
            _dejar_como_aviso(h, 'Propuesta incompleta, no se aplica sola: '
                              + ' '.join(_sin_indice(e) for e in errores))
            incompletos += 1
            validos.append(h)
        hallazgos_entrada = validos

        # Resumenes por correo
        n_correos = 0
        for entrada in (datos.get('correos') or []):
            correo = pendientes.get(entrada.get('mail_id'))
            if not correo:
                continue
            correo.categoria = (entrada.get('categoria') or 'otro')[:50]
            correo.resumen = entrada.get('resumen') or ''
            correo.temas = entrada.get('temas') or []
            correo.requiere_accion = bool(entrada.get('requiere_accion'))
            correo.estado = 'analizado'
            correo.analizado_en = datetime.utcnow()
            n_correos += 1

        # Solo vale la version mas reciente de cada tarifa / FSC / cargo.
        def fecha_de_mail(mail_id):
            correo = pendientes.get(mail_id)
            return correo.fecha if correo else None

        entrantes, descartados_por_viejos = _quedarse_con_lo_mas_nuevo(
            hallazgos_entrada, fecha_de_mail
        )

        # Un hallazgo nuevo tambien reemplaza a uno pendiente de una corrida
        # anterior que hable de lo mismo, para que el portal no muestre dos
        # propuestas contradictorias para la misma tarifa.
        superados = 0
        previos = AgenteHallazgo.query.filter_by(estado='pendiente').all()
        claves_entrantes = {
            clave_hallazgo(h.get('tipo'), h.get('aerolinea'), h.get('detalle'))
            for h in entrantes
        }
        claves_entrantes.discard(None)

        for previo in previos:
            clave = clave_hallazgo(previo.tipo, previo.aerolinea, previo.detalle)
            if clave is not None and clave in claves_entrantes:
                previo.estado = 'descartado'
                superados += 1

        # Hallazgos
        n_hallazgos = 0
        con_alerta = 0
        for h in entrantes:
            detalle = h.get('detalle') or {}
            destino = h.get('destino') or ''
            if h.get('tipo') == 'fsc' and not destino:
                destinos = detalle.get('destinos') or []
                destino = ', '.join(destinos) if destinos else ''

            alerta = reglas.revisar({
                'tipo': h.get('tipo'),
                'destino': destino,
                'detalle': detalle,
            })
            if h.get('_aviso'):
                # La razon por la que no se aplica va primero: es lo que
                # Daniela tiene que leer antes que cualquier otra alerta.
                alerta = h['_aviso'] + (' ' + alerta if alerta else '')
            if alerta:
                con_alerta += 1

            hallazgo = AgenteHallazgo(
                mail_id=h.get('mail_id'),
                tipo=h.get('tipo'),
                aerolinea=(h.get('aerolinea') or detalle.get('aerolinea') or '')[:100],
                destino=destino[:20],
                descripcion=h.get('descripcion') or '',
                valor_actual=str(h.get('valor_actual') or '')[:50],
                valor_nuevo=str(h.get('valor_nuevo') or '')[:50],
                confianza=h.get('confianza') or 'media',
                cita=h.get('cita') or '',
                alerta=alerta,
                estado='pendiente',
            )
            hallazgo.detalle = detalle
            db.session.add(hallazgo)
            n_hallazgos += 1

        # Los correos de esta tanda que el analisis no menciono quedan
        # marcados como revisados sin novedades, para que no se re-exporten
        # siempre.
        #
        # OJO: solo los de ESTA tanda. Con el analisis por tandas, los demas
        # pendientes no se miraron siquiera; darlos por revisados los sacaria
        # de la cola para siempre y se perderian tarifas en silencio.
        en_la_tanda = _ids_de_la_tanda()
        mencionados = {e.get('mail_id') for e in (datos.get('correos') or [])}
        sin_mencionar = 0
        for mail_id, correo in pendientes.items():
            if mail_id in mencionados:
                continue
            if en_la_tanda is not None and mail_id not in en_la_tanda:
                continue
            correo.estado = 'analizado'
            correo.categoria = 'otro'
            correo.resumen = 'Sin novedades de tarifas ni FSC.'
            correo.analizado_en = datetime.utcnow()
            sin_mencionar += 1

        db.session.commit()

    print(f'{n_hallazgos} hallazgo(s) cargados, {n_correos} correo(s) resumidos.')
    if incompletos:
        print(f'{incompletos} propuesta(s) venian incompletas y quedaron solo '
              f'como aviso.')
    if descartados_formato:
        print(f'{descartados_formato} propuesta(s) descartadas por no poder '
              f'ubicarlas (tipo desconocido o correo fuera de la cola).')
    if no_aplicables:
        print(f'{no_aplicables} tarifa(s) quedaron solo como aviso: no vienen de '
              f'una respuesta a tu solicitud, o salen de una reserva o guia.')
    if descartados_por_viejos:
        print(f'{descartados_por_viejos} hallazgo(s) ignorados por venir de un '
              f'correo mas viejo que otro que habla de lo mismo.')
    if superados:
        print(f'{superados} propuesta(s) anteriores quedaron descartadas porque '
              f'llego informacion mas reciente.')
    if sin_mencionar:
        print(f'{sin_mencionar} correo(s) marcados como sin novedades.')
    if con_alerta:
        print(f'{con_alerta} hallazgo(s) traen alerta de reglas de negocio. '
              f'Revisalos con cuidado en el portal.')
    print('Listo. Abre Agente Lux en el portal para aprobar y aplicar.')


# ---------------------------------------------------------------------------
# exportar-resumen / cargar-resumen: la pasada liviana para la bitacora
# ---------------------------------------------------------------------------

def cmd_exportar_resumen(args):
    """Vuelca los correos en cola de resumen, solo texto, sin adjuntos.

    Mas nuevos primero: lo del dia es lo que Daniela esta mirando."""
    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux.models import AgenteMail, AgenteAdjunto
    from lux_portal.agente_lux.texto import limpiar_banners, sin_enlaces

    with app.app_context():
        cola = (_filtrar_rango(AgenteMail.query.filter_by(estado='por_resumir'), args)
                .order_by(AgenteMail.fecha.desc())
                .all())
        quedan = 0
        if args.max_correos and len(cola) > args.max_correos:
            quedan = len(cola) - args.max_correos
            cola = cola[:args.max_correos]

        # Solo los nombres de los adjuntos, en una consulta para toda la
        # tanda: cargarlos correo por correo eran 40 viajes a la base, y
        # traerlos completos arrastraria las imagenes que aca no se usan.
        nombres_adj = {}
        if cola:
            filas = (db.session.query(AgenteAdjunto.mail_id, AgenteAdjunto.nombre)
                     .filter(AgenteAdjunto.mail_id.in_([c.id for c in cola])).all())
            for mail_id, nombre in filas:
                nombres_adj.setdefault(mail_id, []).append(nombre)

        correos = []
        for c in cola:
            cuerpo = sin_enlaces(limpiar_banners(c.cuerpo))
            correos.append({
                'mail_id': c.id,
                'fecha': c.fecha.strftime('%Y-%m-%d %H:%M') if c.fecha else None,
                'carpeta': c.carpeta or '',
                'remitente': c.remitente,
                'remitente_nombre': c.remitente_nombre,
                'asunto': c.asunto,
                'es_reserva_o_guia': bool(c.operativo),
                # Suficiente para saber de que es; el resto suele ser firma
                # y el hilo citado.
                'cuerpo': cuerpo[:2500],
                'adjuntos': nombres_adj.get(c.id, []),
            })

    os.makedirs(CARPETA, exist_ok=True)
    with open(ARCHIVO_POR_RESUMIR, 'w', encoding='utf-8') as fh:
        json.dump({'generado_en': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'correos': correos}, fh, ensure_ascii=False, indent=2)

    if not correos:
        print('No hay nada por resumir.')
        return
    print(f'{len(correos)} correo(s) por resumir exportados a {ARCHIVO_POR_RESUMIR}')
    if quedan:
        print(f'  quedan {quedan} para la siguiente tanda')


def cmd_cargar_resumen(args):
    """Sube _agente_lux/resumenes.json: categoria, resumen y temas por correo."""
    if not os.path.exists(ARCHIVO_RESUMENES):
        sys.exit(f'No existe {ARCHIVO_RESUMENES}.')
    with open(ARCHIVO_RESUMENES, 'r', encoding='utf-8-sig') as fh:
        try:
            datos = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f'{ARCHIVO_RESUMENES} no es JSON valido: {exc}')

    try:
        with open(ARCHIVO_POR_RESUMIR, 'r', encoding='utf-8-sig') as fh:
            en_la_tanda = {c.get('mail_id') for c in json.load(fh).get('correos', [])}
    except (OSError, ValueError):
        en_la_tanda = set()

    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux.models import AgenteMail

    with app.app_context():
        cola = {m.id: m for m in AgenteMail.query.filter_by(estado='por_resumir').all()}
        resumidos, sin_resumen = 0, 0
        vistos = set()
        for entrada in (datos.get('correos') or []):
            correo = cola.get(entrada.get('mail_id'))
            if not correo:
                continue
            resumen = (entrada.get('resumen') or '').strip()
            if not resumen:
                continue
            categoria = (entrada.get('categoria') or '').strip().lower()
            if categoria in CATEGORIAS_VALIDAS:
                correo.categoria = categoria
            correo.resumen = resumen
            correo.temas = entrada.get('temas') or []
            correo.requiere_accion = bool(entrada.get('requiere_accion'))
            correo.estado = 'analizado'
            correo.analizado_en = datetime.utcnow()
            vistos.add(correo.id)
            resumidos += 1

        # Lo que estaba en la tanda y no volvio con resumen no se queda en
        # la cola para siempre: pasa a analizado sin resumen y el portal
        # muestra el primer parrafo en su lugar.
        for mail_id, correo in cola.items():
            if mail_id in vistos or mail_id not in en_la_tanda:
                continue
            correo.estado = 'analizado'
            correo.analizado_en = datetime.utcnow()
            sin_resumen += 1

        db.session.commit()

    print(f'{resumidos} correo(s) resumidos.')
    if sin_resumen:
        print(f'{sin_resumen} correo(s) de la tanda volvieron sin resumen; quedan '
              f'con su primer parrafo.')


# ---------------------------------------------------------------------------
# contactos-enviados: a quien le pide tarifas Daniela, segun sus enviados
# ---------------------------------------------------------------------------

ARCHIVO_ENVIADOS = os.path.join(CARPETA, 'contactos_enviados.json')


def cmd_contactos_enviados(args):
    """Vuelca a _agente_lux/contactos_enviados.json los correos de solicitud
    de tarifas que Daniela mando en los ultimos --dias, con destinatarios
    reales y los IATA que pidio. Corre en la PC, con Outlook abierto."""
    from lux_portal.agente_lux import outlook_local

    desde = datetime.now() - timedelta(days=args.dias)
    try:
        enviados = outlook_local.leer_enviados(desde, filtro_asunto=args.asunto)
    except outlook_local.OutlookNoDisponible as exc:
        sys.exit(str(exc))

    os.makedirs(CARPETA, exist_ok=True)
    with open(ARCHIVO_ENVIADOS, 'w', encoding='utf-8') as fh:
        json.dump({'generado_en': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                   'dias': args.dias, 'enviados': enviados},
                  fh, ensure_ascii=False, indent=2)
    print(f'{len(enviados)} correo(s) enviados con "{args.asunto}" en el asunto, '
          f'guardados en {ARCHIVO_ENVIADOS}')
    for e in enviados[:60]:
        para = ', '.join(d['email'] or d['nombre'] for d in e['para'])
        print(f"  {e['fecha']} | {e['asunto'][:28]:28} | {para[:60]:60} | {' '.join(e['iatas'])[:50]}")


# ---------------------------------------------------------------------------
# enviar: manda por Outlook lo que quedo en cola en la pestana Mails
# ---------------------------------------------------------------------------

def cmd_enviar(args):
    """Version a mano de lo que hace el vigia cuando hay envios en cola."""
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux import envio_local, outlook_local

    with app.app_context():
        try:
            enviados, fallidos = envio_local.enviar_pendientes()
        except outlook_local.OutlookNoDisponible as exc:
            sys.exit(str(exc))
    print(f'{enviados} correo(s) enviados por Outlook.')
    if fallidos:
        print(f'{fallidos} con error: revisa la pestana Mails del portal.')


# ---------------------------------------------------------------------------
# estado
# ---------------------------------------------------------------------------

def cmd_estado(args):
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux.models import (
        AgenteCuenta, AgenteMail, AgenteHallazgo, a_ecuador,
    )

    with app.app_context():
        cuenta = AgenteCuenta.query.first()
        print('Cuenta conectada :', cuenta.email if cuenta else 'ninguna')
        if cuenta and cuenta.ultimo_scan:
            print('Ultimo refresh   :',
                  a_ecuador(cuenta.ultimo_scan).strftime('%Y-%m-%d %H:%M'),
                  '(hora Ecuador)')
        print('Correos por analizar:', AgenteMail.query.filter_by(estado='pendiente').count())
        print('Correos por resumir :', AgenteMail.query.filter_by(estado='por_resumir').count())
        print('Hallazgos pendientes:', AgenteHallazgo.query.filter_by(estado='pendiente').count())
        print('Hallazgos aplicados :', AgenteHallazgo.query.filter_by(estado='aplicado').count())


# ---------------------------------------------------------------------------
# leer-outlook  (alternativa a Microsoft Graph, sin aprobacion del admin)
# ---------------------------------------------------------------------------

# El rango de lectura lo decide ingesta_local, que es el mismo codigo que usa
# el vigia cuando la lectura la dispara el boton del portal.


def cmd_carpetas(args):
    """Lista las carpetas de Outlook, para saber que pasarle a --carpeta."""
    from lux_portal.agente_lux import outlook_local

    try:
        print('Cuenta:', outlook_local.cuenta_principal() or '(no identificada)')
        print()
        print('Carpetas disponibles:')
        for nombre in outlook_local.listar_carpetas():
            print('  ' + nombre)
    except outlook_local.OutlookNoDisponible as exc:
        sys.exit(str(exc))


def cmd_leer_outlook(args):
    """Lee el buzon desde el Outlook de escritorio y guarda los correos nuevos.

    Es la version a mano de lo mismo que hace el vigia cuando Daniela aprieta
    el boton del portal: los dos llaman a ingesta_local.ingerir."""
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux import ingesta_local, outlook_local

    with app.app_context():
        existia = ingesta_local.cuenta_local(crear=False) is not None
        try:
            cuenta = ingesta_local.cuenta_local()
        except outlook_local.OutlookNoDisponible as exc:
            sys.exit(str(exc))
        if not existia:
            print(f'Cuenta local registrada: {cuenta.email}')

        alcance = args.carpeta + ('' if args.sin_subcarpetas else ' (con subcarpetas)')
        desde, hasta = _fechas_rango(args)
        print(f'Leyendo "{alcance}" ...')

        try:
            stats = ingesta_local.ingerir(
                cuenta,
                desde=desde,
                hasta=hasta,
                dias=args.dias,
                carpeta=args.carpeta,
                limite=args.limite,
                recursivo=not args.sin_subcarpetas,
            )
        except outlook_local.OutlookNoDisponible as exc:
            sys.exit(str(exc))

    print(f'{stats["revisados"]} correo(s) revisados, '
          f'{stats["nuevos"]} nuevo(s) guardados.')
    if stats['adjuntos']:
        print(f'{stats["adjuntos"]} adjunto(s) con contenido (imagenes/PDF).')

    if stats['truncado']:
        print()
        print(f'AVISO: se llego al tope de {args.limite} correos, asi que puede '
              f'haber mas dentro del rango sin leer.')
        print('No se movio la marca de la ultima lectura. Corre de nuevo con un '
              'rango mas corto, por ejemplo:  --dias 2')

    if stats['pendientes']:
        print()
        print(f'Hay {stats["pendientes"]} correo(s) por analizar. Siguiente paso:')
        print('  python agente_lux_cli.py exportar')
    else:
        print('No quedo nada pendiente de analisis.')


def cmd_clasificar(args):
    """Rellena las senales de origen en los correos ya leidos.

    Se calculan sobre el asunto y el cuerpo que ya estan guardados, sin abrir
    Outlook, asi que corre en segundos. Sirve para los correos que se leyeron
    antes de que existieran estas columnas."""
    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux.models import AgenteCuenta, AgenteMail
    from lux_portal.agente_lux import outlook_local

    with app.app_context():
        cuenta = AgenteCuenta.query.first()
        mi_correo = cuenta.email if cuenta else ''
        if not mi_correo:
            sys.exit('No hay cuenta guardada, no se sabe cual es tu direccion.')
        print(f'Tu direccion: {mi_correo}')

        correos = AgenteMail.query.all()
        respuestas, operativos = 0, 0

        for correo in correos:
            correo.respuesta_mia = outlook_local.es_respuesta_a_mi(
                correo.asunto, correo.cuerpo, mi_correo)
            correo.operativo = outlook_local.parece_operativo(correo.asunto)
            if correo.respuesta_mia:
                respuestas += 1
            if correo.operativo:
                operativos += 1

        db.session.commit()

    print()
    print(f'{len(correos)} correo(s) clasificados:')
    print(f'  {respuestas} contestan a una solicitud tuya de tarifas')
    print(f'  {operativos} son reservas, cierres o guias (bloqueados como '
          f'fuente de tarifas)')


def main():
    parser = argparse.ArgumentParser(
        description='Puente entre el portal Lux y el analisis local de correos.'
    )
    parser.add_argument('--db', help='URL de PostgreSQL (por defecto usa DATABASE_URL).')
    sub = parser.add_subparsers(dest='comando', required=True)

    p_outlook = sub.add_parser(
        'leer-outlook',
        help='Lee el buzon desde el Outlook de escritorio (sin Azure ni admin).')
    p_outlook.add_argument('--dias', type=int, default=0,
                           help='Leer los ultimos N dias. Sin --dias ni '
                                '--desde/--hasta se lee solo el dia de hoy.')
    _agregar_rango(p_outlook)
    p_outlook.add_argument('--carpeta', default='Inbox',
                           help='Carpeta a leer. Por defecto Inbox con todas sus '
                                'subcarpetas. Para solo tarifas: '
                                '--carpeta "Inbox/AEROLINEAS"')
    p_outlook.add_argument('--sin-subcarpetas', action='store_true',
                           dest='sin_subcarpetas',
                           help='Leer solo la carpeta indicada, sin entrar a las de adentro.')
    p_outlook.add_argument('--limite', type=int, default=500,
                           help='Tope de correos por corrida (por defecto 500).')

    sub.add_parser('carpetas', help='Lista las carpetas de Outlook disponibles.')
    sub.add_parser('clasificar',
                   help='Marca en los correos ya leidos cuales contestan a una '
                        'solicitud tuya y cuales son reservas o guias.')

    p_exp = sub.add_parser('exportar',
                           help='Vuelca los correos pendientes a _agente_lux/.')
    p_exp.add_argument('--solo-tarifas', action='store_true', dest='solo_tarifas',
                       help='Mandar a Claude solo los correos que parecen traer '
                            'tarifas o recargos y las respuestas a tus '
                            'solicitudes. El resto se clasifica por el asunto '
                            'y queda en la bitacora sin resumen. Mucho mas '
                            'rapido.')
    p_exp.add_argument('--max-correos', type=int, default=0, dest='max_correos',
                       help='Tope de correos por tanda. 0 = todos.')
    _agregar_rango(p_exp)
    sub.add_parser('cargar', help='Sube _agente_lux/hallazgos.json al portal.')

    p_res = sub.add_parser('exportar-resumen',
                           help='Vuelca los correos sin tarifas que esperan resumen '
                                '(solo texto, sin adjuntos).')
    p_res.add_argument('--max-correos', type=int, default=40, dest='max_correos',
                       help='Tope de correos por tanda (por defecto 40). 0 = todos.')
    _agregar_rango(p_res)
    sub.add_parser('cargar-resumen',
                   help='Sube _agente_lux/resumenes.json a la bitacora del portal.')
    sub.add_parser('enviar',
                   help='Manda por Outlook los correos en cola de la pestana Mails.')
    p_env = sub.add_parser('contactos-enviados',
                           help='Vuelca a quien le mando Daniela solicitudes de '
                                'tarifas (Elementos enviados de Outlook).')
    p_env.add_argument('--dias', type=int, default=120)
    p_env.add_argument('--asunto', default='tarifa',
                       help='Palabra que debe tener el asunto (por defecto "tarifa").')
    sub.add_parser('estado', help='Contadores rapidos.')

    args = parser.parse_args()
    {
        'leer-outlook': cmd_leer_outlook,
        'carpetas': cmd_carpetas,
        'clasificar': cmd_clasificar,
        'exportar': cmd_exportar,
        'cargar': cmd_cargar,
        'exportar-resumen': cmd_exportar_resumen,
        'cargar-resumen': cmd_cargar_resumen,
        'enviar': cmd_enviar,
        'contactos-enviados': cmd_contactos_enviados,
        'estado': cmd_estado,
    }[args.comando](args)


if __name__ == '__main__':
    main()
