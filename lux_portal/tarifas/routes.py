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

_SUFIJOS = re.compile(
    r'\s+(FREIGHTER|PAX|CARGO|AIRLINES|AIRWAYS|AIR CARGO|PASSENGER|FREIGHT)\s*$',
    re.IGNORECASE
)

PROMPT = """Eres un extractor de tarifas de flete aereo de flores frescas.
Analiza la imagen o texto y extrae TODOS los datos de tarifas.

Devuelve SOLO JSON valido sin texto adicional ni markdown:
{
  "aerolinea": "nombre base de la aerolinea en MAYUSCULAS (sin FREIGHTER, PAX, CARGO, AIRLINES)",
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
- "aerolinea": solo nombre base — AVIANCA, DELTA, LUFTHANSA, COPA, TURKISH — sin FREIGHTER, PAX, CARGO
- "kg" siempre con "+" al inicio: +45, +100, +300, +500, +1000
- "tarifa" es el valor numerico USD por kg (solo el numero, sin simbolos)
- "fsc": si viene separado en el documento ponlo; si no, pon 0.00
- Incluye TODOS los destinos que aparezcan
"""


def _normalizar_kg(kg):
    kg = str(kg).strip()
    if not kg.startswith('+'):
        kg = '+' + kg
    return kg


def _normalizar_aerolinea(nombre):
    return _SUFIJOS.sub('', str(nombre).upper().strip()).strip()


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


@tarifas_bp.route('/api/analizar', methods=['POST'])
@login_required
def analizar():
    """Extrae tarifas con Claude y devuelve tabla de revisión. No toca la DB."""
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

    aerolinea_ext = hint_aerolinea or _normalizar_aerolinea(extracted.get('aerolinea', ''))

    # Filas para la tabla de revisión
    filas = []      # matches existentes
    sin_match = []  # aerolíneas/destinos nuevos

    for dest_data in extracted.get('destinos', []):
        iata = dest_data.get('iata', '').upper().strip()
        nuevas = dest_data.get('kg_rates', [])
        fsc_extraido = float(dest_data.get('fsc', 0) or 0)
        found_match = False

        for cot in cots:
            if not cot.destino or cot.destino.upper() != iata:
                continue

            for aero in (cot.aerolineas or []):
                nombre_norm = _normalizar_aerolinea(aero.get('aerolinea', ''))
                if aerolinea_ext != nombre_norm:
                    continue

                actuales = aero.get('kg_rates', [])
                map_actual = {_normalizar_kg(kr.get('kg', '')): kr for kr in actuales}

                for nr in nuevas:
                    kg_key = _normalizar_kg(nr.get('kg', ''))
                    t_nueva = float(nr.get('tarifa', 0) or 0)
                    kr_actual = map_actual.get(kg_key)
                    t_actual = float(kr_actual.get('tarifa', 0) or 0) if kr_actual else None
                    fsc_actual = float(kr_actual.get('fsc', 0) or 0) if kr_actual else 0.0

                    filas.append({
                        'cot_id': cot.id,
                        'aerolinea': aerolinea_ext,
                        'destino': iata,
                        'kg': kg_key,
                        'tarifa_actual': t_actual,
                        'tarifa_nueva': t_nueva,
                        'fsc_actual': fsc_actual,
                        'fsc_extraido': fsc_extraido,
                        'cambio': t_actual is None or abs(t_nueva - t_actual) > 0.001,
                        'es_nueva_kg': t_actual is None,
                    })
                found_match = True

        if not found_match:
            cots_iata = [
                {'id': c.id, 'label': f"#{c.id} — {c.destino}{(' / ' + c.customer) if c.customer else ''}"}
                for c in cots if c.destino and c.destino.upper() == iata
            ]
            sin_match.append({
                'iata': iata,
                'ciudad': dest_data.get('ciudad', ''),
                'aerolinea': aerolinea_ext,
                'nuevas_rates': [{'kg': _normalizar_kg(nr.get('kg', '')), 'tarifa': nr.get('tarifa')}
                                 for nr in nuevas],
                'fsc_nuevo': fsc_extraido,
                'tiene_cot_propia': len(cots_iata) > 0,
                'cotizaciones_disponibles': cots_iata,
            })

    return jsonify({
        'aerolinea': aerolinea_ext,
        'destinos_extraidos': list({f['destino'] for f in filas} | {s['iata'] for s in sin_match}),
        'filas': filas,
        'sin_match': sin_match,
    })


@tarifas_bp.route('/api/aplicar', methods=['POST'])
@login_required
def aplicar():
    """Aplica los cambios confirmados. Solo actualiza tarifa neta (FSC no se toca aquí)."""
    data = request.json or {}
    filas = data.get('filas', [])       # matches a actualizar
    nuevas = data.get('nuevas', [])     # sin_match a agregar/crear
    hoy = datetime.now().strftime('%Y-%m-%d')

    from lux_portal.cotizaciones.models import Cotizacion
    actualizadas = 0
    errores = []

    # --- Agrupar filas por cot_id ---
    por_cot = {}
    for f in filas:
        cid = f.get('cot_id')
        por_cot.setdefault(cid, []).append(f)

    for cot_id, rows in por_cot.items():
        cot = Cotizacion.query.get(cot_id)
        if not cot:
            errores.append(f'Cotización {cot_id} no encontrada')
            continue

        aerolinea_nombre = rows[0]['aerolinea']
        aerolineas = list(cot.aerolineas or [])
        changed = False

        for aero in aerolineas:
            if _normalizar_aerolinea(aero.get('aerolinea', '')) != aerolinea_nombre:
                continue
            kg_rates = list(aero.get('kg_rates', []))
            kg_idx = {_normalizar_kg(kr.get('kg', '')): i for i, kr in enumerate(kg_rates)}

            for row in rows:
                kg_key = row['kg']
                t_nueva = float(row['tarifa_nueva'])
                if kg_key in kg_idx:
                    kr = dict(kg_rates[kg_idx[kg_key]])
                    margen = float(kr.get('margen', 0) or 0)
                    co = float(kr.get('costo_operativo', 0.09) or 0.09)
                    fsc = float(kr.get('fsc', 0) or 0)  # FSC no cambia aquí
                    kr['tarifa'] = f"{t_nueva:.2f}"
                    kr['tarifa_cliente'] = f"{t_nueva + margen + co + fsc:.2f}"
                    kg_rates[kg_idx[kg_key]] = kr
                    changed = True

            aero['kg_rates'] = kg_rates
            aero['fecha_actualizacion'] = hoy

        if changed:
            cot.aerolineas = aerolineas
            actualizadas += 1

    # --- Nuevas aerolíneas / cotizaciones ---
    for item in nuevas:
        iata = item.get('iata', '').upper()
        nombre_aero = item.get('aerolinea', '')
        rates = item.get('nuevas_rates', [])
        fsc_usar = float(item.get('fsc_nuevo', 0) or 0)
        cot_id = item.get('cot_id')  # None = crear cotización nueva

        def _kr(nr):
            t = float(nr.get('tarifa', 0) or 0)
            return {'kg': _normalizar_kg(nr.get('kg', '')), 'tarifa': f"{t:.2f}",
                    'margen': '0.00', 'costo_operativo': '0.09',
                    'fsc': f"{fsc_usar:.2f}", 'tarifa_cliente': f"{t + 0.09 + fsc_usar:.2f}"}

        aero_obj = {
            'aerolinea': nombre_aero, 'vuelo': '', 'itinerario': '',
            'tiempo_transito': '', 'granjas_entrega': '', 'salida': '', 'llegada': '',
            'kg_rates': [_kr(r) for r in rates],
            'rate_increases': [], 'cargos_adicionales': [],
            'notas': '', 'es_continuacion': False, 'fecha_actualizacion': hoy
        }

        if cot_id:
            cot = Cotizacion.query.get(cot_id)
            if not cot:
                errores.append(f'Cotización {cot_id} no encontrada')
                continue
            aerolineas = list(cot.aerolineas or [])
            aerolineas.append(aero_obj)
            cot.aerolineas = aerolineas
        else:
            nueva_cot = Cotizacion(
                origen='UIO', destino=iata,
                valid_from=datetime.now().strftime('%m/%d/%Y'),
                contacto_nombre='Daniela Echeverria',
                contacto_email='daniela.echeverria@freight-wise.com',
                mercancia='FRESH CUT FLOWERS',
                customer='', attn='', estado='borrador'
            )
            nueva_cot.aerolineas = [aero_obj]
            nueva_cot.cargos_freightwise = [
                {"concepto": "Due Agent", "monto": "0"},
                {"concepto": "Certificado", "monto": "0"},
                {"concepto": "Fitosanitario", "monto": "0"},
            ]
            nueva_cot.notas_freightwise = ''
            db.session.add(nueva_cot)

        actualizadas += 1

    if actualizadas > 0:
        db.session.commit()

    return jsonify({'actualizadas': actualizadas, 'errores': errores})
