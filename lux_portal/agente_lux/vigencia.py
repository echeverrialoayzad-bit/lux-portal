#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vigencia e incrementos por temporada de un hallazgo.

La tarjeta de Actualizaciones muestra, para cada propuesta, la tarifa pasada
y la nueva con su fecha y su FSC, y abajo una fila de "Incremento por
temporada": cuanto sube y desde/hasta cuando (los recargos de San Valentin,
Dia de la Madre, etc. que las aerolineas anuncian junto con la tarifa).

Esto lo escribe el analisis (Claude Code) en el detalle del hallazgo, lo
corrige Daniela desde la tarjeta y lo lee `aplicar` para dejarlo en el campo
Rate Increase de la cotizacion. Como entra por tres caminos distintos, la
normalizacion vive aca, sin depender de Flask ni de Windows.

Formato dentro de `detalle`:
    "vigencia_desde": "2026-10-01"      # desde cuando rige lo nuevo, si el correo lo dice
    "vigencia_hasta": "2026-12-31"      # opcional
    "incrementos": [
        {"monto": "0.30", "desde": "2026-01-15", "hasta": "2026-02-14",
         "nota": "Peak season San Valentin"}
    ]
"""

from datetime import date, datetime
import re

_RE_ISO = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})$')
_RE_DMY = re.compile(r'^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$')
_RE_YMD_BARRA = re.compile(r'^(\d{4})/(\d{1,2})/(\d{1,2})$')


def fecha_iso(valor):
    """Fecha en 'AAAA-MM-DD' a partir de lo que venga; None si viene vacio.

    Entiende date/datetime, ISO, 'DD/MM/AAAA' (como se escribe en Ecuador),
    'DD-MM-AAAA' y 'AAAA/MM/DD'. Un texto que no se puede leer se devuelve tal
    cual, sin espacios de sobra, para no perder lo que decia el correo."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    if not texto:
        return None
    for patron, orden in ((_RE_ISO, 'ymd'), (_RE_YMD_BARRA, 'ymd'), (_RE_DMY, 'dmy')):
        m = patron.match(texto)
        if not m:
            continue
        partes = [int(p) for p in m.groups()]
        y, mo, d = partes if orden == 'ymd' else (partes[2], partes[1], partes[0])
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return texto
    return texto


def es_iso(texto):
    return bool(texto) and bool(_RE_ISO.match(str(texto)))


def _monto(valor):
    """'0.30', 0.3, '$0.30', '0,30' -> '0.30'. None si no es un numero."""
    if valor is None:
        return None
    texto = str(valor).strip().replace('$', '').replace('USD', '').strip()
    if not texto:
        return None
    if ',' in texto and '.' not in texto:
        texto = texto.replace(',', '.')
    try:
        return f'{float(texto):.2f}'
    except ValueError:
        return None


def normalizar_incrementos(valor):
    """Lista limpia de incrementos a partir de lo que venga.

    Acepta una lista de dicts, un dict suelto (un solo incremento) o nada.
    Se queda solo con los que traen monto: un incremento sin cifra no le
    sirve a nadie. Devuelve [] si no hay ninguno."""
    if not valor:
        return []
    if isinstance(valor, dict):
        valor = [valor]
    if not isinstance(valor, (list, tuple)):
        return []
    salida = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        monto = _monto(item.get('monto', item.get('amount')))
        if monto is None:
            continue
        inc = {'monto': monto}
        desde = fecha_iso(item.get('desde', item.get('from')))
        hasta = fecha_iso(item.get('hasta', item.get('to')))
        if desde:
            inc['desde'] = desde
        if hasta:
            inc['hasta'] = hasta
        nota = str(item.get('nota') or item.get('note') or '').strip()
        if nota:
            inc['nota'] = nota[:200]
        salida.append(inc)
    return salida


def normalizar_detalle(detalle):
    """Deja la vigencia y los incrementos del detalle en el formato de arriba.

    Muta el dict y lo devuelve. Acepta `incremento` (singular, como lo puede
    escribir el analisis) y lo pasa a la lista `incrementos`. Las claves que
    quedan vacias se quitan para que la tarjeta no las muestre."""
    if not isinstance(detalle, dict):
        return detalle
    for clave in ('vigencia_desde', 'vigencia_hasta'):
        if clave in detalle:
            valor = fecha_iso(detalle.get(clave))
            if valor:
                detalle[clave] = valor
            else:
                detalle.pop(clave, None)
    suelto = detalle.pop('incremento', None)
    incrementos = normalizar_incrementos(detalle.get('incrementos') or suelto)
    if incrementos:
        detalle['incrementos'] = incrementos
    else:
        detalle.pop('incrementos', None)
    return detalle


def _dmy(iso):
    """'2026-01-15' -> '15/01/2026'. Un texto que no es ISO se devuelve igual."""
    if not iso:
        return ''
    m = _RE_ISO.match(str(iso))
    if not m:
        return str(iso)
    y, mo, d = m.groups()
    return f'{int(d):02d}/{int(mo):02d}/{y}'


def texto_rango(incremento):
    """El texto de fechas que va en Rate Increase de la cotizacion, en el
    formato que Daniela escribe a mano en el formulario (DD/MM/AAAA)."""
    desde = _dmy(incremento.get('desde'))
    hasta = _dmy(incremento.get('hasta'))
    if desde and hasta:
        return f'{desde} - {hasta}'
    if desde:
        return f'desde {desde}'
    if hasta:
        return f'hasta {hasta}'
    return ''


def rate_increases_de(incrementos):
    """Los incrementos de un hallazgo en la forma que guarda la cotizacion:
    [{'amount': '0.30', 'date': '15/01/2026 - 14/02/2026'}]."""
    return [{'amount': inc['monto'], 'date': texto_rango(inc)}
            for inc in normalizar_incrementos(incrementos)]
