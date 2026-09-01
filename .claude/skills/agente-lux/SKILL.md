---
name: agente-lux
description: Analiza los correos que Agente Lux descargó del buzón de Microsoft 365 y genera las actualizaciones de tarifas netas, FSC y cargos para que Daniela las apruebe en el portal. Úsalo cuando pida "revisa mis correos", "actualiza las tarifas", "qué llegó por correo", "corre el agente" o invoque /agente-lux.
---

# Agente Lux — análisis local de correos

El portal en Railway descarga los correos; **el análisis lo haces tú aquí**, con la
suscripción de Claude Code (no con la API). Nada se aplica solo: tu trabajo termina
en un archivo de propuestas que Daniela aprueba desde el portal.

## Flujo

```
1. python agente_lux_cli.py exportar     -> _agente_lux/pendientes.json
2. (tú) leer, comparar y decidir         -> _agente_lux/hallazgos.json
3. python agente_lux_cli.py cargar       -> sube las propuestas al portal
```

Si `exportar` dice que no hay correos pendientes, avísale que primero le dé
**Refresh correos** en el portal (`/agente-lux/`). No inventes hallazgos.

`DATABASE_URL` debe apuntar al Postgres de Railway. Si no está, pásalo con `--db`.

## Qué contiene `pendientes.json`

- `correos[]` — asunto, remitente, cuerpo en texto plano y rutas a los adjuntos
  ya decodificados en `_agente_lux/adjuntos/` (imágenes y PDFs). **Léelos con la
  herramienta Read**: casi siempre la tabla de tarifas viene en una imagen, no en
  el texto.
- `estado_actual` — la foto de lo que hay hoy en producción:
  - `cotizaciones[]` con `cot_id`, `destino` y los `kg_rates` vigentes por aerolínea
  - `fsc_reglas[]` con `regla_id`, `aerolinea`, `destinos` y `fsc`
  - `cargos[]` y `dias_salida[]`

Siempre compara contra `estado_actual`. Un hallazgo sin valor actual al lado no
sirve: Daniela necesita ver "de 3.00 a 2.85", no solo "2.85".

## Reglas que no se negocian

**FSC — el error más caro.** `detalle.destinos` es obligatorio y explícito:
- `[]` significa **TODOS los destinos de esa aerolínea**.
- `["MAD","LHR"]` significa solo esos trayectos.

Si el correo dice "new fuel surcharge for European destinations", NO pongas `[]`:
lista los IATA de Europa que esa aerolínea maneja según `estado_actual`. Ante la
duda, usa destinos específicos y `confianza: "baja"` — es más fácil que Daniela
amplíe el alcance a que descubra tarde que se aplicó de más.

Antes de crear una regla de FSC nueva, busca en `estado_actual.fsc_reglas` si ya
existe una con esos mismos destinos y reusa su `regla_id`.

**Días de salida y cargos.** Los días de salida (`tipo: "dias"`) nunca se aplican
solos: el portal los muestra como aviso. Repórtalos igual, pero no los presentes
como si fueran a cambiar algo.

**Costo operativo y margen.** No los toques desde aquí. El portal ya alerta solo
cuando quedan por debajo de los mínimos (0.09 de operativo; 0.10 de margen en
Europa/Asia/Medio Oriente/Oceanía; Australia va con 0.19 y 0.09). Tu parte es la
tarifa neta y el FSC.

**Nombres de aerolínea canónicos.** Sin sufijos: `AVIANCA`, no "Avianca Cargo" ni
"AVIANCA FREIGHTER". `AIR CANADA` y `COPA AIRLINES` van con esa forma exacta.

## Formato de salida

El formato completo, campo por campo, está en el docstring de
`agente_lux_cli.py` — léelo antes de escribir el archivo. En resumen:

```json
{
  "correos":   [{"mail_id":12, "categoria":"tarifas", "resumen":"...",
                 "temas":["..."], "requiere_accion":true}],
  "hallazgos": [{"mail_id":12, "tipo":"tarifa", "aerolinea":"AVIANCA",
                 "destino":"MAD", "descripcion":"...", "valor_actual":"3.00",
                 "valor_nuevo":"2.85", "confianza":"alta", "cita":"...",
                 "detalle":{"cot_id":7, "kg":"+100", "tarifa_nueva":2.85}}]
}
```

- Un objeto en `correos` por **cada** correo de `pendientes.json`, tenga o no
  hallazgos. Los que no menciones quedan marcados como "sin novedades".
- `resumen` es lo que Daniela lee en la Bitácora: qué dijo el correo, en una o dos
  frases, en español. `temas` son los pendientes concretos que quedaron.
- `cita` es el fragmento textual del correo que respalda el número. Sin cita, ella
  no puede verificar rápido — ponla siempre que exista.
- `confianza`: `alta` solo si el número está explícito y sin ambigüedad de alcance.

`cargar` valida el archivo entero antes de escribir nada. Si te reporta errores,
corrígelos y vuelve a correrlo — no hay carga parcial.

## Al terminar

Dile cuántos hallazgos quedaron, cuáles traen alerta, y que entre a
`/agente-lux/` a revisarlos. No prometas que algo "ya quedó actualizado": hasta
que ella no aprueba y aplica en el portal, no se tocó ninguna tarifa.
