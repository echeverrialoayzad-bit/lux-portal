import io
import os
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from lux_portal.current_status import current_status_bp
from lux_portal.current_status.models import StatusClient, AirlineRate, StatusAirline, StatusPayment, ClientShipment, ShipmentHistory
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


@current_status_bp.route('/facturacion')
@login_required
def facturacion():
    """Vista de facturacion con informacion de pagos por cliente"""
    busqueda = request.args.get('q', '').strip()
    query = StatusClient.query.filter_by(activo=True)
    if busqueda:
        query = query.filter(StatusClient.nombre.ilike(f'%{busqueda}%'))
    clientes = query.order_by(StatusClient.nombre).all()
    return render_template('current_status/facturacion.html', clientes=clientes, busqueda=busqueda)


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
    if 'extra' in data:
        extra = rate.get_extra()
        extra.update(data['extra'])
        rate.extra_data = json.dumps(extra)
    else:
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
    if 'extra' in data:
        extra = airline.get_extra()
        extra.update(data['extra'])
        airline.extra_data = json.dumps(extra)
    else:
        for field in ['current_status', 'proximo_vuelo', 'kg', 'entrega_fincas', 'hora_maxima', 'aerolinea', 'all_in_rate']:
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
    if 'extra' in data:
        extra = payment.get_extra()
        extra.update(data['extra'])
        payment.extra_data = json.dumps(extra)
    else:
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


# ===================== API: SHIPMENTS (Table 4 & 5) =====================

SHIPMENT_FIELDS = ['ship_date', 'mark', 'awb', 'client_name', 'origin', 'destination',
                   'airline', 'fulles', 'pieces_gross', 'volume', 'charge', 'phyto',
                   'dup_phyto', 'c_origin', 'dup_co', 'termografo', 'transmision']

FACTURA_FIELDS = ['flete', 'fsc', 'esc', 'due_agent', 'due_carrier', 'fito_venta',
                  'co_venta', 'termografo_venta', 'fitos_venta', 'dup_fito_venta',
                  'co_factura', 'dup_co_factura', 'transmision_factura', 'beneficio', 'beneficio_x_kg']


@current_status_bp.route('/api/client/<int:id>/shipment', methods=['POST'])
@login_required
def agregar_shipment(id):
    StatusClient.query.get_or_404(id)
    shipment = ClientShipment(
        client_id=id,
        fito_venta='2.50',
        co_venta='15',
        termografo_venta='35'
    )
    db.session.add(shipment)
    db.session.commit()
    return jsonify({'success': True, 'id': shipment.id})


@current_status_bp.route('/api/shipment/<int:id>', methods=['PUT'])
@login_required
def actualizar_shipment(id):
    shipment = ClientShipment.query.get_or_404(id)
    data = request.get_json()
    for field in SHIPMENT_FIELDS + FACTURA_FIELDS:
        if field in data:
            setattr(shipment, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/shipment/<int:id>', methods=['DELETE'])
@login_required
def eliminar_shipment(id):
    shipment = ClientShipment.query.get_or_404(id)
    db.session.delete(shipment)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/client/<int:id>/enviar-shipments', methods=['POST'])
@login_required
def enviar_shipments(id):
    """Enviar embarques al historial y contar"""
    cliente = StatusClient.query.get_or_404(id)
    shipments = ClientShipment.query.filter_by(client_id=id).all()
    if not shipments:
        return jsonify({'success': False, 'error': 'No hay embarques para enviar'}), 400

    # Snapshot data
    snapshot = []
    for s in shipments:
        row = {}
        for f in SHIPMENT_FIELDS + FACTURA_FIELDS:
            row[f] = getattr(s, f, '') or ''
        snapshot.append(row)

    history = ShipmentHistory(
        client_id=id,
        client_name=cliente.nombre,
        shipment_count=len(shipments),
        shipment_data=json.dumps(snapshot)
    )
    db.session.add(history)
    db.session.commit()

    return jsonify({
        'success': True,
        'history_id': history.id,
        'count': len(shipments)
    })


@current_status_bp.route('/historial')
@login_required
def historial_clientes():
    """Historial combinado tipo Excel de todos los embarques enviados"""
    busqueda = request.args.get('q', '').strip()
    query = ShipmentHistory.query

    if busqueda:
        query = query.filter(ShipmentHistory.client_name.ilike(f'%{busqueda}%'))

    entries = query.order_by(ShipmentHistory.sent_at.desc()).all()

    # Flatten all entries into individual rows
    all_rows = []
    for entry in entries:
        shipments = entry.get_shipments()
        for idx, s in enumerate(shipments):
            s['_history_id'] = entry.id
            s['_row_index'] = idx
            s['_client'] = entry.client_name
            s['_sent_at'] = entry.sent_at.strftime('%d/%m/%Y %H:%M')
            all_rows.append(s)

    return render_template(
        'current_status/historial.html',
        rows=all_rows,
        total_rows=len(all_rows),
        total_entries=len(entries),
        busqueda=busqueda,
        SHIPMENT_FIELDS=SHIPMENT_FIELDS,
        FACTURA_FIELDS=FACTURA_FIELDS
    )


@current_status_bp.route('/api/historial/<int:id>', methods=['DELETE'])
@login_required
def eliminar_historial(id):
    """Eliminar una entrada completa del historial"""
    entry = ShipmentHistory.query.get_or_404(id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/historial/<int:id>/row/<int:row_idx>', methods=['DELETE'])
@login_required
def eliminar_historial_row(id, row_idx):
    """Eliminar una fila individual de una entrada del historial"""
    entry = ShipmentHistory.query.get_or_404(id)
    shipments = entry.get_shipments()
    if row_idx < 0 or row_idx >= len(shipments):
        return jsonify({'success': False, 'error': 'Fila no encontrada'}), 404
    shipments.pop(row_idx)
    if not shipments:
        db.session.delete(entry)
    else:
        entry.shipment_data = json.dumps(shipments)
        entry.shipment_count = len(shipments)
    db.session.commit()
    return jsonify({'success': True})


# ===================== API: CUSTOM COLUMNS =====================

@current_status_bp.route('/api/client/<int:id>/custom-column', methods=['POST'])
@login_required
def agregar_custom_column(id):
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    table_type = data.get('table_type')
    col_name = data.get('name', 'Nueva Columna')
    try:
        cols = json.loads(cliente.custom_columns or '{}')
        if table_type not in cols:
            cols[table_type] = []
        cols[table_type].append(col_name)
        cliente.custom_columns = json.dumps(cols)
        db.session.commit()
        return jsonify({'success': True, 'columns': cols[table_type], 'index': len(cols[table_type]) - 1})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@current_status_bp.route('/api/client/<int:id>/custom-column', methods=['DELETE'])
@login_required
def eliminar_custom_column(id):
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    table_type = data.get('table_type')
    col_name = data.get('name')
    try:
        cols = json.loads(cliente.custom_columns or '{}')
        if table_type in cols and col_name in cols[table_type]:
            cols[table_type].remove(col_name)
            cliente.custom_columns = json.dumps(cols)
            # Remove data from rows
            if table_type == 'rates':
                rows = cliente.rates
            elif table_type == 'airlines':
                rows = cliente.airlines
            else:
                rows = cliente.payments
            for row in rows:
                extra = row.get_extra()
                extra.pop(col_name, None)
                row.extra_data = json.dumps(extra)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Column not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@current_status_bp.route('/api/client/<int:id>/custom-column/rename', methods=['PUT'])
@login_required
def renombrar_custom_column(id):
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    table_type = data.get('table_type')
    old_name = data.get('old_name')
    new_name = data.get('new_name', '')
    try:
        cols = json.loads(cliente.custom_columns or '{}')
        if table_type in cols and old_name in cols[table_type]:
            idx = cols[table_type].index(old_name)
            cols[table_type][idx] = new_name
            cliente.custom_columns = json.dumps(cols)
            if table_type == 'rates':
                rows = cliente.rates
            elif table_type == 'airlines':
                rows = cliente.airlines
            else:
                rows = cliente.payments
            for row in rows:
                extra = row.get_extra()
                if old_name in extra:
                    extra[new_name] = extra.pop(old_name)
                    row.extra_data = json.dumps(extra)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Column not found'}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ===================== EXPORT: SINGLE CLIENT =====================

@current_status_bp.route('/descargar/<int:id>')
@login_required
def descargar_cliente(id):
    """Descargar formulario de un cliente en Excel o PDF"""
    cliente = StatusClient.query.get_or_404(id)
    formato = request.args.get('formato', 'excel')
    hide_internal = request.args.get('hide_internal', '0') == '1'
    tabla = request.args.get('table', 'all')  # all, rates, status, payment
    if formato == 'pdf':
        return _generar_pdf_cliente(cliente, hide_internal=hide_internal, tabla=tabla)
    return _generar_excel_cliente(cliente, hide_internal=hide_internal, tabla=tabla)


@current_status_bp.route('/descargar-todos')
@login_required
def descargar_todos():
    """Descargar listado de todos los clientes con pagos y estado"""
    clientes = StatusClient.query.filter_by(activo=True).order_by(StatusClient.nombre).all()
    formato = request.args.get('formato', 'excel')
    if formato == 'pdf':
        return _generar_pdf_todos(clientes)
    return _generar_excel_todos(clientes)


# ===================== UPLOAD EXCEL =====================

@current_status_bp.route('/api/client/<int:id>/upload-excel', methods=['POST'])
@login_required
def upload_excel(id):
    """Subir un Excel para rellenar las 3 tablas del cliente"""
    from openpyxl import load_workbook

    cliente = StatusClient.query.get_or_404(id)
    file = request.files.get('file')
    if not file or not file.filename.endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'Archivo Excel requerido (.xlsx)'}), 400

    # Fields that should be rounded to 2 decimals
    NUMERIC_FIELDS = {'net_rate', 'operative', 'net_ops', 'profit', 'final_rate',
                      'additional_costs_value', 'kg_availability', 'valor'}

    def round_val(val, field):
        """Round to 2 decimals if field is numeric."""
        if field not in NUMERIC_FIELDS or not val:
            return val
        try:
            return f"{float(val.replace(',', '')):.2f}"
        except (ValueError, AttributeError):
            return val

    try:
        wb = load_workbook(file, data_only=True)
        ws = wb.active

        # Read all rows as lists of string values
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([str(cell).strip() if cell is not None else '' for cell in row])

        # Detect table sections by looking for header keywords
        table1_start = None  # Airline Rates
        table2_start = None  # Current Status
        table3_start = None  # Payment

        for i, row in enumerate(rows):
            row_lower = [c.lower() for c in row]
            row_joined = ' '.join(row_lower)

            if table1_start is None and ('airline' in row_lower or 'airline' in row_joined) and ('route' in row_lower or 'route' in row_joined):
                table1_start = i
            elif table1_start is not None and table2_start is None and ('current status' in row_joined or 'current_status' in row_joined or ('proximo' in row_joined and 'vuelo' in row_joined)):
                table2_start = i
            elif table2_start is not None and table3_start is None and ('payment' in row_joined or ('valor' in row_lower and 'fecha' in row_lower)):
                table3_start = i

        # Parse Table 1: Airline Rates (from table1_start+1 to table2_start-1)
        if table1_start is not None:
            end1 = table2_start if table2_start else len(rows)
            for i in range(table1_start + 1, end1):
                row = rows[i]
                # Skip empty rows
                if all(c == '' or c == 'None' for c in row):
                    continue
                rate = AirlineRate(client_id=id)
                # Map columns by position (matching header order)
                fields1 = ['airline', 'route', 'transit_time', 'kg_availability', 'date',
                           'net_rate', 'operative', 'net_ops', 'profit', 'final_rate',
                           'additional_costs', 'additional_costs_value', 'notes']
                for j, field in enumerate(fields1):
                    if j < len(row):
                        val = row[j] if row[j] != 'None' else ''
                        setattr(rate, field, round_val(val, field))
                db.session.add(rate)

        # Parse Table 2: Current Status (from table2_start+1 to table3_start-1)
        if table2_start is not None:
            end2 = table3_start if table3_start else len(rows)
            for i in range(table2_start + 1, end2):
                row = rows[i]
                if all(c == '' or c == 'None' for c in row):
                    continue
                airline = StatusAirline(client_id=id)
                fields2 = ['current_status', 'proximo_vuelo', 'kg', 'entrega_fincas', 'hora_maxima', 'aerolinea', 'all_in_rate']
                for j, field in enumerate(fields2):
                    if j < len(row):
                        val = row[j] if row[j] != 'None' else ''
                        setattr(airline, field, val)
                db.session.add(airline)

        # Parse Table 3: Payment (from table3_start+1 to end)
        if table3_start is not None:
            # Payment header may have: "Payment ClientName", Valor, Fecha, Credito
            # Data rows have: empty first col, valor, fecha, credito
            for i in range(table3_start + 1, len(rows)):
                row = rows[i]
                if all(c == '' or c == 'None' for c in row):
                    continue
                payment = StatusPayment(client_id=id)
                # The payment table header has 4 cols, data starts at col 2 (index 1)
                fields3 = [('valor', 1), ('fecha', 2), ('credito', 3)]
                for field, idx in fields3:
                    if idx < len(row):
                        val = row[idx] if row[idx] != 'None' else ''
                        setattr(payment, field, round_val(val, field))
                db.session.add(payment)

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ===================== EXPORT HELPERS =====================

def _fmt_dollar(val):
    """Format a value with $ sign if it looks numeric."""
    if not val:
        return val
    s = str(val).replace('$', '').replace(',', '').strip()
    try:
        num = float(s)
        if num == int(num):
            return f'${int(num):,}'
        return f'${num:,.2f}'
    except (ValueError, TypeError):
        return val

def _get_addcosts_display(rate):
    """Get addcosts names and values from extra_data, fallback to old columns."""
    extra = rate.get_extra()
    addcosts = extra.get('addcosts', [])
    if addcosts:
        names = '\n'.join(item.get('name', '') for item in addcosts if item.get('name'))
        values = '\n'.join(_fmt_dollar(item.get('value', '')) for item in addcosts if item.get('value'))
        return names, values
    # Fallback to old columns
    return rate.additional_costs or '', _fmt_dollar(rate.additional_costs_value) if rate.additional_costs_value else ''


# ===================== EXCEL GENERATORS =====================

def _generar_excel_cliente(cliente, hide_internal=False, tabla='all'):
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
    header_font = Font(bold=True, color='FFFFFF', size=10)
    data_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    gray_fill = PatternFill(start_color='E2E8F0', end_color='E2E8F0', fill_type='solid')
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    row = 4
    # Client name
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    ws.cell(row=row, column=1, value=cliente.nombre).font = Font(bold=True, size=14)
    row += 2

    custom_rates = cliente.get_custom_cols('rates')
    custom_airlines = cliente.get_custom_cols('airlines')
    custom_payments = cliente.get_custom_cols('payments')

    # Table 1: Airline Rates
    if tabla in ('all', 'rates'):
        if hide_internal:
            headers1 = ['Airline', 'Route', 'Transit Time', 'KG Availability', 'Date',
                        'Final Rate', 'Additional Costs', '', 'Notes']
            add_costs_col = 7
        else:
            headers1 = ['Airline', 'Route', 'Transit Time', 'KG Availability', 'Date',
                        'Net Rate', 'Operative', 'Net+OPS', 'Profit', 'Final Rate',
                        'Additional Costs', '', 'Notes']
            add_costs_col = 11
        headers1 += custom_rates
        for col, h in enumerate(headers1, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.fill = purple_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border
        ws.merge_cells(start_row=row, start_column=add_costs_col, end_row=row, end_column=add_costs_col + 1)
        row += 1
        sorted_rates = sorted(cliente.rates, key=lambda r: (r.airline or '').lower())
        data_start_row = row
        # Build group index per row (same airline group = same color)
        group_idx = 0
        row_group = []
        i = 0
        while i < len(sorted_rates):
            airline = (sorted_rates[i].airline or '').strip().lower()
            start = i
            while i < len(sorted_rates) and (sorted_rates[i].airline or '').strip().lower() == airline:
                row_group.append(group_idx)
                i += 1
            group_idx += 1
        for idx, r in enumerate(sorted_rates):
            addcost_names, addcost_values = _get_addcosts_display(r)
            if hide_internal:
                vals = [r.airline, r.route, r.transit_time, r.kg_availability, r.date,
                        _fmt_dollar(r.final_rate), addcost_names, addcost_values, r.notes]
            else:
                vals = [r.airline, r.route, r.transit_time, r.kg_availability, r.date,
                        _fmt_dollar(r.net_rate), _fmt_dollar(r.operative), _fmt_dollar(r.net_ops),
                        _fmt_dollar(r.profit), _fmt_dollar(r.final_rate),
                        addcost_names, addcost_values, r.notes]
            extra = r.get_extra()
            vals += [extra.get(c, '') for c in custom_rates]
            for col, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = thin_border
                cell.alignment = data_alignment
                if row_group[idx] % 2 == 1:
                    cell.fill = gray_fill
            row += 1
        # Merge airline cells for same-airline groups
        i = 0
        while i < len(sorted_rates):
            airline = (sorted_rates[i].airline or '').strip().lower()
            start = i
            while i < len(sorted_rates) and (sorted_rates[i].airline or '').strip().lower() == airline:
                i += 1
            if i - start > 1 and airline:
                ws.merge_cells(start_row=data_start_row + start, start_column=1,
                               end_row=data_start_row + i - 1, end_column=1)
        row += 1

    # Table 2: Current Status
    if tabla in ('all', 'status'):
        headers2 = ['Current Status', 'Next Flight', 'KG', 'Farms Deliver', 'Farm Maximum Delivery Time', 'Airline', 'All in Rate'] + custom_airlines
        for col, h in enumerate(headers2, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.fill = purple_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border
        row += 1
        for idx, a in enumerate(cliente.airlines):
            extra = a.get_extra()
            vals = [a.current_status, a.proximo_vuelo, a.kg, a.entrega_fincas, a.hora_maxima, a.aerolinea, a.all_in_rate]
            vals += [extra.get(c, '') for c in custom_airlines]
            for col, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = thin_border
                cell.alignment = data_alignment
                if idx % 2 == 1:
                    cell.fill = gray_fill
            row += 1
        row += 1

    # Table 3: Payment
    if tabla in ('all', 'payment'):
        headers3 = [f'Payment {cliente.nombre}', 'Valor', 'Fecha', 'Credito'] + custom_payments
        for col, h in enumerate(headers3, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.fill = purple_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border
        row += 1
        for idx, p in enumerate(cliente.payments):
            extra = p.get_extra()
            vals = ['', p.valor, p.fecha, p.credito]
            vals += [extra.get(c, '') for c in custom_payments]
            for col, v in enumerate(vals, 1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = thin_border
                cell.alignment = data_alignment
                if idx % 2 == 1:
                    cell.fill = gray_fill
            row += 1

    # FreightWise Additional Charges
    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=13)
    cell = ws.cell(row=row, column=1, value='FreightWise Additional Charges')
    cell.font = Font(bold=True, color='FFFFFF', size=11)
    cell.fill = purple_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[row].height = 25
    row += 1

    cargos_fw = [
        ('Due Agent', '$ 50.00'),
        ('Certificate', '$ 15.00'),
        ('Phytosanitary', '$ 2.50'),
    ]
    no_side = Side(style=None)
    thin_side = Side(style='thin', color='000000')
    fw_start = row
    for concepto, monto in cargos_fw:
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=9)
        c1 = ws.cell(row=row, column=5, value=concepto)
        c1.font = Font(name='Arial', size=9)
        c1.alignment = Alignment(horizontal='center', vertical='center')
        ws.merge_cells(start_row=row, start_column=10, end_row=row, end_column=11)
        c2 = ws.cell(row=row, column=10, value=monto)
        c2.font = Font(name='Arial', size=9)
        c2.alignment = Alignment(horizontal='center', vertical='center')
        row += 1
    fw_end = row - 1
    # Outer border only for FreightWise section
    for r in range(fw_start, fw_end + 1):
        for c in range(1, 14):
            left = thin_side if c == 1 else no_side
            right = thin_side if c == 13 else no_side
            top = thin_side if r == fw_start else no_side
            bottom = thin_side if r == fw_end else no_side
            ws.cell(row=r, column=c).border = Border(left=left, right=right, top=top, bottom=bottom)
    row += 1

    # Auto-width: increase cap to 50 and set minimum of 15
    for col in ws.columns:
        max_len = 0
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        width = max(max_len + 4, 15)
        ws.column_dimensions[col[0].column_letter].width = min(width, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    suffix = f"_{tabla}" if tabla != 'all' else ''
    filename = f"current_status_{cliente.nombre}{suffix}_{datetime.now().strftime('%Y%m%d')}.xlsx"
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
        width = max(max_len + 4, 15)
        ws.column_dimensions[col[0].column_letter].width = min(width, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"resumen_clientes_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ===================== PDF GENERATORS =====================

def _generar_pdf_cliente(cliente, hide_internal=False, tabla='all'):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=10*mm, rightMargin=10*mm)
    elements = []
    styles = getSampleStyleSheet()

    # Cell paragraph styles (wraps text automatically)
    cell_style = ParagraphStyle('CellCenter', parent=styles['Normal'],
                                fontSize=7, leading=9, alignment=TA_CENTER)
    cell_header = ParagraphStyle('CellHeader', parent=styles['Normal'],
                                 fontSize=7, leading=9, alignment=TA_CENTER,
                                 textColor=colors.white)

    def P(text, style=cell_style):
        return Paragraph(str(text or ''), style)

    def PH(text):
        return Paragraph(str(text or ''), cell_header)

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

    common_style = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]

    custom_rates = cliente.get_custom_cols('rates')
    custom_airlines = cliente.get_custom_cols('airlines')
    custom_payments = cliente.get_custom_cols('payments')

    # Table 1: Airline Rates
    if tabla in ('all', 'rates'):
        extra_w = [20*mm] * len(custom_rates)
        sorted_rates = sorted(cliente.rates, key=lambda r: (r.airline or '').lower())
        if hide_internal:
            data1 = [[PH('Airline'), PH('Route'), PH('Transit'), PH('KG'), PH('Date'),
                       PH('Final Rate'), PH('Additional Costs'), PH(''), PH('Notes')] + [PH(c) for c in custom_rates]]
            add_span = (6, 0, 7, 0)
            col_widths1 = [40*mm, 38*mm, 22*mm, 18*mm, 28*mm, 20*mm, 28*mm, 20*mm, 55*mm] + extra_w
            for r in sorted_rates:
                extra = r.get_extra()
                addcost_names, addcost_values = _get_addcosts_display(r)
                data1.append([P(r.airline), P(r.route), P(r.transit_time), P(r.kg_availability), P(r.date),
                              P(_fmt_dollar(r.final_rate)), P(addcost_names), P(addcost_values), P(r.notes)]
                             + [P(extra.get(c, '')) for c in custom_rates])
        else:
            data1 = [[PH('Airline'), PH('Route'), PH('Transit'), PH('KG'), PH('Date'),
                       PH('Net Rate'), PH('Operative'), PH('Net+OPS'), PH('Profit'), PH('Final Rate'),
                       PH('Add. Costs'), PH(''), PH('Notes')] + [PH(c) for c in custom_rates]]
            add_span = (10, 0, 11, 0)
            col_widths1 = [28*mm, 28*mm, 18*mm, 14*mm, 22*mm, 14*mm, 14*mm, 14*mm, 14*mm, 16*mm, 22*mm, 16*mm, 37*mm] + extra_w
            for r in sorted_rates:
                extra = r.get_extra()
                addcost_names, addcost_values = _get_addcosts_display(r)
                data1.append([P(r.airline), P(r.route), P(r.transit_time), P(r.kg_availability), P(r.date),
                              P(_fmt_dollar(r.net_rate)), P(_fmt_dollar(r.operative)), P(_fmt_dollar(r.net_ops)),
                              P(_fmt_dollar(r.profit)), P(_fmt_dollar(r.final_rate)),
                              P(addcost_names), P(addcost_values), P(r.notes)]
                             + [P(extra.get(c, '')) for c in custom_rates])
        # Build merge spans and group-based backgrounds for same-airline groups
        airline_spans = []
        group_bg = []
        group_idx = 0
        i = 0
        while i < len(sorted_rates):
            airline = (sorted_rates[i].airline or '').strip().lower()
            start = i
            while i < len(sorted_rates) and (sorted_rates[i].airline or '').strip().lower() == airline:
                i += 1
            if i - start > 1 and airline:
                airline_spans.append(('SPAN', (0, start + 1), (0, i)))  # +1 for header row
            bg_color = colors.HexColor('#E2E8F0') if group_idx % 2 == 1 else colors.white
            for row_i in range(start, i):
                group_bg.append(('BACKGROUND', (0, row_i + 1), (-1, row_i + 1), bg_color))
            group_idx += 1
        if len(data1) > 1:
            t1 = Table(data1, repeatRows=1, colWidths=col_widths1)
            t1.setStyle(TableStyle([
                ('SPAN', (add_span[0], add_span[1]), (add_span[2], add_span[3])),
                ('BACKGROUND', (0, 0), (-1, 0), purple),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ] + group_bg + common_style + airline_spans))
            elements.append(t1)
            elements.append(Spacer(1, 15))

    # Table 2: Current Status
    if tabla in ('all', 'status'):
        data2 = [[PH('Current Status'), PH('Next Flight'), PH('KG'), PH('Farms Deliver'), PH('Farm Max Delivery'), PH('Airline'), PH('All in Rate')]
                  + [PH(c) for c in custom_airlines]]
        col_widths2 = [40*mm, 40*mm, 20*mm, 40*mm, 40*mm, 30*mm, 25*mm] + [30*mm] * len(custom_airlines)
        for a in cliente.airlines:
            extra = a.get_extra()
            data2.append([P(a.current_status), P(a.proximo_vuelo), P(a.kg), P(a.entrega_fincas), P(a.hora_maxima), P(a.aerolinea), P(a.all_in_rate)]
                         + [P(extra.get(c, '')) for c in custom_airlines])
        if len(data2) > 1:
            t2 = Table(data2, repeatRows=1, colWidths=col_widths2)
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), purple),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#E2E8F0')]),
            ] + common_style))
            elements.append(t2)
            elements.append(Spacer(1, 15))

    # Table 3: Payment
    if tabla in ('all', 'payment'):
        data3 = [[PH(f'Payment {cliente.nombre}'), PH('Valor'), PH('Fecha'), PH('Credito')]
                  + [PH(c) for c in custom_payments]]
        col_widths3 = [65*mm, 65*mm, 65*mm, 65*mm] + [40*mm] * len(custom_payments)
        for p in cliente.payments:
            extra = p.get_extra()
            data3.append([P(''), P(p.valor), P(p.fecha), P(p.credito)]
                         + [P(extra.get(c, '')) for c in custom_payments])
        if len(data3) > 1:
            t3 = Table(data3, repeatRows=1, colWidths=col_widths3)
            t3.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), purple),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#E2E8F0')]),
            ] + common_style))
            elements.append(t3)

    # FreightWise Additional Charges
    elements.append(Spacer(1, 15))
    fw_header = [[Paragraph('<b>FreightWise Additional Charges</b>', cell_header)]]
    fw_header_t = Table(fw_header, colWidths=[260*mm])
    fw_header_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), purple),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    elements.append(fw_header_t)

    cargos_fw = [
        ('Due Agent', '$ 50.00'),
        ('Certificate', '$ 15.00'),
        ('Phytosanitary', '$ 2.50'),
    ]
    fw_col_w = [60*mm, 70*mm, 70*mm, 60*mm]
    fw_data = [[P(''), P(concepto), P(monto), P('')] for concepto, monto in cargos_fw]
    fw_table = Table(fw_data, colWidths=fw_col_w)
    fw_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
    ] + common_style))
    elements.append(fw_table)

    doc.build(elements)
    output.seek(0)
    suffix = f"_{tabla}" if tabla != 'all' else ''
    filename = f"current_status_{cliente.nombre}{suffix}_{datetime.now().strftime('%Y%m%d')}.pdf"
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
