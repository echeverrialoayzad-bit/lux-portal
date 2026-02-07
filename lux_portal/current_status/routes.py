import io
import os
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from lux_portal.current_status import current_status_bp
from lux_portal.current_status.models import StatusClient, AirlineRate, StatusAirline, StatusPayment
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required


def get_logo_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, '..', 'static', 'images', 'freightwise_logo.png')


# ===================== PAGES =====================

@current_status_bp.route('/')
@login_required
def dashboard():
    """Dashboard con lista de clientes y resumen de pagos"""
    busqueda = request.args.get('q', '').strip()
    query = StatusClient.query.filter_by(activo=True)
    if busqueda:
        query = query.filter(StatusClient.nombre.ilike(f'%{busqueda}%'))
    clientes = query.order_by(StatusClient.fecha_actualizacion.desc()).all()
    return render_template('current_status/dashboard.html', clientes=clientes, busqueda=busqueda)


@current_status_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_cliente():
    """Crear nuevo cliente"""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        if not nombre:
            flash('El nombre del cliente es requerido', 'danger')
            return redirect(url_for('current_status.nuevo_cliente'))
        cliente = StatusClient(nombre=nombre)
        db.session.add(cliente)
        db.session.commit()
        flash(f'Cliente {nombre} creado exitosamente', 'success')
        return redirect(url_for('current_status.detalle_cliente', id=cliente.id))
    return render_template('current_status/nuevo.html')


@current_status_bp.route('/<int:id>')
@login_required
def detalle_cliente(id):
    """Ver detalle del cliente con tablas editables"""
    cliente = StatusClient.query.get_or_404(id)
    return render_template('current_status/detail.html', cliente=cliente)


# ===================== API: CLIENT =====================

@current_status_bp.route('/api/client/<int:id>/estado', methods=['PUT'])
@login_required
def cambiar_estado(id):
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    cliente.estado = data.get('estado', 'pendiente')
    db.session.commit()
    return jsonify({'success': True, 'estado': cliente.estado})


@current_status_bp.route('/api/client/<int:id>/nombre', methods=['PUT'])
@login_required
def cambiar_nombre(id):
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    cliente.nombre = data.get('nombre', cliente.nombre)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/client/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cliente(id):
    cliente = StatusClient.query.get_or_404(id)
    cliente.activo = False
    db.session.commit()
    return jsonify({'success': True})


# ===================== API: AIRLINE RATES (Table 1) =====================

@current_status_bp.route('/api/client/<int:id>/rate', methods=['POST'])
@login_required
def agregar_rate(id):
    StatusClient.query.get_or_404(id)
    rate = AirlineRate(client_id=id)
    db.session.add(rate)
    db.session.commit()
    return jsonify({'success': True, 'id': rate.id})


@current_status_bp.route('/api/rate/<int:id>', methods=['PUT'])
@login_required
def actualizar_rate(id):
    rate = AirlineRate.query.get_or_404(id)
    data = request.get_json()
    for field in ['airline', 'route', 'transit_time', 'kg_availability', 'date',
                  'net_rate', 'operative', 'net_ops', 'profit',
                  'final_rate', 'additional_costs', 'additional_costs_value', 'notes']:
        if field in data:
            setattr(rate, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/rate/<int:id>', methods=['DELETE'])
@login_required
def eliminar_rate(id):
    rate = AirlineRate.query.get_or_404(id)
    db.session.delete(rate)
    db.session.commit()
    return jsonify({'success': True})


# ===================== API: STATUS AIRLINES (Table 2) =====================

@current_status_bp.route('/api/client/<int:id>/airline', methods=['POST'])
@login_required
def agregar_airline(id):
    StatusClient.query.get_or_404(id)
    airline = StatusAirline(client_id=id)
    db.session.add(airline)
    db.session.commit()
    return jsonify({'success': True, 'id': airline.id})


@current_status_bp.route('/api/airline/<int:id>', methods=['PUT'])
@login_required
def actualizar_airline(id):
    airline = StatusAirline.query.get_or_404(id)
    data = request.get_json()
    for field in ['current_status', 'proximo_vuelo', 'entrega_fincas', 'hora_maxima', 'aerolinea']:
        if field in data:
            setattr(airline, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/airline/<int:id>', methods=['DELETE'])
@login_required
def eliminar_airline(id):
    airline = StatusAirline.query.get_or_404(id)
    db.session.delete(airline)
    db.session.commit()
    return jsonify({'success': True})


# ===================== API: PAYMENTS (Table 3) =====================

@current_status_bp.route('/api/client/<int:id>/payment', methods=['POST'])
@login_required
def agregar_payment(id):
    StatusClient.query.get_or_404(id)
    payment = StatusPayment(client_id=id)
    db.session.add(payment)
    db.session.commit()
    return jsonify({'success': True, 'id': payment.id})


@current_status_bp.route('/api/payment/<int:id>', methods=['PUT'])
@login_required
def actualizar_payment(id):
    payment = StatusPayment.query.get_or_404(id)
    data = request.get_json()
    for field in ['valor', 'fecha', 'credito']:
        if field in data:
            setattr(payment, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/payment/<int:id>', methods=['DELETE'])
@login_required
def eliminar_payment(id):
    payment = StatusPayment.query.get_or_404(id)
    db.session.delete(payment)
    db.session.commit()
    return jsonify({'success': True})


# ===================== EXPORT: SINGLE CLIENT =====================

@current_status_bp.route('/descargar/<int:id>')
@login_required
def descargar_cliente(id):
    """Descargar formulario de un cliente en Excel o PDF"""
    cliente = StatusClient.query.get_or_404(id)
    formato = request.args.get('formato', 'excel')
    if formato == 'pdf':
        return _generar_pdf_cliente(cliente)
    return _generar_excel_cliente(cliente)


@current_status_bp.route('/descargar-todos')
@login_required
def descargar_todos():
    """Descargar listado de todos los clientes con pagos y estado"""
    clientes = StatusClient.query.filter_by(activo=True).order_by(StatusClient.nombre).all()
    formato = request.args.get('formato', 'excel')
    if formato == 'pdf':
        return _generar_pdf_todos(clientes)
    return _generar_excel_todos(clientes)


# ===================== EXCEL GENERATORS =====================

def _generar_excel_cliente(cliente):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image

    wb = Workbook()
    ws = wb.active
    ws.title = cliente.nombre

    # Logo
    logo_path = get_logo_path()
    if os.path.exists(logo_path):
        img = Image(logo_path)
        img.width = 180
        img.height = 50
        ws.add_image(img, 'A1')

    # Styles
    purple_fill = PatternFill(start_color='7C3AED', end_color='7C3AED', fill_type='solid')
    blue_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid')
    green_fill = PatternFill(start_color='924A4A', end_color='924A4A', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    row = 4
    # Client name
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    ws.cell(row=row, column=1, value=cliente.nombre).font = Font(bold=True, size=14)
    row += 2

    # Table 1: Airline Rates
    headers1 = ['Airline', 'Route', 'Transit Time', 'KG Availability', 'Date',
                'Net Rate', 'Operative', 'Net+OPS', 'Profit', 'Final Rate',
                'Additional Costs', '', 'Notes']
    for col, h in enumerate(headers1, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.fill = green_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    row += 1
    for r in cliente.rates:
        vals = [r.airline, r.route, r.transit_time, r.kg_availability, r.date,
                r.net_rate, r.operative, r.net_ops, r.profit, r.final_rate,
                r.additional_costs, r.additional_costs_value, r.notes]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.border = thin_border
        row += 1

    row += 1
    # Table 2: Current Status
    headers2 = ['Current Status', 'Proximo Vuelo', 'Entrega de Fincas', 'Hora Maxima', 'Aerolinea']
    for col, h in enumerate(headers2, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.fill = purple_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    row += 1
    for a in cliente.airlines:
        vals = [a.current_status, a.proximo_vuelo, a.entrega_fincas, a.hora_maxima, a.aerolinea]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.border = thin_border
        row += 1

    row += 1
    # Table 3: Payment
    headers3 = [f'Payment {cliente.nombre}', 'Valor', 'Fecha', 'Credito']
    for col, h in enumerate(headers3, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.fill = blue_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    row += 1
    for p in cliente.payments:
        vals = ['', p.valor, p.fecha, p.credito]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.border = thin_border
        row += 1

    # Auto-width
    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 35)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"current_status_{cliente.nombre}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _generar_excel_todos(clientes):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image

    wb = Workbook()
    ws = wb.active
    ws.title = 'Resumen Clientes'

    logo_path = get_logo_path()
    if os.path.exists(logo_path):
        img = Image(logo_path)
        img.width = 180
        img.height = 50
        ws.add_image(img, 'A1')

    blue_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    row = 4
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    ws.cell(row=row, column=1, value='Resumen de Clientes - Payment Status').font = Font(bold=True, size=14)
    row += 2

    headers = ['Cliente', 'Valor', 'Fecha', 'Credito', 'Estado']
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.fill = blue_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    row += 1

    for c in clientes:
        last_payment = c.payments[-1] if c.payments else None
        vals = [
            c.nombre,
            last_payment.valor if last_payment else '',
            last_payment.fecha if last_payment else '',
            last_payment.credito if last_payment else '',
            c.estado.capitalize()
        ]
        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.border = thin_border
            if col == 5:
                cell.font = Font(bold=True, color='059669' if c.estado == 'finalizado' else 'D97706')
        row += 1

    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 35)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"resumen_clientes_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ===================== PDF GENERATORS =====================

def _generar_pdf_cliente(cliente):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    elements = []
    styles = getSampleStyleSheet()

    # Logo
    logo_path = get_logo_path()
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=120, height=35)
        elements.append(logo)
        elements.append(Spacer(1, 10))

    # Client name
    elements.append(Paragraph(f'<b>{cliente.nombre}</b>', styles['Title']))
    elements.append(Spacer(1, 10))

    purple = colors.HexColor('#7C3AED')
    blue = colors.HexColor('#3B82F6')
    burgundy = colors.HexColor('#924A4A')
    white = colors.white

    # Table 1: Airline Rates
    data1 = [['Airline', 'Route', 'Transit', 'KG', 'Date', 'Net Rate', 'Operative', 'Net+OPS', 'Profit', 'Final Rate', 'Add. Costs', '', 'Notes']]
    for r in cliente.rates:
        data1.append([r.airline, r.route, r.transit_time, r.kg_availability, r.date,
                      r.net_rate, r.operative, r.net_ops, r.profit, r.final_rate,
                      r.additional_costs, r.additional_costs_value, r.notes])
    if len(data1) > 1:
        t1 = Table(data1, repeatRows=1)
        t1.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), burgundy),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t1)
        elements.append(Spacer(1, 15))

    # Table 2: Current Status
    data2 = [['Current Status', 'Proximo Vuelo', 'Entrega de Fincas', 'Hora Maxima', 'Aerolinea']]
    for a in cliente.airlines:
        data2.append([a.current_status, a.proximo_vuelo, a.entrega_fincas, a.hora_maxima, a.aerolinea])
    if len(data2) > 1:
        t2 = Table(data2, repeatRows=1)
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), purple),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F3FF')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 15))

    # Table 3: Payment
    data3 = [[f'Payment {cliente.nombre}', 'Valor', 'Fecha', 'Credito']]
    for p in cliente.payments:
        data3.append(['', p.valor, p.fecha, p.credito])
    if len(data3) > 1:
        t3 = Table(data3, repeatRows=1)
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), blue),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#EFF6FF')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t3)

    doc.build(elements)
    output.seek(0)
    filename = f"current_status_{cliente.nombre}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/pdf')


def _generar_pdf_todos(clientes):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    elements = []
    styles = getSampleStyleSheet()

    logo_path = get_logo_path()
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=120, height=35)
        elements.append(logo)
        elements.append(Spacer(1, 10))

    elements.append(Paragraph('<b>Resumen de Clientes - Payment Status</b>', styles['Title']))
    elements.append(Spacer(1, 15))

    blue = colors.HexColor('#3B82F6')
    data = [['Cliente', 'Valor', 'Fecha', 'Credito', 'Estado']]
    for c in clientes:
        last = c.payments[-1] if c.payments else None
        data.append([
            c.nombre,
            last.valor if last else '',
            last.fecha if last else '',
            last.credito if last else '',
            c.estado.capitalize()
        ])

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#EFF6FF')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)

    doc.build(elements)
    output.seek(0)
    filename = f"resumen_clientes_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(output, as_attachment=True, download_name=filename, mimetype='application/pdf')
