#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Datos predefinidos para cotizaciones
"""

# Lista de aerolineas
AEROLINEAS_LISTA = [
    # Medio Oriente
    "QATAR", "EMIRATES", "ETIHAD", "SAUDIA", "GULF AIR",
    # Asia
    "CATHAY PACIFIC", "SINGAPORE", "KOREAN AIR", "CHINA AIRLINES",
    "EVA AIR", "ANA", "JAL", "ASIANA", "THAI", "VIETNAM",
    "MALAYSIA", "GARUDA", "PHILIPPINE",
    # Europa
    "LUFTHANSA", "AIR FRANCE", "KLM", "BRITISH AIRWAYS", "SWISS",
    "TURKISH", "IBERIA", "ITA AIRWAYS", "SAS", "FINNAIR",
    "TAP PORTUGAL", "AUSTRIAN", "BRUSSELS", "LOT",
    # Americas
    "AMERICAN", "UNITED", "DELTA", "AIR CANADA", "LATAM",
    "COPA", "AVIANCA", "AEROMEXICO", "AZUL", "GOL",
    # Cargueras dedicadas
    "CARGOLUX", "ATLAS AIR", "POLAR AIR", "KALITTA AIR",
    # Express/Courier
    "FEDEX", "UPS", "DHL"
]

# Cargos comunes
CARGOS_COMUNES = [
    {"concepto": "Due Carrier", "monto": ""},
    {"concepto": "CC (Carrier Charges)", "monto": ""},
    {"concepto": "CG HAWB C/U", "monto": ""},
    {"concepto": "FSC (Fuel Surcharge)", "monto": ""},
    {"concepto": "ESC (Security Surcharge)", "monto": ""},
    {"concepto": "Handling Fee", "monto": ""},
    {"concepto": "AWB Fee", "monto": ""},
    {"concepto": "Dangerous Goods Fee", "monto": ""},
    {"concepto": "Temperature Control", "monto": ""}
]

# Cargos fijos de FreightWise que aparecen al final del documento
CARGOS_FREIGHTWISE = [
    {"concepto": "Due Agent", "monto": "50.00"},
    {"concepto": "Certificado", "monto": "15.00"},
    {"concepto": "Fitosanitario", "monto": "2.50"}
]
