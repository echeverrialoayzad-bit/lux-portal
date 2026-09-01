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
"""

import argparse
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

# Reutiliza la conexion y el arranque de la app del CLI.
from agente_lux_cli import crear_app, resolver_db

LATIDO_SEGUNDOS = 15


def _ahora():
    return datetime.now().strftime('%H:%M:%S')


def log(mensaje):
    print(f'[{_ahora()}] {mensaje}', flush=True)


def instalar_tarea():
    """Registra una tarea de Windows que arranca el vigia al iniciar sesion."""
    import os
    import subprocess

    script = os.path.abspath(__file__)
    carpeta = os.path.dirname(script)
    comando = f'cmd /c cd /d "{carpeta}" && "{sys.executable}" "{script}"'

    resultado = subprocess.run(
        ['schtasks', '/Create', '/TN', 'Agente Lux - vigia',
         '/TR', comando, '/SC', 'ONLOGON', '/RL', 'LIMITED', '/F'],
        capture_output=True, text=True,
    )
    if resultado.returncode == 0:
        print('Tarea creada: el vigia va a arrancar solo cada vez que inicies '
              'sesion en Windows.')
        print('Para quitarla:  schtasks /Delete /TN "Agente Lux - vigia" /F')
    else:
        print('No se pudo crear la tarea:')
        print(resultado.stdout or resultado.stderr)
        sys.exit(1)


PROMPT_ANALISIS = (
    'Usa el skill agente-lux. Lee _agente_lux/pendientes.json y los adjuntos '
    'que referencia, comparalos contra estado_actual, y escribe '
    '_agente_lux/hallazgos.json con el formato del docstring de '
    'agente_lux_cli.py. Recuerda: de cada tarifa o FSC solo vale el correo mas '
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
    resumenes = []

    for tanda in range(1, args.max_tandas + 1):
        etiqueta = f'tanda {tanda}' if tanda > 1 else 'los correos'
        _marcar(app, 'analizando', f'Preparando {etiqueta}...')
        # Sin --solo-tarifas a proposito: la bitacora necesita el resumen de
        # todos los correos, no solo los de tarifas. Los que no son de tarifas
        # salen rapido igual, porque de esos no se vuelcan los adjuntos.
        ok, salida_exp = _correr(
            [py, cli, 'exportar', '--max-correos', str(args.tanda)],
            carpeta_proyecto, 300)
        if not ok:
            raise RuntimeError(f'Fallo el exportar: {salida_exp[-400:]}')

        if 'No hay nada por analizar' in salida_exp:
            break

        quedan = 'para la siguiente tanda' in salida_exp

        log(f'Analizando {etiqueta} con Claude Code...')
        _marcar(app, 'analizando',
                f'Claude Code esta revisando {etiqueta}'
                + (' (hay mas en cola)' if quedan else '') + '...')
        ok, salida = _correr(
            # Skill va en la lista porque el prompt le pide usar agente-lux;
            # sin eso no puede cargarlo y pierde las reglas de vigencia y FSC.
            ['claude', '-p', PROMPT_ANALISIS,
             '--allowedTools', 'Skill', 'Read', 'Write', 'Glob', 'Grep',
             '--permission-mode', 'acceptEdits'],
            carpeta_proyecto, args.timeout_analisis)
        if not ok:
            raise RuntimeError(f'Fallo el analisis: {salida[-400:]}')

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
    parser.add_argument('--tanda', type=int, default=25,
                        help='Correos por tanda de analisis (por defecto 25).')
    parser.add_argument('--max-tandas', type=int, default=12, dest='max_tandas',
                        help='Tope de tandas por ciclo, para no quedarse toda '
                             'la noche vaciando una cola vieja.')
    parser.add_argument('--timeout-analisis', type=int, default=900,
                        dest='timeout_analisis',
                        help='Segundos maximos por tanda (por defecto 15 min).')
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
    from lux_portal.agente_lux import outlook_local
    try:
        correo = outlook_local.cuenta_principal()
    except outlook_local.OutlookNoDisponible as exc:
        sys.exit(f'{exc}')

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
                log('Fallo el latido, reintentando:')
                traceback.print_exc()

            time.sleep(LATIDO_SEGUNDOS)

    except KeyboardInterrupt:
        log('Vigia detenido.')


if __name__ == '__main__':
    main()
