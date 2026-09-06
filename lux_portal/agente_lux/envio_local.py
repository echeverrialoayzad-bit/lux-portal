#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Envio de correos por el Outlook de escritorio, desde la PC de Daniela.

Es la otra mitad de la pestana Mails de Agente Lux: el portal deja en cola
lo que ella pidio enviar (AgenteEnvio) y esto lo manda con su cuenta y su
firma, igual que si lo escribiera ella.

Solo corre en la PC, nunca en Railway: usa COM y necesita Outlook abierto.
"""

import html
from datetime import datetime

from lux_portal.extensions import db
from lux_portal.agente_lux.models import AgenteEnvio

OL_MAIL_ITEM = 0


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


def enviar_por_outlook(para, cc, asunto, cuerpo):
    """Manda un correo y devuelve sin error, o lanza la excepcion de COM."""
    import win32com.client

    app = win32com.client.Dispatch('Outlook.Application')
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
    mail.Send()


def enviar_pendientes():
    """Manda todo lo que este en cola. Devuelve (enviados, fallidos).

    Se llama dentro de un app_context y con COM inicializado en el hilo."""
    enviados, fallidos = 0, 0
    for envio in AgenteEnvio.query.filter_by(estado='pendiente').order_by(AgenteEnvio.id).all():
        try:
            enviar_por_outlook(envio.para, envio.cc, envio.asunto, envio.cuerpo)
            envio.estado = 'enviado'
            envio.enviado_en = datetime.utcnow()
            envio.error = None
            enviados += 1
        except Exception as exc:
            envio.estado = 'error'
            envio.error = str(exc)[:1000]
            fallidos += 1
        db.session.commit()
    return enviados, fallidos
