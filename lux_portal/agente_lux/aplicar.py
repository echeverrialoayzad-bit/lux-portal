#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aplicacion de un hallazgo aprobado sobre los datos reales.

Nada de esto corre solo: routes.py solo llama aqui despues de que Daniela
aprobo el hallazgo explicitamente en la pantalla de revision.
"""

from datetime import datetime

from lux_portal.extensions import db
from lux_portal.agente_lux.reglas import TIPOS_SOLO_INFORMATIVOS


def _normalizadores():
    """Reusa los normalizadores del modulo Tarifas para que el emparejamiento
    de aerolineas y tiers sea identico en los dos flujos."""
    from lux_portal.tarifas.routes import _normalizar_aerolinea, _normalizar_kg
    return _normalizar_aerolinea, _normalizar_kg


def aplicar_hallazgo(hallazgo):
    """Aplica un hallazgo aprobado. Devuelve (ok, mensaje).

    No hace commit: el caller decide cuando confirmar toda la tanda."""
    if hallazgo.tipo in TIPOS_SOLO_INFORMATIVOS:
        return False, 'Este hallazgo es informativo y no se aplica automaticamente.'

    if hallazgo.tipo == 'tarifa':
        return _aplicar_tarifa(hallazgo)
    if hallazgo.tipo == 'fsc':
        return _aplicar_fsc(hallazgo)
    if hallazgo.tipo == 'cargo':
        return _aplicar_cargo(hallazgo)

    return False, f'Tipo de hallazgo desconocido: {hallazgo.tipo}'


# ---------------------------------------------------------------------------
# Tarifa neta dentro de una cotizacion
# ---------------------------------------------------------------------------

def _aplicar_tarifa(hallazgo):
    from lux_portal.cotizaciones.models import Cotizacion
    normalizar_aerolinea, normalizar_kg = _normalizadores()

    detalle = hallazgo.detalle
    cot_id = detalle.get('cot_id')
    kg_objetivo = normalizar_kg(detalle.get('kg', ''))

    try:
        tarifa_nueva = float(detalle.get('tarifa_nueva'))
    except (TypeError, ValueError):
        return False, 'La tarifa propuesta no es un numero.'

    cot = Cotizacion.query.get(cot_id) if cot_id else None
    if not cot:
        return False, f'No existe la cotizacion {cot_id}.'

    objetivo = normalizar_aerolinea(hallazgo.aerolinea or '')
    aerolineas = list(cot.aerolineas or [])
    hoy = datetime.now().strftime('%Y-%m-%d')
    tocado = False

    for aero in aerolineas:
        if normalizar_aerolinea(aero.get('aerolinea', '')) != objetivo:
            continue

        kg_rates = list(aero.get('kg_rates', []))
        for i, kr in enumerate(kg_rates):
            if normalizar_kg(kr.get('kg', '')) != kg_objetivo:
                continue

            nuevo = dict(kr)
            margen = _num(nuevo.get('margen'), 0.0)
            costo_operativo = _num(nuevo.get('costo_operativo'), 0.09)
            fsc = _num(nuevo.get('fsc'), 0.0)

            nuevo['tarifa'] = f'{tarifa_nueva:.2f}'
            nuevo['tarifa_cliente'] = f'{tarifa_nueva + margen + costo_operativo + fsc:.2f}'
            kg_rates[i] = nuevo
            tocado = True

        if tocado:
            aero['kg_rates'] = kg_rates
            aero['fecha_actualizacion'] = hoy

    if not tocado:
        return False, (f'No se encontro {objetivo} {kg_objetivo} en la '
                       f'cotizacion {cot_id}.')

    cot.aerolineas = aerolineas
    return True, f'Cotizacion {cot_id}: {objetivo} {kg_objetivo} -> {tarifa_nueva:.2f}'


# ---------------------------------------------------------------------------
# FSC en la tabla maestra
# ---------------------------------------------------------------------------

def _aplicar_fsc(hallazgo):
    """Actualiza o crea una regla de FSC.

    destinos == [] es la regla catch-all de la aerolinea (todos los destinos);
    una lista con IATAs es una regla que aplica solo a esos trayectos."""
    from lux_portal.cotizaciones.models import AirlineFscRule, AirlineFscGroup
    normalizar_aerolinea, _ = _normalizadores()

    detalle = hallazgo.detalle
    aerolinea = normalizar_aerolinea(hallazgo.aerolinea or detalle.get('aerolinea', ''))
    if not aerolinea:
        return False, 'El hallazgo de FSC no trae aerolinea.'

    try:
        fsc_nuevo = float(detalle.get('fsc_nuevo'))
    except (TypeError, ValueError):
        return False, 'El FSC propuesto no es un numero.'

    destinos = [d.strip().upper() for d in (detalle.get('destinos') or []) if d and d.strip()]
    regla_id = detalle.get('regla_id')

    regla = AirlineFscRule.query.get(regla_id) if regla_id else None

    if regla is None:
        # Sin id explicito: buscar una regla existente con los mismos destinos
        # para no duplicar filas cada vez que llega un correo de fuel.
        for candidata in AirlineFscRule.query.filter_by(aerolinea=aerolinea).all():
            if sorted(candidata.destinos) == sorted(destinos):
                regla = candidata
                break

    if regla is not None:
        anterior = regla.fsc
        regla.fsc = f'{fsc_nuevo:.2f}'
        if detalle.get('nombre'):
            regla.nombre = detalle['nombre']
        alcance = ', '.join(destinos) if destinos else 'todos los destinos'
        return True, f'FSC {aerolinea} ({alcance}): {anterior} -> {regla.fsc}'

    # Regla nueva
    ultimo = (AirlineFscRule.query
              .filter_by(aerolinea=aerolinea)
              .order_by(AirlineFscRule.order.desc())
              .first())
    nombre = detalle.get('nombre') or (', '.join(destinos) if destinos else 'Todos los destinos')

    regla = AirlineFscRule(
        aerolinea=aerolinea,
        nombre=nombre,
        fsc=f'{fsc_nuevo:.2f}',
        order=(ultimo.order + 1) if ultimo else 1,
    )
    regla.destinos = destinos
    db.session.add(regla)

    if not AirlineFscGroup.query.filter_by(aerolinea=aerolinea).first():
        db.session.add(AirlineFscGroup(aerolinea=aerolinea))

    alcance = ', '.join(destinos) if destinos else 'todos los destinos'
    return True, f'FSC {aerolinea} ({alcance}): regla nueva en {regla.fsc}'


# ---------------------------------------------------------------------------
# Cargos adicionales por aerolinea
# ---------------------------------------------------------------------------

def _aplicar_cargo(hallazgo):
    from lux_portal.cotizaciones.models import AirlineCargoRule, AirlineCargoGroup
    normalizar_aerolinea, _ = _normalizadores()

    detalle = hallazgo.detalle
    aerolinea = normalizar_aerolinea(hallazgo.aerolinea or detalle.get('aerolinea', ''))
    concepto = (detalle.get('concepto') or '').strip()
    if not aerolinea or not concepto:
        return False, 'El hallazgo de cargo no trae aerolinea o concepto.'

    try:
        monto = float(detalle.get('monto_nuevo'))
    except (TypeError, ValueError):
        return False, 'El monto propuesto no es un numero.'

    regla = (AirlineCargoRule.query
             .filter_by(aerolinea=aerolinea, concepto=concepto)
             .first())

    if regla is not None:
        anterior = regla.monto
        regla.monto = f'{monto:.2f}'
        return True, f'Cargo {aerolinea} / {concepto}: {anterior} -> {regla.monto}'

    ultimo = (AirlineCargoRule.query
              .filter_by(aerolinea=aerolinea)
              .order_by(AirlineCargoRule.order.desc())
              .first())
    db.session.add(AirlineCargoRule(
        aerolinea=aerolinea,
        concepto=concepto,
        monto=f'{monto:.2f}',
        order=(ultimo.order + 1) if ultimo else 1,
    ))

    if not AirlineCargoGroup.query.filter_by(aerolinea=aerolinea).first():
        db.session.add(AirlineCargoGroup(aerolinea=aerolinea, notas=''))

    return True, f'Cargo {aerolinea} / {concepto}: nuevo en {monto:.2f}'


def _num(valor, defecto):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return defecto
