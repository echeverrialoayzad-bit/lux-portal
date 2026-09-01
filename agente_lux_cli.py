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
    python agente_lux_cli.py estado        # contadores rapidos

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


# ---------------------------------------------------------------------------
# exportar
# ---------------------------------------------------------------------------

def cmd_exportar(args):
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux.models import AgenteMail
    from lux_portal.agente_lux import contexto

    with app.app_context():
        pendientes = (AgenteMail.query
                      .filter_by(estado='pendiente')
                      .order_by(AgenteMail.fecha.asc())
                      .all())

        relevantes = {c.id for c in pendientes if parece_tarifas(c)}
        if args.solo_tarifas:
            pendientes = [c for c in pendientes if c.id in relevantes]

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

def _validar_hallazgo(h, indice, ids_validos):
    """Devuelve lista de errores para un hallazgo. Vacia = esta bien."""
    errores = []
    prefijo = f'hallazgos[{indice}]'

    tipo = h.get('tipo')
    if tipo not in TIPOS_VALIDOS:
        errores.append(f'{prefijo}: tipo "{tipo}" invalido '
                       f'(esperaba {sorted(TIPOS_VALIDOS)}).')
        return errores

    mail_id = h.get('mail_id')
    if mail_id is not None and mail_id not in ids_validos:
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

        # Validar todo antes de escribir nada.
        errores = []
        for i, h in enumerate(datos.get('hallazgos') or []):
            errores.extend(_validar_hallazgo(h, i, set(pendientes.keys())))

        if errores:
            print('El archivo tiene problemas y no se cargo nada:\n')
            for e in errores:
                print('  - ' + e)
            sys.exit(1)

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
            datos.get('hallazgos') or [], fecha_de_mail
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

        # Los correos pendientes que el analisis no menciono quedan marcados
        # como analizados sin hallazgos, para que no se re-exporten siempre.
        mencionados = {e.get('mail_id') for e in (datos.get('correos') or [])}
        sin_mencionar = 0
        for mail_id, correo in pendientes.items():
            if mail_id in mencionados:
                continue
            correo.estado = 'analizado'
            correo.categoria = 'otro'
            correo.resumen = 'Sin novedades de tarifas ni FSC.'
            correo.analizado_en = datetime.utcnow()
            sin_mencionar += 1

        db.session.commit()

    print(f'{n_hallazgos} hallazgo(s) cargados, {n_correos} correo(s) resumidos.')
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
# estado
# ---------------------------------------------------------------------------

def cmd_estado(args):
    app = crear_app(resolver_db(args))
    from lux_portal.agente_lux.models import (
        AgenteCuenta, AgenteMail, AgenteHallazgo,
    )

    with app.app_context():
        cuenta = AgenteCuenta.query.first()
        print('Cuenta conectada :', cuenta.email if cuenta else 'ninguna')
        if cuenta and cuenta.ultimo_scan:
            print('Ultimo refresh   :', cuenta.ultimo_scan.strftime('%Y-%m-%d %H:%M'))
        print('Correos por analizar:', AgenteMail.query.filter_by(estado='pendiente').count())
        print('Hallazgos pendientes:', AgenteHallazgo.query.filter_by(estado='pendiente').count())
        print('Hallazgos aplicados :', AgenteHallazgo.query.filter_by(estado='aplicado').count())


# ---------------------------------------------------------------------------
# leer-outlook  (alternativa a Microsoft Graph, sin aprobacion del admin)
# ---------------------------------------------------------------------------

DIAS_PRIMERA_LECTURA = 7
HORAS_SOLAPE = 6


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
    """Lee el buzon desde el Outlook de escritorio y guarda los correos nuevos."""
    from lux_portal.agente_lux import outlook_local

    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux.models import AgenteCuenta, AgenteMail, AgenteAdjunto

    with app.app_context():
        cuenta = AgenteCuenta.query.first()

        if cuenta is None:
            try:
                email = outlook_local.cuenta_principal()
            except outlook_local.OutlookNoDisponible as exc:
                sys.exit(str(exc))
            cuenta = AgenteCuenta(email=email or 'Outlook local', modo='local',
                                  conectada_en=datetime.utcnow())
            db.session.add(cuenta)
            db.session.commit()
            print(f'Cuenta local registrada: {cuenta.email}')
        elif (cuenta.modo or 'graph') != 'local':
            sys.exit('La cuenta guardada esta en modo Microsoft 365. Para pasar a '
                     'modo local, desconectala primero desde el portal.')

        if args.dias:
            desde = datetime.now() - timedelta(days=args.dias)
        elif cuenta.ultimo_scan:
            desde = cuenta.ultimo_scan - timedelta(hours=HORAS_SOLAPE)
        else:
            desde = datetime.now() - timedelta(days=DIAS_PRIMERA_LECTURA)

        alcance = args.carpeta + ('' if args.sin_subcarpetas else ' (con subcarpetas)')
        print(f'Leyendo "{alcance}" desde {desde.strftime("%Y-%m-%d %H:%M")} ...')

        try:
            correos = outlook_local.leer(
                desde,
                carpeta=args.carpeta,
                limite=args.limite,
                recursivo=not args.sin_subcarpetas,
            )
        except outlook_local.OutlookNoDisponible as exc:
            sys.exit(str(exc))

        truncado = len(correos) >= args.limite
        nuevos, adjuntos_guardados = 0, 0

        for datos in correos:
            if AgenteMail.query.filter_by(graph_id=datos['id_unico']).first():
                continue

            correo = AgenteMail(
                graph_id=datos['id_unico'],
                fecha=datos['fecha'],
                carpeta=(datos.get('carpeta') or '')[:300],
                remitente=(datos['remitente'] or '')[:250],
                remitente_nombre=(datos['remitente_nombre'] or '')[:250],
                asunto=(datos['asunto'] or '(sin asunto)')[:500],
                cuerpo=datos['cuerpo'],
                estado='pendiente',
            )
            db.session.add(correo)
            db.session.flush()

            for adj in datos['adjuntos']:
                contenido_b64 = None
                if adj['contenido']:
                    contenido_b64 = base64.b64encode(adj['contenido']).decode('ascii')
                    adjuntos_guardados += 1
                db.session.add(AgenteAdjunto(
                    mail_id=correo.id,
                    nombre=(adj['nombre'] or 'adjunto')[:400],
                    mime=(adj['mime'] or '')[:150],
                    size=adj['size'],
                    contenido_b64=contenido_b64,
                ))
            nuevos += 1

        # Si se llego al tope, hay correos dentro del rango que no se
        # alcanzaron a leer: mover la marca de agua los daria por leidos.
        if not truncado:
            cuenta.ultimo_scan = datetime.utcnow()
        db.session.commit()

        pendientes = AgenteMail.query.filter_by(estado='pendiente').count()

    print(f'{len(correos)} correo(s) revisados, {nuevos} nuevo(s) guardados.')
    if adjuntos_guardados:
        print(f'{adjuntos_guardados} adjunto(s) con contenido (imagenes/PDF).')

    if truncado:
        print()
        print(f'AVISO: se llego al tope de {args.limite} correos, asi que puede '
              f'haber mas dentro del rango sin leer.')
        print('No se movio la marca de la ultima lectura. Corre de nuevo con un '
              'rango mas corto, por ejemplo:  --dias 2')

    if pendientes:
        print()
        print(f'Hay {pendientes} correo(s) por analizar. Siguiente paso:')
        print('  python agente_lux_cli.py exportar')
    else:
        print('No quedo nada pendiente de analisis.')


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
                           help='Cuantos dias hacia atras leer (por defecto, desde '
                                'la ultima lectura; 7 dias la primera vez).')
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

    p_exp = sub.add_parser('exportar',
                           help='Vuelca los correos pendientes a _agente_lux/.')
    p_exp.add_argument('--solo-tarifas', action='store_true', dest='solo_tarifas',
                       help='Exportar unicamente los correos que parecen traer '
                            'tarifas o recargos. Mas rapido, pero la bitacora '
                            'queda sin el resto de los correos.')
    sub.add_parser('cargar', help='Sube _agente_lux/hallazgos.json al portal.')
    sub.add_parser('estado', help='Contadores rapidos.')

    args = parser.parse_args()
    {
        'leer-outlook': cmd_leer_outlook,
        'carpetas': cmd_carpetas,
        'exportar': cmd_exportar,
        'cargar': cmd_cargar,
        'estado': cmd_estado,
    }[args.comando](args)


if __name__ == '__main__':
    main()
