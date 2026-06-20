#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Cotizaciones FreightWise
"""

from flask import render_template, request, jsonify, send_file, redirect, url_for, flash
from datetime import datetime
from collections import defaultdict
from lux_portal.cotizaciones import cotizaciones_bp
from lux_portal.cotizaciones.models import Cotizacion, AirlineFscRule, AirlineCargoRule
from lux_portal.cotizaciones.data import AEROLINEAS_LISTA, CARGOS_COMUNES, CARGOS_FREIGHTWISE
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
    return render_template('cotizaciones/form.html', cotizacion=None, aerolineas=[], now=datetime.now())


@cotizaciones_bp.route('/editar/<int:id>')
@login_required
def editar_cotizacion(id):
    """Formulario para editar cotizacion existente."""
    cotizacion = Cotizacion.query.get_or_404(id)
    return render_template('cotizaciones/form.html', cotizacion=cotizacion, aerolineas=cotizacion.aerolineas, now=datetime.now())


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
        cotizacion.cargos_freightwise = data.get('cargos_freightwise')
        cotizacion.notas_freightwise = data.get('notas_freightwise', '')

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
        idioma = request.args.get('idioma', 'ambos')

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
            'aerolineas': cotizacion.aerolineas,
            'cargos_freightwise': cotizacion.cargos_freightwise or CARGOS_FREIGHTWISE,
            'notas_freightwise': cotizacion.notas_freightwise or ''
        }

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Sufijo de idioma para el nombre del archivo
        idioma_sufijo = {'es': '_ES', 'en': '_EN', 'ambos': ''}
        sufijo = idioma_sufijo.get(idioma, '')

        if formato == 'pdf':
            # Generar PDF
            pdf_bytes = guardar_cotizacion_pdf_bytes(datos, idioma=idioma)
            nombre_archivo = f"FreightWise_Cotizacion_{cotizacion.ruta}{sufijo}_{timestamp}.pdf"

            return send_file(
                pdf_bytes,
                as_attachment=True,
                download_name=nombre_archivo,
                mimetype='application/pdf'
            )
        else:
            # Generar Excel (por defecto)
            excel_bytes = guardar_cotizacion_bytes(datos, idioma=idioma)
            nombre_archivo = f"FreightWise_Cotizacion_{cotizacion.ruta}{sufijo}_{timestamp}.xlsx"

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


# ===================== FSC POR AEROLINEA =====================

BASE_OPERATIVO = 0.09


@cotizaciones_bp.route('/fsc')
@login_required
def fsc_dashboard():
    """Tabla maestra editable de FSC por aerolinea/destino."""
    reglas = AirlineFscRule.query.order_by(AirlineFscRule.aerolinea, AirlineFscRule.order, AirlineFscRule.id).all()
    aerolineas = defaultdict(list)
    for r in reglas:
        aerolineas[r.aerolinea].append(r.to_dict())
    return render_template('cotizaciones/fsc.html', aerolineas=dict(sorted(aerolineas.items())))


@cotizaciones_bp.route('/api/fsc-rule', methods=['POST'])
@login_required
def crear_fsc_rule():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        max_order = db.session.query(db.func.max(AirlineFscRule.order)).filter_by(aerolinea=aerolinea).scalar() or 0
        regla = AirlineFscRule(
            aerolinea=aerolinea,
            nombre=data.get('nombre') or 'Todos los destinos',
            fsc=data.get('fsc', '0.00'),
            order=max_order + 1,
        )
        regla.destinos = data.get('destinos') or []
        db.session.add(regla)
        db.session.commit()
        return jsonify({'success': True, 'regla': regla.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/fsc-rule/<int:id>', methods=['PUT'])
@login_required
def actualizar_fsc_rule(id):
    regla = AirlineFscRule.query.get_or_404(id)
    try:
        data = request.get_json()
        if 'nombre' in data:
            regla.nombre = data['nombre']
        if 'destinos' in data:
            regla.destinos = data['destinos']
        if 'fsc' in data:
            regla.fsc = data['fsc']
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/fsc-rule/<int:id>', methods=['DELETE'])
@login_required
def eliminar_fsc_rule(id):
    regla = AirlineFscRule.query.get_or_404(id)
    try:
        db.session.delete(regla)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _resolver_fsc(reglas_por_aerolinea, aerolinea, destino):
    """Busca la regla de FSC que aplica: primero una con el destino especifico
    en su lista de codigos IATA, si no hay, la regla 'catch-all' (destinos vacios)."""
    reglas = reglas_por_aerolinea.get((aerolinea or '').strip().upper())
    if not reglas:
        return None
    destino_u = (destino or '').strip().upper()
    catch_all = None
    for r in reglas:
        codigos = [c.strip().upper() for c in r.destinos]
        if codigos and destino_u in codigos:
            return r.fsc
        if not codigos:
            catch_all = r
    return catch_all.fsc if catch_all else None


@cotizaciones_bp.route('/api/fsc-aplicar', methods=['POST'])
@login_required
def aplicar_fsc_a_cotizaciones():
    """Aplica la tabla maestra de FSC a TODAS las cotizaciones guardadas que
    calcen por aerolinea+destino, sobrescribiendo su campo fsc y recalculando
    el precio final. Tambien resetea Costo Operativo a su base (0.09) ya que
    en cotizaciones viejas el FSC venia mezclado dentro de ese campo."""
    try:
        reglas = AirlineFscRule.query.all()
        reglas_por_aerolinea = defaultdict(list)
        for r in reglas:
            reglas_por_aerolinea[r.aerolinea.strip().upper()].append(r)

        cotizaciones = Cotizacion.query.all()
        cotizaciones_actualizadas = 0
        entradas_actualizadas = 0

        for cot in cotizaciones:
            aerolineas = cot.aerolineas
            cambio = False
            for entry in aerolineas:
                fsc_resuelto = _resolver_fsc(reglas_por_aerolinea, entry.get('aerolinea', ''), cot.destino)
                if fsc_resuelto is None:
                    continue
                try:
                    fsc_val = float(fsc_resuelto)
                except (TypeError, ValueError):
                    continue
                for kr in entry.get('kg_rates') or []:
                    try:
                        tarifa = float(kr.get('tarifa', '0') or 0)
                        margen = float(kr.get('margen', '0') or 0)
                    except (TypeError, ValueError):
                        tarifa = margen = 0.0
                    kr['costo_operativo'] = f"{BASE_OPERATIVO:.2f}"
                    kr['fsc'] = f"{fsc_val:.2f}"
                    kr['tarifa_cliente'] = f"{(tarifa + margen + BASE_OPERATIVO + fsc_val):.2f}"
                    entradas_actualizadas += 1
                    cambio = True
            if cambio:
                cot.aerolineas = aerolineas
                cotizaciones_actualizadas += 1

        db.session.commit()
        return jsonify({
            'success': True,
            'cotizaciones_actualizadas': cotizaciones_actualizadas,
            'entradas_actualizadas': entradas_actualizadas,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ===================== CARGOS ADICIONALES POR AEROLINEA =====================

@cotizaciones_bp.route('/cargos')
@login_required
def cargos_dashboard():
    """Tabla maestra editable de cargos adicionales fijos por aerolinea."""
    reglas = AirlineCargoRule.query.order_by(AirlineCargoRule.aerolinea, AirlineCargoRule.order, AirlineCargoRule.id).all()
    aerolineas = defaultdict(list)
    for r in reglas:
        aerolineas[r.aerolinea].append(r.to_dict())
    return render_template('cotizaciones/cargos.html', aerolineas=dict(sorted(aerolineas.items())))


@cotizaciones_bp.route('/api/cargo-rule', methods=['POST'])
@login_required
def crear_cargo_rule():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        max_order = db.session.query(db.func.max(AirlineCargoRule.order)).filter_by(aerolinea=aerolinea).scalar() or 0
        regla = AirlineCargoRule(
            aerolinea=aerolinea,
            concepto=data.get('concepto') or 'Nuevo cargo',
            monto=data.get('monto', '0.00'),
            order=max_order + 1,
        )
        db.session.add(regla)
        db.session.commit()
        return jsonify({'success': True, 'regla': regla.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-rule/<int:id>', methods=['PUT'])
@login_required
def actualizar_cargo_rule(id):
    regla = AirlineCargoRule.query.get_or_404(id)
    try:
        data = request.get_json()
        if 'concepto' in data:
            regla.concepto = data['concepto']
        if 'monto' in data:
            regla.monto = data['monto']
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-rule/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cargo_rule(id):
    regla = AirlineCargoRule.query.get_or_404(id)
    try:
        db.session.delete(regla)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-aplicar', methods=['POST'])
@login_required
def aplicar_cargos_a_cotizaciones():
    """Aplica la tabla maestra de cargos adicionales a TODAS las cotizaciones
    guardadas cuya aerolinea tenga reglas, reemplazando su lista de cargos
    adicionales. Aerolineas sin reglas en la tabla maestra quedan intactas."""
    try:
        reglas = AirlineCargoRule.query.order_by(AirlineCargoRule.order, AirlineCargoRule.id).all()
        reglas_por_aerolinea = defaultdict(list)
        for r in reglas:
            reglas_por_aerolinea[r.aerolinea.strip().upper()].append(r)

        cotizaciones = Cotizacion.query.all()
        cotizaciones_actualizadas = 0
        entradas_actualizadas = 0

        for cot in cotizaciones:
            aerolineas = cot.aerolineas
            cambio = False
            for entry in aerolineas:
                key = (entry.get('aerolinea') or '').strip().upper()
                if key not in reglas_por_aerolinea:
                    continue
                entry['cargos_adicionales'] = [
                    {'concepto': r.concepto, 'monto': r.monto} for r in reglas_por_aerolinea[key]
                ]
                entradas_actualizadas += 1
                cambio = True
            if cambio:
                cot.aerolineas = aerolineas
                cotizaciones_actualizadas += 1

        db.session.commit()
        return jsonify({
            'success': True,
            'cotizaciones_actualizadas': cotizaciones_actualizadas,
            'entradas_actualizadas': entradas_actualizadas,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
