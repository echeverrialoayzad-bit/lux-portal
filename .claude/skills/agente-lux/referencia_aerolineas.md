# Referencia: cómo escribe cada aerolínea sus tarifas

Sacada de los 119 correos de tarifas y FSC que llegaron al buzón de Daniela
entre agosto y septiembre de 2026. Léela completa antes de analizar: dice
quién es quién, qué significa cada abreviatura y qué campo del portal
corresponde a cada cifra. Cuando un correo no calce con lo de aquí, dilo en
la `descripcion` en vez de adivinar.

## Quién es quién (remitente → aerolínea)

El remitente manda sobre la carpeta de Outlook. Las reglas de Outlook a veces
archivan mal (los correos de ECS Group caen en la carpeta AERCARIBE, y son de
QATAR).

| Dominio / persona | Aerolínea en el portal | Notas |
|---|---|---|
| `@ecsgroup.aero` (Eduardo Alvarez, Susana Castillo, "CSQR - WGS EC", "QATAR - WGS EC") | **QATAR** | GSA ECS Group. Aunque esté en la carpeta AERCARIBE. |
| `@primeair.com.ec` (Lorena Molestina, Ismael Guayasamin, Ana Emilia Garces, José Luis Sancho, Andrés Guerrero) y `@primeair.aero` (Jose Luis Suarez, cartas de fuel) | **EMIRATES** | GSA Prime Air. Ojo: Prime Air también es GSA de **ATLAS** (Carolina Aimara, `salesatlasec@`): lo decide la carpeta (ATLAS o EMIRATES), el remitente o el texto. |
| `@fenixecuador.com` (Catalina Castillo, "GSA for ATLAS AIR UIO") | **ATLAS** | Fénix Ecuador lleva Atlas a MIA. Cotiza "all in + AWC": FSC 0 en esa ruta. |
| `@kales.com` ("KASEC-CUSTOMERCARE.UIO", David Manzano, Colleen Aguilar) | **TURKISH** | GSA Kales. |
| `@flyus.aero` (Lissette Pereira, "AC Cargo UIO") | **AIR CANADA** | GSA Flyus. |
| `@transoceanica.com.ec` Karina Cazar, Joe Proaño | **LUFTHANSA** | Transoceánica representa a dos aerolíneas: mira la persona. |
| `@transoceanica.com.ec` Karen Guevara, Bolívar Pérez, Ana Cabezas; o cualquier correo con el link `bit.ly/laratesec2024` o "$/kg CHW + $43 MCC" | **LAN** (LATAM Cargo) | Mismo GSA, otra aerolínea. |
| `@gsaforce.com` (Diana Cabrera, Diana Rodriguez, CathayECU) | **CATHAY** | GSA Force. |
| `@copaair.com` (Evelyn Vargas) | **COPA AIRLINES** | |
| `@delta.com` David Vargas ("GSSA for Delta Cargo") | **DELTA** | Jean Boada (`@delta.com`, Handsmart) manda confirmaciones de reserva: operativo, no tarifas. |
| `@dhl.com` (Mayari Mafla, Mateo Ayala, "DHL Aviation / TRANSAM") | **DHL** | |
| `@avianca.com` (Jose Grijalva) | **AVIANCA** | |
| `@mawneyecuador.com` (María Avila, Mawney Associates) | **AIR EUROPA** | Vuelan sobre Aeromexico; "UX" = Air Europa. |
| `@solent.com` (Cecilia Acosta) | **SOLENT** | Solent Air, conexión LOT vía MIA. |
| `@freight-wise.com` (Pahola, Ignacio, Johana, Daniela, Mónica, Felipe) | (reenvío interno) | Un "RV:" o "FW:" reenvía el comunicado de una aerolínea: la aerolínea sale del asunto y el cuerpo citado. Casi siempre es copia de un correo que ya llegó por otra vía: no lo propongas dos veces. |

## Qué significa cada abreviatura

| En el correo | Qué es | Dónde va en el portal |
|---|---|---|
| **AWC** ("+25awc", "AWC 35.00", "AWC $45.00") | Air Waybill Charge, cargo fijo por guía | Cargo **Due Carrier** de esa aerolínea (Emirates 25, Cathay 25, Copa 25, Delta 25, Turkish 35, Qatar 45). |
| **MCC** en LAN ("$ 3.05/kg CHW + $43.00 MCC") | Cargo fijo por embarque de LATAM | Cargo **Due Carrier** de LAN (43). |
| **MCC** en DHL ("$20 neto - Cuarentena") | Cuarentena vía PTY, solo cuando aplica | No es cargo fijo: no lo cargues. |
| **MR** en Lufthansa ("+ $1.20 MR (x CWT)") | Fuel surcharge por peso cobrable | **FSC** de Lufthansa (1.20). |
| **MYC** en Air Canada ("+ MYC USD 0.27 fsc") | Fuel surcharge, va en el Due Carrier, sobre peso bruto | **FSC** de Air Canada, por región. |
| **AFS** en DHL | Fuel surcharge por región | **FSC** de DHL: reglas "Interregional America", "VCP, EZE y SCL", "Intercontinental Europa Asia Australia". |
| **FSC** (Emirates, tablas) | Fuel surcharge | **FSC**. Emirates: la cifra "SkyFresh" de la carta es la de flores; la de "other commodities" no aplica. |
| **SSC** ("0.03ssc" Copa, "SSC 0,05" Air Europa) | Security surcharge por kilo | En Copa, Daniela lo suma al FSC de la cotización: FSC 0.63 = fuel 0.60 + SSC 0.03. No lo propongas aparte ni propongas el fuel solo. |
| **ALL IN** ("2.70 All in", "$3.23 ALL IN") | Tarifa con el fuel ya incluido | Tarifa neta tal cual y FSC 0. Nunca le sumes un FSC aparte. |
| **CC** en Qatar ("CC: $15.00 Transmisión manual") | Cargo por transmisión manual de AWB | Cargo **CC (Carrier Charges)** de Qatar. |
| **CH / CHC** en Lufthansa ("+ $40 CH") | Carrier charges | Cargo **CC (Carrier Charges)** de Lufthansa (40). Mismo cargo con otro nombre. |
| **PA** en Lufthansa ("$50 PA perishable fee") | Fee de perecibles por guía | Cargo **Due Carrier** de Lufthansa (50). Mismo cargo con otro nombre. |
| **PCG** en Lufthansa ("$12 PCG xc/hawb") | Fee por guía hija | No está en el portal; propónlo solo como aviso. |
| **CG** en Qatar ("CG: $3.00 transmisión electrónica") | Fee por guía | Cargo **CG HAWB C/U** de Qatar (3). |
| **CG/(MAWB)** y **CB/(HAWB)** en Emirates | Fees por guía master y por guía hija | Cargos **CG MAWB** (10) y **CB HAWB** (0.25) de Emirates. |
| **FWB / FHL** en DHL ("$2,00 por transmisión") | Fees por transmisión de guía master / hija | Cargos nuevos de DHL si Daniela los quiere; propónlos como cargo con esos nombres. |
| **Fee 2 usd/Mawb for China and Japan** (Cathay) | Fee por guía solo a China y Japón | Ya existe como cargo "Fee" 2.00 de Cathay. No lo repitas. |
| "+ USD 18.00 HAWB si la aerolínea realiza la transmisión" (Air Canada) | Texto de la firma de Flyus, va en todos sus correos | No es un cargo nuevo: ignóralo. |
| **DGR** ("$100 por UN", "$135 + $80 por UN") | Mercancía peligrosa | Según el caso, nunca cargo fijo. |
| **DI, BF, DF, e-AWB fee** (Qatar), **Collect Fee / Disbursement** (Avianca), penalidades (Turkish) | Fees condicionales | Según el caso, nunca cargo fijo. |
| **CHW / CWT / x cwght** | Chargeable weight (peso cobrable) | Es "por kilo". |
| **ASPER100** (Emirates) | Menos de 100 kg se cobra como 100 | Tarifa aplica desde 100 kg: tramo +100. |
| **M / Min / Mínimum** | Mínimo por guía en USD (200, 350, 595…) | No es tarifa por kilo. No lo propongas como tramo. |
| **N / Normal 18-44 kg / Tarifa 40-99kg** | Tarifa por kilo para menos de 45 (o 100) kg | El portal no maneja esos tramos: solo menciónalo. |
| **Q45 / Q100 / Q300 / Q500** (Lufthansa), **45.0 / 100.0 / 300.0 / 500.0 / 1,000.0** (Air Canada), **+45kgs / +100 kgs / +500kgs / +1000kgs** (Qatar), **-45 / +45 / +100 / +500 / +1000** (DHL), **100 KILOS / 300 KILOS…** (Solent) | Tramos de peso | `kg`: "+45", "+100", "+300", "+500", "+1000". |
| **PAX / CAO** (Avianca, LATAM) | Avión de pasajeros / carguero, tarifas distintas | Dilo en la descripción; el portal hoy no distingue el tipo de avión. |
| **TT** ("+2 ó +3", "TT 2D", "3-4 días") | Tiempo de tránsito | Solo informativo. |
| **Salidas 2-3-4-5-7** (Emirates) | Días de la semana, 1 = lunes: martes, miércoles, jueves, viernes, domingo | Hallazgo `dias`, solo aviso. |
| **D1/D2/D3/D4/D5/D6** (DHL) | Lunes a sábado | Hallazgo `dias`, solo aviso. |
| "tarifa dinámica", "sujeta a disponibilidad" | La tarifa puede cambiar | Igual se propone; es la tarifa vigente hoy. |
| "no llegamos", "no operamos", "no contamos con llegada" | Sin servicio a ese destino | Solo resumen del correo, sin hallazgo. |

## Cómo escribe cada una

**AIR CANADA (Flyus).** Un bloque por destino: "Días de vuelo: viernes y sábado / Ruta UIO YYZ AMS / TT +2 / + MYC USD 0.27 fsc, aplica al gross weight", y luego una tabla con encabezados `Destination Code, Region, Service, Point Of Connection, Product, Product Name, Min, N, 45.0, 100.0, 300.0, 500.0, 1,000.0` y valores como `350, 8.00, 7.70, 3.00, 2.95, 2.90, 2.85`: Min 350 por guía, N 8.00, +45 7.70, +100 3.00, +300 2.95, +500 2.90, +1000 2.85. A veces viene en lista: "+ 1000 kg USD 2.60 / + 500 kg USD 2.65 / + 300 kg USD 2.70 / + 100 kg USD 2.75". Los avisos de fuel ("ACTUALIZACION FUEL SURCHARGE") traen cinco regiones: Canadá, US Northeast, US Midwest, Miami y "Otros destinos en el mundo"; en el portal son las reglas de FSC de Air Canada con esos mismos nombres (YYZ y ORD tienen regla propia; LAX, AMS, LHR, FRA, ICN, KIX, NRT, SJU, SYD, DUB, BUD son "Otros destinos"). "No llegamos con perecederos a BUD" o "SYD restringido" van como aviso.

**EMIRATES (Prime Air).** Tabla `Origen, Destino, Commodity, Tarifa, FSC, AWC, CG/(MAWB), CB/(HAWB), Salidas, Ruta, T/T`, una fila por destino: `UIO, KWI, Fresh Flowers, $3.56, $0.54, $25.00, $10.00, $0.25, 2-3-4-5-7, UIO_DWC_DXB_KWI, +2 o +3 días`. La tarifa aplica desde 100 kg (tramo +100). José Luis Sancho a veces manda lista con "ALL IN" vía MIA ("AMS: $3.23 ALL IN + AWC $25.00"): esa tarifa ya incluye el fuel y es otro producto, no la compares con la neta + 0.54. Las cartas "Emirates SkyCargo Fuel Surcharge" (PDF "Fuel activation letter effective …") dan la fecha de vigencia y dos cifras: SkyFresh (flores) y otras mercancías; solo vale SkyFresh, para todos los destinos.

**QATAR (ECS Group).** Tabla `Destino, Mínimum 1-17 kg, Normal 18-44 kg, +45kgs, +100 kgs, +500kgs, +1000kgs` con una fila por destino (`SYD, $595, $32.81, $23.63, $17.16, $8.00, $7.50`), seguida de: TT, AWC $45, CC $12 → $15 desde 01may/2026, CG $3, DI/BF/DF, ruta UIO-PTY-AMS-DOH-destino, "Operación ex UIO: MARTES y VIERNES", DGR, e-AWB. Eduardo Alvarez también contesta en lista corta con una sola cifra por destino ("DOH $5.15", "BAH $6.00 sujeta a disponibilidad"): es el tramo +100. Qatar no da FSC aparte (las tarifas son "+ cargos"). Un mismo correo puede llegar dos veces (carpeta QATAR y carpeta AERCARIBE).

**TURKISH (Kales).** Por destino: "UIO – DMM / +100kg USD 6.20/kg / AWC 35.00", y "Vuelo Online: Miércoles: UIO - MST - IST - Destino final TT+3" (a veces también viernes). Un solo tramo, +100. Sin FSC. Ojo con el destino mal rotulado: contestaron "UIO – ASB" a una solicitud de DMM y a los segundos mandaron el correcto; compara con lo que se pidió.

**LUFTHANSA (Transoceánica, Karina Cazar / Joe Proaño).** Tabla por destino `Product Name, M, N, Q45, Q100, Q300, Q500` con valores con coma decimal: `Perishables/td.Pro, 200,00, 5,30, 4,50, 2,80, 2,80, 2,70` = mínimo 200, N 5.30, +45 4.50, +100 2.80, +300 2.80, +500 2.70. Luego "Adicionar cargos: + $1.20 MR (x/cwght) + $40 CHC + $12 PCG (xc/hawb) + $50.00 PA (Perishable Fee)". O en texto: ">>> WAW / +500 Kg: $3.40 + $1.20 MR (x CWT) / Otros cargos: + $40 CH + $50 PA". Ruta UIO-MIA-FRA-destino, TT 3-4 días. En el portal Lufthansa suele estar cargada con el tramo +500.

**LAN / LATAM (Transoceánica, Karen Guevara / Bolívar Pérez).** Lista "ASU: $ 3.05/kg CHW + $43.00 MCC en la ruta UIO-LIM-ASU; TT+3.", separada en "Cotización PAX" y "CARGUERO". "Para este embarque" es su fórmula estándar: sigue siendo la tarifa vigente, no una reserva. Vigencia "3 semanas". Sus comunicados "AJUSTE DE TARIFA AMS" o "INCREMENTO TARIFA AMS por temporada alta (+0.20 desde el 24 de agosto)" son incrementos por temporada: van en `incrementos`, no como tarifa nueva.

**DHL.** Tabla de cotización con columnas `MIN, -45, +45, +100, +500, +1000` (los primeros suelen venir vacíos): `VCP, FLORES, 3.50, 3.40, 3.40, UIO-MIA-VCP, D1/D2/D3/D4/D5/D6, +2` = +100 3.50, +500 3.40, +1000 3.40. Luego CARGOS: AFS (fuel) por región con fecha de cambio ("Desde 10 de septiembre USD 0,50"), FWB 2, FHL 2, DGR 100, MCC 20. A veces adjuntan el PDF "TARIFARIO": léelo, ahí vienen los destinos. Coma decimal en los cargos.

**AVIANCA.** Tabla `Ruta, Arvl Arp, Tarifa Min 1-39kg, Tarifa 40-99kg, Flor +100kg (, Tipo de Aeronave)`: `UIO-BOG-GRU, GRU, $130,00, $5,18, $1,95` = mínimo 130, 40-99 kg 5.18, +100 1.95. Puede traer dos filas del mismo destino, PAX y CAO. Coma decimal. Los avisos "*** IMPORTANTE *** Fuel Surcharge / Ecuador" dan SH/MH/LH (distancia corta/media/larga): son las reglas de FSC "Short Haul", "Medium Haul" y "Long Haul" del portal; "GYE-MIA se toma como SH".

**DELTA (David Vargas).** Por destino: "UIO-AMS (Flores) / +100K: 2.70 All in + AWC 25.00 / Routing: UIO-ATL-AMS / TT 2D". Tarifa all in: FSC 0. "Salidas diarias desde UIO".

**CATHAY (GSA Force).** "KIX : 3.55+25awc+2fee", "6.25+25awc", una cifra que a veces cubre varios destinos ("MEL, SYD, BNE tarifa aplicar 6.85+25awc"): es el tramo +100 para cada uno de esos destinos. "Tt 3-4 dias, Ruta uio-mia-hkg-beyond". Sin FSC. Propón un hallazgo por destino que tenga cotización.

**COPA (Evelyn Vargas).** Una línea: "2.90usd + 25awc +0,60usd + 0.03ssc / Vuelos diarios UIO PTY MVD +1" = +100 2.90, AWC 25, fuel 0.60 y SSC 0.03 (el portal guarda FSC 0.63, la suma).

**AIR EUROPA (Mawney).** "AMS 2,60 mas cargos (AWC 25,00 SSC 0,05 MIN 10,00 MCY 0.06)" por destino, tramo +100. Avisos de fuel "Incremento cargo combustible UX": una cifra para todos los destinos.

**SOLENT (Cecilia Acosta).** "100 KILOS 3,26 / 300 KILOS 3,16 / 500 KILOS 3,06 / 1000 KILOS 2,96 + 95,00 de corte de guía + 40.00 de inspección", días de conexión desde MIA, y "LA TARIFA APLICA HASTA EL 13 DE SEPTIEMBRE" (eso es `vigencia_hasta`). Contesta a quien pida de FreightWise, no solo a Daniela.

## Reglas que salen de estos correos

- Las solicitudes de tarifa las mandan Daniela, Johana, Felipe o Mónica (todos `@freight-wise.com`). Una respuesta a cualquiera de ellos es una respuesta válida.
- Correos de Daniela "Tarifa Flor" sin respuesta abajo son su solicitud: sin hallazgos.
- Un reenvío interno (RV:/FW:) de un aviso de fuel repite un correo que ya se analizó: un solo hallazgo por aviso.
- Reservas, confirmaciones de booking, distribuciones, flight plans, pipelines: no traen tarifas.
- Si el correo dice desde cuándo rige ("a partir del 21 de septiembre", "effective 22nd September", "desde el 01may/2026") ponlo en `vigencia_desde`; si dice hasta cuándo, en `vigencia_hasta`.
- Si un mismo GSA contesta dos veces con contenido distinto (Turkish ASB/DMM), vale el que coincide con lo pedido.
