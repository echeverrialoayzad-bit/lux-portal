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
      "iata": "codigo IATA del AEROPUERTO DESTINO (3 letras)",
      "ciudad": "nombre de la ciudad destino",
      "kg_rates": [
        {"kg": "+100", "tarifa": 3.50},
        {"kg": "+300", "tarifa": 3.20}
      ],
      "fsc": 0.00
    }
  ]
}

Reglas IMPORTANTES:
- "aerolinea": solo nombre base — AVIANCA, DELTA, LUFTHANSA, COPA, TURKISH, IBERIA — sin FREIGHTER ni PAX
- "iata" es el CODIGO DE AEROPUERTO DESTINO (NO el codigo de aerolinea).
  Ejemplos correctos: MAD=Madrid, LHR=Londres, AMS=Amsterdam, MIA=Miami, VLC=Valencia,
  BER=Berlin, FRA=Frankfurt, CDG=Paris, BCN=Barcelona, FCO=Roma, NRT=Tokio, DXB=Dubai
- "kg" siempre con "+" al inicio: +45, +100, +300, +500, +1000
- "tarifa" es el valor numerico USD por kg (sin simbolos)
- "fsc": si aparece FSC/Fuel Surcharge ponlo en numerico; si no aparece pon 0.00
- Incluye TODOS los destinos que aparezcan en la imagen/texto
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
    # Todas las cotizaciones para el dropdown de sin_match
    todas_cots = [
        {'id': c.id, 'label': f"#{c.id} — {c.destino}{(' / ' + c.customer) if c.customer else ''}"}
        for c in cots
    ]
    return render_template('tarifas/index.html',
                           destinos=destinos,
                           aerolineas=aerolineas,
                           todas_cots=todas_cots,
                           api_ok=bool(ANTHROPIC_API_KEY))


@tarifas_bp.route('/api/analizar', methods=['POST'])
@login_required
def analizar():
    """Extrae tarifas con Claude y devuelve tabla de revisión agrupada. No toca la DB."""
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
        content.append({"type": "image",
                         "source": {"type": "base64", "media_type": mime, "data": img_b64}})

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

    # grupos: una entrada por (cot_id, aerolinea, destino)
    grupos = []
    sin_match = []

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
                # FSC actual: tomar del primer KG rate
                fsc_actual = float(actuales[0].get('fsc', 0) or 0) if actuales else 0.0

                kgs = []
                for nr in nuevas:
                    kg_key = _normalizar_kg(nr.get('kg', ''))
                    t_nueva = float(nr.get('tarifa', 0) or 0)
                    kr_act = map_actual.get(kg_key)
                    t_actual = float(kr_act.get('tarifa', 0) or 0) if kr_act else None
                    kgs.append({
                        'kg': kg_key,
                        'tarifa_actual': t_actual,
                        'tarifa_nueva': t_nueva,
                        'cambio': t_actual is None or abs(t_nueva - t_actual) > 0.001,
                    })

                fsc_cambia = fsc_extraido > 0 and abs(fsc_extraido - fsc_actual) > 0.001

                grupos.append({
                    'cot_id': cot.id,
                    'aerolinea': aerolinea_ext,
                    'aerolinea_original': aero.get('aerolinea'),
                    'destino': iata,
                    'kgs': kgs,
                    'fsc_actual': fsc_actual,
                    'fsc_extraido': fsc_extraido,
                    'fsc_cambia': fsc_cambia,
                    'hay_cambios': any(k['cambio'] for k in kgs),
                })
                found_match = True

        if not found_match:
            kgs_nuevas = [{'kg': _normalizar_kg(nr.get('kg', '')),
                           'tarifa_nueva': float(nr.get('tarifa', 0) or 0)}
                          for nr in nuevas]
            sin_match.append({
                'iata': iata,
                'iata_original': iata,
                'ciudad': dest_data.get('ciudad', ''),
                'aerolinea': aerolinea_ext,
                'kgs': kgs_nuevas,
                'fsc_extraido': fsc_extraido,
            })

    # Todos los KG tiers únicos (para columnas)
    all_kgs = []
    seen = set()
    for g in grupos:
        for k in g['kgs']:
            if k['kg'] not in seen:
                all_kgs.append(k['kg'])
                seen.add(k['kg'])
    for s in sin_match:
        for k in s['kgs']:
            if k['kg'] not in seen:
                all_kgs.append(k['kg'])
                seen.add(k['kg'])
    all_kgs.sort(key=lambda x: int(x.replace('+', '') or 0))

    return jsonify({
        'aerolinea': aerolinea_ext,
        'destinos_extraidos': list({g['destino'] for g in grupos} | {s['iata'] for s in sin_match}),
        'grupos': grupos,
        'sin_match': sin_match,
        'all_kgs': all_kgs,
    })


@tarifas_bp.route('/api/aplicar', methods=['POST'])
@login_required
def aplicar():
    """Aplica los cambios. Solo actualiza tarifa neta (FSC no se toca aquí)."""
    data = request.json or {}
    grupos = data.get('grupos', [])
    nuevas = data.get('nuevas', [])
    hoy = datetime.now().strftime('%Y-%m-%d')

    from lux_portal.cotizaciones.models import Cotizacion
    actualizadas = 0
    errores = []

    # --- Matches existentes ---
    for g in grupos:
        cot_id = g.get('cot_id')
        aerolinea_nombre = g.get('aerolinea', '')
        kgs = g.get('kgs', [])

        cot = Cotizacion.query.get(cot_id)
        if not cot:
            errores.append(f'Cotización {cot_id} no encontrada')
            continue

        aerolineas = list(cot.aerolineas or [])
        changed = False

        for aero in aerolineas:
            if _normalizar_aerolinea(aero.get('aerolinea', '')) != aerolinea_nombre:
                continue

            kg_rates = list(aero.get('kg_rates', []))
            kg_idx = {_normalizar_kg(kr.get('kg', '')): i for i, kr in enumerate(kg_rates)}

            for k in kgs:
                kg_key = k['kg']
                t_nueva = float(k.get('tarifa_nueva', 0))
                if kg_key in kg_idx:
                    kr = dict(kg_rates[kg_idx[kg_key]])
                    margen = float(kr.get('margen', 0) or 0)
                    co = float(kr.get('costo_operativo', 0.09) or 0.09)
                    fsc = float(kr.get('fsc', 0) or 0)
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
        kgs = item.get('kgs', [])
        fsc_usar = float(item.get('fsc_extraido', 0) or 0)
        cot_id = item.get('cot_id')

        kg_rates_nuevas = []
        for k in kgs:
            t = float(k.get('tarifa_nueva', 0) or 0)
            kg_rates_nuevas.append({
                'kg': k['kg'], 'tarifa': f"{t:.2f}",
                'margen': '0.00', 'costo_operativo': '0.09',
                'fsc': f"{fsc_usar:.2f}",
                'tarifa_cliente': f"{t + 0.09 + fsc_usar:.2f}"
            })

        aero_obj = {
            'aerolinea': nombre_aero, 'vuelo': '', 'itinerario': '',
            'tiempo_transito': '', 'granjas_entrega': '', 'salida': '', 'llegada': '',
            'kg_rates': kg_rates_nuevas,
            'rate_increases': [], 'cargos_adicionales': [],
            'notas': '', 'es_continuacion': False, 'fecha_actualizacion': hoy
        }

        if cot_id and cot_id != 'NEW':
            cot = Cotizacion.query.get(int(cot_id))
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
