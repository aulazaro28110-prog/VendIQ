# Línea base — Fase 0 (antes de tocar nada)

> Medida el 2026-09-30 en la rama `conversaciones-tipo`, con `py` (Python 3.14.5),
> sin `--con-llm` (los bancos vacían `GROQ_API_KEY`, redacción determinista).
> Es el punto de comparación de C5: **nada puede empeorar respecto a esto.**

## Bancos de prueba (todos PASAN)

| test | casos | resultado | cifra clave | tiempo |
|---|---|---|---|---|
| `test_conversaciones.py` | 223 | PASA · 100 % | 0 invariantes rotos | no cronometrado individual |
| `test_busqueda.py` | 80 | PASA | **acierto@1 90 % · @3 99 % · guardarraíl 40/40 (100 %)** | 38,8 s |
| `test_precios.py` | — | PASA | 5000/5000 con precio; 0 combos inexistentes | 34,1 s |
| `test_ofertas.py` | — | PASA | reglas de descuento coherentes | 0,6 s |
| `test_mesa.py` | 45 | PASA · 45/45 | cada pregunta a su grupo | 0,4 s |
| `test_ciclo.py` | 9 | PASA · 9/9 | el ciclo de la conversación | 28,3 s |
| `test_canales.py` | — | PASA | 50 correos + 20 wallapop (209 msg, 0 repetidas) | 68,2 s |
| `test_frio.py` | 50 | PASA | 1041 turnos, 0 invariantes, 22 descartes del modelo | 351,1 s |
| `test_prompt.py` | 12 | PASA · 12/12 | sección a sección del prompt | 33,6 s |
| `test_llm.py` | — | PASA | petición a Groq, guardarraíl, caídas (con mocks) | 27,4 s |

**Umbrales que C5 vigila:** `test_busqueda` acierto ≥ 0,90 (hoy **exactamente 0,90**) y
guardarraíl = 1,0 (hoy **1,0**). Margen cero en el acierto: cualquier bajada rompe C5.

## Recuento de datos de negocio (estado real previo, antes de correr nada)

| fichero | entradas | desglose por prefijo de sesión |
|---|---|---|
| `salida/reservas.json` | **33** | banco 17 · panel 6 · estres 4 · (otro/cliente) 6 |
| `salida/no_resueltas.json` | **41** | banco 20 · panel 8 · sim 6 · estres 4 · (otro/cliente) 3 |
| `salida/actividad.json` | 16 | (sin prefijo de sesión) |

Ninguna reserva es de un cliente real (todas de prueba). Es la fuga de D4.

## Contaminación medida al correr la línea base (D4 en vivo)

Correr `test_conversaciones.py` + el resto del banco añadió a los datos reales:

| fichero | antes → después | se coló |
|---|---|---|
| `reservas.json` | 33 → 40 | **+7**: `banco-182..186` (5) y **`aud6`, `aud10`** (2) |
| `no_resueltas.json` | 41 → 42 | **+1**: `banco-180` |
| `actividad.json` | 16 → 16 | 0 |

> **Hallazgo para la Fase 1.3:** además de `banco-`, hay sesiones `aud*` (de
> `test_ciclo`/`test_llm`) que también escriben reservas. La lista de prefijos de
> `es_prueba()` que propone D4 (`sim-, banco-, guion-, diag-, estres-`) **no cubre
> `aud*`**. Hay que revisar qué prefijos usan de verdad todos los bancos.

*(Esta contaminación de +7/+1 sigue en `salida/` a la espera de que Álvaro decida si
se restaura desde el backup del scratchpad. No se ha limpiado sin su permiso, §11.)*
