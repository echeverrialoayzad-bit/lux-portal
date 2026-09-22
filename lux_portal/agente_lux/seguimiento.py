#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Que contesto cada aerolinea a las solicitudes de tarifa.

El cuadro de Actualizaciones solo muestra lo que hay que aprobar. Cuando la
aerolinea confirma la misma tarifa que ya estaba, contesta sin cifra o no
contesta, ahi no aparece nada: la pantalla queda vacia y parece que el agente
no hizo nada. Paso de verdad el 20-sep-2026, con la tanda de MIA.

Este modulo es el otro lado: una fila por aerolinea y destino pedido, con lo
que paso. Solo lee; a diferencia de /api/hallazgos, no cambia ningun estado.

Lo dificil es que no hay ningun vinculo guardado entre una solicitud y su
respuesta, y el que contesta casi nunca es la direccion a la que se escribio
(a Atlas se le escribe a salesatlasec@primeair.com.ec y contesta Carolina; a
DHL a acsuiobook.ia@dhl.com y contesta Mateo). Asi que se reconstruye por
cascada, del criterio mas fuerte al mas debil, y lo que no resuelve queda
SIN EMPAREJAR y se muestra aparte: nunca se adivina.
"""

from datetime import timedelta
import re

from lux_portal.extensions import db
from lux_portal.agente_lux.models import (AgenteEnvio, AgenteMail, AgenteHallazgo,
                                          a_ecuador, ahora_ecuador)
from lux_portal.agente_lux.texto import destinos_de_cuerpo

# Una respuesta mas vieja que esto ya no es de ese pedido.
DIAS_VENTANA = 10
# Cuanto hacia atras se listan las solicitudes.
DIAS_HISTORIA = 30
# Holgura de reloj al comparar el envio contra la fecha del correo.
MARGEN_HORAS = 2

# Una misma aerolinea archivada con dos nombres: la carpeta de Outlook dice
# LAN y la solicitud dice LATAM. Hasta que se unifique la base (hay dos filas
# en cotizacion_mail_requests con el mismo destinatario), se tratan como la
# misma; si no, la banda la muestra dos veces.
ALIAS_AEROLINEA = {
    'LAN': 'LATAM',
    'AERCARIBE': 'AIR CARIBE',
    'COPA AIRLINE': 'COPA AIRLINES',
}

# Respuestas automaticas: no cuentan como que la aerolinea contesto. A
# proposito NO se agregan al normalizador de asunto, porque entonces
# entrarian como respuesta valida y marcarian la solicitud como atendida.
_RE_AUTO = re.compile(r'^\s*(automatic reply|respuesta autom[aá]tica|out of office|'
                      r'fuera de la oficina|undeliverable|no entregado)', re.I)
_RE_PREFIJO = re.compile(r'^\s*((re|rv|fw|fwd|ref)\s*:\s*)+', re.I)
_RE_MAIL = re.compile(r'[\w.+-]+@[\w.-]+\.\w+')
_RE_HDR = re.compile(r'^(?:Para|To|CC|Cc):\s*(.+)$', re.M)

PROPIO = 'freight-wise.com'

ESTADOS = ('con_tarifa', 'confirmo', 'te_pide_algo', 'sin_tarifa', 'sin_respuesta')


# ---------------------------------------------------------------------------
# Direcciones
# ---------------------------------------------------------------------------

def _normalizar(direccion):
    """Minusculas y sin espacios. La base guarda el mismo buzon de las dos
    formas (kguevara@TRANSOCEANICA.COM.EC y kguevara@transoceanica.com.ec),
    y sin esto son dos buzones distintos."""
    return (direccion or '').strip().lower()


def _direcciones(texto):
    return {_normalizar(e) for e in _RE_MAIL.findall(texto or '')}


def _dominio(direccion):
    direccion = _normalizar(direccion)
    return direccion.split('@', 1)[1] if '@' in direccion else ''


def _citados(cuerpo):
    """Las direcciones que el correo cita en sus lineas Para:/To:/CC:.

    Se mira solo la cabecera citada y no "cualquier direccion del cuerpo",
    porque las firmas traen direcciones que no son destinatarias (DHL cita
    acs.data.quality@dhl.com en el pie de todos sus correos)."""
    salida = set()
    for linea in _RE_HDR.findall((cuerpo or '')[:4000]):
        for e in _direcciones(linea):
            if PROPIO not in e:
                salida.add(e)
    return salida


def _aero(nombre):
    nombre = (nombre or '').strip().upper()
    return ALIAS_AEROLINEA.get(nombre, nombre)


def _asunto_limpio(asunto):
    return _RE_PREFIJO.sub('', asunto or '').strip().lower()


# ---------------------------------------------------------------------------
# Que se pidio y que llego
# ---------------------------------------------------------------------------

def _envios_recientes():
    """Las solicitudes enviadas en los ultimos DIAS_HISTORIA dias.

    De cada (aerolinea, destino) se queda la mas reciente: si Daniela pidio
    MIA dos veces, lo que importa es si contestaron el ultimo pedido."""
    corte = ahora_ecuador() - timedelta(days=DIAS_HISTORIA)
    filas = (AgenteEnvio.query
             .filter(AgenteEnvio.estado == 'enviado',
                     AgenteEnvio.enviado_en.isnot(None))
             .order_by(AgenteEnvio.enviado_en.desc())
             .all())
    recientes, vistos = [], set()
    for e in filas:
        cuando = a_ecuador(e.enviado_en)
        if cuando is None or cuando < corte:
            continue
        destinos = destinos_de_cuerpo(e.cuerpo) or ['']
        clave = (_aero(e.aerolinea), tuple(destinos))
        if clave in vistos:
            continue
        vistos.add(clave)
        recientes.append((e, cuando, destinos))
    return recientes


def _respuestas_candidatas(desde):
    """Correos que podrian ser respuesta a una solicitud.

    Fuera quedan los propios (los mails 1507-1511 son las solicitudes de
    Daniela que volvieron a su Inbox, con asunto identico y el minuto exacto
    del envio: sin este filtro cada envio se empareja consigo mismo) y los
    duplicados, que existen porque el mismo correo esta archivado en dos
    carpetas a la vez (ECS Group aparece igual en QATAR y en AERCARIBE)."""
    filas = (AgenteMail.query
             .filter(AgenteMail.fecha >= desde,
                     AgenteMail.remitente.isnot(None))
             .order_by(AgenteMail.fecha.asc())
             .all())
    salida, vistos = [], set()
    for m in filas:
        if PROPIO in _normalizar(m.remitente):
            continue
        if _RE_AUTO.match(m.asunto or ''):
            continue
        clave = (_normalizar(m.remitente), m.fecha, (m.asunto or '').strip())
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append(m)
    return salida


def emparejar(envios, mails):
    """A que solicitud contesta cada correo.

    Cascada de tres niveles; gana el primero que resuelva a exactamente un
    envio. Si un nivel empata o no resuelve, se baja al siguiente; si se
    agotan todos, el correo queda sin emparejar y se muestra al pie.

    Devuelve ({envio_id: [(mail, nivel), ...]}, [mails sin emparejar])."""
    por_envio, huerfanas = {}, []

    for m in mails:
        asunto_m = _asunto_limpio(m.asunto)
        remitente = _normalizar(m.remitente)
        dom = _dominio(remitente)
        citadas = _citados(m.cuerpo)

        posibles = []
        for envio, cuando, _destinos in envios:
            # La ventana es filtro, no criterio. Ojo: enviado_en es UTC y
            # AgenteMail.fecha es hora de Ecuador; sin a_ecuador() la
            # respuesta de Atlas (16:49 local) queda "cinco horas antes" de
            # su propio envio (21:41 UTC) y se descarta sola.
            if not m.fecha:
                continue
            if m.fecha < cuando - timedelta(hours=MARGEN_HORAS):
                continue
            if m.fecha > cuando + timedelta(days=DIAS_VENTANA):
                continue
            # El asunto no distingue nada (todas las solicitudes se llaman
            # "Tarifa Flor"): sirve de guardarraíl para descartar ruido
            # operativo, no de llave.
            asunto_e = _asunto_limpio(envio.asunto)
            if asunto_e and asunto_e not in asunto_m:
                continue
            posibles.append((envio, cuando))

        if not posibles:
            huerfanas.append((m, 'no cae en la ventana de ninguna solicitud'))
            continue

        elegido, nivel = _elegir(posibles, remitente, dom, citadas, m)
        if elegido is None:
            huerfanas.append((m, 'contesto alguien que no pude ligar a un pedido'))
            continue
        por_envio.setdefault(elegido.id, []).append((m, nivel))

    return por_envio, huerfanas


def _elegir(posibles, remitente, dom, citadas, mail):
    """El envio al que contesta este correo, y por que criterio."""
    # Nivel 1: el correo cita en Para:/To: la direccion a la que se escribio.
    # Es el mas fuerte y resuelve 3 de los 4 casos de la tanda de MIA.
    if citadas:
        por_cita = [e for e, _ in posibles if _direcciones(e.para) & citadas]
        if len(por_cita) == 1:
            return por_cita[0], 'cita'

    # Nivel 2: el dominio de quien contesta es el de algun destinatario.
    # Resuelve Atlas, cuyo cliente de correo no cita cabeceras.
    por_dom = [e for e, _ in posibles
               if dom and dom in {_dominio(d) for d in _direcciones(e.para)}]
    if len(por_dom) == 1:
        return por_dom[0], 'dominio'

    # Nivel 3: la carpeta de Outlook, y SOLO para desempatar lo anterior.
    # Nunca como criterio propio: la carpeta llega tarde o nunca.
    if len(por_dom) > 1:
        from lux_portal.agente_lux.routes import _aerolinea_de_carpeta
        de_carpeta = _aero(_aerolinea_de_carpeta(mail.carpeta))
        afinados = [e for e in por_dom if _aero(e.aerolinea) == de_carpeta]
        if len(afinados) == 1:
            return afinados[0], 'carpeta'

    return None, None


# ---------------------------------------------------------------------------
# Que paso con cada solicitud
# ---------------------------------------------------------------------------

def _hallazgos_de(mail_ids):
    """{mail_id: [hallazgo, ...]} de los correos emparejados."""
    if not mail_ids:
        return {}
    filas = (AgenteHallazgo.query
             .filter(AgenteHallazgo.mail_id.in_(list(mail_ids)))
             .all())
    salida = {}
    for h in filas:
        salida.setdefault(h.mail_id, []).append(h)
    return salida


def _estado_linea(respuestas, hallazgos_por_mail, destino):
    """(estado, detalle[], pide_algo) de una aerolinea para un destino.

    El orden importa: manda el primero que aplica. `requiere_accion` decide
    solo cuando no hay tarifa, porque el analisis lo pone con manga ancha y
    si se lo deja por encima casi todo termina en "te pide algo" y la
    distincion se muere. Por eso ademas va como bandera aparte."""
    if not respuestas:
        return 'sin_respuesta', [], False

    destino = (destino or '').strip().upper()
    pide_algo = any(bool(m.requiere_accion) for m, _ in respuestas)
    detalle, propios, otros_destinos = [], [], set()

    for m, _nivel in respuestas:
        for h in hallazgos_por_mail.get(m.id, []):
            if h.tipo != 'tarifa':
                continue
            suyo = (h.destino or '').strip().upper()
            if suyo == destino or not suyo:
                propios.append(h)
            elif suyo:
                otros_destinos.add(suyo)

    if any(h.estado in ('pendiente', 'aprobado') for h in propios):
        detalle.append('Trajo tarifa nueva: está arriba, para aprobar.')
        return 'con_tarifa', detalle, pide_algo

    ya = [h for h in propios if h.estado in ('resuelto', 'aplicado')]
    if ya:
        valor = next((h.valor_nuevo for h in ya if h.valor_nuevo), None)
        detalle.append(f'Contestó {valor}: la misma que ya tenías.' if valor
                       else 'Contestó la misma tarifa que ya tenías.')
        return 'confirmo', detalle, pide_algo

    if pide_algo:
        detalle.append('Contestó pidiendo algo: hay que responderle.')
        return 'te_pide_algo', detalle, True

    # Medio punto del problema original: contestar de OTRO destino no es
    # contestar el que se pidio.
    if otros_destinos:
        detalle.append(f'Contestó de {", ".join(sorted(otros_destinos))}, '
                       f'no de {destino or "lo pedido"}.')
    else:
        detalle.append('Contestó sin dar tarifa.')
    return 'sin_tarifa', detalle, False


def _resumen_mail(m):
    texto = (m.resumen or '').strip()
    return texto[:220] + ('...' if len(texto) > 220 else '')


def _dias_desde(cuando):
    """Dias de calendario, no horas transcurridas.

    Un correo de ayer a las 10:20 tiene menos de 24 horas, y contando por
    horas salia como "hoy" cuando en realidad fue ayer. Lo que Daniela lee
    es el dia del calendario, asi que se comparan fechas."""
    if not cuando:
        return None
    return max((ahora_ecuador().date() - cuando.date()).days, 0)


def resumen_solicitudes():
    """El JSON de la banda de seguimiento. Solo lee."""
    envios = _envios_recientes()
    if not envios:
        return {'dias': DIAS_HISTORIA, 'conteo': {e: 0 for e in ESTADOS},
                'grupos': [], 'huerfanas': []}

    mas_viejo = min(cuando for _e, cuando, _d in envios)
    mails = _respuestas_candidatas(mas_viejo - timedelta(hours=MARGEN_HORAS))
    por_envio, huerfanas = emparejar(envios, mails)
    hallazgos = _hallazgos_de({m.id for lista in por_envio.values() for m, _ in lista})

    conteo = {e: 0 for e in ESTADOS}
    por_destino = {}

    for envio, cuando, destinos in envios:
        respuestas = sorted(por_envio.get(envio.id, []), key=lambda x: x[0].fecha)
        for destino in destinos:
            estado, detalle, pide_algo = _estado_linea(respuestas, hallazgos, destino)
            conteo[estado] += 1
            ultima = respuestas[-1] if respuestas else None
            linea = {
                'aerolinea': _aero(envio.aerolinea),
                'envio_id': envio.id,
                'pedido_en': cuando.strftime('%Y-%m-%d %H:%M'),
                'para': envio.para or '',
                'estado': estado,
                'pide_algo': pide_algo,
                'detalle': detalle,
                'respuesta': None,
                'hallazgos': [],
            }
            if ultima:
                m, nivel = ultima
                linea['respuesta'] = {
                    'mail_id': m.id,
                    'fecha': m.fecha.strftime('%Y-%m-%d %H:%M') if m.fecha else None,
                    'dias': _dias_desde(m.fecha),
                    'remitente': m.remitente_nombre or m.remitente,
                    'asunto': m.asunto,
                    'nivel': nivel,
                    'resumen': _resumen_mail(m),
                    'n_respuestas': len(respuestas),
                }
                linea['hallazgos'] = [
                    {'id': h.id, 'tipo': h.tipo, 'estado': h.estado,
                     'valor_nuevo': h.valor_nuevo}
                    for mm, _ in respuestas for h in hallazgos.get(mm.id, [])
                ]
            else:
                dias = _dias_desde(cuando)
                linea['detalle'] = ['Sin respuesta, se pidió hoy.' if dias == 0
                                    else f'Sin respuesta desde hace {dias} día(s).']
            clave = destino or '(sin destino en el correo)'
            grupo = por_destino.setdefault(clave, {
                'destino': clave, 'pedido_en': linea['pedido_en'],
                'conteo': {e: 0 for e in ESTADOS}, 'lineas': [],
            })
            grupo['conteo'][estado] += 1
            grupo['lineas'].append(linea)
            if linea['pedido_en'] > grupo['pedido_en']:
                grupo['pedido_en'] = linea['pedido_en']

    # Primero lo accionable: lo que hay que aprobar y lo que espera respuesta.
    orden = {e: i for i, e in enumerate(ESTADOS)}
    grupos = sorted(por_destino.values(), key=lambda g: g['pedido_en'], reverse=True)
    for g in grupos:
        g['lineas'].sort(key=lambda l: (orden[l['estado']], l['aerolinea']))

    return {
        'dias': DIAS_HISTORIA,
        'conteo': conteo,
        'grupos': grupos,
        'huerfanas': [
            {'mail_id': m.id,
             'fecha': m.fecha.strftime('%Y-%m-%d %H:%M') if m.fecha else None,
             'remitente': m.remitente_nombre or m.remitente,
             'asunto': m.asunto, 'nota': nota}
            for m, nota in huerfanas
            if (m.respuesta_mia or _asunto_limpio(m.asunto) == 'tarifa flor')
        ][:15],
    }
