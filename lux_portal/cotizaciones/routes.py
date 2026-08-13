#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas del modulo Cotizaciones FreightWise
"""

from flask import render_template, request, jsonify, send_file, redirect, url_for, flash
from datetime import datetime
from collections import defaultdict
import re
import json
from lux_portal.cotizaciones import cotizaciones_bp
from lux_portal.cotizaciones.models import (
    Cotizacion, AirlineFscRule, AirlineFscGroup, AirlineCargoRule, AirlineCargoGroup,
    AirlineDepartureDays, AirlineMailRequest,
)
from lux_portal.cotizaciones.data import AEROLINEAS_LISTA, CARGOS_COMUNES, CARGOS_FREIGHTWISE
from lux_portal.cotizaciones.continentes import CONTINENTES, continente_de
from lux_portal.cotizaciones.utils.excel_generator import (
    guardar_cotizacion_bytes, generar_desglose_tarifa_bytes, generar_desglose_tarifa_png_bytes,
    generar_reporte_netas_bytes,
)
from lux_portal.cotizaciones.utils.pdf_generator import guardar_cotizacion_pdf_bytes
from lux_portal.auth.decorators import login_required
from lux_portal.extensions import db


@cotizaciones_bp.route('/continentes')
@login_required
def continentes_dashboard():
    """Pantalla de seleccion de continente antes de ver las cotizaciones."""
    cotizaciones = Cotizacion.query.all()
    conteo = {c: 0 for c in CONTINENTES}
    sin_clasificar = 0
    for cot in cotizaciones:
        cont = continente_de(cot.destino)
        if cont:
            conteo[cont] += 1
        else:
            sin_clasificar += 1
    return render_template(
        'cotizaciones/continentes.html',
        continentes=CONTINENTES,
        conteo=conteo,
        total=len(cotizaciones),
        sin_clasificar=sin_clasificar,
    )


@cotizaciones_bp.route('/')
@login_required
def dashboard():
    """Dashboard principal - Lista de cotizaciones, opcionalmente filtrada por continente."""
    continente = request.args.get('continente', '').strip().upper()
    query = Cotizacion.query.order_by(Cotizacion.fecha_creacion.desc())
    if continente in CONTINENTES:
        cotizaciones = [c for c in query.all() if continente_de(c.destino) == continente]
    else:
        continente = ''
        cotizaciones = query.all()

    destinos_disponibles = sorted({
        (d or '').strip().upper()
        for (d,) in db.session.query(Cotizacion.destino).distinct()
        if d and d.strip()
    })

    return render_template(
        'cotizaciones/dashboard.html',
        cotizaciones=cotizaciones,
        continente_activo=continente,
        destinos_disponibles=destinos_disponibles,
    )


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


def _snapshot_tarifas(aerolineas):
    """Devuelve un dict {nombre_aerolinea: (hash_kg_rates, fecha_actualizacion)}
    para detectar qué aerolíneas cambiaron sus tarifas al guardar."""
    snap = {}
    for entry in (aerolineas or []):
        nombre = entry.get('aerolinea', '')
        if not nombre:
            continue
        campos_tarifa = [
            {k: kr.get(k) for k in ('kg', 'tarifa', 'fsc', 'margen', 'costo_operativo', 'tarifa_cliente')}
            for kr in (entry.get('kg_rates') or [])
        ]
        snap[nombre] = (
            json.dumps(campos_tarifa, sort_keys=True),
            entry.get('fecha_actualizacion', ''),
        )
    return snap


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

        # Capturar snapshot de tarifas anteriores ANTES de sobreescribir
        snap_anterior = _snapshot_tarifas(cotizacion.aerolineas if cotizacion_id else [])

        # Marcar fecha_actualizacion solo en aerolíneas cuyas tarifas cambiaron
        hoy = datetime.now().strftime('%Y-%m-%d')
        aerolineas_nuevas = data.get('aerolineas', [])
        for entry in aerolineas_nuevas:
            nombre = entry.get('aerolinea', '')
            campos_tarifa = [
                {k: kr.get(k) for k in ('kg', 'tarifa', 'fsc', 'margen', 'costo_operativo', 'tarifa_cliente')}
                for kr in (entry.get('kg_rates') or [])
            ]
            hash_nuevo = json.dumps(campos_tarifa, sort_keys=True)
            hash_anterior, fecha_anterior = snap_anterior.get(nombre, ('', ''))
            if hash_nuevo != hash_anterior:
                entry['fecha_actualizacion'] = hoy
            else:
                entry['fecha_actualizacion'] = fecha_anterior

        # Actualizar campos
        cotizacion.contacto_nombre = data.get('contacto_nombre', 'Daniela Echeverria')
        cotizacion.contacto_email = data.get('contacto_email', 'daniela.echeverria@freight-wise.com')
        cotizacion.valid_from = datetime.now().strftime('%m/%d/%Y')
        cotizacion.mercancia = data.get('mercancia', 'FRESH CUT FLOWERS')
        cotizacion.customer = data.get('customer', '')
        cotizacion.attn = data.get('attn', '')
        cotizacion.origen = data.get('origen', '').upper()
        cotizacion.destino = data.get('destino', '').upper()
        cotizacion.aerolineas = aerolineas_nuevas
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


def _validar_cotizacion(cotizacion):
    """Devuelve una lista de mensajes de error si la cotizacion tiene
    problemas que deben bloquear la impresion: aerolineas no reconocidas, o
    tramos de kg repetidos dentro de la misma aerolinea (la escala deberia
    ser progresiva, ej. +100, +500, +1000, nunca el mismo tramo dos veces)."""
    canonicas = _aerolineas_canonicas()
    errores = []
    aerolineas_invalidas = []

    for entry in cotizacion.aerolineas:
        nombre = (entry.get('aerolinea') or '').strip().upper()
        if nombre and nombre not in canonicas and nombre not in aerolineas_invalidas:
            aerolineas_invalidas.append(nombre)

        vistos, duplicados = [], []
        for kr in entry.get('kg_rates') or []:
            kg = (kr.get('kg') or '').strip()
            if not kg:
                continue
            if kg in vistos and kg not in duplicados:
                duplicados.append(kg)
            else:
                vistos.append(kg)
        if duplicados:
            errores.append(
                f"{nombre or '(sin nombre)'} tiene el tramo de kg repetido: " + ', '.join(duplicados)
                + ' (la escala debe ser progresiva, ej. +100, +500, +1000, sin repetir un tramo)'
            )

    if aerolineas_invalidas:
        errores.append(
            'Estas aerolineas no estan bien escritas o no estan registradas en las tablas '
            'maestras (FSC / Cargos / Dias Salida): ' + ', '.join(aerolineas_invalidas)
        )

    return errores


@cotizaciones_bp.route('/api/validar/<int:id>')
@login_required
def validar_cotizacion_api(id):
    """Devuelve los errores de validacion de una cotizacion en JSON."""
    cotizacion = Cotizacion.query.get_or_404(id)
    errores = _validar_cotizacion(cotizacion)
    return jsonify({'valido': len(errores) == 0, 'errores': errores})


@cotizaciones_bp.route('/descargar/<int:id>')
@login_required
def descargar_cotizacion(id):
    """Generar y descargar cotizacion en Excel o PDF."""
    try:
        cotizacion = Cotizacion.query.get_or_404(id)
        formato = request.args.get('formato', 'excel')
        idioma = request.args.get('idioma', 'ambos')
        forzar = request.args.get('forzar', '0') == '1'

        errores = _validar_cotizacion(cotizacion)
        if errores and not forzar:
            flash('No se puede imprimir: ' + ' | '.join(errores) + '. Corrige la cotizacion e intenta de nuevo.', 'error')
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

        # Nombre de archivo: {Cliente}_{ruta}_FW  o  {ruta}_FW si no hay cliente
        cliente_raw = (cotizacion.customer or '').strip()
        cliente_slug = re.sub(r'[^\w\-]', '_', cliente_raw).strip('_') if cliente_raw else ''
        prefijo = f"{cliente_slug}_{cotizacion.ruta}" if cliente_slug else cotizacion.ruta

        # Generar archivo antes de limpiar el cliente
        if formato == 'pdf':
            archivo_bytes = guardar_cotizacion_pdf_bytes(datos, idioma=idioma)
            nombre_archivo = f"{prefijo}_FW.pdf"
            mimetype = 'application/pdf'
        else:
            archivo_bytes = guardar_cotizacion_bytes(datos, idioma=idioma)
            nombre_archivo = f"{prefijo}_FW.xlsx"
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        # Actualizar fecha y limpiar cliente tras imprimir
        cotizacion.valid_from = datetime.now().strftime('%m/%d/%Y')
        cotizacion.customer = ''
        cotizacion.attn = ''
        db.session.commit()

        return send_file(
            archivo_bytes,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype=mimetype
        )

    except Exception as e:
        flash(f'Error al generar archivo: {str(e)}', 'error')
        return redirect(url_for('cotizaciones.dashboard'))


def _filas_desglose_de(cotizacion):
    """Construye las filas (aerolinea, kg, tarifa_neta, fsc, operativo,
    profit, tarifa_venta) para el desglose de una cotizacion, separando el
    FSC de Operativo cuando no viene explicito (ver BASE_OPERATIVO)."""
    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    filas = []
    for entry in cotizacion.aerolineas:
        aerolinea = entry.get('aerolinea', '')
        for kr in entry.get('kg_rates') or []:
            fsc_val = _num(kr.get('fsc'))
            operativo_val = _num(kr.get('costo_operativo'))
            # Si el FSC no esta explicito (cotizaciones viejas o aerolineas
            # como Avianca que varian por destino y no tienen regla maestra),
            # viene mezclado dentro de Operativo: se separa para el desglose.
            if fsc_val == 0 and operativo_val > BASE_OPERATIVO:
                fsc_val = round(operativo_val - BASE_OPERATIVO, 2)
                operativo_val = BASE_OPERATIVO

            filas.append({
                'aerolinea': aerolinea,
                'kg': kr.get('kg', ''),
                'tarifa_neta': _num(kr.get('tarifa')),
                'fsc': fsc_val,
                'operativo': operativo_val,
                'profit': _num(kr.get('margen')),
                'tarifa_venta': _num(kr.get('tarifa_cliente')),
                'fecha_actualizacion': entry.get('fecha_actualizacion', ''),
            })
    return filas


@cotizaciones_bp.route('/descargar-desglose/<int:id>')
@login_required
def descargar_desglose(id):
    """Genera un Excel mostrando, por aerolinea, como se compone la tarifa de
    venta (neta + FSC + operativo + profit = venta), en el estilo visual
    FreightWise (header morado, filas alternadas)."""
    try:
        cotizacion = Cotizacion.query.get_or_404(id)
        forzar = request.args.get('forzar', '0') == '1'

        errores = _validar_cotizacion(cotizacion)
        if errores and not forzar:
            flash('No se puede imprimir: ' + ' | '.join(errores) + '. Corrige la cotizacion e intenta de nuevo.', 'error')
            return redirect(url_for('cotizaciones.editar_cotizacion', id=id))

        filas = _filas_desglose_de(cotizacion)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        formato = request.args.get('formato', 'excel')
        idioma = request.args.get('idioma', 'es')
        sufijo_idioma = '_EN' if idioma == 'en' else ''

        if formato == 'png':
            png_bytes = generar_desglose_tarifa_png_bytes(cotizacion.ruta, filas, idioma=idioma)
            nombre_archivo = f"FreightWise_Desglose_{cotizacion.ruta}{sufijo_idioma}_{timestamp}.png"
            return send_file(
                png_bytes,
                as_attachment=True,
                download_name=nombre_archivo,
                mimetype='image/png'
            )

        excel_bytes = generar_desglose_tarifa_bytes(cotizacion.ruta, filas, idioma=idioma)
        nombre_archivo = f"FreightWise_Desglose_{cotizacion.ruta}{sufijo_idioma}_{timestamp}.xlsx"

        return send_file(
            excel_bytes,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        flash(f'Error al generar el desglose: {str(e)}', 'error')
        return redirect(url_for('cotizaciones.dashboard'))


@cotizaciones_bp.route('/exportar-netas')
@login_required
def exportar_netas():
    """Genera un Excel con una hoja por destino (formato 'tarifas netas',
    como el archivo de referencia AMS/LHR/etc), sacando los datos de la
    cotizacion mas reciente guardada para cada destino. Destinos cuya
    cotizacion mas reciente tenga errores (aerolinea no reconocida, tramo de
    kg repetido) se excluyen y quedan listados en una hoja de Avisos."""
    try:
        cotizaciones = Cotizacion.query.order_by(Cotizacion.fecha_modificacion.desc()).all()

        mas_reciente_por_destino = {}
        for cot in cotizaciones:
            destino = (cot.destino or '').strip().upper()
            if destino and destino not in mas_reciente_por_destino:
                mas_reciente_por_destino[destino] = cot

        # Si viene ?destinos=AMS,MAD,... solo se exportan esos. Sin el
        # parametro (o vacio) se exportan todos, como antes.
        destinos_param = request.args.get('destinos', '').strip()
        if destinos_param:
            seleccionados = {d.strip().upper() for d in destinos_param.split(',') if d.strip()}
            claves = sorted(d for d in mas_reciente_por_destino if d in seleccionados)
        else:
            claves = sorted(mas_reciente_por_destino.keys())

        destinos_filas = []
        errores_generales = []
        for destino in claves:
            cot = mas_reciente_por_destino[destino]
            errores = _validar_cotizacion(cot)
            if errores:
                errores_generales.append(f"{destino} (cotizacion {cot.id}): " + ' | '.join(errores))
                continue
            destinos_filas.append((destino, _filas_desglose_de(cot)))

        idioma = request.args.get('idioma', 'es')
        con_fechas = request.args.get('con_fechas', '0') == '1'
        excel_bytes = generar_reporte_netas_bytes(destinos_filas, idioma=idioma, errores=errores_generales, con_fechas=con_fechas)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sufijo_idioma = '_EN' if idioma == 'en' else ''
        nombre_archivo = f"FreightWise_Tarifas_Netas{sufijo_idioma}_{timestamp}.xlsx"

        return send_file(
            excel_bytes,
            as_attachment=True,
            download_name=nombre_archivo,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash(f'Error al generar el reporte de tarifas netas: {str(e)}', 'error')
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
    """Devuelve la hora guardada (ultima linea), o '' si esa ultima linea
    en realidad es un dia (LUN/MAR/...) y no una hora real."""
    if not text:
        return ''
    partes = text.split('\n')
    ultima = partes[-1] if partes else ''
    if ultima.strip().upper() in _DIAS_MAPPING:
        return ''
    return ultima


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


# ===================== SOLICITUD DE TARIFAS (MAILS) =====================

# Nombres que en realidad son la misma aerolinea/agente que otro ya
# existente: se consolidan bajo la clave canonica al agregar destinos.
_AEROLINEA_ALIASES = {
    'AVIANCA PAX': 'AVIANCA',
    'DHL FREIGHTER': 'DHL',
    'SINGAPORE': 'SUNRISE',
}

# Saludo especifico por aerolinea (contacto conocido). Si la aerolinea no
# esta aqui, se usa el saludo generico.
_MAIL_SALUDOS = {
    'COPA AIRLINES': 'Estimada Eve,\n\nEspero te encuentres bien.',
    'SOLENT': 'Estimada Ceci,\n\nEspero te encuentres bien.',
}


def _generar_cuerpo_mail(aerolinea, destinos):
    """Cuerpo del correo, con los destinos en bullets (columna). Usa un
    saludo personalizado si la aerolinea tiene contacto conocido en
    _MAIL_SALUDOS, si no el saludo generico."""
    saludo = _MAIL_SALUDOS.get(aerolinea, 'Estimados,\n\nEspero se encuentren bien.')
    if destinos:
        bullets = '\n'.join(f"• {d}" for d in destinos)
    else:
        bullets = "• (agrega un destino)"
    return (
        f"{saludo}\n\n"
        "Solicito su ayuda con tarifas actualizadas para flor:\n\n"
        f"{bullets}\n\n"
        "Quedo atenta.\n\n"
        "Saludos cordiales,"
    )


def _destinos_vivos_por_aerolinea():
    """Destinos detectados en las cotizaciones guardadas, por aerolinea
    (consolidando alias de _AEROLINEA_ALIASES bajo el nombre canonico)."""
    destinos_por_aerolinea = defaultdict(set)
    for cot in Cotizacion.query.all():
        if not cot.destino:
            continue
        for entry in cot.aerolineas:
            aerolinea = (entry.get('aerolinea') or '').strip().upper()
            if aerolinea:
                aerolinea = _AEROLINEA_ALIASES.get(aerolinea, aerolinea)
                destinos_por_aerolinea[aerolinea].add(cot.destino.strip().upper())
    return destinos_por_aerolinea


@cotizaciones_bp.route('/solicitud-tarifas')
@login_required
def solicitud_tarifas_dashboard():
    """Correos editables de solicitud de tarifas por aerolinea. Los destinos
    arrancan sembrados con lo que se identifica en las cotizaciones guardadas
    y de ahi en adelante son editables a mano (agregar/quitar); cualquier
    destino nuevo detectado en una cotizacion se agrega solo a la lista (sin
    borrar lo que se haya quitado a mano)."""
    destinos_vivos = _destinos_vivos_por_aerolinea()

    registros = {r.aerolinea: r for r in AirlineMailRequest.query.all()}
    cambio = False
    for aerolinea, destinos in destinos_vivos.items():
        registro = registros.get(aerolinea)
        if not registro:
            registro = AirlineMailRequest(aerolinea=aerolinea)
            registro.destinos = sorted(destinos)
            db.session.add(registro)
            registros[aerolinea] = registro
            cambio = True
        else:
            actuales = set(registro.destinos)
            nuevos = destinos - actuales
            if nuevos:
                registro.destinos = sorted(actuales | nuevos)
                cambio = True
    if cambio:
        db.session.commit()

    aerolineas = []
    for aerolinea in sorted(registros):
        r = registros[aerolinea]
        asunto = r.asunto or f"Tarifas actualizadas – {aerolinea}"
        cuerpo = r.cuerpo if r.cuerpo_editado and r.cuerpo else _generar_cuerpo_mail(aerolinea, r.destinos)
        aerolineas.append({
            'id': r.id,
            'aerolinea': aerolinea,
            'destinos': r.destinos,
            'asunto': asunto,
            'cuerpo': cuerpo,
            'cuerpo_editado': r.cuerpo_editado,
        })

    return render_template('cotizaciones/solicitud_tarifas.html', aerolineas=aerolineas)


@cotizaciones_bp.route('/api/mail-request', methods=['POST'])
@login_required
def crear_mail_request():
    try:
        data = request.get_json()
        aerolinea = (data.get('aerolinea') or '').strip().upper()
        if not aerolinea:
            return jsonify({'success': False, 'error': 'Falta el nombre de la aerolinea'}), 400
        if AirlineMailRequest.query.filter_by(aerolinea=aerolinea).first():
            return jsonify({'success': False, 'error': 'Esa aerolinea ya esta en Mails'}), 400
        registro = AirlineMailRequest(aerolinea=aerolinea)
        registro.destinos = []
        db.session.add(registro)
        db.session.commit()
        return jsonify({
            'success': True,
            'registro': {
                'id': registro.id,
                'aerolinea': aerolinea,
                'destinos': [],
                'asunto': f"Tarifas actualizadas – {aerolinea}",
                'cuerpo': _generar_cuerpo_mail(aerolinea, []),
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/mail-request/<int:id>', methods=['PUT'])
@login_required
def actualizar_mail_request(id):
    registro = AirlineMailRequest.query.get_or_404(id)
    try:
        data = request.get_json()
        if 'destinos' in data:
            destinos = sorted({(d or '').strip().upper() for d in (data.get('destinos') or []) if (d or '').strip()})
            registro.destinos = destinos
            if not registro.cuerpo_editado:
                registro.cuerpo = None
        if 'asunto' in data:
            registro.asunto = (data.get('asunto') or '').strip() or None
        if 'cuerpo' in data:
            registro.cuerpo = data.get('cuerpo')
            registro.cuerpo_editado = True
        if data.get('restablecer_cuerpo'):
            registro.cuerpo = None
            registro.cuerpo_editado = False
        db.session.commit()
        cuerpo_actual = registro.cuerpo if registro.cuerpo_editado and registro.cuerpo else _generar_cuerpo_mail(registro.aerolinea, registro.destinos)
        return jsonify({'success': True, 'cuerpo': cuerpo_actual, 'destinos': registro.destinos})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@cotizaciones_bp.route('/api/mail-request/<int:id>', methods=['DELETE'])
@login_required
def eliminar_mail_request(id):
    registro = AirlineMailRequest.query.get_or_404(id)
    try:
        db.session.delete(registro)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
