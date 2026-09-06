#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Limpieza del texto de los correos.

La usan la ingesta (en la PC, al guardar el cuerpo) y el portal (en Railway,
al armar el vistazo de correos guardados antes de que existiera esto). Por eso
no depende de nada de Windows.
"""

import re

# Avisos que Outlook y Microsoft 365 pegan arriba del cuerpo. No los escribio
# nadie: son del sistema, y en el vistazo tapaban el contenido real ("Algunos
# contactos que recibieron este mensaje no suelen recibir correos de...").
_BANNERS = [
    r'Algunos contactos que recibieron este mensaje no suelen recibir correos '
    r'electr[oó]nicos de \S+\s*Por qu[eé] es esto importante\s*<[^>]*>',
    r'No suele recibir correos electr[oó]nicos de \S+\s*'
    r'Por qu[eé] es esto importante\s*<[^>]*>',
    r"Some people who received this message don't often get email from \S+\s*"
    r'Learn why this is important\s*<[^>]*>',
    r"You don't often get email from \S+\s*Learn why this is important\s*<[^>]*>",
    r'\[?(?:CAUTION|PRECAUCI[OÓ]N|ATENCI[OÓ]N)[:\]]?\s*'
    r'(?:This email originated from outside|Este correo (?:electr[oó]nico )?'
    r'(?:proviene|se origin[oó]) (?:de )?fuera)[^\n]*',
]
_RE_BANNERS = re.compile('|'.join(f'(?:{b})' for b in _BANNERS), re.I)

# Al pasar un correo a texto plano, Outlook deja cada enlace como
# "texto <https://...>" y cada direccion como "nombre <mailto:...>".
_RE_ENLACES = re.compile(r'<(?:https?://|mailto:)[^>]*>')


def limpiar_banners(texto):
    """Quita los avisos del sistema del principio del cuerpo."""
    if not texto:
        return ''
    return _RE_BANNERS.sub('', texto).strip()


def sin_enlaces(texto):
    """Quita los <https://...> y <mailto:...> que ensucian un vistazo."""
    return _RE_ENLACES.sub('', texto or '')


# Microsoft envuelve cada enlace en safelinks.protection.outlook.com/?url=...
# y el original queda ilegible dentro de una URL de 300 caracteres.
_RE_SAFELINK = re.compile(
    r'https?://[a-z0-9.-]*safelinks\.protection\.outlook\.com/\?url=([^&\s>]+)[^\s>]*',
    re.I)
_RE_MAILTO = re.compile(r'\s*<(?:mailto|tel):[^>]*>')


def limpiar_para_ver(texto):
    """El cuerpo como para leerlo en pantalla: sin avisos del sistema, con
    los enlaces reales en vez de los de safelinks, y sin los <mailto:...>
    que repiten la direccion que ya esta al lado."""
    from urllib.parse import unquote
    limpio = limpiar_banners(texto)
    limpio = _RE_SAFELINK.sub(lambda m: unquote(m.group(1)), limpio)
    return _RE_MAILTO.sub('', limpio)
