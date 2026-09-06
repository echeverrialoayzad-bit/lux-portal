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
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

# Reutiliza la conexion y el arranque de la app del CLI.
from agente_lux_cli import ARCHIVO_HALLAZGOS, crear_app, resolver_db

LATIDO_SEGUNDOS = 15

# Bitacora en disco ademas de la consola: cuando el vigia corre como tarea
# programada nadie ve la ventana, y un "tu PC no esta escuchando" sin un log
# atras es imposible de diagnosticar.
RUTA_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '_agente_lux', 'vigia.log')


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
    # newline='' para que Python no convierta el \r\n en \r\r\n.
    with open(lanzador, 'w', encoding='ascii', newline='') as fh:
        fh.write('@echo off\r\n'
                 'cd /d "%~dp0.."\r\n'
                 f'"{python}" agente_lux_watcher.py\r\n')
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
    from lux_portal.agente_lux import ingesta_local

    with app.app_context():
        cuenta = ingesta_local.cuenta_local()
        return cuenta.id, cuenta.refresh_estado == 'solicitado'


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


def _analizar(app, args, carpeta_proyecto):
    """Exporta, le pide el analisis a Claude Code sin ventana, y carga.

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
    exportar = [py, cli, 'exportar', '--max-correos', str(args.tanda)]
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


def _leer(app, args, motivo):
    """Lee el buzon y, si corresponde, analiza. Deja todo visible en el portal."""
    import os
    from lux_portal.agente_lux import ingesta_local

    carpeta_proyecto = os.path.dirname(os.path.abspath(__file__))

    try:
        _marcar(app, 'corriendo', 'Leyendo tu Outlook...')
        with app.app_context():
            cuenta = ingesta_local.cuenta_local()
            stats = ingesta_local.ingerir(
                cuenta,
                carpeta=args.carpeta,
                limite=args.limite,
                recursivo=not args.sin_subcarpetas,
            )
        resumen = ingesta_local.resumen_texto(stats)
        log(f'{motivo}: {resumen} ({stats["pendientes"]} por analizar)')

        if args.analizar and stats['pendientes']:
            resumen += ' ' + _analizar(app, args, carpeta_proyecto)

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
    parser.add_argument('--instalar-tarea', action='store_true',
                        dest='instalar_tarea',
                        help='Programar el vigia para que arranque con Windows.')
    args = parser.parse_args()

    if args.instalar_tarea:
        instalar_tarea()
        return

    app = crear_app(resolver_db(args))
    from lux_portal.extensions import db
    from lux_portal.agente_lux import ingesta_local

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
            resultado['correo'] = outlook_local.cuenta_principal()
        except Exception as exc:
            resultado['error'] = str(exc)
        finally:
            pythoncom.CoUninitialize()

    hilo = threading.Thread(target=comprobar, daemon=True)
    hilo.start()
    hilo.join(timeout=60)

    if hilo.is_alive():
        log('Outlook no responde: la llamada se quedo colgada mas de un minuto.\n'
            'Suele pasar cuando quedo una instancia trabada. Prueba:\n'
            '  1. Cerrar Outlook y volver a abrirlo.\n'
            '  2. Si sigue igual, reiniciar la PC.\n'
            'Despues vuelve a arrancar el vigia.')
        sys.exit(1)
    if 'error' in resultado:
        log(resultado['error'])
        sys.exit(1)

    correo = resultado.get('correo') or '(cuenta sin identificar)'

    log(f'Vigia arrancado para {correo}')
    log(f'Carpeta: {args.carpeta}'
        + ('' if args.sin_subcarpetas else ' (con subcarpetas)'))
    log('Relectura automatica: '
        + (f'cada {args.auto} min' if args.auto else 'desactivada'))
    log('Escuchando el boton del portal. Ctrl+C para parar.')

    ultimo_auto = datetime.utcnow()
    # El ciclo completo puede tardar media hora entre leer y analizar. Corre en
    # otro hilo para que el latido no se congele: si se congelara, el portal
    # diria "tu PC no esta escuchando" justo mientras esta trabajando.
    trabajando = threading.Event()

    def lanzar(motivo):
        if trabajando.is_set():
            return
        trabajando.set()

        def tarea():
            # COM hay que inicializarlo en cada hilo que lo use: sin esto,
            # Outlook falla con "No se ha llamado a CoInitialize" apenas el
            # trabajo salio del hilo principal.
            import pythoncom
            pythoncom.CoInitialize()
            try:
                _leer(app, args, motivo)
            finally:
                pythoncom.CoUninitialize()
                trabajando.clear()

        threading.Thread(target=tarea, daemon=True).start()

    try:
        while True:
            try:
                cuenta_id, solicitado = _hay_solicitud(app)
                _latir(app, cuenta_id)

                if solicitado:
                    lanzar('boton del portal')
                    ultimo_auto = datetime.utcnow()

                elif args.auto and not trabajando.is_set() and (
                        datetime.utcnow() - ultimo_auto
                        >= timedelta(minutes=args.auto)):
                    lanzar('relectura automatica')
                    ultimo_auto = datetime.utcnow()

            except Exception:
                # Un fallo de red no puede tumbar el vigia: se reintenta en el
                # siguiente latido.
                log('Fallo el latido, reintentando:\n' + traceback.format_exc())

            time.sleep(LATIDO_SEGUNDOS)

    except KeyboardInterrupt:
        log('Vigia detenido.')


if __name__ == '__main__':
    main()
