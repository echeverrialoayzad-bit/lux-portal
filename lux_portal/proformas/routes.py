from datetime import date
from flask import render_template, request, jsonify
from lux_portal.proformas import proformas_bp
from lux_portal.proformas.models import Proforma
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required


def _siguiente_numero():
    ultima = db.session.query(db.func.max(Proforma.id)).scalar() or 0
    seq = ultima + 34  # base histórica
    return f'001-003-{seq:07d}'


@proformas_bp.route('/')
@login_required
def dashboard():
    proformas = Proforma.query.order_by(Proforma.fecha_creacion.desc()).all()
    return render_template('proformas/dashboard.html', proformas=proformas)


@proformas_bp.route('/nueva')
@login_required
def nueva():
    numero = _siguiente_numero()
    hoy = date.today().isoformat()
    return render_template('proformas/form.html', proforma=None, numero=numero, hoy=hoy)


@proformas_bp.route('/<int:id>/editar')
@login_required
def editar(id):
    proforma = Proforma.query.get_or_404(id)
    hoy = date.today().isoformat()
    return render_template('proformas/form.html', proforma=proforma, numero=proforma.numero, hoy=hoy)


@proformas_bp.route('/api/proforma', methods=['POST'])
@login_required
def guardar():
    data = request.get_json()
    pid = data.get('id')

    if pid:
        p = Proforma.query.get_or_404(pid)
    else:
        p = Proforma()
        p.numero = data.get('numero') or _siguiente_numero()
        db.session.add(p)

    p.customer = data.get('customer', '')
    p.customer_id = data.get('customer_id', '')
    p.fecha = data.get('fecha', '')
    p.fecha_desde = data.get('fecha_desde', '')
    p.fecha_hasta = data.get('fecha_hasta', '')
    p.peso = data.get('peso') or 0
    p.tarifa = data.get('tarifa') or 0
    p.aerolinea = data.get('aerolinea', '')
    p.moneda = data.get('moneda', 'USD')
    p.origen = (data.get('origen') or 'UIO').upper()
    p.destino = (data.get('destino') or '').upper()
    p.descripcion = data.get('descripcion', '')
    p.comentarios = data.get('comentarios', '')
    p.cargos = data.get('cargos', [])
    p.estado = data.get('estado', 'borrador')

    db.session.commit()
    return jsonify({'success': True, 'id': p.id, 'numero': p.numero})


@proformas_bp.route('/api/proforma/<int:id>', methods=['DELETE'])
@login_required
def eliminar(id):
    p = Proforma.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'success': True})


@proformas_bp.route('/api/proforma/<int:id>/estado', methods=['POST'])
@login_required
def cambiar_estado(id):
    p = Proforma.query.get_or_404(id)
    p.estado = request.get_json().get('estado', p.estado)
    db.session.commit()
    return jsonify({'success': True})
