import os
import json
import base64
from datetime import datetime
from flask import render_template, request, jsonify
from lux_portal.tarifas import tarifas_bp
from lux_portal.extensions import db
from lux_portal.auth.decorators import login_required

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

PROMPT = """Eres un extractor de tarifas de flete aereo de flores frescas.
Analiza la imagen o texto y extrae TODOS los datos de tarifas.

Devuelve SOLO JSON valido sin texto adicional ni markdown:
{
  "aerolinea": "nombre de la aerolinea en mayusculas",
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
- "kg" siempre con "+" al inicio: +45, +100, +300, +500, +1000
- "tarifa" es el valor numerico USD por kg (solo el numero, sin simbolos)
- Si hay FSC separado para ese destino ponlo en "fsc"; si no, pon 0.00
- Incluye TODOS los destinos que aparezcan en la imagen
- Si hay muchos destinos (lista de precios), extraelos todos
"""


def _normalizar_kg(kg):
    """Asegura formato +NNN."""
    kg = str(kg).strip()
    if not kg.startswith('+'):
        kg = '+' + kg
    return kg


@tarifas_bp.route('/')
@login_required
def index():
    from lux_portal.cotizaciones.models import Cotizacion
    cots = Cotizacion.query.filter(Cotizacion.estado != 'eliminado').all()
    destinos = sorted({c.destino for c in cots if c.destino})
    aerolineas_set = set()
    for c in cots:
        for a in (c.aerolineas or []):
            nombre = a.get('aerolinea', '').strip()
            if nombre:
                aerolineas_set.add(nombre)
    aerolineas = sorted(aerolineas_set)
    return render_template('tarifas/index.html',
                           destinos=destinos,
                           aerolineas=aerolineas,
                           api_ok=bool(ANTHROPIC_API_KEY))


@tarifas_bp.route('/api/analizar', methods=['POST'])
@login_required
def analizar():
    if not ANTHROPIC_API_KEY:
        return jsonify({'error': 'ANTHROPIC_API_KEY no configurada en Railway.'}), 500

    texto = request.form.get('texto', '').strip()
    imagen_file = request.files.get('imagen')
    hint_aerolinea = request.form.get('aerolinea_hint', '').strip().upper()

    if not texto and not imagen_file:
        return jsonify({'error': 'Sube una imagen o pega el texto de las tarifas.'}), 400

    content = []
    if imagen_file:
        img_bytes = imagen_file.read()
        img_b64 = base64.standard_b64encode(img_bytes).decode('utf-8')
        mime = imagen_file.content_type or 'image/png'
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": img_b64}
        })

    prompt_final = PROMPT
    if hint_aerolinea:
        prompt_final += f"\n\nNota: La aerolinea es {hint_aerolinea}."
    if texto:
        prompt_final += f"\n\nTexto de las tarifas:\n{texto}"
    content.append({"type": "text", "text": prompt_final})

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": content}]
        )
        raw = resp.content[0].text.strip()
        # Limpiar posible markdown
        if '```' in raw:
            parts = raw.split('```')
            for p in parts:
                p = p.strip()
                if p.startswith('json'):
                    p = p[4:].strip()
                try:
                    extracted = json.loads(p)
                    break
                except Exception:
                    continue
            else:
                extracted = json.loads(raw)
        else:
            extracted = json.loads(raw)
    except json.JSONDecodeError as e:
        return jsonify({'error': f'Claude no devolvio JSON valido: {e}', 'raw': raw[:500]}), 500
    except Exception as e:
        return jsonify({'error': f'Error Claude API: {str(e)}'}), 500

    # Cruzar con cotizaciones existentes
    from lux_portal.cotizaciones.models import Cotizacion
    cots = Cotizacion.query.filter(Cotizacion.estado != 'eliminado').all()

    aerolinea_ext = extracted.get('aerolinea', '').upper().strip()
    matches = []

    for dest_data in extracted.get('destinos', []):
        iata = dest_data.get('iata', '').upper().strip()
        nuevas = dest_data.get('kg_rates', [])
        fsc_nuevo = float(dest_data.get('fsc', 0) or 0)

        for cot in cots:
            if not cot.destino or cot.destino.upper() != iata:
                continue

            for aero in (cot.aerolineas or []):
                nombre = aero.get('aerolinea', '').upper()
                # Match: primera palabra coincide
                base_ext = aerolinea_ext.split()[0] if aerolinea_ext else ''
                base_nom = nombre.split()[0] if nombre else ''
                if base_ext and base_ext != base_nom:
                    continue

                actuales = aero.get('kg_rates', [])
                map_actual = {_normalizar_kg(kr.get('kg', '')): float(kr.get('tarifa', 0) or 0)
                              for kr in actuales}
                fsc_actual = float(actuales[0].get('fsc', 0) if actuales else 0)

                diff_rows = []
                for nr in nuevas:
                    kg_key = _normalizar_kg(nr.get('kg', ''))
                    t_nueva = float(nr.get('tarifa', 0) or 0)
                    t_actual = map_actual.get(kg_key, None)
                    diff_rows.append({
                        'kg': kg_key,
                        'tarifa_actual': t_actual,
                        'tarifa_nueva': t_nueva,
                        'cambio': t_actual is None or abs(t_nueva - t_actual) > 0.001
                    })

                matches.append({
                    'cot_id': cot.id,
                    'destino': cot.destino,
                    'aerolinea': aero.get('aerolinea'),
                    'itinerario': aero.get('itinerario', ''),
                    'fsc_actual': fsc_actual,
                    'fsc_nuevo': fsc_nuevo,
                    'fsc_cambia': fsc_nuevo > 0 and abs(fsc_nuevo - fsc_actual) > 0.001,
                    'diff_rows': diff_rows,
                    'nuevas_rates': [{'kg': _normalizar_kg(nr.get('kg', '')),
                                      'tarifa': nr.get('tarifa')} for nr in nuevas],
                    'hay_cambios': any(r['cambio'] for r in diff_rows)
                })

    return jsonify({
        'aerolinea': extracted.get('aerolinea'),
        'destinos_extraidos': [d.get('iata') for d in extracted.get('destinos', [])],
        'matches': matches
    })


@tarifas_bp.route('/api/aplicar', methods=['POST'])
@login_required
def aplicar():
    data = request.json or {}
    aplicaciones = data.get('aplicaciones', [])

    if not aplicaciones:
        return jsonify({'error': 'Nada para aplicar'}), 400

    from lux_portal.cotizaciones.models import Cotizacion
    hoy = datetime.now().strftime('%Y-%m-%d')
    actualizadas = 0
    errores = []

    for ap in aplicaciones:
        cot_id = ap.get('cot_id')
        nombre_aero = ap.get('aerolinea', '').upper()
        nuevas_rates = ap.get('nuevas_rates', [])
        fsc_nuevo = float(ap.get('fsc_nuevo', 0) or 0)

        cot = Cotizacion.query.get(cot_id)
        if not cot:
            errores.append(f'Cotización {cot_id} no encontrada')
            continue

        aerolineas = list(cot.aerolineas or [])
        cambiado = False

        for aero in aerolineas:
            if aero.get('aerolinea', '').upper() != nombre_aero:
                continue

            kg_rates = list(aero.get('kg_rates', []))
            kg_idx = {_normalizar_kg(kr.get('kg', '')): i for i, kr in enumerate(kg_rates)}

            for nr in nuevas_rates:
                kg_key = _normalizar_kg(nr.get('kg', ''))
                t_nueva = float(nr.get('tarifa', 0) or 0)

                if kg_key in kg_idx:
                    kr = dict(kg_rates[kg_idx[kg_key]])
                    kr['tarifa'] = f"{t_nueva:.2f}"
                    m = float(kr.get('margen', 0) or 0)
                    co = float(kr.get('costo_operativo', 0.09) or 0.09)
                    fsc_usar = fsc_nuevo if fsc_nuevo > 0 else float(kr.get('fsc', 0) or 0)
                    kr['fsc'] = f"{fsc_usar:.2f}"
                    kr['tarifa_cliente'] = f"{t_nueva + m + co + fsc_usar:.2f}"
                    kg_rates[kg_idx[kg_key]] = kr
                    cambiado = True

            aero['kg_rates'] = kg_rates
            aero['fecha_actualizacion'] = hoy

        if cambiado:
            cot.aerolineas = aerolineas
            actualizadas += 1

    if actualizadas > 0:
        db.session.commit()

    return jsonify({'actualizadas': actualizadas, 'errores': errores})
