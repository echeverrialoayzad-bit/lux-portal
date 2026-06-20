#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Excel Online: hojas de calculo dinamicas embebidas en el portal.
"""

from datetime import datetime
from flask import render_template, request, jsonify, send_file
from lux_portal.excel_online import excel_online_bp
from lux_portal.excel_online.models import ExcelSheet
from lux_portal.excel_online.exportador import generar_excel_online_bytes
from lux_portal.auth.decorators import login_required
from lux_portal.extensions import db


@excel_online_bp.route('/')
@login_required
def index():
    sheets = ExcelSheet.query.order_by(ExcelSheet.order, ExcelSheet.id).all()
    return render_template('excel_online/index.html', sheets=[s.to_dict() for s in sheets])


@excel_online_bp.route('/exportar')
@login_required
def exportar():
    sheets = ExcelSheet.query.order_by(ExcelSheet.order, ExcelSheet.id).all()
    excel_bytes = generar_excel_online_bytes([s.to_dict() for s in sheets])
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(
        excel_bytes,
        as_attachment=True,
        download_name=f'Excel_Online_FreightWise_{timestamp}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@excel_online_bp.route('/api/sheet', methods=['POST'])
@login_required
def crear_sheet():
    data = request.get_json() or {}
    try:
        max_order = db.session.query(db.func.max(ExcelSheet.order)).scalar() or 0
        sheet = ExcelSheet(name=data.get('name') or 'Hoja', order=max_order + 1)
        sheet.headers = data.get('headers') or ['A', 'B', 'C']
        sheet.rows = data.get('rows') or [['', '', '']]
        db.session.add(sheet)
        db.session.commit()
        return jsonify({'success': True, 'sheet': sheet.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@excel_online_bp.route('/api/sheet/<int:id>', methods=['PUT'])
@login_required
def actualizar_sheet(id):
    sheet = ExcelSheet.query.get_or_404(id)
    data = request.get_json() or {}
    try:
        if 'name' in data:
            sheet.name = data['name']
        if 'headers' in data:
            sheet.headers = data['headers']
        if 'rows' in data:
            sheet.rows = data['rows']
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@excel_online_bp.route('/api/sheet/<int:id>', methods=['DELETE'])
@login_required
def eliminar_sheet(id):
    sheet = ExcelSheet.query.get_or_404(id)
    try:
        db.session.delete(sheet)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
