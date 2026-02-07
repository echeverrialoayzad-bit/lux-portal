from flask import render_template, request, redirect, url_for, flash, jsonify
from lux_portal.current_status import current_status_bp
from lux_portal.current_status.models import StatusClient, StatusAirline, StatusPayment
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required


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


# --- API endpoints ---

@current_status_bp.route('/api/client/<int:id>/estado', methods=['PUT'])
@login_required
def cambiar_estado(id):
    """Cambiar estado pendiente/finalizado"""
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    cliente.estado = data.get('estado', 'pendiente')
    db.session.commit()
    return jsonify({'success': True, 'estado': cliente.estado})


@current_status_bp.route('/api/client/<int:id>/nombre', methods=['PUT'])
@login_required
def cambiar_nombre(id):
    """Cambiar nombre del cliente"""
    cliente = StatusClient.query.get_or_404(id)
    data = request.get_json()
    cliente.nombre = data.get('nombre', cliente.nombre)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/client/<int:id>/airline', methods=['POST'])
@login_required
def agregar_airline(id):
    """Agregar fila de aerolinea"""
    cliente = StatusClient.query.get_or_404(id)
    airline = StatusAirline(client_id=cliente.id)
    db.session.add(airline)
    db.session.commit()
    return jsonify({'success': True, 'id': airline.id})


@current_status_bp.route('/api/airline/<int:id>', methods=['PUT'])
@login_required
def actualizar_airline(id):
    """Actualizar fila de aerolinea"""
    airline = StatusAirline.query.get_or_404(id)
    data = request.get_json()
    for field in ['current_status', 'proximo_vuelo', 'entrega_fincas', 'hora_maxima',
                  'aerolinea', 'awb', 'itinerario', 'eta']:
        if field in data:
            setattr(airline, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/airline/<int:id>', methods=['DELETE'])
@login_required
def eliminar_airline(id):
    """Eliminar fila de aerolinea"""
    airline = StatusAirline.query.get_or_404(id)
    db.session.delete(airline)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/client/<int:id>/payment', methods=['POST'])
@login_required
def agregar_payment(id):
    """Agregar fila de pago"""
    cliente = StatusClient.query.get_or_404(id)
    payment = StatusPayment(client_id=cliente.id)
    db.session.add(payment)
    db.session.commit()
    return jsonify({'success': True, 'id': payment.id})


@current_status_bp.route('/api/payment/<int:id>', methods=['PUT'])
@login_required
def actualizar_payment(id):
    """Actualizar fila de pago"""
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
    """Eliminar fila de pago"""
    payment = StatusPayment.query.get_or_404(id)
    db.session.delete(payment)
    db.session.commit()
    return jsonify({'success': True})


@current_status_bp.route('/api/client/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cliente(id):
    """Eliminar cliente (soft delete)"""
    cliente = StatusClient.query.get_or_404(id)
    cliente.activo = False
    db.session.commit()
    return jsonify({'success': True})
