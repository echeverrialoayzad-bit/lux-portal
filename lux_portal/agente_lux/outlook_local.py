#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lectura del buzon desde el Outlook de escritorio, sin pasar por Azure.

Esta es la alternativa a Microsoft Graph cuando el tenant no deja que los
usuarios aprueben aplicaciones. Corre en la maquina de Daniela, dentro de su
propia sesion de Outlook, asi que no necesita permisos del administrador ni
tokens: alcanza exactamente lo mismo que ella ve al abrir Outlook.

Solo lectura. Nunca marca como leido, ni mueve, ni borra, ni responde.

IMPORTANTE: este modulo NUNCA debe importarse desde el portal en Railway.
Depende de pywin32 y de Outlook instalado, que solo existen en Windows. El
CLI local lo importa a proposito de forma perezosa.

Requiere:  pip install pywin32
"""

import mimetypes
import os
import re
import tempfile
from datetime import datetime

# Solo se guarda el contenido de adjuntos que pueden traer tarifas.
MIMES_UTILES = ('image/', 'application/pdf')
MAX_ADJUNTO_BYTES = 5 * 1024 * 1024

# Piso de tamano para imagenes. Casi todos los correos traen el logo de la
# firma, iconos de redes y separadores: son cientos de imagenes de 1-15 KB que
# no aportan nada y ensucian el analisis. Una captura de una tabla de tarifas
# pesa bastante mas que esto, incluso pegada en el cuerpo del correo.
MIN_IMAGEN_BYTES = 20 * 1024

# Tope de adjuntos con contenido por correo, por si alguno viene con decenas.
MAX_ADJUNTOS_POR_CORREO = 10

# Constantes de Outlook (no dependen de pywin32).
OL_FOLDER_INBOX = 6
OL_MAIL_ITEM = 43

# Tope de mensajes a recorrer, para no colgarse en un buzon enorme.
MAX_RECORRIDO = 800


class OutlookNoDisponible(RuntimeError):
    """Outlook clasico no esta instalado, o esta el Outlook nuevo solamente."""


def _conectar():
    try:
        import win32com.client
    except ImportError:
        raise OutlookNoDisponible(
            'Falta pywin32. Instalalo con:  pip install pywin32'
        )

    try:
        app = win32com.client.Dispatch('Outlook.Application')
        return app.GetNamespace('MAPI')
    except Exception as exc:
        # COM se inicializa por hilo. Si el llamador arranco esto desde un hilo
        # secundario sin CoInitialize, el error no tiene nada que ver con que
        # Outlook falte, y decir lo contrario manda a buscar el problema al
        # lugar equivocado.
        if 'CoInitialize' in str(exc):
            raise OutlookNoDisponible(
                'Fallo de inicializacion de COM: quien llamo a esto lo hizo '
                'desde un hilo que no llamo a pythoncom.CoInitialize(). '
                'Outlook esta bien; el problema es del codigo que lo invoca. '
                f'Detalle: {exc}'
            )
        raise OutlookNoDisponible(
            'No se pudo abrir Outlook. Revisa que tengas el Outlook clasico '
            '(el de Office, no el nuevo de Windows) instalado y con tu cuenta '
            f'configurada. Detalle: {exc}'
        )


# ExchangeConnectionMode de Outlook. Importa porque un Outlook levantado por
# COM sin ventana puede quedar bajando solo encabezados (400) o sin conexion,
# y entonces el buzon que ve el vigia no es el buzon real.
MODOS_CONEXION = {
    0: 'sin Exchange',
    100: 'sin conexion (Trabajar sin conexion)',
    200: 'desconectado',
    300: 'conectando, solo encabezados',
    400: 'conectado, solo encabezados',
    500: 'cache: conectando',
    600: 'cache: desconectado',
    700: 'cache: conectado completo',
    800: 'en linea',
}
MODOS_SANOS = {700, 800}


def modo_conexion():
    """(codigo, texto) del estado de conexion de Outlook con Exchange."""
    ns = _conectar()
    try:
        codigo = int(ns.ExchangeConnectionMode)
    except Exception:
        return None, 'desconocido'
    return codigo, MODOS_CONEXION.get(codigo, f'codigo {codigo}')


def cuenta_principal():
    """Correo de la cuenta por defecto de Outlook."""
    ns = _conectar()
    try:
        return ns.Accounts.Item(1).SmtpAddress or ''
    except Exception:
        try:
            return ns.CurrentUser.AddressEntry.GetExchangeUser().PrimarySmtpAddress or ''
        except Exception:
            return ''


def listar_carpetas():
    """Nombres de las carpetas disponibles, para poder elegir una distinta
    a la bandeja de entrada."""
    ns = _conectar()
    inbox = ns.GetDefaultFolder(OL_FOLDER_INBOX)
    nombres = ['Inbox']

    def recorrer(carpeta, prefijo):
        for sub in carpeta.Folders:
            ruta = f'{prefijo}/{sub.Name}'
            nombres.append(ruta)
            try:
                recorrer(sub, ruta)
            except Exception:
                pass

    try:
        recorrer(inbox, 'Inbox')
    except Exception:
        pass
    return nombres


def _resolver_carpeta(ns, ruta):
    """Devuelve la carpeta pedida. `ruta` es 'Inbox' o 'Inbox/Tarifas'."""
    carpeta = ns.GetDefaultFolder(OL_FOLDER_INBOX)
    if not ruta:
        return carpeta

    partes = [p for p in ruta.replace('\\', '/').split('/') if p]
    if partes and partes[0].lower() in ('inbox', 'bandeja de entrada'):
        partes = partes[1:]

    for parte in partes:
        encontrada = None
        for sub in carpeta.Folders:
            if sub.Name.strip().lower() == parte.strip().lower():
                encontrada = sub
                break
        if encontrada is None:
            raise OutlookNoDisponible(
                f'No existe la carpeta "{ruta}". Carpetas disponibles: '
                + ', '.join(listar_carpetas())
            )
        carpeta = encontrada
    return carpeta


def _email_remitente(item):
    """El SMTP real del remitente.

    En Exchange, SenderEmailAddress devuelve un DN interno tipo
    '/O=EXCHANGELABS/OU=.../CN=...' que no sirve para nada, asi que hay que
    resolverlo por otro lado."""
    try:
        if (item.SenderEmailType or '').upper() == 'EX':
            try:
                return item.Sender.GetExchangeUser().PrimarySmtpAddress or ''
            except Exception:
                pass
            try:
                # PR_SMTP_ADDRESS
                return item.PropertyAccessor.GetProperty(
                    'http://schemas.microsoft.com/mapi/proptag/0x39FE001E'
                ) or ''
            except Exception:
                pass
        return item.SenderEmailAddress or ''
    except Exception:
        return ''


def _fecha(item):
    try:
        recibido = item.ReceivedTime
        return datetime(recibido.year, recibido.month, recibido.day,
                        recibido.hour, recibido.minute, recibido.second)
    except Exception:
        return datetime.now()


def _vale_la_pena(mime, size):
    """Si guardamos o no el contenido del adjunto.

    Guardamos PDFs siempre, e imagenes solo si son lo bastante grandes como
    para ser una tabla de tarifas y no el logo de una firma."""
    if size > MAX_ADJUNTO_BYTES:
        return False
    if mime == 'application/pdf':
        return True
    if mime.startswith('image/'):
        return size >= MIN_IMAGEN_BYTES
    return False


def _adjuntos(item):
    """Adjuntos del correo. Solo devuelve bytes de PDFs e imagenes grandes."""
    salida = []
    try:
        total = item.Attachments.Count
    except Exception:
        return salida

    guardados = 0

    for i in range(1, total + 1):
        try:
            att = item.Attachments.Item(i)
            nombre = att.FileName or f'adjunto_{i}'
            size = int(getattr(att, 'Size', 0) or 0)
        except Exception:
            continue

        mime = mimetypes.guess_type(nombre)[0] or 'application/octet-stream'

        # Las imagenes chicas son firmas e iconos: no se listan siquiera, para
        # no llenar la pantalla y el analisis de ruido.
        if mime.startswith('image/') and size < MIN_IMAGEN_BYTES:
            continue

        contenido = None
        if _vale_la_pena(mime, size) and guardados < MAX_ADJUNTOS_POR_CORREO:
            ruta_tmp = None
            try:
                extension = os.path.splitext(nombre)[1] or '.bin'
                fd, ruta_tmp = tempfile.mkstemp(suffix=extension)
                os.close(fd)
                att.SaveAsFile(ruta_tmp)
                with open(ruta_tmp, 'rb') as fh:
                    contenido = fh.read()
                guardados += 1
            except Exception:
                contenido = None
            finally:
                if ruta_tmp and os.path.exists(ruta_tmp):
                    try:
                        os.remove(ruta_tmp)
                    except OSError:
                        pass

        salida.append({
            'nombre': nombre,
            'mime': mime,
            'size': size,
            'contenido': contenido,   # bytes o None
        })
    return salida


def es_respuesta_a_mi(asunto, cuerpo, mi_correo):
    """Si el correo contesta a un hilo que arranco Daniela.

    Cuando la aerolinea responde sobre el mismo correo, el mensaje original de
    ella queda citado abajo con su direccion en el encabezado. Eso se detecta
    leyendo el cuerpo, sin recorrer Outlook: enumerar Elementos enviados por
    COM tomaba mas de siete minutos y era inviable.

    Medido sobre 210 correos reales: lo cumplen el 59% de los correos de
    tarifas y solo el 3% de las reservas."""
    if not mi_correo:
        return None
    if not re.match(r'\s*(re|rv|fwd|fw)\s*:', asunto or '', re.I):
        return False
    return mi_correo.lower() in (cuerpo or '').lower()


def parece_operativo(asunto):
    """Correos de reserva, guia o cierre.

    Estan llenos de cifras por kilo que son el precio de un embarque puntual,
    no la tarifa vigente. De aca nunca se sacan tarifas netas."""
    return bool(re.search(
        r'\breserva|\bcierre|\bawb\b|\bbooking|manifiesto|\bguia\b|\bpre[\s-]?alert',
        asunto or '', re.I))


def _expandir(carpeta, ruta):
    """(carpeta, ruta) de esta carpeta y de todas sus subcarpetas."""
    salida = [(carpeta, ruta)]
    try:
        for sub in carpeta.Folders:
            salida.extend(_expandir(sub, f'{ruta}/{sub.Name}'))
    except Exception:
        pass
    return salida


def _leer_carpeta(carpeta, ruta, desde, limite, mi_correo=None, omitir=None):
    """Correos de una sola carpeta, mas nuevos primero.

    `omitir` son los id_unico que ya estan guardados: de esos no se baja ni
    el cuerpo ni los adjuntos, que es lo lento. Devuelve (correos, omitidos)."""
    omitir = omitir or set()
    omitidos = 0
    try:
        items = carpeta.Items
    except Exception:
        return [], 0

    try:
        # Descendente por fecha: asi se puede cortar apenas se pasa el corte.
        items.Sort('[ReceivedTime]', True)
    except Exception:
        pass

    correos = []
    recorridos = 0

    for item in items:
        recorridos += 1
        if recorridos > MAX_RECORRIDO or len(correos) >= limite:
            break

        try:
            if getattr(item, 'Class', None) != OL_MAIL_ITEM:
                continue
        except Exception:
            continue

        fecha = _fecha(item)
        if fecha < desde:
            # Van de mas nuevo a mas viejo: de aca en adelante todos quedan
            # fuera del rango.
            break

        try:
            entry_id = item.EntryID
        except Exception:
            continue

        id_unico = f'outlook:{entry_id}'
        if id_unico in omitir:
            omitidos += 1
            continue

        try:
            cuerpo = item.Body or ''
        except Exception:
            cuerpo = ''

        asunto = getattr(item, 'Subject', '') or '(sin asunto)'

        correos.append({
            'id_unico': id_unico,
            'fecha': fecha,
            'carpeta': ruta,
            'respuesta_mia': es_respuesta_a_mi(asunto, cuerpo, mi_correo),
            'operativo': parece_operativo(asunto),
            'remitente': _email_remitente(item),
            'remitente_nombre': getattr(item, 'SenderName', '') or '',
            'asunto': asunto,
            'cuerpo': cuerpo.strip(),
            'adjuntos': _adjuntos(item),
        })

    return correos, omitidos


def leer(desde, carpeta='Inbox', limite=200, recursivo=True, mi_correo=None,
         omitir=None):
    """Correos recibidos desde `desde` (datetime), mas nuevos primero.

    Con `recursivo` recorre tambien las subcarpetas, que es lo util aca:
    el buzon tiene una carpeta por aerolinea bajo Inbox/AEROLINEAS, asi que
    la ruta de la carpeta identifica la aerolinea sin tener que adivinarla
    del texto del correo.

    `omitir` son los id_unico ya guardados: se saltan sin bajar el cuerpo.

    Devuelve (correos, omitidos): dicts listos para volcar en AgenteMail y
    cuantos se saltaron por ya estar guardados. No toca los mensajes: ni los
    marca como leidos ni cambia nada en el buzon."""
    ns = _conectar()
    origen = _resolver_carpeta(ns, carpeta)

    if not mi_correo:
        try:
            mi_correo = ns.Accounts.Item(1).SmtpAddress or ''
        except Exception:
            mi_correo = ''

    ruta_base = carpeta or 'Inbox'
    objetivos = _expandir(origen, ruta_base) if recursivo else [(origen, ruta_base)]

    correos = []
    omitidos = 0
    for sub, ruta in objetivos:
        nuevos, saltados = _leer_carpeta(sub, ruta, desde, limite, mi_correo, omitir)
        correos.extend(nuevos)
        omitidos += saltados

    correos.sort(key=lambda c: c['fecha'], reverse=True)
    return correos[:limite], omitidos
