#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Cotizaciones FreightWise
"""

from flask import render_template, request, jsonify, send_file, redirect, url_for, flash
from datetime import datetime
from collections import defaultdict
import re
from lux_portal.cotizaciones import cotizaciones_bp
from lux_portal.cotizaciones.models import (
    Cotizacion, AirlineFscRule, AirlineFscGroup, AirlineCargoRule, AirlineCargoGroup,
    AirlineDepartureDays,
)
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


def _aerolineas_canonicas():
    """Aerolineas reconocidas: la union de las que estan gestionadas en las
    tablas maestras de FSC, Cargos Adicionales y Dias de Salida. Si una
    aerolinea no aparece en ninguna de las 3, se considera mal escrita."""
    fsc = {g.aerolinea for g in AirlineFscGroup.query.all()}
    cargo = {g.aerolinea for g in AirlineCargoGroup.query.all()}
    dias = {r.aerolinea for r in AirlineDepartureDays.query.all()}
    return fsc | cargo | dias


def _validar_aerolineas(cotizacion):
    """Devuelve la lista de nombres de aerolinea usados en la cotizacion que
    no calzan con ninguna aerolinea canonica."""
    canonicas = _aerolineas_canonicas()
    invalidas = []
    for entry in cotizacion.aerolineas:
        nombre = (entry.get('aerolinea') or '').strip().upper()
        if nombre and nombre not in canonicas and nombre not in invalidas:
            invalidas.append(nombre)
    return invalidas


@cotizaciones_bp.route('/descargar/<int:id>')
@login_required
def descargar_cotizacion(id):
    """Generar y descargar cotizacion en Excel o PDF."""
    try:
        cotizacion = Cotizacion.query.get_or_404(id)
        formato = request.args.get('formato', 'excel')
        idioma = request.args.get('idioma', 'ambos')

        invalidas = _validar_aerolineas(cotizacion)
        if invalidas:
            flash(
                'No se puede imprimir: estas aerolineas no estan bien escritas o no '
                'estan registradas en las tablas maestras (FSC / Cargos / Dias Salida): '
                + ', '.join(invalidas) + '. Corrige el nombre en la cotizacion o agregalo '
                'en las tablas maestras.',
                'error'
            )
            return redirect(url_for('cotizaciones.editar_cotizacion', id=id))

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


def _get_or_create_fsc_group(aerolinea):
    grupo = AirlineFscGroup.query.filter_by(aerolinea=aerolinea).first()
    if not grupo:
        grupo = AirlineFscGroup(aerolinea=aerolinea)
        db.session.add(grupo)
        db.session.flush()
    return grupo


@cotizaciones_bp.route('/fsc')
@login_required
def fsc_dashboard():
    """Tabla maestra editable de FSC por aerolinea/destino."""
    grupos = AirlineFscGroup.query.order_by(AirlineFscGroup.aerolinea).all()
    reglas = AirlineFscRule.query.order_by(AirlineFscRule.aerolinea, AirlineFscRule.order, AirlineFscRule.id).all()
    aerolineas = defaultdict(list)
    grupos_por_nombre = {}
    for g in grupos:
        aerolineas[g.aerolinea]  # asegura que la aerolinea aparezca aunque tenga 0 reglas
        grupos_por_nombre[g.aerolinea] = g.id
    for r in reglas:
        aerolineas[r.aerolinea].append(r.to_dict())
    return render_template(
        'cotizaciones/fsc.html',
        aerolineas=dict(sorted(aerolineas.items())),
        grupo_ids=grupos_por_nombre,
    )


@cotizaciones_bp.route('/api/fsc-rule', methods=['POST'])
@login_required
def crear_fsc_rule():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        _get_or_create_fsc_group(aerolinea)
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
    """Elimina solo esta regla. La aerolinea (AirlineFscGroup) se mantiene
    aunque quede en 0 reglas, para que Actualizar la siga reconociendo y
    limpie el FSC en sus cotizaciones en vez de dejarlo intacto."""
    regla = AirlineFscRule.query.get_or_404(id)
    try:
        db.session.delete(regla)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/fsc-aerolinea/<int:id>', methods=['DELETE'])
@login_required
def eliminar_fsc_aerolinea(id):
    """Elimina la aerolinea por completo de la tabla de FSC (grupo + reglas)."""
    grupo = AirlineFscGroup.query.get_or_404(id)
    try:
        AirlineFscRule.query.filter_by(aerolinea=grupo.aerolinea).delete()
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _resolver_fsc(reglas_por_aerolinea, aerolineas_gestionadas, aerolinea, destino):
    """Resuelve el FSC a aplicar:
    - Si la aerolinea no esta gestionada en la tabla maestra: None (no tocar).
    - Si esta gestionada y hay una regla que calza el destino (o catch-all): ese valor.
    - Si esta gestionada pero ninguna regla calza (incluye 0 reglas): '0.00' (limpiar)."""
    key = (aerolinea or '').strip().upper()
    if key not in aerolineas_gestionadas:
        return None
    reglas = reglas_por_aerolinea.get(key)
    if not reglas:
        return '0.00'
    destino_u = (destino or '').strip().upper()
    catch_all = None
    for r in reglas:
        codigos = [c.strip().upper() for c in r.destinos]
        if codigos and destino_u in codigos:
            return r.fsc
        if not codigos:
            catch_all = r
    return catch_all.fsc if catch_all else '0.00'


@cotizaciones_bp.route('/api/fsc-aplicar', methods=['POST'])
@login_required
def aplicar_fsc_a_cotizaciones():
    """Aplica la tabla maestra de FSC a TODAS las cotizaciones guardadas cuya
    aerolinea este gestionada aqui (tenga o no reglas activas en este momento),
    sobrescribiendo su campo fsc y recalculando el precio final. Tambien
    resetea Costo Operativo a su base (0.09) ya que en cotizaciones viejas el
    FSC venia mezclado dentro de ese campo. Aerolineas que no aparecen en la
    tabla quedan completamente intactas."""
    try:
        aerolineas_gestionadas = {g.aerolinea for g in AirlineFscGroup.query.all()}
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
                fsc_resuelto = _resolver_fsc(reglas_por_aerolinea, aerolineas_gestionadas, entry.get('aerolinea', ''), cot.destino)
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

def _get_or_create_cargo_group(aerolinea):
    grupo = AirlineCargoGroup.query.filter_by(aerolinea=aerolinea).first()
    if not grupo:
        grupo = AirlineCargoGroup(aerolinea=aerolinea, notas='')
        db.session.add(grupo)
        db.session.flush()
    return grupo


@cotizaciones_bp.route('/cargos')
@login_required
def cargos_dashboard():
    """Tabla maestra editable de cargos adicionales fijos por aerolinea."""
    grupos = AirlineCargoGroup.query.order_by(AirlineCargoGroup.aerolinea).all()
    reglas = AirlineCargoRule.query.order_by(AirlineCargoRule.aerolinea, AirlineCargoRule.order, AirlineCargoRule.id).all()
    aerolineas = {}
    grupos_por_nombre = {}
    for g in grupos:
        aerolineas[g.aerolinea] = []
        grupos_por_nombre[g.aerolinea] = g
    for r in reglas:
        aerolineas.setdefault(r.aerolinea, []).append(r.to_dict())
    aerolineas = dict(sorted(aerolineas.items()))
    grupos_dict = {nombre: g.to_dict() for nombre, g in grupos_por_nombre.items()}
    return render_template('cotizaciones/cargos.html', aerolineas=aerolineas, grupos=grupos_dict)


@cotizaciones_bp.route('/api/cargo-rule', methods=['POST'])
@login_required
def crear_cargo_rule():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        _get_or_create_cargo_group(aerolinea)
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
    """Elimina solo este cargo. La aerolinea (AirlineCargoGroup) se mantiene
    aunque quede en 0 cargos, para que Actualizar la siga reconociendo."""
    regla = AirlineCargoRule.query.get_or_404(id)
    try:
        db.session.delete(regla)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-aerolinea/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cargo_aerolinea(id):
    """Elimina la aerolinea por completo de la tabla de cargos (grupo + reglas)."""
    grupo = AirlineCargoGroup.query.get_or_404(id)
    try:
        AirlineCargoRule.query.filter_by(aerolinea=grupo.aerolinea).delete()
        db.session.delete(grupo)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-aerolinea/<int:id>/notas', methods=['PUT'])
@login_required
def actualizar_cargo_notas(id):
    grupo = AirlineCargoGroup.query.get_or_404(id)
    try:
        data = request.get_json()
        grupo.notas = data.get('notas', '')
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/cargo-aplicar', methods=['POST'])
@login_required
def aplicar_cargos_a_cotizaciones():
    """Aplica la tabla maestra de cargos adicionales a TODAS las cotizaciones
    guardadas cuya aerolinea este gestionada aqui (tenga o no cargos activos
    en este momento), reemplazando su lista de cargos adicionales. Tambien
    agrega (sin borrar) la nota general de la aerolinea a la nota especifica
    de cada cotizacion, si todavia no esta incluida. Aerolineas que no
    aparecen en la tabla quedan completamente intactas."""
    try:
        grupos = AirlineCargoGroup.query.all()
        aerolineas_gestionadas = {g.aerolinea for g in grupos}
        notas_por_aerolinea = {g.aerolinea: (g.notas or '').strip() for g in grupos}

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
                if key not in aerolineas_gestionadas:
                    continue
                entry['cargos_adicionales'] = [
                    {'concepto': r.concepto, 'monto': r.monto} for r in reglas_por_aerolinea.get(key, [])
                ]
                nota_general = notas_por_aerolinea.get(key, '')
                if nota_general:
                    nota_actual = (entry.get('notas') or '').strip()
                    if nota_general not in nota_actual:
                        entry['notas'] = f"{nota_actual}\n{nota_general}".strip() if nota_actual else nota_general
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


# ===================== DIAS DE SALIDA POR AEROLINEA =====================

DIAS_ORDEN = ['LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB', 'DOM']
_DIAS_MAPPING = {'LUN': 0, 'MAR': 1, 'MIE': 2, 'JUE': 3, 'VIE': 4, 'SAB': 5, 'DOM': 6}
_DIAS_SEMANA = ['DOM', 'LUN', 'MAR', 'MIE', 'JUE', 'VIE', 'SAB']


def _dia_offset(dia, offset):
    """Misma logica que el formulario (form.html) usa en recopilarDatos()
    para calcular granjas_entrega/llegada a partir del dia de salida."""
    idx = _DIAS_MAPPING.get(dia)
    if idx is None:
        return None
    return _DIAS_SEMANA[(idx + offset) % 7]


def _parse_transit_dias(tiempo_transito):
    m = re.search(r'\+?(\d+)-?(\d+)?D', tiempo_transito or '')
    if not m:
        return 2
    return int(m.group(2) or m.group(1))


def _last_line(text):
    if not text:
        return ''
    partes = text.split('\n')
    return partes[-1] if partes else ''


def _aplicar_dias_a_entry(entry, nuevos_dias):
    """Reescribe salida/granjas_entrega/llegada con los nuevos dias,
    preservando las horas (ultima linea) que ya tuviera la entrada."""
    departure_time = _last_line(entry.get('salida'))
    farms_horario = _last_line(entry.get('granjas_entrega'))
    arrival_time = _last_line(entry.get('llegada'))
    transit_dias = _parse_transit_dias(entry.get('tiempo_transito'))

    dias_farms = [d for d in (_dia_offset(d, 6) for d in nuevos_dias) if d]
    dias_llegada = [d for d in (_dia_offset(d, transit_dias) for d in nuevos_dias) if d]

    entry['salida'] = '\n'.join(nuevos_dias) + (f'\n{departure_time}' if departure_time else '')
    entry['granjas_entrega'] = '\n'.join(dias_farms) + (f'\n{farms_horario}' if farms_horario else '')
    entry['llegada'] = '\n'.join(dias_llegada) + (f'\n{arrival_time}' if arrival_time else '')


@cotizaciones_bp.route('/dias-salida')
@login_required
def dias_salida_dashboard():
    """Tabla maestra editable de dias de salida fijos por aerolinea desde UIO."""
    registros = AirlineDepartureDays.query.order_by(AirlineDepartureDays.aerolinea).all()
    return render_template('cotizaciones/dias_salida.html', registros=[r.to_dict() for r in registros], dias_orden=DIAS_ORDEN)


@cotizaciones_bp.route('/api/dias-rule', methods=['POST'])
@login_required
def crear_dias_rule():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        if AirlineDepartureDays.query.filter_by(aerolinea=aerolinea).first():
            return jsonify({'success': False, 'error': 'Esa aerolinea ya esta en la tabla'}), 400
        registro = AirlineDepartureDays(aerolinea=aerolinea)
        registro.dias = [d for d in DIAS_ORDEN if d in (data.get('dias') or [])]
        db.session.add(registro)
        db.session.commit()
        return jsonify({'success': True, 'registro': registro.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/dias-rule/<int:id>', methods=['PUT'])
@login_required
def actualizar_dias_rule(id):
    registro = AirlineDepartureDays.query.get_or_404(id)
    try:
        data = request.get_json()
        if 'dias' in data:
            registro.dias = [d for d in DIAS_ORDEN if d in (data.get('dias') or [])]
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/dias-rule/<int:id>', methods=['DELETE'])
@login_required
def eliminar_dias_rule(id):
    registro = AirlineDepartureDays.query.get_or_404(id)
    try:
        db.session.delete(registro)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/dias-aplicar', methods=['POST'])
@login_required
def aplicar_dias_a_cotizaciones():
    """Aplica los dias de salida de la tabla maestra a TODAS las cotizaciones
    guardadas cuya aerolinea este en la tabla, recalculando salida, llegada y
    granjas_entrega (mismo calculo que usa el formulario), preservando las
    horas que ya tuviera cada entrada. Aerolineas que no estan en la tabla
    quedan completamente intactas."""
    try:
        registros = AirlineDepartureDays.query.all()
        dias_por_aerolinea = {r.aerolinea: r.dias for r in registros}

        cotizaciones = Cotizacion.query.all()
        cotizaciones_actualizadas = 0
        entradas_actualizadas = 0

        for cot in cotizaciones:
            aerolineas = cot.aerolineas
            cambio = False
            for entry in aerolineas:
                key = (entry.get('aerolinea') or '').strip().upper()
                if key not in dias_por_aerolinea:
                    continue
                _aplicar_dias_a_entry(entry, dias_por_aerolinea[key])
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
