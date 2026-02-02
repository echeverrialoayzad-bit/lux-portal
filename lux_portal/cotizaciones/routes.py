#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Cotizaciones FreightWise
"""

from flask import render_template, request, jsonify, send_file, redirect, url_for, flash
from datetime import datetime
from lux_portal.cotizaciones import cotizaciones_bp
from lux_portal.cotizaciones.models import Cotizacion
from lux_portal.cotizaciones.data import AEROLINEAS_LISTA, CARGOS_COMUNES
from lux_portal.cotizaciones.utils.excel_generator import guardar_cotizacion_bytes
from lux_portal.cotizaciones.utils.pdf_generator import guardar_cotizacion_pdf_bytes
from lux_portal.auth.decorators import login_required
from lux_portal.extensions import db


@cotizaciones_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal - Lista de cotizaciones."""
    cotizaciones = Cotizacion.query.order_by(Cotizacion.fecha_creacion.desc()).limit(50).all()
    return render_template('cotizaciones/dashboard.html', cotizaciones=cotizaciones)


@cotizaciones_bp.route('/nueva')
@login_required
def nueva_cotizacion():
    """Formulario para crear nueva cotizacion."""
    return render_template('cotizaciones/form.html', cotizacion=None, aerolineas=[])


@cotizaciones_bp.route('/editar/<int:id>')
@login_required
def editar_cotizacion(id):
    """Formulario para editar cotizacion existente."""
    cotizacion = Cotizacion.query.get_or_404(id)
    return render_template('cotizaciones/form.html', cotizacion=cotizacion, aerolineas=cotizacion.aerolineas)


@cotizaciones_bp.route('/api/cotizacion', methods=['POST'])
@login_required
def guardar_cotizacion():
    """Guardar cotizacion (nueva o existente)."""
    try:
        data = request.get_json()

        cotizacion_id = data.get('id')

        if cotizacion_id:
            cotizacion = Cotizacion.query.get_or_404(cotizacion_id)
        else:
            cotizacion = Cotizacion()
            db.session.add(cotizacion)

        # Actualizar campos
        cotizacion.contacto_nombre = data.get('contacto_nombre', 'Daniela Echeverria')
        cotizacion.contacto_email = data.get('contacto_email', 'daniela.echeverria@freight-wise.com')
        cotizacion.valid_from = data.get('valid_from', datetime.now().strftime('%m/%d/%Y'))
        cotizacion.mercancia = data.get('mercancia', 'FRESH CUT FLOWERS')
        cotizacion.customer = data.get('customer', '')
        cotizacion.attn = data.get('attn', '')
        cotizacion.origen = data.get('origen', '').upper()
        cotizacion.destino = data.get('destino', '').upper()
        cotizacion.aerolineas = data.get('aerolineas', [])

        db.session.commit()

        return jsonify({'success': True, 'id': cotizacion.id, 'message': 'Cotizacion guardada exitosamente'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cotizacion/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cotizacion(id):
    """Eliminar cotizacion."""
    try:
        cotizacion = Cotizacion.query.get_or_404(id)
        db.session.delete(cotizacion)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Cotizacion eliminada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/descargar/<int:id>')
@login_required
def descargar_cotizacion(id):
    """Generar y descargar cotizacion en Excel o PDF."""
    try:
        cotizacion = Cotizacion.query.get_or_404(id)
        formato = request.args.get('formato', 'excel')

        # Preparar datos para el generador
        datos = {
            'contacto_nombre': cotizacion.contacto_nombre,
            'contacto_email': cotizacion.contacto_email,
            'valid_from': cotizacion.valid_from,
            'mercancia': cotizacion.mercancia,
            'customer': cotizacion.customer,
            'attn': cotizacion.attn,
            'origen': cotizacion.origen,
            'destino': cotizacion.destino,
            'ruta': cotizacion.ruta,
            'aerolineas': cotizacion.aerolineas
        }

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if formato == 'pdf':
            # Generar PDF
            pdf_bytes = guardar_cotizacion_pdf_bytes(datos)
            nombre_archivo = f"FreightWise_Cotizacion_{cotizacion.ruta}_{timestamp}.pdf"

            return send_file(
                pdf_bytes,
                as_attachment=True,
                download_name=nombre_archivo,
                mimetype='application/pdf'
            )
        else:
            # Generar Excel (por defecto)
            excel_bytes = guardar_cotizacion_bytes(datos)
            nombre_archivo = f"FreightWise_Cotizacion_{cotizacion.ruta}_{timestamp}.xlsx"

            return send_file(
                excel_bytes,
                as_attachment=True,
                download_name=nombre_archivo,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

    except Exception as e:
        flash(f'Error al generar archivo: {str(e)}', 'error')
        return redirect(url_for('cotizaciones.dashboard'))


@cotizaciones_bp.route('/api/cotizacion/<int:id>')
@login_required
def obtener_cotizacion(id):
    """Obtener datos de cotizacion en JSON."""
    cotizacion = Cotizacion.query.get_or_404(id)
    return jsonify(cotizacion.to_dict())


@cotizaciones_bp.route('/api/aerolineas')
@login_required
def obtener_aerolineas():
    """Obtener lista de aerolineas predefinidas."""
    return jsonify(AEROLINEAS_LISTA)


@cotizaciones_bp.route('/api/cargos')
@login_required
def obtener_cargos():
    """Obtener cargos comunes predefinidos."""
    return jsonify(CARGOS_COMUNES)
