import os
import re
import json
import base64
from datetime import datetime
from flask import render_template, request, jsonify
from lux_portal.tarifas import tarifas_bp
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Sufijos a eliminar del nombre de aerolínea para normalizar
_SUFIJOS = re.compile(
    r'\s+(FREIGHTER|PAX|CARGO|AIRLINES|AIRWAYS|AIR CARGO|PASSENGER|FREIGHT)\s*$',
    re.IGNORECASE
)

PROMPT = """Eres un extractor de tarifas de flete aereo de flores frescas.
Analiza la imagen o texto y extrae TODOS los datos de tarifas.

Devuelve SOLO JSON valido sin texto adicional ni markdown:
{
  "aerolinea": "nombre base de la aerolinea en MAYUSCULAS (sin palabras como FREIGHTER, PAX, CARGO, AIRLINES)",
  "destinos": [
    {
      "iata": "codigo IATA destino 3 letras mayusculas",
      "ciudad": "nombre ciudad",
      "kg_rates": [
        {"kg": "+100", "tarifa": 3.50},
        {"kg": "+300", "tarifa": 3.20}
      ],
      "fsc": 0.00
    }
  ]
}

Reglas:
- "aerolinea": solo el nombre base, ejemplo: AVIANCA, DELTA, LUFTHANSA, COPA, TURKISH — NO incluir FREIGHTER, PAX, CARGO, AIRLINES
- "kg" siempre con "+" al inicio: +45, +100, +300, +500, +1000
- "tarifa" es el valor numerico USD por kg (solo el numero, sin simbolos)
- Si hay FSC separado para ese destino ponlo en "fsc"; si no, pon 0.00
- Incluye TODOS los destinos que aparezcan en la imagen
"""


def _normalizar_kg(kg):
    kg = str(kg).strip()
    if not kg.startswith('+'):
        kg = '+' + kg
    return kg


def _normalizar_aerolinea(nombre):
    """Elimina sufijos como FREIGHTER, PAX, CARGO del nombre."""
    return _SUFIJOS.sub('', str(nombre).upper().strip()).strip()


def _build_kg_rate(nr, margen=0.0, costo_op=0.09, fsc=0.0):
    t = float(nr.get('tarifa', 0) or 0)
    return {
        'kg': _normalizar_kg(nr.get('kg', '')),
        'tarifa': f"{t:.2f}",
        'margen': f"{margen:.2f}",
        'costo_operativo': f"{costo_op:.2f}",
        'fsc': f"{fsc:.2f}",
        'tarifa_cliente': f"{t + margen + costo_op + fsc:.2f}"
    }


def _llamar_claude(content):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
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


@tarifas_bp.route('/')
@login_required
def index():
    from lux_portal.cotizaciones.models import Cotizacion
    cots = Cotizacion.query.filter(Cotizacion.estado != 'eliminado').all()
    destinos = sorted({c.destino for c in cots if c.destino})
    # Nombres limpios y deduplicados para el dropdown
    aerolineas_set = set()
    for c in cots:
        for a in (c.aerolineas or []):
            nombre = _normalizar_aerolinea(a.get('aerolinea', ''))
            if nombre:
                aerolineas_set.add(nombre)
    aerolineas = sorted(aerolineas_set)
    return render_template('tarifas/index.html',
                           destinos=destinos,
                           aerolineas=aerolineas,
                           api_ok=bool(ANTHROPIC_API_KEY))


@tarifas_bp.route('/api/actualizar', methods=['POST'])
@login_required
def actualizar():
    """Extrae tarifas con Claude y las aplica automáticamente. Sin aprobación."""
    if not ANTHROPIC_API_KEY:
        return jsonify({'error': 'ANTHROPIC_API_KEY no configurada en Railway.'}), 500

    texto = request.form.get('texto', '').strip()
    imagen_file = request.files.get('imagen')
    hint_aerolinea = _normalizar_aerolinea(request.form.get('aerolinea_hint', ''))

    if not texto and not imagen_file:
        return jsonify({'error': 'Sube una imagen o pega el texto de las tarifas.'}), 400

    content = []
    if imagen_file:
        img_bytes = imagen_file.read()
        img_b64 = base64.standard_b64encode(img_bytes).decode('utf-8')
        mime = imagen_file.content_type or 'image/png'
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_b64}})

    prompt_final = PROMPT
    if hint_aerolinea:
        prompt_final += f"\n\nNota: La aerolinea es {hint_aerolinea}."
    if texto:
        prompt_final += f"\n\nTexto de las tarifas:\n{texto}"
    content.append({"type": "text", "text": prompt_final})

    try:
        extracted = _llamar_claude(content)
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Claude no devolvió JSON válido: {e}'}), 500
    except Exception as e:
        return jsonify({'error': f'Error Claude API: {str(e)}'}), 500

    from lux_portal.cotizaciones.models import Cotizacion
    cots = Cotizacion.query.filter(Cotizacion.estado != 'eliminado').all()
    hoy = datetime.now().strftime('%Y-%m-%d')

    # Nombre normalizado de la aerolínea
    aerolinea_ext = hint_aerolinea or _normalizar_aerolinea(extracted.get('aerolinea', ''))

    actualizadas = []   # lo que se aplicó automáticamente
    pendientes = []     # casos con múltiples cotizaciones para el mismo IATA → user decide

    for dest_data in extracted.get('destinos', []):
        iata = dest_data.get('iata', '').upper().strip()
        nuevas = dest_data.get('kg_rates', [])
        fsc_nuevo = float(dest_data.get('fsc', 0) or 0)
        found_match = False

        for cot in cots:
            if not cot.destino or cot.destino.upper() != iata:
                continue

            aerolineas = list(cot.aerolineas or [])
            changed = False

            for aero in aerolineas:
                nombre_norm = _normalizar_aerolinea(aero.get('aerolinea', ''))
                if aerolinea_ext != nombre_norm:
                    continue

                # Actualizar tarifas existentes
                kg_rates = list(aero.get('kg_rates', []))
                kg_idx = {_normalizar_kg(kr.get('kg', '')): i for i, kr in enumerate(kg_rates)}

                for nr in nuevas:
                    kg_key = _normalizar_kg(nr.get('kg', ''))
                    t_nueva = float(nr.get('tarifa', 0) or 0)
                    if kg_key in kg_idx:
                        kr = dict(kg_rates[kg_idx[kg_key]])
                        margen = float(kr.get('margen', 0) or 0)
                        co = float(kr.get('costo_operativo', 0.09) or 0.09)
                        fsc_usar = fsc_nuevo if fsc_nuevo > 0 else float(kr.get('fsc', 0) or 0)
                        kr['tarifa'] = f"{t_nueva:.2f}"
                        kr['fsc'] = f"{fsc_usar:.2f}"
                        kr['tarifa_cliente'] = f"{t_nueva + margen + co + fsc_usar:.2f}"
                        kg_rates[kg_idx[kg_key]] = kr
                        changed = True

                aero['kg_rates'] = kg_rates
                aero['fecha_actualizacion'] = hoy
                found_match = True

            if changed:
                cot.aerolineas = aerolineas
                actualizadas.append({
                    'aerolinea': aerolinea_ext, 'destino': iata,
                    'cot_id': cot.id, 'nueva': False
                })

        if not found_match:
            cots_iata = [c for c in cots if c.destino and c.destino.upper() == iata]

            if len(cots_iata) == 0:
                # No existe cotización para este destino → crear nueva
                fsc_usar = fsc_nuevo if fsc_nuevo > 0 else 0.0
                nueva_cot = Cotizacion(
                    origen='UIO', destino=iata,
                    valid_from=datetime.now().strftime('%m/%d/%Y'),
                    contacto_nombre='Daniela Echeverria',
                    contacto_email='daniela.echeverria@freight-wise.com',
                    mercancia='FRESH CUT FLOWERS',
                    customer='', attn='', estado='borrador'
                )
                nueva_cot.aerolineas = [{
                    'aerolinea': aerolinea_ext, 'vuelo': '', 'itinerario': '',
                    'tiempo_transito': '', 'granjas_entrega': '', 'salida': '', 'llegada': '',
                    'kg_rates': [_build_kg_rate(nr, fsc=fsc_usar) for nr in nuevas],
                    'rate_increases': [], 'cargos_adicionales': [],
                    'notas': '', 'es_continuacion': False, 'fecha_actualizacion': hoy
                }]
                nueva_cot.cargos_freightwise = [
                    {"concepto": "Due Agent", "monto": "0"},
                    {"concepto": "Certificado", "monto": "0"},
                    {"concepto": "Fitosanitario", "monto": "0"},
                ]
                nueva_cot.notas_freightwise = ''
                db.session.add(nueva_cot)
                actualizadas.append({
                    'aerolinea': aerolinea_ext, 'destino': iata,
                    'cot_id': None, 'nueva': True
                })

            elif len(cots_iata) == 1:
                # Una sola cotización para este IATA → agregar aerolínea directamente
                cot = cots_iata[0]
                fsc_usar = fsc_nuevo if fsc_nuevo > 0 else 0.0
                aerolineas = list(cot.aerolineas or [])
                aerolineas.append({
                    'aerolinea': aerolinea_ext, 'vuelo': '', 'itinerario': '',
                    'tiempo_transito': '', 'granjas_entrega': '', 'salida': '', 'llegada': '',
                    'kg_rates': [_build_kg_rate(nr, fsc=fsc_usar) for nr in nuevas],
                    'rate_increases': [], 'cargos_adicionales': [],
                    'notas': '', 'es_continuacion': False, 'fecha_actualizacion': hoy
                })
                cot.aerolineas = aerolineas
                actualizadas.append({
                    'aerolinea': aerolinea_ext, 'destino': iata,
                    'cot_id': cot.id, 'nueva': False
                })

            else:
                # Múltiples cotizaciones para este IATA → el usuario elige
                pendientes.append({
                    'iata': iata,
                    'ciudad': dest_data.get('ciudad', ''),
                    'aerolinea': aerolinea_ext,
                    'nuevas_rates': [{'kg': _normalizar_kg(nr.get('kg', '')), 'tarifa': nr.get('tarifa')}
                                     for nr in nuevas],
                    'fsc_nuevo': fsc_nuevo,
                    'cotizaciones_disponibles': [
                        {'id': c.id, 'label': f"#{c.id} — {c.destino}{(' / ' + c.customer) if c.customer else ''}"}
                        for c in cots_iata
                    ]
                })

    db.session.commit()

    return jsonify({
        'aerolinea': aerolinea_ext,
        'actualizadas': actualizadas,
        'pendientes': pendientes
    })


@tarifas_bp.route('/api/aplicar-pendientes', methods=['POST'])
@login_required
def aplicar_pendientes():
    """Aplica los pendientes donde el usuario seleccionó la cotización."""
    data = request.json or {}
    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'Nada para aplicar'}), 400

    from lux_portal.cotizaciones.models import Cotizacion
    hoy = datetime.now().strftime('%Y-%m-%d')
    actualizadas = 0
    errores = []

    for item in items:
        cot_id = item.get('cot_id')
        nombre_aero = item.get('aerolinea', '')
        nuevas_rates = item.get('nuevas_rates', [])
        fsc_nuevo = float(item.get('fsc_nuevo', 0) or 0)

        cot = Cotizacion.query.get(cot_id)
        if not cot:
            errores.append(f'Cotización {cot_id} no encontrada')
            continue

        fsc_usar = fsc_nuevo if fsc_nuevo > 0 else 0.0
        aerolineas = list(cot.aerolineas or [])
        aerolineas.append({
            'aerolinea': nombre_aero, 'vuelo': '', 'itinerario': '',
            'tiempo_transito': '', 'granjas_entrega': '', 'salida': '', 'llegada': '',
            'kg_rates': [_build_kg_rate(nr, fsc=fsc_usar) for nr in nuevas_rates],
            'rate_increases': [], 'cargos_adicionales': [],
            'notas': '', 'es_continuacion': False, 'fecha_actualizacion': hoy
        })
        cot.aerolineas = aerolineas
        actualizadas += 1

    if actualizadas > 0:
        db.session.commit()

    return jsonify({'actualizadas': actualizadas, 'errores': errores})
