#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente Lux - puente entre el portal y el analisis local con Claude Code.

El portal (Railway) baja los correos; el analisis lo hace Claude Code aca en
la maquina, usando la suscripcion en vez de creditos de API. Este script mueve
los datos en las dos direcciones.

USO
---
    python agente_lux_cli.py exportar     # correos pendientes -> _agente_lux/
    python agente_lux_cli.py cargar       # _agente_lux/hallazgos.json -> portal
    python agente_lux_cli.py estado       # contadores rapidos

La conexion sale de DATABASE_URL (la de Railway) o de --db.

FLUJO COMPLETO
--------------
 1. En el portal: boton "Refresh correos".
 2. Aca:  python agente_lux_cli.py exportar
 3. En Claude Code: "analiza _agente_lux/pendientes.json y escribe
    _agente_lux/hallazgos.json"  (ver FORMATO abajo)
 4. Aca:  python agente_lux_cli.py cargar
 5. En el portal: revisar, corregir si hace falta, aprobar y aplicar.

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
from datetime import datetime

CARPETA = '_agente_lux'
ARCHIVO_PENDIENTES = os.path.join(CARPETA, 'pendientes.json')
ARCHIVO_HALLAZGOS = os.path.join(CARPETA, 'hallazgos.json')
CARPETA_ADJUNTOS = os.path.join(CARPETA, 'adjuntos')

TIPOS_VALIDOS = {'tarifa', 'fsc', 'cargo', 'dias', 'info'}
CONFIANZAS_VALIDAS = {'alta', 'media', 'baja'}


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
    url = args.db or os.environ.get('DATABASE_URL', '').strip()
    if not url:
        sys.exit('Falta la conexion. Exporta DATABASE_URL o pasa --db '
                 '"postgresql://usuario:clave@host:puerto/base".')
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

        os.makedirs(CARPETA_ADJUNTOS, exist_ok=True)
        correos = []
        n_adjuntos = 0

        for correo in pendientes:
            archivos = []
            for adj in correo.adjuntos:
                registro = {'nombre': adj.nombre, 'mime': adj.mime, 'size': adj.size}
                if adj.contenido_b64:
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

    print(f'{len(correos)} correo(s) pendientes exportados a {ARCHIVO_PENDIENTES}')
    if n_adjuntos:
        print(f'{n_adjuntos} adjunto(s) guardados en {CARPETA_ADJUNTOS}/')
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

        # Hallazgos
        n_hallazgos = 0
        con_alerta = 0
        for h in (datos.get('hallazgos') or []):
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


def main():
    parser = argparse.ArgumentParser(
        description='Puente entre el portal Lux y el analisis local de correos.'
    )
    parser.add_argument('--db', help='URL de PostgreSQL (por defecto usa DATABASE_URL).')
    sub = parser.add_subparsers(dest='comando', required=True)

    sub.add_parser('exportar', help='Vuelca los correos pendientes a _agente_lux/.')
    sub.add_parser('cargar', help='Sube _agente_lux/hallazgos.json al portal.')
    sub.add_parser('estado', help='Contadores rapidos.')

    args = parser.parse_args()
    {'exportar': cmd_exportar, 'cargar': cmd_cargar, 'estado': cmd_estado}[args.comando](args)


if __name__ == '__main__':
    main()
