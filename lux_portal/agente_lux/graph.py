#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cliente minimo de Microsoft Graph para leer el correo de Microsoft 365.

Solo lectura: los permisos que se piden son Mail.Read y User.Read. El modulo
nunca envia, borra ni marca correos.

Variables de entorno necesarias en Railway:
    MS_CLIENT_ID       ID de la aplicacion registrada en Azure
    MS_CLIENT_SECRET   Secreto de esa aplicacion
    MS_TENANT_ID       ID del tenant (o 'common' si es cuenta suelta)
    MS_REDIRECT_URI    https://<dominio>/agente-lux/oauth/callback
"""

import os
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'
LOGIN_BASE = 'https://login.microsoftonline.com'
SCOPES = 'offline_access User.Read Mail.Read'

# Solo se guarda el contenido de adjuntos que pueden traer tarifas.
MIMES_UTILES = ('image/', 'application/pdf')
MAX_ADJUNTO_BYTES = 5 * 1024 * 1024


def _cfg(nombre, defecto=''):
    return os.environ.get(nombre, defecto).strip()


def client_id():
    return _cfg('MS_CLIENT_ID')


def client_secret():
    return _cfg('MS_CLIENT_SECRET')


def tenant_id():
    return _cfg('MS_TENANT_ID', 'common') or 'common'


def redirect_uri(fallback=''):
    return _cfg('MS_REDIRECT_URI') or fallback


def config_ok():
    """True si las tres variables minimas estan configuradas."""
    return bool(client_id() and client_secret() and tenant_id())


def falta_config():
    """Lista de variables de entorno que faltan, para mostrarlas en la UI."""
    faltan = []
    if not client_id():
        faltan.append('MS_CLIENT_ID')
    if not client_secret():
        faltan.append('MS_CLIENT_SECRET')
    if not _cfg('MS_TENANT_ID'):
        faltan.append('MS_TENANT_ID')
    if not _cfg('MS_REDIRECT_URI'):
        faltan.append('MS_REDIRECT_URI')
    return faltan


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

def url_autorizacion(redirect, state):
    """URL a la que se manda a Daniela para que inicie sesion en Microsoft."""
    params = {
        'client_id': client_id(),
        'response_type': 'code',
        'redirect_uri': redirect,
        'response_mode': 'query',
        'scope': SCOPES,
        'state': state,
        'prompt': 'select_account',
    }
    return f'{LOGIN_BASE}/{tenant_id()}/oauth2/v2.0/authorize?{urlencode(params)}'


def _pedir_token(data):
    """POST al endpoint de token. Devuelve el JSON o lanza RuntimeError."""
    resp = requests.post(
        f'{LOGIN_BASE}/{tenant_id()}/oauth2/v2.0/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=30,
    )
    payload = {}
    try:
        payload = resp.json()
    except ValueError:
        pass
    if resp.status_code != 200:
        desc = payload.get('error_description') or payload.get('error') or resp.text[:300]
        raise RuntimeError(f'Microsoft rechazo la peticion de token: {desc}')
    return payload


def canjear_codigo(code, redirect):
    """Cambia el ?code= del callback por access_token + refresh_token."""
    return _pedir_token({
        'client_id': client_id(),
        'client_secret': client_secret(),
        'code': code,
        'redirect_uri': redirect,
        'grant_type': 'authorization_code',
        'scope': SCOPES,
    })


def refrescar_token(refresh_token):
    """Renueva el access_token usando el refresh_token guardado."""
    return _pedir_token({
        'client_id': client_id(),
        'client_secret': client_secret(),
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'scope': SCOPES,
    })


def guardar_token(cuenta, payload):
    """Vuelca la respuesta del endpoint de token sobre el modelo AgenteCuenta.

    Microsoft no siempre devuelve un refresh_token nuevo; cuando no lo manda
    hay que conservar el que ya se tenia."""
    cuenta.access_token = payload.get('access_token')
    if payload.get('refresh_token'):
        cuenta.refresh_token = payload['refresh_token']
    segundos = int(payload.get('expires_in', 3600) or 3600)
    # Margen de 5 min para no usar un token que expira a mitad del scan.
    cuenta.token_expira = datetime.utcnow() + timedelta(seconds=max(segundos - 300, 60))
    return cuenta


def token_valido(cuenta):
    """Devuelve un access_token utilizable, refrescandolo si hace falta.

    El caller es responsable de hacer db.session.commit() despues, porque
    esta funcion puede actualizar los tokens de la cuenta."""
    if not cuenta or not cuenta.refresh_token:
        raise RuntimeError('No hay ninguna cuenta de correo conectada.')

    vigente = (cuenta.access_token and cuenta.token_expira
               and cuenta.token_expira > datetime.utcnow())
    if vigente:
        return cuenta.access_token

    guardar_token(cuenta, refrescar_token(cuenta.refresh_token))
    return cuenta.access_token


# ---------------------------------------------------------------------------
# Lectura de correo
# ---------------------------------------------------------------------------

def _get(token, url, params=None):
    resp = requests.get(
        url,
        headers={
            'Authorization': f'Bearer {token}',
            # Pide el cuerpo en texto plano en vez de HTML: mucho mas limpio
            # para analizar y muchisimo mas corto.
            'Prefer': 'outlook.body-content-type="text"',
        },
        params=params,
        timeout=60,
    )
    if resp.status_code != 200:
        detalle = resp.text[:300]
        raise RuntimeError(f'Microsoft Graph respondio {resp.status_code}: {detalle}')
    return resp.json()


def perfil(token):
    """Datos basicos de la cuenta conectada."""
    data = _get(token, f'{GRAPH_BASE}/me')
    return {
        'email': data.get('mail') or data.get('userPrincipalName') or '',
        'nombre': data.get('displayName') or '',
    }


def listar_mensajes(token, desde, limite=120, carpeta='Inbox'):
    """Correos recibidos desde la fecha `desde` (datetime UTC), mas nuevos primero.

    Devuelve una lista de dicts crudos de Graph. Pagina automaticamente hasta
    `limite` mensajes para no colgarse en buzones grandes."""
    campos = 'id,receivedDateTime,subject,from,bodyPreview,body,hasAttachments,webLink'
    url = f'{GRAPH_BASE}/me/mailFolders/{carpeta}/messages'
    params = {
        '$select': campos,
        '$top': 50,
        '$orderby': 'receivedDateTime desc',
        '$filter': f"receivedDateTime ge {desde.strftime('%Y-%m-%dT%H:%M:%SZ')}",
    }

    mensajes = []
    while url and len(mensajes) < limite:
        data = _get(token, url, params=params)
        mensajes.extend(data.get('value', []))
        url = data.get('@odata.nextLink')
        params = None  # nextLink ya trae la query completa
    return mensajes[:limite]


def descargar_adjuntos(token, mensaje_id):
    """Adjuntos de un correo. Solo devuelve contenido de imagenes y PDF."""
    try:
        data = _get(token, f'{GRAPH_BASE}/me/messages/{mensaje_id}/attachments')
    except RuntimeError:
        return []

    salida = []
    for att in data.get('value', []):
        if att.get('@odata.type') != '#microsoft.graph.fileAttachment':
            continue
        mime = (att.get('contentType') or '').lower()
        size = int(att.get('size') or 0)
        contenido = None
        if mime.startswith(MIMES_UTILES) and size <= MAX_ADJUNTO_BYTES:
            contenido = att.get('contentBytes')
            # Graph ya lo entrega en base64; validamos que se pueda decodificar
            # para no guardar basura que despues rompa el analisis.
            if contenido:
                try:
                    base64.b64decode(contenido, validate=True)
                except Exception:
                    contenido = None
        salida.append({
            'nombre': att.get('name') or 'adjunto',
            'mime': mime or 'application/octet-stream',
            'size': size,
            'contenido_b64': contenido,
        })
    return salida


def texto_de(mensaje):
    """Cuerpo en texto plano del mensaje, con fallback al preview."""
    cuerpo = (mensaje.get('body') or {}).get('content') or ''
    if not cuerpo.strip():
        cuerpo = mensaje.get('bodyPreview') or ''
    return cuerpo.strip()


def remitente_de(mensaje):
    """(email, nombre) del remitente."""
    direccion = ((mensaje.get('from') or {}).get('emailAddress') or {})
    return direccion.get('address') or '', direccion.get('name') or ''


def fecha_de(mensaje):
    """receivedDateTime como datetime naive en UTC."""
    crudo = mensaje.get('receivedDateTime') or ''
    if not crudo:
        return datetime.utcnow()
    try:
        return datetime.strptime(crudo.replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
    except ValueError:
        try:
            return datetime.fromisoformat(crudo.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return datetime.utcnow()
