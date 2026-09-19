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
                # Desde cuando rige lo que hay hoy, y los incrementos por
                # temporada ya cargados: la tarjeta los muestra como "Pasada".
                'fecha_actualizacion': aero.get('fecha_actualizacion', ''),
                'rate_increases': aero.get('rate_increases') or [],
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


# ---------------------------------------------------------------------------
# Lo que hay HOY para un hallazgo concreto: la columna "Pasada" de la tarjeta
# ---------------------------------------------------------------------------

def _normalizar_kg(kg):
    from lux_portal.tarifas.routes import _normalizar_kg as fn
    return fn(kg or '')


def _fsc_por_regla(aerolinea, destino, reglas):
    """FSC vigente en la tabla maestra para aerolinea + destino: primero la
    regla que nombra ese destino, si no la catch-all ([]). None si no hay."""
    objetivo = _normalizar_aerolinea(aerolinea)
    destino = (destino or '').strip().upper()
    catch_all = None
    for regla in reglas:
        if _normalizar_aerolinea(regla.aerolinea) != objetivo:
            continue
        destinos = [d.strip().upper() for d in (regla.destinos or [])]
        if destino and destino in destinos:
            return regla.fsc
        if not destinos and catch_all is None:
            catch_all = regla.fsc
    return catch_all


def _sin_valor(v):
    try:
        return v in (None, '') or float(v) == 0
    except (TypeError, ValueError):
        return False


def _actual_tarifa(h, cots, reglas):
    """Fecha, tarifa, FSC e incrementos que tiene hoy la cotizacion para la
    aerolinea y el tramo de kilos del hallazgo."""
    detalle = h.get('detalle') or {}
    salida = {'fecha': None, 'tarifa': None, 'fsc': None, 'incrementos': []}
    cot = cots.get(detalle.get('cot_id'))
    if cot is not None:
        objetivo = _normalizar_aerolinea(h.get('aerolinea') or '')
        kg_objetivo = _normalizar_kg(detalle.get('kg'))
        for aero in (cot.aerolineas or []):
            if _normalizar_aerolinea(aero.get('aerolinea', '')) != objetivo:
                continue
            salida['fecha'] = aero.get('fecha_actualizacion') or None
            salida['incrementos'] = [
                {'monto': ri.get('amount', ''), 'texto': ri.get('date', '')}
                for ri in (aero.get('rate_increases') or [])
                if ri.get('amount') or ri.get('date')
            ]
            for kr in (aero.get('kg_rates') or []):
                if _normalizar_kg(kr.get('kg')) == kg_objetivo:
                    salida['tarifa'] = kr.get('tarifa') or None
                    salida['fsc'] = kr.get('fsc') or None
                    break
            break
    # En muchas cotizaciones el FSC del tramo esta en 0 o vacio y el vigente
    # es el de la tabla maestra: se muestra ese para que "Pasada" diga algo.
    if _sin_valor(salida['fsc']):
        por_regla = _fsc_por_regla(h.get('aerolinea'), h.get('destino'), reglas)
        if por_regla is not None:
            salida['fsc'] = por_regla
    return salida


def _actual_fsc(h, reglas):
    detalle = h.get('detalle') or {}
    regla_id = detalle.get('regla_id')
    destinos = sorted(str(d).strip().upper() for d in (detalle.get('destinos') or []))
    objetivo = _normalizar_aerolinea(h.get('aerolinea') or detalle.get('aerolinea') or '')
    for regla in reglas:
        if regla_id and regla.id == regla_id:
            return {'fsc': regla.fsc}
    for regla in reglas:
        if (_normalizar_aerolinea(regla.aerolinea) == objetivo
                and sorted(d.strip().upper() for d in (regla.destinos or [])) == destinos):
            return {'fsc': regla.fsc}
    return {'fsc': None}


def _actual_cargo(h, cargos):
    detalle = h.get('detalle') or {}
    objetivo = _normalizar_aerolinea(h.get('aerolinea') or detalle.get('aerolinea') or '')
    concepto = (detalle.get('concepto') or '').strip().upper()
    for cargo in cargos:
        if (_normalizar_aerolinea(cargo.aerolinea) == objetivo
                and (cargo.concepto or '').strip().upper() == concepto):
            return {'monto': cargo.monto}
    return {'monto': None}


def completar_actual(hallazgos):
    """Le agrega a cada dict de hallazgo (el de AgenteHallazgo.to_dict()) la
    clave `actual`: lo que hay hoy en la cotizacion o en las tablas maestras
    para eso mismo. Es la columna "Pasada" de la tarjeta.

    Mientras la propuesta esta pendiente se mira en vivo, porque lo que se
    va a pisar es lo que haya en ese momento. Cuando ya se aplico, vale la
    foto que `aplicar` congelo en detalle['actual'] justo antes de escribir.

    Consulta las cotizaciones de una sola vez: la pantalla lista decenas de
    propuestas y no puede hacer un viaje a la base por cada una."""
    pendientes = [h for h in hallazgos
                  if not (h.get('estado') == 'aplicado' and (h.get('detalle') or {}).get('actual'))]
    cot_ids = {
        (h.get('detalle') or {}).get('cot_id')
        for h in pendientes if h.get('tipo') == 'tarifa'
    }
    cot_ids.discard(None)
    cots = ({c.id: c for c in Cotizacion.query.filter(Cotizacion.id.in_(cot_ids)).all()}
            if cot_ids else {})
    reglas = AirlineFscRule.query.order_by(AirlineFscRule.aerolinea, AirlineFscRule.order).all()
    cargos = AirlineCargoRule.query.all()

    for h in hallazgos:
        detalle = h.get('detalle') or {}
        if h.get('estado') == 'aplicado' and detalle.get('actual'):
            h['actual'] = detalle['actual']
            continue
        tipo = h.get('tipo')
        if tipo == 'tarifa':
            h['actual'] = _actual_tarifa(h, cots, reglas)
        elif tipo == 'fsc':
            h['actual'] = _actual_fsc(h, reglas)
        elif tipo == 'cargo':
            h['actual'] = _actual_cargo(h, cargos)
        else:
            h['actual'] = {}
    return hallazgos


def actual_de(hallazgo):
    """La foto `actual` de un solo hallazgo (modelo), para congelarla al
    aplicar."""
    return completar_actual([hallazgo.to_dict()])[0].get('actual') or {}


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
