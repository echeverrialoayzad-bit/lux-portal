#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rutas de Documentacion y Verificacion
"""

import os
import io
import json
import base64
from datetime import datetime
from flask import render_template, request, jsonify, send_file, flash, redirect, url_for
from lux_portal.documentacion import documentacion_bp
from lux_portal.documentacion.models import (
    DocCliente, DocArchivo, TIPOS_DOCUMENTO, TIPOS_DOCUMENTO_KEYS, TIPOS_DOCUMENTO_NOMBRES,
    TIPO_EXTRA,
)
from lux_portal.auth.decorators import login_required
from lux_portal.extensions import db

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

EXTENSIONES_PERMITIDAS = {'.pdf', '.jpg', '.jpeg', '.png'}

VERIFICACION_PROMPT = """Eres un asistente que ayuda a un equipo de operaciones de carga aerea a hacer una
revision preliminar de dos documentos de un mismo cliente: (1) un "Customer Associate Format" firmado
por el representante legal, y (2) la cedula/identificacion de esa misma persona.

Compara ambos documentos y responde SOLO JSON valido, sin texto adicional ni markdown, con esta forma:
{
  "nombre_en_cedula": "nombre completo tal como aparece en la cedula, o null si no es legible",
  "nombre_en_formato": "nombre del representante legal escrito/firmado en el Customer Associate Format, o null si no es legible",
  "nombres_coinciden": true/false/null,
  "firma_presente": true/false,
  "observaciones": "explica en 1-3 frases que comparaste y por que llegaste a esa conclusion, incluyendo
   cualquier duda o limitacion (ej. firma poco legible, documento de baja calidad, nombres parecidos pero no identicos)",
  "confianza": "alta" | "media" | "baja"
}

Importante: esto es una revision asistida, NO una verificacion forense de firmas. Se honesto sobre la
incertidumbre: si algo no es claramente legible o no puedes comparar la firma con certeza, dilo en
observaciones y baja la confianza en vez de adivinar."""


def _llamar_claude(content):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}]
    )
    raw = resp.content[0].text.strip()
    if '```' in raw:
        for p in raw.split('```'):
            p = p.strip()
            if p.startswith('json'):
                p = p[4:].strip()
            try:
                return json.loads(p)
            except Exception:
                continue
    return json.loads(raw)


def _content_block(archivo):
    """Arma el bloque de contenido (imagen o documento PDF) para mandar a Claude."""
    b64 = base64.standard_b64encode(archivo.contenido).decode('utf-8')
    mimetype = archivo.mimetype or 'application/octet-stream'
    tipo_bloque = 'document' if mimetype == 'application/pdf' else 'image'
    return {"type": tipo_bloque, "source": {"type": "base64", "media_type": mimetype, "data": b64}}


@documentacion_bp.route('/')
@login_required
def dashboard():
    """Lista de clientes (carpetas)."""
    clientes = DocCliente.query.order_by(DocCliente.nombre).all()
    return render_template(
        'documentacion/index.html',
        clientes=clientes,
        tipos_documento=TIPOS_DOCUMENTO,
    )


@documentacion_bp.route('/api/cliente', methods=['POST'])
@login_required
def crear_cliente():
    try:
        data = request.get_json()
        nombre = (data.get('nombre') or '').strip()
        if not nombre:
            return jsonify({'success': False, 'error': 'Falta el nombre del cliente'}), 400
        if DocCliente.query.filter(db.func.lower(DocCliente.nombre) == nombre.lower()).first():
            return jsonify({'success': False, 'error': 'Ya existe un cliente con ese nombre'}), 400
        cliente = DocCliente(nombre=nombre)
        db.session.add(cliente)
        db.session.commit()
        return jsonify({'success': True, 'cliente': cliente.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@documentacion_bp.route('/api/cliente/<int:id>', methods=['DELETE'])
@login_required
def eliminar_cliente(id):
    try:
        cliente = DocCliente.query.get_or_404(id)
        db.session.delete(cliente)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@documentacion_bp.route('/cliente/<int:id>')
@login_required
def ver_cliente(id):
    """Carpeta del cliente: los 5 documentos esenciales + los adicionales."""
    cliente = DocCliente.query.get_or_404(id)
    archivos = cliente.archivos_por_tipo()
    archivos_extra = cliente.archivos_extra()
    firma_resultado = None
    if cliente.firma_verificacion_detalle:
        try:
            firma_resultado = json.loads(cliente.firma_verificacion_detalle)
        except (TypeError, ValueError):
            firma_resultado = None
    return render_template(
        'documentacion/cliente.html',
        cliente=cliente,
        tipos_documento=TIPOS_DOCUMENTO,
        archivos=archivos,
        archivos_extra=archivos_extra,
        firma_resultado=firma_resultado,
    )


@documentacion_bp.route('/api/cliente/<int:id>/archivo', methods=['POST'])
@login_required
def subir_archivo(id):
    try:
        cliente = DocCliente.query.get_or_404(id)
        tipo = request.form.get('tipo', '')
        titulo_extra = (request.form.get('titulo_extra') or '').strip()

        if tipo == TIPO_EXTRA:
            if not titulo_extra:
                return jsonify({'success': False, 'error': 'Falta el titulo del documento adicional'}), 400
        elif tipo not in TIPOS_DOCUMENTO_KEYS:
            return jsonify({'success': False, 'error': 'Tipo de documento invalido'}), 400

        archivo_file = request.files.get('archivo')
        if not archivo_file or not archivo_file.filename:
            return jsonify({'success': False, 'error': 'No se recibio ningun archivo'}), 400

        ext = os.path.splitext(archivo_file.filename)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return jsonify({'success': False, 'error': 'Solo se aceptan PDF, JPG o PNG'}), 400

        contenido = archivo_file.read()
        if not contenido:
            return jsonify({'success': False, 'error': 'El archivo esta vacio'}), 400

        mimetype = archivo_file.content_type or ('application/pdf' if ext == '.pdf' else 'image/' + ext.strip('.'))

        nuevo = DocArchivo(
            cliente_id=cliente.id,
            tipo=tipo,
            titulo_extra=titulo_extra if tipo == TIPO_EXTRA else None,
            nombre_archivo=archivo_file.filename,
            mimetype=mimetype,
            contenido=contenido,
        )
        db.session.add(nuevo)

        # Un nuevo archivo invalida la verificacion de firma previa si el
        # tipo reemplazado es uno de los dos que se comparan.
        if tipo in ('customer_associate_format', 'cedula_representante'):
            cliente.firma_verificada = None
            cliente.firma_verificacion_detalle = None
            cliente.firma_verificacion_fecha = None

        db.session.commit()
        return jsonify({'success': True, 'archivo': nuevo.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@documentacion_bp.route('/api/archivo/<int:id>')
@login_required
def ver_archivo(id):
    """Muestra/descarga el archivo (inline para que se pueda previsualizar en el navegador)."""
    archivo = DocArchivo.query.get_or_404(id)
    return send_file(
        io.BytesIO(archivo.contenido),
        mimetype=archivo.mimetype or 'application/octet-stream',
        as_attachment=False,
        download_name=archivo.nombre_archivo or f'documento_{archivo.id}',
    )


@documentacion_bp.route('/api/archivo/<int:id>', methods=['DELETE'])
@login_required
def eliminar_archivo(id):
    try:
        archivo = DocArchivo.query.get_or_404(id)
        cliente = archivo.cliente
        if archivo.tipo in ('customer_associate_format', 'cedula_representante'):
            cliente.firma_verificada = None
            cliente.firma_verificacion_detalle = None
            cliente.firma_verificacion_fecha = None
        db.session.delete(archivo)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@documentacion_bp.route('/api/cliente/<int:id>/verificar-firma', methods=['POST'])
@login_required
def verificar_firma(id):
    """Compara el Customer Associate Format con la cedula usando Claude (revision
    asistida, no forense)."""
    if not ANTHROPIC_API_KEY:
        return jsonify({'success': False, 'error': 'ANTHROPIC_API_KEY no configurada en Railway.'}), 500

    cliente = DocCliente.query.get_or_404(id)
    presentes = cliente.archivos_por_tipo()
    formato = presentes.get('customer_associate_format')
    cedula = presentes.get('cedula_representante')

    if not formato or not cedula:
        return jsonify({
            'success': False,
            'error': 'Faltan documentos: se necesita el Customer Associate Format y la Cedula del Representante Legal.'
        }), 400

    content = [
        {"type": "text", "text": "Documento 1 (Customer Associate Format):"},
        _content_block(formato),
        {"type": "text", "text": "Documento 2 (Cedula del Representante Legal):"},
        _content_block(cedula),
        {"type": "text", "text": VERIFICACION_PROMPT},
    ]

    try:
        resultado = _llamar_claude(content)
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Claude no devolvio JSON valido: {e}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error Claude API: {str(e)}'}), 500

    try:
        cliente.firma_verificada = resultado.get('nombres_coinciden')
        cliente.firma_verificacion_detalle = json.dumps(resultado, ensure_ascii=False)
        cliente.firma_verificacion_fecha = datetime.utcnow()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'resultado': resultado})
