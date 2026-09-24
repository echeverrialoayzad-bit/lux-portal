#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validadores de las propuestas antes de cargarlas al portal.

Lo que se aprendio leyendo los correos reales de cada aerolinea (ver
.claude/skills/agente-lux/referencia_aerolineas.md) convertido en reglas que
se aplican a cada hallazgo, venga como venga del analisis:

  1. la aerolinea la decide el remitente (ECS Group es QATAR aunque el
     correo caiga en la carpeta AERCARIBE; Transoceanica es LUFTHANSA o LAN
     segun la persona);
  2. la cifra propuesta tiene que estar escrita en el correo;
  3. los cargos se nombran como en el portal (AWC = Due Carrier, CH = CC),
     los que ya estan iguales se dan por hechos y los condicionales (DGR,
     cuarentena, fees por cambios) no entran como cargo fijo;
  4. un FSC que junto con el SSC del correo da el FSC del portal ya esta
     cargado (Copa guarda fuel + SSC en un solo campo);
  5. una tarifa "all in" trae el fuel incluido: no se le suma FSC;
  6. el mismo correo archivado dos veces produce una sola tanda;
  7. los tramos de kilos validos son +45, +100, +300, +500 y +1000;
  8. la firma de Flyus ("USD 18.00 HAWB...") no es un cargo nuevo.

Ninguna regla escribe en la base: devuelven hallazgos corregidos, marcados
como resueltos o convertidos en aviso, y una bitacora para la terminal.
"""

import re

# ---------------------------------------------------------------------------
# 1. Remitente -> aerolinea
# ---------------------------------------------------------------------------

_DOMINIOS = [
    ('ecsgroup.aero', 'QATAR'),
    ('primeair', 'EMIRATES'),
    ('kales.com', 'TURKISH'),
    ('flyus.aero', 'AIR CANADA'),
    ('gsaforce.com', 'CATHAY'),
    ('copaair.com', 'COPA AIRLINES'),
    ('delta.com', 'DELTA'),
    ('dhl.com', 'DHL'),
    ('avianca.com', 'AVIANCA'),
    ('mawneyecuador.com', 'AIR EUROPA'),
    ('solent.com', 'SOLENT'),
    # Fenix Ecuador es GSA de Atlas para MIA (Prime Air lo es para lo demas).
    ('fenixecuador.com', 'ATLAS'),
]
# Transoceanica representa a dos aerolineas: lo decide la persona.
_TRANSOCEANICA = {
    'kcazar': 'LUFTHANSA', 'jproanio': 'LUFTHANSA',
    'kguevara': 'LAN', 'bperez': 'LAN', 'acabezas': 'LAN',
}


def aerolinea_por_remitente(remitente, cuerpo='', carpeta='', asunto=''):
    """La aerolinea que corresponde al remitente, o None si no es un GSA
    conocido (por ejemplo un reenvio interno de FreightWise) o si el GSA
    representa a varias y no se puede saber cual (entonces se respeta lo
    que dijo el analisis)."""
    r = (remitente or '').lower()
    if not r or 'freight-wise.com' in r:
        return None
    if 'transoceanica' in r:
        for usuario, aero in _TRANSOCEANICA.items():
            if usuario in r:
                return aero
        texto = (cuerpo or '').lower()
        if 'laratesec' in texto or 'mcc' in texto:
            return 'LAN'
        return 'LUFTHANSA'
    if 'primeair' in r:
        # Prime Air es GSA de Emirates y tambien de Atlas (salesatlasec,
        # Carolina Aimara). Lo decide la carpeta, el remitente o el texto.
        pista = ' '.join([r, (carpeta or '').lower(), (asunto or '').lower(), (cuerpo or '')[:1500].lower()])
        if 'atlas' in pista:
            return 'ATLAS'
        if 'emirates' in pista or 'skycargo' in pista or ' ek ' in pista or 'dwc' in pista or 'dxb' in pista:
            return 'EMIRATES'
        return None
    for dominio, aero in _DOMINIOS:
        if dominio in r:
            return aero
    return None


# ---------------------------------------------------------------------------
# Numeros y texto del correo
# ---------------------------------------------------------------------------

_RE_NUM = re.compile(r'\d+(?:[.,]\d+)?')


def numero(valor):
    """'2,90' / '$2.90' / '2.90usd' -> 2.9. None si no hay numero."""
    if valor is None:
        return None
    m = _RE_NUM.search(str(valor))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', '.'))
    except ValueError:
        return None


def numeros_del_texto(texto):
    """Todos los numeros escritos en el correo, con coma o punto decimal."""
    salida = set()
    for m in _RE_NUM.finditer(texto or ''):
        try:
            salida.add(round(float(m.group(0).replace(',', '.')), 2))
        except ValueError:
            pass
    return salida


def cifra_en_correo(valor, texto):
    n = numero(valor)
    if n is None:
        return False
    return any(abs(n - x) < 0.005 for x in numeros_del_texto(texto))


_RE_RESPUESTA_FW = re.compile(
    r'^\s*(?:De|From|Enviado el|Sent|Para|To)\s*:.*@freight-wise\.com', re.I | re.M)


def es_respuesta_freightwise(cuerpo):
    """True si abajo del correo viene citada una solicitud de alguien de
    FreightWise (Daniela, Johana, Felipe, Monica...). Es lo que hace valida
    una tarifa: ellos piden y la aerolinea contesta sobre el mismo hilo."""
    return bool(_RE_RESPUESTA_FW.search(cuerpo or ''))


# ---------------------------------------------------------------------------
# 3. Cargos: nombres del portal, condicionales y ya cargados
# ---------------------------------------------------------------------------

# Como se llama en el correo -> como se llama en el portal. Primero por
# aerolinea (los nombres chocan entre aerolineas), despues el general.
_ALIAS_POR_AEROLINEA = {
    'LUFTHANSA': {'CH': 'CC (Carrier Charges)', 'CHC': 'CC (Carrier Charges)',
                  'PA': 'Due Carrier', 'PERISHABLE': 'Due Carrier'},
    'LAN': {'MCC': 'Due Carrier'},
    'QATAR': {'CC': 'CC (Carrier Charges)', 'CG': 'CG HAWB C/U'},
    'EMIRATES': {'CG': 'CG MAWB', 'CB': 'CB HAWB'},
}
_ALIAS_GENERAL = {'AWC': 'Due Carrier', 'AIR WAYBILL': 'Due Carrier', 'AIRWAY BILL': 'Due Carrier',
                  'DUE CARRIER': 'Due Carrier', 'CARRIER CHARGES': 'CC (Carrier Charges)'}

# Cargos que solo aplican en casos puntuales: nunca como cargo fijo.
_RE_CONDICIONAL = re.compile(
    r'\b(DGR|DANGEROUS|PELIGROS|CUARENTENA|QUARANT|DI\b|BF\b|DF\b|E-?AWB|EAWB|'
    r'COLLECT|DISBURSEMENT|PENALI|OVERSIZE|SOBREDIMENSION|BODEGAJE|STORAGE|'
    r'SPOT|CAMBIOS EN BOOKING|MANUAL BOOKING|CARGA SECA)\b', re.I)

# Texto de la firma de Flyus (Air Canada), pegado en todos sus correos.
_RE_FIRMA_FLYUS = re.compile(r'18[.,]00\s*HAWB|HAWB si la aerol', re.I)


def _token_concepto(concepto):
    """'CH: 40' -> 'CH'; 'PA (perishable fee)' -> 'PA'; 'awc' -> 'AWC'."""
    texto = (concepto or '').strip().upper()
    texto = re.sub(r'[:\-].*$', '', texto).strip()
    m = re.match(r'[A-Z][A-Z /]*', texto)
    return (m.group(0).strip() if m else texto)


def nombre_canonico_cargo(aerolinea, concepto):
    """El nombre con el que el portal conoce ese cargo, o el original."""
    token = _token_concepto(concepto)
    aero = (aerolinea or '').upper().strip()
    por_aero = _ALIAS_POR_AEROLINEA.get(aero, {})
    for clave, nombre in por_aero.items():
        if token == clave or token.startswith(clave + ' '):
            return nombre
    for clave, nombre in _ALIAS_GENERAL.items():
        if token == clave or clave in (concepto or '').upper():
            return nombre
    if 'PERISHABLE' in (concepto or '').upper() and aero == 'LUFTHANSA':
        return 'Due Carrier'
    return (concepto or '').strip()


def es_condicional(concepto, cita=''):
    return bool(_RE_CONDICIONAL.search(concepto or '')) or (
        bool(_RE_CONDICIONAL.search(cita or '')) and not numero(concepto))


# ---------------------------------------------------------------------------
# 6. Correos repetidos (dos carpetas, reenvios internos de la misma carta)
# ---------------------------------------------------------------------------

def _huella(correo):
    """Remitente + cuerpo completo normalizado: dos copias del mismo correo
    (archivado en dos carpetas) son identicas letra por letra. No se usa
    solo el arranque del cuerpo: los GSA repiten el mismo encabezado en
    todas sus respuestas y dos tarifas distintas parecerian una."""
    cuerpo = re.sub(r'\s+', ' ', (correo.cuerpo or '')).strip().lower()
    pdfs = tuple(sorted((a.nombre or '').lower() for a in (correo.adjuntos or [])
                        if (a.nombre or '').lower().endswith('.pdf')))
    return ((correo.remitente or '').lower(), cuerpo), pdfs


def _asunto_base(asunto):
    return re.sub(r'^\s*((re|rv|fw|fwd)\s*:\s*)+', '', (asunto or '').strip(), flags=re.I).strip().lower()


def correos_repetidos(correos):
    """{mail_id repetido: mail_id original}. Original = el de id mas bajo.
    Dos correos son el mismo si coinciden remitente y cuerpo completo, o si
    son el mismo aviso (mismo asunto sin RE:/RV:) con la misma carta PDF
    adjunta: los reenvios internos de un aviso de fuel."""
    por_cuerpo, por_pdf, salida = {}, {}, {}
    for mail_id in sorted(correos):
        c = correos[mail_id]
        (clave_cuerpo, pdfs) = _huella(c)
        clave_pdf = (_asunto_base(c.asunto), pdfs) if pdfs else None
        original = None
        if clave_cuerpo[1] and clave_cuerpo in por_cuerpo:
            original = por_cuerpo[clave_cuerpo]
        elif clave_pdf and clave_pdf in por_pdf:
            original = por_pdf[clave_pdf]
        if original is not None:
            salida[mail_id] = original
            continue
        if clave_cuerpo[1]:
            por_cuerpo.setdefault(clave_cuerpo, mail_id)
        if clave_pdf:
            por_pdf.setdefault(clave_pdf, mail_id)
    return salida


# ---------------------------------------------------------------------------
# Foto del portal, en la forma que necesitan las reglas
# ---------------------------------------------------------------------------

_TRAMOS_VALIDOS = {'+45', '+100', '+300', '+500', '+1000'}


def _norm_aero(nombre):
    return re.sub(r'\s+(FREIGHTER|PAX|CARGO|AIRLINES|AIRWAYS|AIR CARGO|PASSENGER|FREIGHT)$',
                  '', (nombre or '').upper().strip()).strip()


class _Foto:
    def __init__(self, snapshot):
        snapshot = snapshot or {}
        self.cargos = {}          # (aero, concepto upper) -> monto
        for c in snapshot.get('cargos') or []:
            self.cargos[(_norm_aero(c.get('aerolinea')), (c.get('concepto') or '').strip().upper())] = c.get('monto')
        self.tramos = {}          # (cot_id, aero) -> {kg}
        self.fsc_tramo = {}       # (cot_id, aero, kg) -> fsc
        for cot in snapshot.get('cotizaciones') or []:
            for aero in cot.get('aerolineas') or []:
                clave = (cot.get('cot_id'), _norm_aero(aero.get('aerolinea')))
                for kr in aero.get('kg_rates') or []:
                    kg = _norm_kg(kr.get('kg'))
                    self.tramos.setdefault(clave, set()).add(kg)
                    self.fsc_tramo[clave + (kg,)] = kr.get('fsc')
        self.fsc_reglas = {}      # aero -> [(destinos, fsc)]
        for r in snapshot.get('fsc_reglas') or []:
            self.fsc_reglas.setdefault(_norm_aero(r.get('aerolinea')), []).append(
                ([d.upper() for d in (r.get('destinos') or [])], r.get('fsc')))

    def cargo_existente(self, aero, concepto):
        return self.cargos.get((_norm_aero(aero), (concepto or '').strip().upper()))

    def cargo_con_monto(self, aero, monto):
        m = numero(monto)
        if m is None:
            return None
        for (a, concepto), valor in self.cargos.items():
            v = numero(valor)
            if a == _norm_aero(aero) and v is not None and abs(v - m) < 0.005:
                return concepto
        return None

    def fsc_actual(self, aero, destinos):
        reglas = self.fsc_reglas.get(_norm_aero(aero)) or []
        destinos = [d.upper() for d in (destinos or [])]
        for dests, fsc in reglas:
            if dests and destinos and sorted(dests) == sorted(destinos):
                return fsc
        for dests, fsc in reglas:
            if destinos and any(d in dests for d in destinos):
                return fsc
        for dests, fsc in reglas:
            if not dests:
                return fsc
        return None


def _norm_kg(kg):
    kg = str(kg or '').strip().replace(' ', '')
    if kg and not kg.startswith('+'):
        kg = '+' + kg
    return kg


# ---------------------------------------------------------------------------
# El validador
# ---------------------------------------------------------------------------

class Informe:
    def __init__(self):
        self.hallazgos = []
        self.log = []
        self.corregidos = 0
        self.resueltos = 0
        self.avisos = 0
        self.descartados = 0


def _aviso(h, motivo):
    """Convierte en aviso: se ve, no se aplica."""
    if h.get('tipo') != 'info':
        h['tipo'] = 'info'
    h['_aviso'] = (h.get('_aviso') + ' ' if h.get('_aviso') else '') + motivo


def _nota(h, texto):
    h['_notas'] = (h.get('_notas') or []) + [texto]


def validar_lote(hallazgos, correos, snapshot):
    """Aplica todas las reglas. `correos` mapea mail_id -> AgenteMail;
    `snapshot` es contexto.snapshot(). Devuelve un Informe."""
    foto = _Foto(snapshot)
    inf = Informe()
    repetidos = correos_repetidos(correos)
    vistos_en_original = {}   # (mail original, clave) -> True

    for h in hallazgos:
        h = dict(h)
        detalle = dict(h.get('detalle') or {})
        h['detalle'] = detalle
        correo = correos.get(h.get('mail_id'))
        cuerpo = (correo.cuerpo if correo else '') or ''
        tipo = h.get('tipo')
        etiqueta = f"{h.get('aerolinea') or '?'} {h.get('destino') or ''} {tipo}".strip()

        # 6. Correo repetido: se cuenta una sola vez.
        if correo is not None and correo.id in repetidos:
            original = repetidos[correo.id]
            inf.log.append(f'{etiqueta}: el correo {correo.id} es copia del {original}; se descarta la propuesta repetida.')
            inf.descartados += 1
            continue

        # 1. La aerolinea la manda el remitente.
        if correo is not None:
            por_remitente = aerolinea_por_remitente(correo.remitente, cuerpo,
                                                    getattr(correo, 'carpeta', ''), getattr(correo, 'asunto', ''))
            actual = _norm_aero(h.get('aerolinea') or detalle.get('aerolinea'))
            if por_remitente and actual != _norm_aero(por_remitente):
                inf.log.append(f'{etiqueta}: el remitente es de {por_remitente}, no de {h.get("aerolinea") or "(sin aerolinea)"}; se corrige.')
                h['aerolinea'] = por_remitente
                if 'aerolinea' in detalle:
                    detalle['aerolinea'] = por_remitente
                inf.corregidos += 1
                etiqueta = f"{por_remitente} {h.get('destino') or ''} {tipo}".strip()

        # 8. Firma de Flyus.
        if tipo == 'cargo' and _RE_FIRMA_FLYUS.search((h.get('cita') or '') + ' ' + (detalle.get('concepto') or '')):
            inf.log.append(f'{etiqueta}: "USD 18.00 HAWB" es la firma de Flyus, no un cargo nuevo; se descarta.')
            inf.descartados += 1
            continue

        # 7. Tramos de kilos.
        if tipo == 'tarifa':
            kg = _norm_kg(detalle.get('kg'))
            detalle['kg'] = kg
            tramos_cot = foto.tramos.get((detalle.get('cot_id'), _norm_aero(h.get('aerolinea'))), set())
            if kg not in _TRAMOS_VALIDOS and kg not in tramos_cot:
                _nota(h, f'Tramo {kg} fuera de lo habitual (+45, +100, +300, +500, +1000): revisar.')
                inf.avisos += 1

        # 2. La cifra tiene que estar en el correo.
        valor = {'tarifa': detalle.get('tarifa_nueva'), 'fsc': detalle.get('fsc_nuevo'),
                 'cargo': detalle.get('monto_nuevo')}.get(tipo, h.get('valor_nuevo'))
        if tipo in ('tarifa', 'fsc', 'cargo') and valor not in (None, '') and correo is not None:
            if not cifra_en_correo(valor, cuerpo):
                con_adjunto = any((a.mime or '').startswith('image') or (a.nombre or '').lower().endswith('.pdf')
                                  for a in (correo.adjuntos or []))
                if con_adjunto:
                    _nota(h, f'La cifra {valor} no esta en el texto del correo; puede venir en el adjunto. Verificar antes de aplicar.')
                    inf.avisos += 1
                else:
                    _aviso(h, f'La cifra {valor} no aparece en el correo: no se aplica sola.')
                    inf.log.append(f'{etiqueta}: la cifra {valor} no esta en el correo; queda como aviso.')
                    inf.avisos += 1

        # 5. Tarifa all in. Solo se mira la cita y el arranque del correo
        # (donde va la tarifa), no el hilo citado abajo; y con limites de
        # palabra para no confundir "all in" con otras palabras.
        if tipo == 'tarifa' and re.search(r'\ball[\s-]?in\b', (h.get('cita') or '') + ' ' + cuerpo[:800], re.I):
            fsc_tramo = numero(foto.fsc_tramo.get((detalle.get('cot_id'), _norm_aero(h.get('aerolinea')), detalle.get('kg'))))
            if fsc_tramo:
                _nota(h, f'Tarifa "all in" (fuel incluido) y la cotizacion tiene FSC {fsc_tramo:.2f} aparte: dejar FSC en 0 o no sumar.')
                inf.avisos += 1
            else:
                _nota(h, 'Tarifa "all in": el fuel viene incluido, no se le suma FSC.')

        # 4. FSC que ya incluye el SSC.
        if tipo == 'fsc':
            ssc = re.search(r'(\d+[.,]\d+)\s*(?:usd\s*)?ssc|ssc\s*\$?\s*(\d+[.,]\d+)', cuerpo, re.I)
            fsc_nuevo = numero(detalle.get('fsc_nuevo'))
            fsc_hoy = numero(detalle.get('fsc_actual')) or numero(foto.fsc_actual(h.get('aerolinea'), detalle.get('destinos')))
            if ssc and fsc_nuevo is not None and fsc_hoy is not None:
                valor_ssc = numero(ssc.group(1) or ssc.group(2))
                if valor_ssc is not None and abs((fsc_nuevo + valor_ssc) - fsc_hoy) < 0.005:
                    h['_resuelto'] = (f'El FSC del portal ({fsc_hoy:.2f}) ya incluye el SSC: '
                                      f'fuel {fsc_nuevo:.2f} + SSC {valor_ssc:.2f}.')
                    inf.log.append(f'{etiqueta}: {h["_resuelto"]} Se da por hecho.')
                    inf.resueltos += 1

        # 3. Cargos.
        if tipo == 'cargo':
            concepto = detalle.get('concepto') or ''
            if es_condicional(concepto, h.get('cita')):
                _aviso(h, f'"{concepto}" es un cargo segun el caso (mercancia peligrosa, cuarentena, cambios): no va como cargo fijo.')
                inf.log.append(f'{etiqueta}: cargo condicional "{concepto}"; queda como aviso.')
                inf.avisos += 1
            else:
                canonico = nombre_canonico_cargo(h.get('aerolinea'), concepto)
                if canonico != concepto.strip():
                    inf.log.append(f'{etiqueta}: el cargo "{concepto}" en el portal se llama "{canonico}".')
                    detalle['concepto'] = canonico
                    inf.corregidos += 1
                    concepto = canonico
                if 'SSC' in _token_concepto(concepto):
                    _aviso(h, 'El SSC va sumado dentro del FSC de la cotizacion, no como cargo aparte.')
                    inf.avisos += 1
                else:
                    existente = foto.cargo_existente(h.get('aerolinea'), concepto)
                    monto = numero(detalle.get('monto_nuevo'))
                    if existente is not None and monto is not None and numero(existente) is not None \
                            and abs(numero(existente) - monto) < 0.005:
                        h['_resuelto'] = f'El cargo {concepto} ya esta en {existente} en el portal.'
                        inf.log.append(f'{etiqueta}: {h["_resuelto"]}')
                        inf.resueltos += 1
                    elif existente is None and monto is not None:
                        parecido = foto.cargo_con_monto(h.get('aerolinea'), monto)
                        if parecido:
                            _nota(h, f'Mismo monto que el cargo "{parecido}" ya registrado: puede ser el mismo cargo con otro nombre.')
                            inf.avisos += 1
                    if existente is not None:
                        h['valor_actual'] = str(existente)

        # Las notas acumuladas se vuelven parte de la alerta que ve Daniela.
        if h.get('_notas'):
            h['_aviso'] = ((h.get('_aviso') + ' ') if h.get('_aviso') else '') + ' '.join(h.pop('_notas'))
        inf.hallazgos.append(h)

    return inf
