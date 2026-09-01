#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foto del estado actual de tarifas, FSC y cargos.

Esto es lo que el analisis local necesita para poder decir "el correo dice
3.45 y hoy tenemos 3.60" en vez de solo extraer numeros sueltos. Se exporta
junto con los correos pendientes.
"""

from lux_portal.cotizaciones.models import (
    Cotizacion, AirlineFscRule, AirlineCargoRule, AirlineDepartureDays,
)


def _normalizar_aerolinea(nombre):
    from lux_portal.tarifas.routes import _normalizar_aerolinea as fn
    return fn(nombre)


def snapshot():
    """Estado actual completo, en la forma mas compacta que siga siendo util."""
    return {
        'cotizaciones': _cotizaciones(),
        'fsc_reglas': _fsc(),
        'cargos': _cargos(),
        'dias_salida': _dias(),
    }


def _cotizaciones():
    salida = []
    cots = Cotizacion.query.filter(Cotizacion.estado != 'eliminado').all()

    for cot in cots:
        aerolineas = []
        for aero in (cot.aerolineas or []):
            nombre = _normalizar_aerolinea(aero.get('aerolinea', ''))
            if not nombre:
                continue
            aerolineas.append({
                'aerolinea': nombre,
                'aerolinea_original': aero.get('aerolinea', ''),
                'itinerario': aero.get('itinerario', ''),
                'kg_rates': [
                    {
                        'kg': kr.get('kg', ''),
                        'tarifa': kr.get('tarifa', ''),
                        'margen': kr.get('margen', ''),
                        'costo_operativo': kr.get('costo_operativo', ''),
                        'fsc': kr.get('fsc', ''),
                    }
                    for kr in (aero.get('kg_rates') or [])
                ],
            })

        if not aerolineas:
            continue

        salida.append({
            'cot_id': cot.id,
            'origen': cot.origen,
            'destino': cot.destino,
            'customer': cot.customer or '',
            'valid_from': cot.valid_from or '',
            'aerolineas': aerolineas,
        })

    return salida


def _fsc():
    return [
        {
            'regla_id': r.id,
            'aerolinea': r.aerolinea,
            'nombre': r.nombre,
            # [] significa "todos los destinos de esta aerolinea"
            'destinos': r.destinos,
            'fsc': r.fsc,
            'order': r.order,
        }
        for r in AirlineFscRule.query.order_by(
            AirlineFscRule.aerolinea, AirlineFscRule.order
        ).all()
    ]


def _cargos():
    return [
        {
            'aerolinea': c.aerolinea,
            'concepto': c.concepto,
            'monto': c.monto,
        }
        for c in AirlineCargoRule.query.order_by(
            AirlineCargoRule.aerolinea, AirlineCargoRule.order
        ).all()
    ]


def _dias():
    return [
        {'aerolinea': d.aerolinea, 'dias': d.dias}
        for d in AirlineDepartureDays.query.order_by(
            AirlineDepartureDays.aerolinea
        ).all()
    ]


def resumen_corto():
    """Contadores para mostrar en la UI sin traerse todo el snapshot."""
    foto = snapshot()
    aerolineas = set()
    destinos = set()
    for cot in foto['cotizaciones']:
        if cot['destino']:
            destinos.add(cot['destino'])
        for aero in cot['aerolineas']:
            aerolineas.add(aero['aerolinea'])
    return {
        'cotizaciones': len(foto['cotizaciones']),
        'aerolineas': len(aerolineas),
        'destinos': len(destinos),
        'reglas_fsc': len(foto['fsc_reglas']),
    }
