#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reglas de negocio que Agente Lux tiene que respetar antes de proponer o
aplicar un cambio.

Ninguna de estas reglas bloquea el flujo por si sola: lo que hacen es marcar
el hallazgo con una alerta visible para que Daniela decida con el dato a la
vista. La unica excepcion son los dias de salida, que nunca se auto-aplican.
"""

from lux_portal.cotizaciones.continentes import continente_de

# Piso operativo general.
COSTO_OPERATIVO_MINIMO = 0.09

# Margen minimo para destinos largos (Europa, Asia -- que en continentes.py
# incluye Medio Oriente -- y Oceania).
MARGEN_MINIMO_LARGO = 0.10
CONTINENTES_MARGEN_MINIMO = {'EUROPA', 'ASIA', 'OCEANIA'}

# Australia es la excepcion explicita: operativo mas alto y margen mas bajo.
AUSTRALIA_IATA = {
    'SYD', 'MEL', 'BNE', 'PER', 'ADL', 'CBR', 'OOL', 'CNS', 'HBA', 'DRW',
    'TSV', 'MCY', 'LST', 'AVV',
}
AUSTRALIA_COSTO_OPERATIVO = 0.19
AUSTRALIA_MARGEN = 0.09

# Tipos de hallazgo que Agente Lux nunca aplica solo.
TIPOS_SOLO_INFORMATIVOS = {'dias', 'info'}


def es_australia(destino):
    return (destino or '').strip().upper() in AUSTRALIA_IATA


def defaults_de(destino):
    """Valores por defecto de costo operativo y margen para un destino."""
    if es_australia(destino):
        return AUSTRALIA_COSTO_OPERATIVO, AUSTRALIA_MARGEN
    continente = continente_de(destino)
    margen = MARGEN_MINIMO_LARGO if continente in CONTINENTES_MARGEN_MINIMO else 0.0
    return COSTO_OPERATIVO_MINIMO, margen


def revisar_kg_rate(destino, margen, costo_operativo):
    """Alertas sobre un kg_rate concreto. Devuelve lista de strings."""
    alertas = []
    try:
        margen = float(margen or 0)
    except (TypeError, ValueError):
        margen = 0.0
    try:
        costo_operativo = float(costo_operativo or 0)
    except (TypeError, ValueError):
        costo_operativo = 0.0

    destino = (destino or '').strip().upper()

    if es_australia(destino):
        if abs(costo_operativo - AUSTRALIA_COSTO_OPERATIVO) > 0.001:
            alertas.append(
                f'{destino} es Australia: el costo operativo deberia ser '
                f'{AUSTRALIA_COSTO_OPERATIVO:.2f} y esta en {costo_operativo:.2f}.'
            )
        if abs(margen - AUSTRALIA_MARGEN) > 0.001:
            alertas.append(
                f'{destino} es Australia: el margen deberia ser '
                f'{AUSTRALIA_MARGEN:.2f} y esta en {margen:.2f}.'
            )
        return alertas

    if costo_operativo < COSTO_OPERATIVO_MINIMO - 0.001:
        alertas.append(
            f'Costo operativo {costo_operativo:.2f} por debajo del minimo '
            f'{COSTO_OPERATIVO_MINIMO:.2f}. Requiere autorizacion de Daniela.'
        )

    continente = continente_de(destino)
    if continente in CONTINENTES_MARGEN_MINIMO and margen < MARGEN_MINIMO_LARGO - 0.001:
        alertas.append(
            f'{destino} ({continente.title()}): margen {margen:.2f} por debajo '
            f'del minimo {MARGEN_MINIMO_LARGO:.2f}.'
        )

    return alertas


def revisar_hallazgo_tarifa(destino, kg_rate_actual, tarifa_nueva):
    """Alertas para un cambio de tarifa neta propuesto.

    kg_rate_actual es el dict guardado en la cotizacion (puede ser None si el
    tier es nuevo). tarifa_nueva es el valor que propone el correo."""
    alertas = []

    if kg_rate_actual:
        margen = kg_rate_actual.get('margen', 0)
        costo_operativo = kg_rate_actual.get('costo_operativo', COSTO_OPERATIVO_MINIMO)
        alertas.extend(revisar_kg_rate(destino, margen, costo_operativo))

    try:
        nueva = float(tarifa_nueva or 0)
    except (TypeError, ValueError):
        return alertas + ['La tarifa propuesta no es un numero valido.']

    if nueva <= 0:
        alertas.append('La tarifa propuesta es cero o negativa: revisar el correo.')
        return alertas

    if kg_rate_actual:
        try:
            actual = float(kg_rate_actual.get('tarifa', 0) or 0)
        except (TypeError, ValueError):
            actual = 0.0
        # Un salto muy grande casi siempre es un error de lectura del correo
        # (una columna corrida, un total en vez de un por-kg), no una subida real.
        if actual > 0:
            variacion = abs(nueva - actual) / actual
            if variacion >= 0.40:
                direccion = 'sube' if nueva > actual else 'baja'
                alertas.append(
                    f'La tarifa {direccion} {variacion * 100:.0f}% '
                    f'({actual:.2f} -> {nueva:.2f}). Confirmar contra el correo.'
                )

    return alertas


def revisar_hallazgo_fsc(destinos, fsc_actual, fsc_nuevo):
    """Alertas para un cambio de FSC propuesto."""
    alertas = []
    try:
        nuevo = float(fsc_nuevo or 0)
    except (TypeError, ValueError):
        return ['El FSC propuesto no es un numero valido.']

    if nuevo < 0:
        alertas.append('El FSC propuesto es negativo.')

    if not destinos:
        alertas.append(
            'Esta regla aplica a TODOS los destinos de la aerolinea. '
            'Si el correo solo mencionaba algunos trayectos, cambiala a '
            'destinos especificos antes de aprobar.'
        )

    try:
        actual = float(fsc_actual or 0)
    except (TypeError, ValueError):
        actual = 0.0

    if actual > 0 and nuevo > 0:
        variacion = abs(nuevo - actual) / actual
        if variacion >= 0.50:
            alertas.append(
                f'El FSC cambia {variacion * 100:.0f}% '
                f'({actual:.2f} -> {nuevo:.2f}). Confirmar contra el correo.'
            )

    return alertas


def revisar(hallazgo_dict):
    """Punto de entrada unico: recibe el dict de un hallazgo propuesto y
    devuelve el texto de alerta (o cadena vacia si esta limpio)."""
    tipo = hallazgo_dict.get('tipo', 'tarifa')
    detalle = hallazgo_dict.get('detalle') or {}
    destino = (hallazgo_dict.get('destino') or '').upper()

    if tipo == 'tarifa':
        alertas = revisar_hallazgo_tarifa(
            destino,
            detalle.get('kg_rate_actual'),
            detalle.get('tarifa_nueva'),
        )
    elif tipo == 'fsc':
        alertas = revisar_hallazgo_fsc(
            detalle.get('destinos') or [],
            detalle.get('fsc_actual'),
            detalle.get('fsc_nuevo'),
        )
    elif tipo == 'dias':
        alertas = ['Los dias de salida no se aplican automaticamente. '
                   'Cambialos a mano en Cotizaciones si corresponde.']
    else:
        alertas = []

    return ' '.join(alertas)
