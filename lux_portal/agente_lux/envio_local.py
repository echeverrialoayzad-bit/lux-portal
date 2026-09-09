#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envio de correos por el Outlook de escritorio, desde la PC de Daniela.

Es la otra mitad de la pestana Mails de Agente Lux: el portal deja en cola
lo que ella pidio (AgenteEnvio) y esto lo arma con su cuenta y su firma,
igual que si lo escribiera ella, y segun el modo lo manda o lo deja en
Borradores de Outlook para que lo revise y lo envie ella.

Solo corre en la PC, nunca en Railway: usa COM y necesita Outlook abierto.
"""

import html
import time
from datetime import datetime

from lux_portal.extensions import db
from lux_portal.agente_lux.models import AgenteEnvio

OL_MAIL_ITEM = 0
OL_FOLDER_INBOX = 6
OL_SAVE = 0           # MailItem.Close(olSave): guarda y cierra el inspector


def _con_firma(cuerpo_html, firma_html):
    """Mete el cuerpo antes de la firma que Outlook ya puso en el HTML."""
    if not firma_html:
        return cuerpo_html
    bajo = firma_html.lower()
    i = bajo.find('<body')
    j = firma_html.find('>', i) if i >= 0 else -1
    if j < 0:
        return cuerpo_html + firma_html
    return firma_html[:j + 1] + cuerpo_html + firma_html[j + 1:]


def _aplicacion():
    """Outlook por COM, asegurandose de que tenga ventana.

    Si Daniela cierra la ventana del Outlook clasico, la siguiente llamada
    COM lo vuelve a levantar sin ventana. Asi queda en modo "solo
    encabezados" y Send falla con "El parametro no es correcto" (paso el
    2026-09-08 con la primera solicitud a Air Canada). Abrirle la Bandeja de
    entrada le devuelve la ventana. El vigia ademas abre outlook.exe antes
    de llegar aca si no estaba corriendo."""
    import win32com.client

    app = win32com.client.Dispatch('Outlook.Application')
    try:
        if app.Explorers.Count == 0:
            app.GetNamespace('MAPI').GetDefaultFolder(OL_FOLDER_INBOX).Display()
            time.sleep(5)
    except Exception:
        pass
    return app


def _modo_outlook(app):
    """Texto corto del estado de conexion, para explicar un error."""
    try:
        from lux_portal.agente_lux.outlook_local import MODOS_CONEXION
        codigo = int(app.GetNamespace('MAPI').ExchangeConnectionMode)
        return MODOS_CONEXION.get(codigo, f'codigo {codigo}')
    except Exception:
        return 'desconocido'


def preparar_por_outlook(para, cc, asunto, cuerpo, modo='enviar'):
    """Arma el correo con la firma de Daniela y, segun `modo`, lo manda
    ('enviar') o lo deja en Borradores de Outlook ('borrador'). Devuelve sin
    error o lanza la excepcion de COM."""
    app = _aplicacion()
    mail = app.CreateItem(OL_MAIL_ITEM)
    mail.To = para or ''
    mail.CC = cc or ''
    mail.Subject = asunto or ''
    # Al abrir el inspector, Outlook carga la firma por defecto en HTMLBody;
    # asi el correo sale con la firma de Daniela, como los que manda a mano.
    mail.GetInspector
    firma = mail.HTMLBody or ''
    texto = html.escape(cuerpo or '').replace('\r\n', '\n').replace('\n', '<br>')
    cuerpo_html = ('<div style="font-family:Calibri,Arial,sans-serif;'
                   f'font-size:11pt">{texto}</div><br>')
    mail.HTMLBody = _con_firma(cuerpo_html, firma)
    try:
        # Guardar primero: deja el correo en Borradores y le da un EntryID.
        mail.Save()
        if modo == 'borrador':
            mail.Close(OL_SAVE)
            return
        # Enviar: cerrar el inspector, reabrir el correo desde el buzon y
        # mandarlo. El Send directo sobre el item recien creado por COM falla
        # con "El parametro no es correcto" (0x80070057) cuando Outlook esta en
        # modo cache; reabrirlo desde Borradores le da el contexto que Send
        # necesita. Verificado el 2026-09-08: la variante directa fallaba y la
        # reabierta enviaba (por eso la primera solicitud a Air Canada fallo).
        entry_id = mail.EntryID
        try:
            mail.Close(OL_SAVE)
        except Exception:
            pass
        item = app.GetNamespace('MAPI').GetItemFromID(entry_id)
        item.Send()
    except Exception as exc:
        raise RuntimeError(f'{exc} (Outlook: {_modo_outlook(app)})') from exc


def enviar_por_outlook(para, cc, asunto, cuerpo):
    """Compatibilidad: manda directo."""
    preparar_por_outlook(para, cc, asunto, cuerpo, modo='enviar')


def enviar_pendientes():
    """Atiende todo lo que este en cola. Devuelve (enviados, borradores,
    fallidos).

    Se llama dentro de un app_context y con COM inicializado en el hilo."""
    enviados, borradores, fallidos = 0, 0, 0
    for envio in AgenteEnvio.query.filter_by(estado='pendiente').order_by(AgenteEnvio.id).all():
        modo = envio.modo or 'enviar'
        try:
            preparar_por_outlook(envio.para, envio.cc, envio.asunto, envio.cuerpo, modo)
            envio.estado = 'borrador' if modo == 'borrador' else 'enviado'
            envio.enviado_en = datetime.utcnow()
            envio.error = None
            if modo == 'borrador':
                borradores += 1
            else:
                enviados += 1
        except Exception as exc:
            envio.estado = 'error'
            envio.error = str(exc)[:1000]
            fallidos += 1
        db.session.commit()
    return enviados, borradores, fallidos
