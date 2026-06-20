#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clasificacion de codigos IATA de destino por continente.
"""

CONTINENTES = ['AFRICA', 'AMERICA', 'ASIA', 'EUROPA', 'OCEANIA']

IATA_CONTINENTE = {
    # America
    'ASU': 'AMERICA', 'EZE': 'AMERICA', 'GRU': 'AMERICA', 'LAX': 'AMERICA',
    'LIM': 'AMERICA', 'MIA': 'AMERICA', 'ORD': 'AMERICA', 'PTY': 'AMERICA',
    'SAL': 'AMERICA', 'SCL': 'AMERICA', 'SJU': 'AMERICA', 'VCP': 'AMERICA',
    'YYZ': 'AMERICA', 'YUL': 'AMERICA',
    # Europa
    'AMS': 'EUROPA', 'BEG': 'EUROPA', 'DUB': 'EUROPA', 'FRA': 'EUROPA',
    'LHR': 'EUROPA', 'MAD': 'EUROPA', 'OTP': 'EUROPA', 'VKO': 'EUROPA',
    # Asia (incluye Oriente Medio)
    'ALA': 'ASIA', 'DOH': 'ASIA', 'DXB': 'ASIA', 'EVN': 'ASIA',
    'FUK': 'ASIA', 'GYD': 'ASIA', 'ICN': 'ASIA', 'KIX': 'ASIA',
    'KWI': 'ASIA', 'NRT': 'ASIA', 'RUH': 'ASIA', 'TAS': 'ASIA',
    'TBS': 'ASIA', 'TPE': 'ASIA', 'DMM': 'ASIA', 'SIN': 'ASIA',
    'KUL': 'ASIA', 'HKG': 'ASIA', 'HKP': 'ASIA',
    # Africa
    'NBO': 'AFRICA', 'TUN': 'AFRICA',
    # Oceania
    'SYD': 'OCEANIA',
}


def continente_de(destino):
    """Devuelve el continente del codigo IATA, o None si no esta clasificado."""
    return IATA_CONTINENTE.get((destino or '').strip().upper())
