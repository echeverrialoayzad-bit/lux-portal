#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agente Lux - vigia local.

El portal corre en Railway y no puede alcanzar el Outlook de esta PC. Este
proceso cierra ese hueco: se queda escuchando y, cuando Daniela aprieta
"Refresh correos" en el portal, hace todo el ciclo de una:

    1. lee el buzon de Outlook
    2. le pide el analisis a Claude Code sin ventana (claude -p), que usa la
       suscripcion en vez de creditos de API
    3. sube los hallazgos al portal para que ella los apruebe

Ademas repite el ciclo solo cada cierto rato, para que la bitacora del dia
este al dia sin tener que apretar nada.

USO
---
    python agente_lux_watcher.py                # cada 20 min + atiende el boton
    python agente_lux_watcher.py --auto 10      # relee cada 10 minutos
    python agente_lux_watcher.py --auto 0       # solo cuando se aprieta el boton
    python agente_lux_watcher.py --carpeta "Inbox/AEROLINEAS"

Dejalo abierto en una ventana, o programalo para que arranque con Windows:
    python agente_lux_watcher.py --instalar-tarea

Para que pare: Ctrl+C.

Todo lo que dice queda tambien en _agente_lux/vigia.log, para poder ver que
paso cuando corre como tarea programada y nadie mira la ventana.
"""

import argparse
import os
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

# Reutiliza la conexion y el arranque de la app del CLI.
from agente_lux_cli import (
    ARCHIVO_HALLAZGOS, ARCHIVO_RESUMENES, crear_app, resolver_db,
)

LATIDO_SEGUNDOS = 15

# Bitacora en disco ademas de la consola: cuando el vigia corre como tarea
# programada nadie ve la ventana, y un "tu PC no esta escuchando" sin un log
# atras es imposible de diagnosticar.
RUTA_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '_agente_lux', 'vigia.log')
# Un solo vigia a la vez: el acceso directo de Inicio y un arranque a mano
# pueden coincidir, y dos vigias leen el mismo buzon y pisan los mismos
# archivos de trabajo. El lock guarda el PID del que esta corriendo.
RUTA_LOCK = os.path.join(os.path.dirname(RUTA_LOG), 'vigia.lock')
# Si aparece este archivo, el vigia termina limpio apenas no este trabajando:
# es la forma de pararlo sin matar el proceso a mitad de una llamada COM.
RUTA_PARAR = os.path.join(os.path.dirname(RUTA_LOG), 'parar')


def _proceso_vivo(pid):
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    ctypes.windll.kernel32.CloseHandle(h)
    return True


def _tomar_lock():
    """True si este proceso queda como el unico vigia; False si ya hay otro."""
    try:
        with open(RUTA_LOCK, 'r', encoding='utf-8') as fh:
            otro = int((fh.read() or '0').strip() or 0)
    except (OSError, ValueError):
        otro = 0
    if otro and otro != os.getpid() and _proceso_vivo(otro):
        return False
    os.makedirs(os.path.dirname(RUTA_LOCK), exist_ok=True)
    with open(RUTA_LOCK, 'w', encoding='utf-8') as fh:
        fh.write(str(os.getpid()))
    return True


def _soltar_lock():
    try:
        with open(RUTA_LOCK, 'r', encoding='utf-8') as fh:
            if (fh.read() or '').strip() == str(os.getpid()):
                os.remove(RUTA_LOCK)
    except OSError:
        pass


def _ahora():
    return datetime.now().strftime('%H:%M:%S')


def log(mensaje):
    linea = f'[{_ahora()}] {mensaje}'
    print(linea, flush=True)
    try:
        os.makedirs(os.path.dirname(RUTA_LOG), exist_ok=True)
        with open(RUTA_LOG, 'a', encoding='utf-8') as fh:
            fh.write(datetime.now().strftime('%Y-%m-%d ') + linea + '\n')
    except OSError:
        pass


def _contestar_dialogos_outlook():
    """Contesta los cuadros con los que Outlook se queda esperando al abrir.

    Despues de un cierre sucio, Outlook pregunta "no se inicio correctamente
    la ultima vez, ¿modo a prueba de errores?" y luego "Elegir perfil", y no
    atiende COM hasta que alguien responde. Aca se responde lo mismo que
    responderia Daniela: No al modo a prueba de errores, Aceptar al perfil.
    Devuelve cuantos cuadros contesto."""
    import ctypes
    import ctypes.wintypes as w
    user32 = ctypes.windll.user32
    BM_CLICK = 0x00F5

    def texto(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, b, n + 1)
        return b.value

    def clase(hwnd):
        b = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, b, 256)
        return b.value

    dialogos = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
    def arriba(hwnd, _):
        if user32.IsWindowVisible(hwnd) and clase(hwnd) == '#32770':
            dialogos.append(hwnd)
        return True

    user32.EnumWindows(arriba, 0)
    contestados = 0

    for d in dialogos:
        hijos = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
        def dentro(hc, _):
            hijos.append((clase(hc), texto(hc)))
            return True

        user32.EnumChildWindows(d, dentro, 0)
        estaticos = ' '.join(t for c, t in hijos if c == 'Static').lower()
        titulo = texto(d).lower()

        boton = None
        if 'prueba de errores' in estaticos or 'safe mode' in estaticos:
            boton = 'no'
        elif titulo.startswith('elegir perfil') or titulo.startswith('choose profile'):
            boton = 'aceptar'
        if not boton:
            continue

        # Solo el boton de ese cuadro: no se toca nada mas de la pantalla.
        objetivo = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, w.HWND, w.LPARAM)
        def buscar(hc, _):
            nonlocal objetivo
            if objetivo is None and clase(hc) == 'Button' and \
                    texto(hc).replace('&', '').strip().lower() in (boton, 'ok'):
                objetivo = hc
            return True

        user32.EnumChildWindows(d, buscar, 0)
        if objetivo is not None:
            user32.SendMessageW(objetivo, BM_CLICK, 0, 0)
            log(f'Outlook preguntaba "{texto(d)}": le contesto {boton.upper()}.')
            contestados += 1

    return contestados


def _abrir_outlook_si_hace_falta():
    """Arranca el Outlook de escritorio con ventana si no esta corriendo.

    Devuelve True si lo tuvo que abrir. Se usa el nombre corto porque el
    ShellExecute de Windows lo resuelve por el registro (App Paths), sin
    tener que adivinar donde esta instalado Office."""
    import subprocess
    try:
        salida = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq OUTLOOK.EXE'],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        salida = ''
    if 'OUTLOOK.EXE' in salida.upper():
        return False
    try:
        os.startfile('outlook.exe')
        return True
    except OSError as exc:
        log(f'No pude abrir Outlook solo ({exc}); sigo con COM.')
        return False


def _ruta_corta(ruta):
    """Version 8.3 de una ruta (sin acentos ni espacios), si Windows la da."""
    import ctypes
    buf = ctypes.create_unicode_buffer(512)
    if ctypes.windll.kernel32.GetShortPathNameW(ruta, buf, 512):
        return buf.value
    return ruta


def escribir_lanzador():
    """Deja en _agente_lux/vigia.cmd un .cmd que arranca el vigia.

    Va solo con ASCII a proposito: cmd.exe lo lee con la pagina de codigos de
    la consola y un acento en la ruta lo rompe. Por eso la carpeta sale de
    %~dp0 y python va en su ruta corta."""
    carpeta = os.path.dirname(os.path.abspath(__file__))
    lanzador = os.path.join(carpeta, '_agente_lux', 'vigia.cmd')

    python = _ruta_corta(sys.executable)
    if not python.isascii():
        python = 'python'   # el de PATH, que es con el que se instalo todo
    os.makedirs(os.path.dirname(lanzador), exist_ok=True)
    # Al iniciar sesion, la carpeta de OneDrive y la red pueden tardar en
    # estar listas: se espera hasta dos minutos antes de rendirse, y si algo
    # falla la ventana se queda abierta con el error a la vista en vez de
    # cerrarse en silencio (asi paso el 2026-09-06: reinicio y nada arranco).
    lineas = [
        '@echo off',
        'title Agente Lux - vigia',
        'set INTENTOS=0',
        ':espera',
        'if exist "%~dp0..\\agente_lux_watcher.py" goto listo',
        'set /a INTENTOS+=1',
        'if %INTENTOS% GEQ 24 goto falta',
        'timeout /t 5 /nobreak >nul',
        'goto espera',
        ':listo',
        'cd /d "%~dp0.."',
        f'"{python}" agente_lux_watcher.py',
        'if errorlevel 1 (',
        '  echo.',
        '  echo El vigia termino con error. Revisa _agente_lux\\vigia.log',
        '  pause',
        ')',
        'goto fin',
        ':falta',
        'echo No encuentro la carpeta del proyecto. Esta OneDrive sincronizando?',
        'pause',
        ':fin',
    ]
    # newline='' para que Python no convierta el \r\n en \r\r\n.
    with open(lanzador, 'w', encoding='ascii', newline='') as fh:
        fh.write('\r\n'.join(lineas) + '\r\n')
    return lanzador


def instalar_tarea():
    """Deja el vigia arrancando solo cada vez que Daniela inicia sesion.

    Va como acceso directo en la carpeta Inicio de Windows y no como tarea
    programada: schtasks pide permisos de administrador para las tareas de
    inicio de sesion (aca dio "Acceso denegado"), y ademas mata las tareas
    que llevan mas de tres dias corriendo. La carpeta Inicio no pide nada y
    no tiene ese limite."""
    carpeta = os.path.dirname(os.path.abspath(__file__))
    lanzador = escribir_lanzador()

    inicio = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows',
                          'Start Menu', 'Programs', 'Startup')
    if not os.path.isdir(inicio):
        sys.exit(f'No encontre la carpeta Inicio de Windows ({inicio}).')
    acceso = os.path.join(inicio, 'Agente Lux - vigia.lnk')

    import win32com.client
    shell = win32com.client.Dispatch('WScript.Shell')
    atajo = shell.CreateShortcut(acceso)
    atajo.TargetPath = lanzador
    atajo.WorkingDirectory = carpeta
    atajo.WindowStyle = 7          # minimizada, para que no tape nada al iniciar
    atajo.Description = 'Vigia de Agente Lux: conecta el portal con tu Outlook'
    atajo.Save()

    print('Listo: el vigia va a arrancar solo (minimizado) cada vez que '
          'inicies sesion en Windows.')
    print(f'Lo que vaya haciendo queda en {RUTA_LOG}')
    print(f'Para quitarlo, borra este acceso directo:\n  {acceso}')


PROMPT_ANALISIS = (
    'Usa el skill agente-lux. Lee _agente_lux/pendientes.json y los adjuntos '
    'que referencia, comparalos contra estado_actual, y escribe '
    '_agente_lux/hallazgos.json con el formato del docstring de '
    'agente_lux_cli.py. Reglas clave: las tarifas netas solo salen de correos '
    'con respuesta_a_mi_solicitud true que no sean reserva ni guia; un aviso '
    'de tarifa que la aerolinea mando por su cuenta va como tipo info. El FSC '
    'si puede venir directo. De cada tarifa o FSC solo vale el correo mas '
    'reciente, y en los hallazgos de FSC el campo destinos es obligatorio. '
    'No corras ningun comando ni modifiques nada mas: tu unica salida es ese '
    'archivo.'
)

# Pasada liviana para la bitacora: solo texto, sin skill ni adjuntos.
PROMPT_RESUMEN = (
    'Lee _agente_lux/por_resumir.json. Son correos del buzon de Daniela '
    '(FreightWise, carga aerea de flores desde Ecuador) que no traen tarifas. '
    'Escribe _agente_lux/resumenes.json con este formato exacto: '
    '{"correos": [{"mail_id": 12, "categoria": "operativo", "resumen": "...", '
    '"temas": ["..."], "requiere_accion": false}]}. Un objeto por cada correo. '
    'El resumen va en espanol, en una o dos frases, y tiene que decir QUE ES '
    'el correo: quien lo manda, para que, y que informa o pide. Ejemplo: '
    '"Fugran envia el certificado de fumigacion del contenedor de flores del '
    'viernes 5". No copies firmas, avisos del sistema ni el hilo citado. '
    'categoria es una de: tarifas, fsc, operativo, comercial, otro. temas son '
    'los pendientes concretos que quedan, si los hay. requiere_accion es true '
    'solo si Daniela tiene que hacer algo. No uses el skill agente-lux, no '
    'leas adjuntos ni corras comandos: tu unica salida es ese archivo.'
)


def _marcar(app, estado, mensaje, limpiar_solicitud=False):
    """Deja el estado visible en el portal."""
    from lux_portal.extensions import db
    from lux_portal.agente_lux import ingesta_local

    with app.app_context():
        cuenta = ingesta_local.cuenta_local()
        cuenta.refresh_estado = estado
        cuenta.refresh_mensaje = mensaje[:500]
        cuenta.vigia_visto = datetime.utcnow()
        if limpiar_solicitud:
            cuenta.refresh_solicitado = None
        db.session.commit()


def _latir(app, cuenta_id):
    """Marca que el vigia sigue vivo.

    Va como UPDATE puntual y no por el ORM a proposito: el ciclo de trabajo
    corre en otro hilo y escribe refresh_estado sobre la misma fila, asi que
    guardar el objeto entero desde aca podria pisarle el estado con un valor
    viejo."""
    from lux_portal.extensions import db

    with app.app_context():
        db.session.execute(
            db.text('UPDATE agente_cuenta SET vigia_visto = :ahora WHERE id = :id'),
            {'ahora': datetime.utcnow(), 'id': cuenta_id},
        )
        db.session.commit()


def _hay_solicitud(app):
    """(id de la cuenta, hay solicitud del boton, desde, hasta)."""
    from lux_portal.agente_lux import ingesta_local

    with app.app_context():
        cuenta = ingesta_local.cuenta_local()
        return (cuenta.id, cuenta.refresh_estado == 'solicitado',
                cuenta.refresh_desde, cuenta.refresh_hasta)


def _hay_envios(app):
    from lux_portal.agente_lux.models import AgenteEnvio

    with app.app_context():
        return AgenteEnvio.query.filter_by(estado='pendiente').count()


def _enviar(app):
    """Manda por Outlook lo que Daniela dejo en cola en la pestana Mails."""
    from lux_portal.agente_lux import envio_local

    with app.app_context():
        enviados, fallidos = envio_local.enviar_pendientes()
    log(f'Correos enviados por Outlook: {enviados}'
        + (f' ({fallidos} con error, ver la pestana Mails)' if fallidos else ''))


MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
         'jul', 'ago', 'sep', 'oct', 'nov', 'dic']


def _texto_rango(desde, hasta):
    """'6 sep' o 'del 17 ago al 5 sep', para los mensajes del portal."""
    def f(d):
        return f'{d.day} {MESES[d.month - 1]}'
    return f(desde) if desde == hasta else f'del {f(desde)} al {f(hasta)}'


def _args_rango(desde, hasta):
    return ['--desde', desde.isoformat(), '--hasta', hasta.isoformat()]


def _correr(comando, cwd, timeout):
    """Corre un comando y devuelve (ok, salida)."""
    import subprocess
    try:
        # stdin cerrado: el vigia corre de fondo y no tiene consola, asi que
        # cualquier subproceso que intente leer entrada se colgaria.
        r = subprocess.run(comando, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, encoding='utf-8', errors='replace',
                           stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, f'Se paso de {timeout} segundos.'
    salida = (r.stdout or '') + (r.stderr or '')
    return r.returncode == 0, salida.strip()


def _analizar(app, args, carpeta_proyecto, rango):
    """Exporta, le pide el analisis a Claude Code sin ventana, y carga.

    `rango` son los argumentos --desde/--hasta: solo se analizan los correos
    de esos dias.

    Va por tandas chicas a proposito: la primera corrida puede traer un mes
    entero de correos, y un lote enorme que se cae a la mitad pierde todo el
    trabajo. Cada tanda se carga y queda guardada antes de seguir.

    Claude Code corre con la suscripcion de Daniela, no con creditos de API:
    por eso el analisis pasa por el CLI local y no por el servidor."""
    import os
    import sys as _sys

    py = _sys.executable
    cli = os.path.join(carpeta_proyecto, 'agente_lux_cli.py')
    hallazgos = os.path.join(carpeta_proyecto, ARCHIVO_HALLAZGOS)
    resumenes = []

    # Por defecto Claude solo mira los correos con pinta de tarifas y las
    # respuestas a las solicitudes de Daniela; las reservas y lo operativo se
    # clasifican por el asunto sin pasar por el. Es la diferencia entre 8
    # tandas y 3 para un mes de correo. Con --resumir-todo vuelve a resumir
    # todo, a costa de la espera.
    exportar = [py, cli, 'exportar', '--max-correos', str(args.tanda)] + rango
    if not args.resumir_todo:
        exportar.append('--solo-tarifas')

    for tanda in range(1, args.max_tandas + 1):
        etiqueta = f'tanda {tanda}' if tanda > 1 else 'los correos'
        _marcar(app, 'analizando', f'Preparando {etiqueta}...')
        ok, salida_exp = _correr(exportar, carpeta_proyecto, 300)
        if not ok:
            raise RuntimeError(f'Fallo el exportar: {salida_exp[-400:]}')

        if 'No hay nada por analizar' in salida_exp:
            break

        quedan = 'para la siguiente tanda' in salida_exp

        # Un hallazgos.json viejo es peligroso: si Claude Code terminara sin
        # escribir el suyo, cargar subiria propuestas de otra tanda y daria
        # por revisados correos que nadie miro.
        if os.path.exists(hallazgos):
            os.remove(hallazgos)

        log(f'Analizando {etiqueta} con Claude Code...')
        _marcar(app, 'analizando',
                f'Claude Code esta revisando {etiqueta}'
                + (' (hay mas en cola)' if quedan else '') + '...')
        ok, salida = _correr(
            # Skill va en la lista porque el prompt le pide usar agente-lux;
            # sin eso no puede cargarlo y pierde las reglas de vigencia y FSC.
            #
            # Modelo y esfuerzo van explicitos: si no, manda la configuracion
            # personal de Daniela, que puede quedar en cualquier cosa despues
            # de un /model. Sonnet es el mismo modelo con el que se hizo el
            # primer analisis; el esfuerzo alto es el punto medio entre la
            # espera y el cuidado al leer una tabla.
            ['claude', '-p', PROMPT_ANALISIS,
             '--model', args.modelo, '--effort', args.esfuerzo,
             '--allowedTools', 'Skill', 'Read', 'Write', 'Glob', 'Grep',
             '--permission-mode', 'acceptEdits'],
            carpeta_proyecto, args.timeout_analisis)
        if not ok:
            raise RuntimeError(f'Fallo el analisis: {salida[-400:]}')
        if not os.path.exists(hallazgos):
            raise RuntimeError(
                'Claude Code termino sin escribir _agente_lux/hallazgos.json. '
                f'Lo ultimo que dijo: {salida[-300:]}')

        _marcar(app, 'analizando', f'Guardando los hallazgos de {etiqueta}...')
        ok, salida_car = _correr([py, cli, 'cargar'], carpeta_proyecto, 300)
        if not ok:
            raise RuntimeError(f'Fallo el cargar: {salida_car[-400:]}')

        primera = salida_car.splitlines()[0] if salida_car else ''
        log(f'{etiqueta}: {primera}')
        resumenes.append(primera)

        if not quedan:
            break

    if not resumenes:
        return 'Sin correos nuevos por analizar.'
    if len(resumenes) == 1:
        return resumenes[0]
    return f'{len(resumenes)} tandas analizadas. Ultima: {resumenes[-1]}'


def _resumir(app, args, carpeta_proyecto, rango):
    """Resumen rapido de los correos que no pasaron por el analisis de tarifas.

    Es una pasada aparte y mas liviana: solo texto, sin adjuntos, en tandas
    grandes. Daniela quiere saber de que es cada correo del dia sin tener
    que abrirlo, y meterlos todos en el analisis de tarifas lo hacia tres
    veces mas lento. Devuelve cuantos correos se resumieron."""
    import sys as _sys

    py = _sys.executable
    cli = os.path.join(carpeta_proyecto, 'agente_lux_cli.py')
    resumenes = os.path.join(carpeta_proyecto, ARCHIVO_RESUMENES)
    total = 0

    for tanda in range(1, args.max_tandas + 1):
        ok, salida_exp = _correr(
            [py, cli, 'exportar-resumen', '--max-correos', str(args.tanda_resumen)]
            + rango,
            carpeta_proyecto, 300)
        if not ok:
            raise RuntimeError(f'Fallo el exportar-resumen: {salida_exp[-400:]}')
        if 'No hay nada por resumir' in salida_exp:
            break

        m = re.search(r'(\d+) correo\(s\) por resumir', salida_exp)
        n = int(m.group(1)) if m else 0
        quedan = 'para la siguiente tanda' in salida_exp
        _marcar(app, 'analizando',
                f'Resumiendo {n} correo(s) para la bitacora'
                + (' (hay mas en cola)' if quedan else '') + '...')
        log(f'Resumiendo {n} correo(s) con Claude Code...')

        if os.path.exists(resumenes):
            os.remove(resumenes)
        ok, salida = _correr(
            ['claude', '-p', PROMPT_RESUMEN,
             '--model', args.modelo, '--effort', args.esfuerzo_resumen,
             '--allowedTools', 'Read', 'Write',
             '--permission-mode', 'acceptEdits'],
            carpeta_proyecto, args.timeout_resumen)
        if not ok:
            raise RuntimeError(f'Fallo el resumen: {salida[-400:]}')
        if not os.path.exists(resumenes):
            raise RuntimeError(
                'Claude Code termino sin escribir _agente_lux/resumenes.json. '
                f'Lo ultimo que dijo: {salida[-300:]}')

        ok, salida_car = _correr([py, cli, 'cargar-resumen'], carpeta_proyecto, 300)
        if not ok:
            raise RuntimeError(f'Fallo el cargar-resumen: {salida_car[-400:]}')
        log(salida_car.splitlines()[0] if salida_car else 'Resumenes cargados.')
        total += n

        if not quedan:
            break

    return total


def _leer(app, args, motivo, desde, hasta):
    """Lee el buzon y, si corresponde, analiza. Deja todo visible en el portal.

    `desde` y `hasta` son las fechas (date) del rango: solo esos dias se
    leen, analizan y resumen."""
    import os
    from lux_portal.agente_lux import ingesta_local

    carpeta_proyecto = os.path.dirname(os.path.abspath(__file__))
    rango = _args_rango(desde, hasta)
    texto_rango = _texto_rango(desde, hasta)

    try:
        _marcar(app, 'corriendo', f'Leyendo tu Outlook ({texto_rango})...')
        with app.app_context():
            cuenta = ingesta_local.cuenta_local()
            stats = ingesta_local.ingerir(
                cuenta,
                desde=desde,
                hasta=hasta,
                carpeta=args.carpeta,
                limite=args.limite,
                recursivo=not args.sin_subcarpetas,
            )
        resumen = f'[{texto_rango}] ' + ingesta_local.resumen_texto(stats)
        log(f'{motivo} ({texto_rango}): {ingesta_local.resumen_texto(stats)} '
            f'({stats["pendientes"]} por analizar en el rango)')

        if args.analizar and stats['pendientes']:
            resumen += ' ' + _analizar(app, args, carpeta_proyecto, rango)

        # La bitacora va despues de las tarifas, que son lo que importa. Y
        # si falla no tumba el ciclo: las tarifas ya quedaron cargadas y los
        # correos sin resumen se reintentan en la siguiente vuelta.
        if args.analizar:
            try:
                resumidos = _resumir(app, args, carpeta_proyecto, rango)
            except Exception as exc:
                log(f'Fallo el resumen rapido: {exc}')
                resumen += (' El resumen de los otros correos fallo; se '
                            'reintenta en el proximo ciclo.')
            else:
                if resumidos:
                    resumen += f' {resumidos} correo(s) resumidos para la bitacora.'

        _marcar(app, 'ok', resumen, limpiar_solicitud=True)
        log(resumen)
        return stats

    except Exception as exc:
        log(f'ERROR en {motivo}: {exc}')
        try:
            _marcar(app, 'error', str(exc), limpiar_solicitud=True)
        except Exception:
            pass
        return None


def main():
    parser = argparse.ArgumentParser(description='Vigia local de Agente Lux.')
    parser.add_argument('--db', help='URL de PostgreSQL (por defecto usa .env).')
    parser.add_argument('--auto', type=int, default=20,
                        help='Releer solo cada N minutos. 0 = solo con el boton.')
    parser.add_argument('--carpeta', default='Inbox',
                        help='Carpeta a leer. Por defecto Inbox con subcarpetas.')
    parser.add_argument('--sin-subcarpetas', action='store_true',
                        dest='sin_subcarpetas')
    parser.add_argument('--limite', type=int, default=500)
    parser.add_argument('--sin-analisis', action='store_false', dest='analizar',
                        help='Solo bajar los correos, sin pedirle el analisis '
                             'a Claude Code.')
    # 12 y no 25: como ya solo van a Claude los correos con tarifas, cada uno
    # trae adjuntos que leer, y 25 de esos rozaban el tope de tiempo.
    parser.add_argument('--tanda', type=int, default=12,
                        help='Correos por tanda de analisis (por defecto 12).')
    parser.add_argument('--max-tandas', type=int, default=12, dest='max_tandas',
                        help='Tope de tandas por ciclo, para no quedarse toda '
                             'la noche vaciando una cola vieja.')
    parser.add_argument('--timeout-analisis', type=int, default=1800,
                        dest='timeout_analisis',
                        help='Segundos maximos por tanda (por defecto 30 min).')
    parser.add_argument('--resumir-todo', action='store_true', dest='resumir_todo',
                        help='Pasar tambien las reservas y los correos operativos '
                             'por Claude Code para que los resuma en la bitacora. '
                             'Mas completo, pero unas tres veces mas lento.')
    parser.add_argument('--modelo', default='sonnet',
                        help='Modelo de Claude Code para el analisis (por defecto sonnet).')
    # Alto y no medio: a Daniela le preocupa que una lectura ligera se coma un
    # numero de una tabla, y la ganancia grande de tiempo ya viene de no
    # pasarle las reservas a Claude, no de este ajuste.
    parser.add_argument('--esfuerzo', default='high',
                        help='Nivel de esfuerzo del modelo (por defecto high).')
    parser.add_argument('--tanda-resumen', type=int, default=40, dest='tanda_resumen',
                        help='Correos por tanda del resumen rapido (por defecto 40).')
    parser.add_argument('--timeout-resumen', type=int, default=600, dest='timeout_resumen',
                        help='Segundos maximos por tanda de resumen (por defecto 10 min).')
    parser.add_argument('--esfuerzo-resumen', default='medium', dest='esfuerzo_resumen',
                        help='Esfuerzo del modelo para los resumenes (por defecto medium: '
                             'es solo texto, sin tablas que leer).')
    parser.add_argument('--instalar-tarea', action='store_true',
                        dest='instalar_tarea',
                        help='Programar el vigia para que arranque con Windows.')
    args = parser.parse_args()

    if args.instalar_tarea:
        instalar_tarea()
        return

    # Primera linea del log antes de cualquier cosa que pueda fallar, para
    # poder distinguir "no arranco" de "arranco y se cayo".
    log('Vigia iniciando...')

    if not _tomar_lock():
        log('Ya hay otro vigia corriendo (ver _agente_lux/vigia.lock). '
            'Este se cierra para no leer el buzon dos veces.')
        return
    if os.path.exists(RUTA_PARAR):
        os.remove(RUTA_PARAR)

    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux import ingesta_local

    # Outlook tiene que estar abierto de verdad, con ventana. Si el vigia lo
    # levanta por COM sin ventana, queda bajando solo encabezados y el buzon
    # que ve no es el buzon real: asi estuvo ciego a 170 correos.
    if _abrir_outlook_si_hace_falta():
        log('Outlook estaba cerrado: lo abro y espero a que arranque...')
        time.sleep(20)
    try:
        _contestar_dialogos_outlook()
    except Exception as exc:
        log(f'No pude revisar los cuadros de Outlook: {exc}')

    # Verifica Outlook antes de entrar al bucle, para fallar con un mensaje
    # claro en vez de repetir el mismo error cada 15 segundos.
    #
    # Con timeout porque las llamadas COM pueden colgarse indefinidamente si
    # quedo una instancia de Outlook trabada (pasa cuando se mata un proceso
    # a mitad de una operacion). Sin esto el vigia se queda mudo para siempre
    # y desde el portal parece que la PC simplemente no escucha.
    from lux_portal.agente_lux import outlook_local

    resultado = {}

    def comprobar():
        import pythoncom
        pythoncom.CoInitialize()
        try:
            # Recien abierto, Outlook tarda en registrarse como servidor COM
            # y la primera llamada falla con "Error en la ejecucion de
            # servidor" (paso al arrancar con Windows: abrio Outlook y 50 s
            # despues se rindio). Se reintenta un rato antes de darse por
            # vencido.
            ultimo = None
            for _ in range(40):          # hasta 10 minutos
                try:
                    resultado['correo'] = outlook_local.cuenta_principal()
                    resultado['modo'] = outlook_local.modo_conexion()
                    return
                except Exception as exc:
                    ultimo = exc
                    time.sleep(15)
            resultado['error'] = str(ultimo)
        finally:
            pythoncom.CoUninitialize()

    hilo = threading.Thread(target=comprobar, daemon=True)
    hilo.start()
    hilo.join(timeout=90)

    # Si la llamada se queda colgada, NO se sale: salir con una llamada COM a
    # medias deja a Outlook zombi (paso dos veces, y solo lo arregla un
    # reinicio). Se espera a que Outlook termine de abrir, avisando cada
    # minuto para que el log diga que esta pasando.
    while hilo.is_alive():
        try:
            if _contestar_dialogos_outlook():
                hilo.join(timeout=30)
                continue
        except Exception as exc:
            log(f'No pude revisar los cuadros de Outlook: {exc}')
        log('Outlook todavia no responde (suele estar abriendo o reparando el '
            'buzon). Sigo esperando; si pasa de 10 minutos, cierra Outlook a '
            'mano y vuelve a abrirlo.')
        hilo.join(timeout=60)

    if 'error' in resultado:
        log(resultado['error'])
        sys.exit(1)

    correo = resultado.get('correo') or '(cuenta sin identificar)'

    log(f'Vigia arrancado para {correo}')
    codigo, texto_modo = resultado.get('modo') or (None, 'desconocido')
    if codigo in outlook_local.MODOS_SANOS:
        log(f'Outlook conectado: {texto_modo}')
    else:
        log(f'OJO: Outlook esta "{texto_modo}". Puede que el buzon no este '
            f'completo hasta que termine de sincronizar; si dura, abre '
            f'Outlook a mano y revisa que no este en "Trabajar sin conexion".')
    log(f'Carpeta: {args.carpeta}'
        + ('' if args.sin_subcarpetas else ' (con subcarpetas)'))
    log('Relectura automatica: '
        + (f'cada {args.auto} min' if args.auto else 'desactivada'))
    log('Escuchando el boton del portal. Ctrl+C para parar.')

    from lux_portal.agente_lux.models import ahora_ecuador

    ultimo_auto = datetime.utcnow() - timedelta(minutes=args.auto or 0)
    # El ciclo completo puede tardar media hora entre leer y analizar. Corre en
    # otro hilo para que el latido no se congele: si se congelara, el portal
    # diria "tu PC no esta escuchando" justo mientras esta trabajando.
    trabajando = threading.Event()

    def en_hilo_com(fn):
        """Corre fn en otro hilo con COM inicializado y el candado puesto.

        COM hay que inicializarlo en cada hilo que lo use: sin esto, Outlook
        falla con "No se ha llamado a CoInitialize" apenas el trabajo salio
        del hilo principal."""
        def tarea():
            import pythoncom
            pythoncom.CoInitialize()
            try:
                fn()
            except Exception as exc:
                log(f'ERROR: {exc}')
            finally:
                pythoncom.CoUninitialize()
                trabajando.clear()

        threading.Thread(target=tarea, daemon=True).start()

    def lanzar(motivo, desde=None, hasta=None):
        if trabajando.is_set():
            return
        trabajando.set()
        # Sin rango pedido, el dia de hoy: es lo que Daniela quiere ver y lo
        # que hace corto el ciclo. Lo de otras fechas espera a que ella elija
        # ese rango con el boton del portal.
        hoy = ahora_ecuador().date()
        desde = desde or hoy
        hasta = hasta or hoy
        en_hilo_com(lambda: _leer(app, args, motivo, desde, hasta))

    def lanzar_envios():
        if trabajando.is_set():
            return
        trabajando.set()
        en_hilo_com(lambda: _enviar(app))

    try:
        while True:
            if os.path.exists(RUTA_PARAR) and not trabajando.is_set():
                log('Parado por pedido (archivo _agente_lux/parar).')
                os.remove(RUTA_PARAR)
                break
            try:
                cuenta_id, solicitado, desde, hasta = _hay_solicitud(app)
                _latir(app, cuenta_id)

                # Los envios de la pestana Mails van primero: son un clic de
                # Daniela esperando, y tardan segundos.
                if not trabajando.is_set() and _hay_envios(app):
                    lanzar_envios()

                elif solicitado:
                    lanzar('boton del portal', desde, hasta)
                    ultimo_auto = datetime.utcnow()

                elif args.auto and not trabajando.is_set() and (
                        datetime.utcnow() - ultimo_auto
                        >= timedelta(minutes=args.auto)):
                    # Con ultimo_auto arrancando "vencido", la primera
                    # lectura sale enseguida en vez de esperar 20 minutos.
                    lanzar('relectura automatica')
                    ultimo_auto = datetime.utcnow()

            except Exception:
                # Un fallo de red no puede tumbar el vigia: se reintenta en el
                # siguiente latido.
                log('Fallo el latido, reintentando:\n' + traceback.format_exc())

            time.sleep(LATIDO_SEGUNDOS)

    except KeyboardInterrupt:
        log('Vigia detenido.')
    finally:
        _soltar_lock()


if __name__ == '__main__':
    main()
