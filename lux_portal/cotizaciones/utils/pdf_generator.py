#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de cotizaciones PDF para FreightWise
Genera PDF identico al Excel usando reportlab
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm, mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from datetime import datetime
import os
import io
import re

# Ruta del logo (relativa al proyecto)
def get_logo_path():
    """Obtiene la ruta del logo de forma compatible con cualquier entorno."""
    # Ruta relativa desde este archivo
    current_dir = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(current_dir, '..', '..', 'static', 'images', 'freightwise_logo.png')
    return os.path.normpath(logo_path)

# Colores FreightWise (igual que Excel)
PURPLE_COLOR = HexColor('#5f259f')
GRAY_COLOR = HexColor('#808080')
WHITE_COLOR = colors.white
BLACK_COLOR = colors.black

# Diccionario de dias de la semana
DIAS_ES_EN = {
    'LUN': 'MON', 'MAR': 'TUE', 'MIE': 'WED', 'MIER': 'WED',
    'JUE': 'THU', 'VIE': 'FRI', 'SAB': 'SAT', 'DOM': 'SUN'
}


def traducir_dias(texto, a_ingles=True):
    """Traduce las abreviaciones de dias de la semana."""
    if not texto or not texto.strip():
        return texto
    resultado = texto
    for dia_origen, dia_destino in DIAS_ES_EN.items():
        resultado = re.sub(r'\b' + re.escape(dia_origen) + r'\b', dia_destino, resultado, flags=re.IGNORECASE)
    return resultado


def _generar_elementos_pdf(datos, idioma, available_width):
    """Genera los elementos de una pagina PDF para el idioma dado."""
    elements = []

    # Textos segun idioma
    if idioma == 'es':
        titulo = 'C O T I Z A C I O N   F L E T E   A E R E O'
        contacto_label = 'Contacto FreightWise'
        valido_label = 'Valido desde'
        cliente_label = 'CLIENTE'
        mercancia_label = 'MERCANCIA'
        fw_titulo = 'Cargos Adicionales FreightWise:'
    else:
        titulo = 'A I R F R E I G H T   Q U O T A T I O N'
        contacto_label = 'FreightWise Contact'
        valido_label = 'Valid from'
        cliente_label = 'CUSTOMER'
        mercancia_label = 'COMMODITY'
        fw_titulo = 'FreightWise Additional Charges:'

    # Encabezado con logo
    logo_cell = ''
    logo_path = get_logo_path()
    if os.path.exists(logo_path):
        try:
            logo_cell = Image(logo_path, width=2.5*inch, height=0.35*inch)
        except:
            logo_cell = ''

    header_data = [[titulo, logo_cell]]
    header_table = Table(header_data, colWidths=[available_width * 0.6, available_width * 0.4])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 11),
        ('TEXTCOLOR', (0, 0), (0, 0), GRAY_COLOR),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.3*cm))

    # Info cliente y contacto
    info_data = [
        [f'{cliente_label}:', datos.get('customer', ''), '', f'{contacto_label}:', datos.get('contacto_nombre', '')],
        ['ATTN:', datos.get('attn', ''), '', 'eMail:', datos.get('contacto_email', '')],
        [f'{mercancia_label}:', datos.get('mercancia', ''), '', f'{valido_label}:', datos.get('valid_from', '')],
        ['ORI - DES:', datos.get('ruta', ''), '', '', ''],
    ]
    col_widths_info = [available_width * 0.08, available_width * 0.30, available_width * 0.12,
                       available_width * 0.15, available_width * 0.35]
    info_table = Table(info_data, colWidths=col_widths_info)
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2*cm))

    # Barra de ruta
    ruta_data = [[datos.get('ruta', '')]]
    ruta_table = Table(ruta_data, colWidths=[available_width])
    ruta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE_COLOR),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(ruta_table)

    # Encabezados de tabla
    col_proportions = [0.08, 0.06, 0.10, 0.06, 0.07, 0.07, 0.07, 0.04, 0.05, 0.12, 0.02, 0.04, 0.22]
    col_widths = [available_width * p for p in col_proportions]

    if idioma == 'es':
        enc_simple = ['AEROLINEA', 'VUELO', 'ITINERARIO', 'TIEMPO\nTRANSITO', 'FINCAS\nENTREGA',
                      'SALIDA', 'LLEGADA', 'KG', 'TARIFA', 'CARGOS ADICIONALES', '', '', 'NOTAS']
    else:
        enc_simple = ['AIRLINE', 'FLIGHT', 'ITINERARY', 'TRANSIT\nTIME', 'FARMS\nDELIVER',
                      'DEPARTURE', 'ARRIVAL', 'KG', 'RATE', 'ADD CHARGES', '', '', 'NOTES']

    enc_header_data = [enc_simple]
    enc_header_table = Table(enc_header_data, colWidths=col_widths)
    enc_header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE_COLOR),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, WHITE_COLOR),
        ('SPAN', (9, 0), (11, 0)),
    ]))
    elements.append(enc_header_table)

    # Datos de aerolineas
    aerolineas = datos.get('aerolineas', [])

    if aerolineas:
        table_data = []
        row_colors = []

        color_idx = 0
        for idx, aero in enumerate(aerolineas):
            es_continuacion = aero.get('es_continuacion', False)
            if not es_continuacion and idx > 0:
                color_idx += 1

            bg_color = WHITE_COLOR if color_idx % 2 == 0 else GRAY_COLOR
            text_color = BLACK_COLOR if color_idx % 2 == 0 else WHITE_COLOR

            cargos = aero.get('cargos_adicionales', [])
            if idioma == 'en':
                cargos_items = []
                for c in cargos:
                    if not c.get('concepto'):
                        continue
                    concepto = c.get('concepto', '')
                    if concepto.lower() == 'fitosanitario':
                        concepto = 'Phytosanitary'
                    elif concepto.lower() == 'certificado':
                        concepto = 'Certificate'
                    cargos_items.append(f"{concepto}: ${c.get('monto', '')}")
            else:
                cargos_items = [f"{c.get('concepto', '')}: ${c.get('monto', '')}" for c in cargos if c.get('concepto')]
            cargos_texto = '\n'.join(cargos_items)

            kg_rates = aero.get('kg_rates', [])
            if kg_rates:
                kg_texto = '\n'.join([kr.get('kg', '') for kr in kg_rates])
                tarifa_texto = '\n'.join([f"${kr.get('tarifa_cliente', kr.get('tarifa', ''))}" for kr in kg_rates])
            else:
                kg_texto = aero.get('kg', '')
                tarifa_texto = f"${aero.get('tarifa_cliente', aero.get('tarifa', ''))}"

            fincas = aero.get('granjas_entrega', '')
            salida = aero.get('salida', '')
            llegada = aero.get('llegada', '')
            if idioma == 'en':
                fincas = traducir_dias(fincas, a_ingles=True)
                salida = traducir_dias(salida, a_ingles=True)
                llegada = traducir_dias(llegada, a_ingles=True)

            row = [
                aero.get('aerolinea', ''),
                aero.get('vuelo', ''),
                aero.get('itinerario', ''),
                aero.get('tiempo_transito', ''),
                fincas,
                salida,
                llegada,
                kg_texto,
                tarifa_texto,
                cargos_texto,
                '',
                '',
                aero.get('notas', '')
            ]

            table_data.append(row)
            row_colors.append((bg_color, text_color))

        if table_data:
            data_table = Table(table_data, colWidths=col_widths)

            style_cmds = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('GRID', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
            ]

            for row_idx, (bg, txt) in enumerate(row_colors):
                style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
                style_cmds.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), txt))
                style_cmds.append(('SPAN', (9, row_idx), (11, row_idx)))

            # Fusionar columna A para rutas multiples de misma aerolinea
            idx_aero = 0
            while idx_aero < len(aerolineas):
                if not aerolineas[idx_aero].get('es_continuacion', False):
                    num_filas = 1
                    for j in range(idx_aero + 1, len(aerolineas)):
                        if aerolineas[j].get('es_continuacion', False):
                            num_filas += 1
                        else:
                            break
                    if num_filas > 1:
                        style_cmds.append(('SPAN', (0, idx_aero), (0, idx_aero + num_filas - 1)))
                    idx_aero += num_filas
                else:
                    idx_aero += 1

            data_table.setStyle(TableStyle(style_cmds))
            elements.append(data_table)

    elements.append(Spacer(1, 0.3*cm))

    # Cargos FreightWise
    fw_header = [[fw_titulo]]
    fw_header_table = Table(fw_header, colWidths=[available_width])
    fw_header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PURPLE_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE_COLOR),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
    ]))
    elements.append(fw_header_table)

    cargos_fw = [
        {'concepto_es': 'Due Agent', 'concepto_en': 'Due Agent', 'monto': '50.00'},
        {'concepto_es': 'Certificado', 'concepto_en': 'Certificate', 'monto': '15.00'},
        {'concepto_es': 'Fitosanitario', 'concepto_en': 'Phytosanitary', 'monto': '2.50'}
    ]

    fw_data = []
    for cargo in cargos_fw:
        concepto = cargo['concepto_es'] if idioma == 'es' else cargo['concepto_en']
        fw_data.append(['', '', '', '', concepto, f"$ {cargo['monto']}", '', '', '', '', '', '', ''])

    fw_table = Table(fw_data, colWidths=col_widths)
    fw_table.setStyle(TableStyle([
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('ALIGN', (5, 0), (5, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
        ('SPAN', (4, 0), (8, 0)),
        ('SPAN', (4, 1), (8, 1)),
        ('SPAN', (4, 2), (8, 2)),
        ('SPAN', (9, 0), (11, 0)),
        ('SPAN', (9, 1), (11, 1)),
        ('SPAN', (9, 2), (11, 2)),
    ]))
    elements.append(fw_table)

    return elements


def guardar_cotizacion_pdf_bytes(datos, idioma='es'):
    """Genera la cotizacion PDF y retorna los bytes del archivo.
    Si idioma='ambos', genera un PDF con pagina en español seguida de pagina en ingles.
    """
    buffer = io.BytesIO()

    page_width, page_height = landscape(A4)
    left_margin = 0.5 * cm
    right_margin = 0.5 * cm
    top_margin = 0.8 * cm
    bottom_margin = 0.5 * cm

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=right_margin,
        leftMargin=left_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin
    )

    available_width = page_width - left_margin - right_margin

    if idioma == 'ambos':
        elements = _generar_elementos_pdf(datos, 'es', available_width)
        elements.append(PageBreak())
        elements += _generar_elementos_pdf(datos, 'en', available_width)
    else:
        elements = _generar_elementos_pdf(datos, idioma, available_width)

    doc.build(elements)
    buffer.seek(0)
    return buffer
