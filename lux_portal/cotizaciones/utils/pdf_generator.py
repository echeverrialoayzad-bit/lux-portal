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

# Importar funciones de traduccion del excel_generator
from lux_portal.cotizaciones.utils.excel_generator import detectar_idioma, traducir_texto_auto

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
WHITE_COLOR = HexColor('#E8D5F5')  # Lila claro para filas alternas
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


def _make_cell_paragraph(text, font_size=6, alignment=TA_CENTER, text_color=BLACK_COLOR):
    """Crea un Paragraph que hace word-wrap dentro de una celda de tabla."""
    style = ParagraphStyle(
        'cell',
        fontName='Helvetica',
        fontSize=font_size,
        leading=font_size + 2,
        alignment=alignment,
        textColor=text_color,
    )
    # Reemplazar saltos de linea por <br/>
    safe_text = str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')
    return Paragraph(safe_text, style)


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

    # Detectar si alguna aerolinea tiene datos de rate increase
    aerolineas_list = datos.get('aerolineas', [])
    show_ri_cols = any(aero.get('rate_increases') for aero in aerolineas_list)

    # Encabezados de tabla
    if show_ri_cols:
        col_proportions = [0.07, 0.05, 0.08, 0.05, 0.06, 0.06, 0.06, 0.04, 0.05, 0.06, 0.07, 0.10, 0.02, 0.04, 0.19]
    else:
        col_proportions = [0.07, 0.05, 0.08, 0.05, 0.06, 0.06, 0.06, 0.04, 0.05, 0.16, 0.02, 0.04, 0.26]
    col_widths = [available_width * p for p in col_proportions]

    if show_ri_cols:
        if idioma == 'es':
            enc_simple = ['AEROLINEA', 'VUELO', 'ITINERARIO', 'TIEMPO\nTRANSITO', 'FINCAS\nENTREGA',
                          'SALIDA', 'LLEGADA', 'KG', 'TARIFA', 'AUMENTO\nTARIFA', 'FECHA',
                          'CARGOS ADICIONALES', '', '', 'NOTAS']
        else:
            enc_simple = ['AIRLINE', 'FLIGHT', 'ITINERARY', 'TRANSIT\nTIME', 'FARMS\nDELIVER',
                          'DEPARTURE', 'ARRIVAL', 'KG', 'RATE', 'RATE\nINCREASE', 'DATE',
                          'ADD CHARGES', '', '', 'NOTES']
    else:
        if idioma == 'es':
            enc_simple = ['AEROLINEA', 'VUELO', 'ITINERARIO', 'TIEMPO\nTRANSITO', 'FINCAS\nENTREGA',
                          'SALIDA', 'LLEGADA', 'KG', 'TARIFA',
                          'CARGOS ADICIONALES', '', '', 'NOTAS']
        else:
            enc_simple = ['AIRLINE', 'FLIGHT', 'ITINERARY', 'TRANSIT\nTIME', 'FARMS\nDELIVER',
                          'DEPARTURE', 'ARRIVAL', 'KG', 'RATE',
                          'ADD CHARGES', '', '', 'NOTES']

    charges_col_start = 11 if show_ri_cols else 9
    charges_col_end = 13 if show_ri_cols else 11
    notes_col = 14 if show_ri_cols else 12

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
        ('SPAN', (charges_col_start, 0), (charges_col_end, 0)),
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

            # Rate increases
            rate_increases = aero.get('rate_increases', [])
            if rate_increases:
                ri_amounts = '\n'.join([f"${ri.get('amount', '')}" for ri in rate_increases if ri.get('amount')])
                ri_dates_raw = '\n'.join([ri.get('date', '') for ri in rate_increases if ri.get('date')])
            else:
                ri_amounts = ''
                ri_dates_raw = ''

            # Traducir fechas de rate increase
            if ri_dates_raw:
                idioma_ri = detectar_idioma(ri_dates_raw)
                if idioma == 'en' and idioma_ri == 'es':
                    ri_dates = traducir_texto_auto(ri_dates_raw, 'en')
                    ri_dates = re.sub(r'(\d+)(st|nd|rd|th)\b', r'\1', ri_dates)
                elif idioma == 'es' and idioma_ri == 'en':
                    ri_dates = traducir_texto_auto(ri_dates_raw, 'es')
                else:
                    ri_dates = ri_dates_raw
            else:
                ri_dates = ri_dates_raw

            notas_originales = aero.get('notas', '')
            if idioma == 'en':
                idioma_notas = detectar_idioma(notas_originales)
                if idioma_notas == 'es':
                    notas_texto = traducir_texto_auto(notas_originales, 'en')
                else:
                    notas_texto = notas_originales
            else:
                idioma_notas = detectar_idioma(notas_originales)
                if idioma_notas == 'en':
                    notas_texto = traducir_texto_auto(notas_originales, 'es')
                else:
                    notas_texto = notas_originales

            # Usar Paragraph para cargos, notas, rate increase y date (word-wrap)
            cargos_para = _make_cell_paragraph(cargos_texto, font_size=6, alignment=TA_CENTER, text_color=text_color)
            notas_para = _make_cell_paragraph(notas_texto, font_size=6, alignment=TA_CENTER, text_color=text_color)

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
            ]
            if show_ri_cols:
                ri_amounts_para = _make_cell_paragraph(ri_amounts, font_size=6, alignment=TA_CENTER, text_color=text_color)
                ri_dates_para = _make_cell_paragraph(ri_dates, font_size=6, alignment=TA_CENTER, text_color=text_color)
                row += [ri_amounts_para, ri_dates_para]
            row += [cargos_para, '', '', notas_para]

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
                style_cmds.append(('SPAN', (charges_col_start, row_idx), (charges_col_end, row_idx)))

            # Fusionar columna A y columna NOTAS para rutas multiples de misma aerolinea
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
                        # Fusionar notas si son iguales en el grupo
                        notas_grupo = [aerolineas[idx_aero + k].get('notas', '') for k in range(num_filas)]
                        if len(set(notas_grupo)) == 1:
                            style_cmds.append(('SPAN', (notes_col, idx_aero), (notes_col, idx_aero + num_filas - 1)))
                            for k in range(1, num_filas):
                                table_data[idx_aero + k][notes_col] = ''
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

    traducciones_en = {
        'certificado': 'Certificate',
        'fitosanitario': 'Phytosanitary',
    }
    cargos_fw = datos.get('cargos_freightwise', [
        {'concepto': 'Due Agent', 'monto': '50.00'},
        {'concepto': 'Certificado', 'monto': '15.00'},
        {'concepto': 'Fitosanitario', 'monto': '2.50'}
    ])

    fw_data = []
    fw_concepto_end = charges_col_start - 1  # col before charges_col_start
    fw_num_cols = notes_col + 1  # total columns
    for cargo in cargos_fw:
        concepto = cargo.get('concepto', '')
        if idioma == 'en':
            concepto = traducciones_en.get(concepto.lower(), concepto)
        monto = cargo.get('monto', '')
        row_fw = [''] * fw_num_cols
        row_fw[4] = concepto
        row_fw[charges_col_start] = f"$ {monto}" if monto else ''
        fw_data.append(row_fw)

    fw_style_cmds = [
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),
        ('ALIGN', (charges_col_start, 0), (charges_col_start, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
    ]
    for i in range(len(fw_data)):
        fw_style_cmds.append(('SPAN', (4, i), (fw_concepto_end, i)))
        fw_style_cmds.append(('SPAN', (charges_col_start, i), (charges_col_end, i)))

    fw_table = Table(fw_data, colWidths=col_widths)
    fw_table.setStyle(TableStyle(fw_style_cmds))
    elements.append(fw_table)

    # Notas FreightWise - mismo formato morado que el header de cargos
    notas_fw = datos.get('notas_freightwise', '').strip()
    if notas_fw:
        elements.append(Spacer(1, 0.3*cm))

        # Header gris
        titulo_notas = 'Notas:' if idioma == 'es' else 'Notes:'
        notas_header = [[titulo_notas]]
        notas_header_table = Table(notas_header, colWidths=[available_width])
        notas_header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#D9D9D9')),
            ('TEXTCOLOR', (0, 0), (-1, -1), BLACK_COLOR),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BOX', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
        ]))
        elements.append(notas_header_table)

        # Contenido morado con letras blancas
        notas_texto = notas_fw.replace('\n', '<br/>')
        notas_style = ParagraphStyle(
            'NotasFW', fontName='Helvetica', fontSize=7, leading=9,
            textColor=HexColor('#FFFFFF'), alignment=TA_CENTER
        )
        notas_body = [[Paragraph(notas_texto, notas_style)]]
        notas_body_table = Table(notas_body, colWidths=[available_width])
        notas_body_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PURPLE_COLOR),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('BOX', (0, 0), (-1, -1), 0.5, BLACK_COLOR),
        ]))
        elements.append(notas_body_table)

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
