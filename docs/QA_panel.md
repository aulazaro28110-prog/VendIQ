# QA funcional del panel

Repaso completo del panel de VendIQ: los quince endpoints, el cableado entre la
vista y el JavaScript, el guardarraíl de precio y la regresión del Camry.

**Fecha:** 20-09-2026 · **Rama:** `qa-prepush` · **Servidor:** `06_panel.py` en
`127.0.0.1:8420`

## Cómo se ha probado

Los endpoints de lectura se han llamado contra el panel en marcha. Los cuatro
que **escriben en disco** se han probado con datos sintéticos marcados
(`cliente: "QA sintetico - borrar"`), tomando antes una huella SHA-256 de los
nueve ficheros de `salida/` y restaurándolos después. Las nueve huellas vuelven
a coincidir, y el servidor se reinició al terminar: restaurar el fichero no
deshace lo que el proceso ya tiene en memoria.

`/api/aprender` **no** se ha ejecutado por su camino de escritura: reconstruye
el índice de embeddings (7,3 MB) y eso no es una prueba en seco. Se ha probado
solo su guarda de entrada, que rechaza sin tocar nada.

Lo que necesita un navegador —pulsar, ver, medir— está marcado **N-P** (no
probado) en vez de darlo por bueno.

---

## A · GET

| Función | Resultado | Nota |
|---|---|---|
| `/api/estado` | OK | 200 · 12 claves · `resumen`, `verificacion`, `historico` presentes |
| `/api/actividad` | OK | 200 · 16 claves · `por_dia` con 7 días |
| `/api/ofertas` | OK | 200 · 15 ofertas + 12 piezas ofertables |
| `/api/precios` | OK | 200 · **0 pendientes**: estado vacío legítimo, todo el catálogo tiene precio |
| `/api/guiones` | OK | 200 · 5 guiones de conversación |
| `/api/mesa` | OK | 200 · 7 grupos · 35 pendientes · 1.287 clientes esperando |
| `/api/no-resueltas` | OK | 200 · 41 pendientes |
| `/stock/<id>` | OK | `/stock/77499` → 200 · 1.295 bytes con la ficha |
| `/stock/<id>` inexistente | OK | 404 limpio, no excepción |

## B · POST de solo lectura

| Función | Resultado | Nota |
|---|---|---|
| `/api/consultar` por descripción | OK | «alternador BMW Serie 1 118d» → 4 resultados · mejor **0,905** · `RESPONDE` |
| `/api/consultar` por referencia OEM | OK | `6483HM11A` → encuentra la pieza exacta |
| `/api/consultar` vacía | OK | 400 · `escribe una consulta` |
| `/api/chat` | OK | 200 · devuelve `bot`, `busqueda`, `memoria` |
| `/api/chat` vacío | OK | 400 · `escribe un mensaje` |
| `/api/correo` | OK | 200 · destila «Alternador BMW Serie 1» del correo · `registrar=False`, no escribe |
| `/api/correo` sin cuerpo | OK | 400 · `pega el correo del cliente` |
| `/api/aprender` sin texto | OK | 400 sin tocar el índice — la guarda protege el camino caro |

## C · POST que escriben (sintético + restaurado)

| Función | Resultado | Nota |
|---|---|---|
| `/api/oferta` | OK | 100 € sobre 409,70 € → `RECHAZAR` · «76 % por debajo del precio publicado» |
| `/api/oferta` queda registrada | OK | 15 → 16 ofertas |
| `/api/oferta` en zona gris | OK | 266,31 € (35 % dto.) → `A_MANO` · estado `pendiente` |
| `/api/resolver` | OK | n=17 → `cerrada`, `resuelta_por: Álvaro` |
| `/api/resolver` sobre oferta ya cerrada | OK | 400 · «La oferta 16 ya está cerrada» — se niega a re-decidir lo que cerró la regla |
| `/api/resolver` con n inexistente | OK | 400 · «No existe la oferta 999999» |
| `/api/descartar` | OK | 200 · saca de la mesa sin escribir en la base de conocimiento |
| `/api/precio` | OK | 200 · fija 123,45 € en la pieza 77499 |
| Restauración | OK | las 9 huellas SHA-256 vuelven al estado previo · 15 ofertas · precio 250,37 € |

## D · Guardarraíl de precio

| Función | Resultado | Nota |
|---|---|---|
| Pieza genérica sin coche | OK | «motor completo», «un alternador», «quiero un faro» → ninguna publica precio |
| Consulta vaga | OK | «necesito una pieza», «tengo un Seat Ibiza, ¿qué tienes?» → sin precio |
| El motivo tiene nombre | OK | `sin_coche`, `no_es_la_mejor` — no es un `None` silencioso |
| Con pieza + coche identificado **sí** hay precio | OK | 250,37 € + IVA · pieza 77499 — el guardarraíl no bloquea de más |

El cuarto es tan importante como los tres primeros: un guardarraíl que no deja
pasar nada nunca también estaría «pasando» la prueba.

## E · Regresión Camry

El bug real: con matrícula pero sin decir el coche, el bot ofrecía un motor
completo de Toyota Camry a quien no había dicho qué coche tenía. Conversación
completa contra `/api/chat`:

| Turno | Cliente | Bot | ¿Camry? | ¿Precio? |
|---|---|---|---|---|
| 1 | «mi matrícula es 1234 BCD y necesito un motor completo» | «Anotada, 1234 BCD. Dime qué pieza buscas.» | no | no |
| 2 | «motor completo» | «De motor completo tengo, **pero necesito confirmar el coche**. La matrícula la revisa una persona; dime marca y modelo y te digo cuál te vale y el precio.» | no | no |
| 3 | «es un Toyota Corolla 1.8 Hybrid de 2005» | «Tengo motor completo de **Toyota Corolla** 1.8 Hybrid 2005, comprobado…» | no | no |

**OK.** No nombra el Camry en ningún momento, no suelta precio antes de saber el
coche, y en cuanto lo sabe ofrece el Corolla correcto.

## F · Cableado vista ↔ JavaScript

| Función | Resultado | Nota |
|---|---|---|
| Los 9 enlaces del menú apuntan a secciones reales | OK | `cliente · mesa · tumesa · stock · dia · informe · reglas · canales · letra` |
| Todos los `#id` que pide el JS existen en el HTML | OK | 80 ids en 11 ficheros; el único que no aparece (`#puntitos`) lo **crea** `chat.js` |
| Los 15 endpoints que llama el JS existen en el backend | OK | ninguna llamada a una ruta inexistente |
| Los 18 `.js`/`.css` referenciados existen | OK | incluidos `lenguaje.css` y `paleta.js` |
| Secciones sin entrada en el menú | N-P | `atasco`, `precios`, `faltan` — se alcanzan bajando, no desde el menú |
| Ficheros en `panel/` que ya no se cargan | N-P | `fondo.js`, desactivado a propósito en el reskin |

## G · Interactivos

| Función | Resultado | Nota |
|---|---|---|
| Buscador de stock por descripción | OK | verificado por API |
| Buscador de stock por referencia | OK | verificado por API |
| Paleta de comandos ⌘K | N-P | código revisado (índice leído del menú, freno de 180 ms, turno anti-carrera); falta pulsarla |
| Drawer de oferta | N-P | 420 px, cierra con Esc — código revisado |
| Respuesta sugerida editable | OK | es un `<textarea>` de verdad, marcado «demo — no envía», con aviso explícito |
| Toggle de tema | N-P | `localStorage` dentro de `try/catch`, se aplica en el `<head>` para no dar fogonazo |
| Desplegables (2 acordeones) | N-P | código revisado en `estados.js` |

## H · Estados

| Función | Resultado | Nota |
|---|---|---|
| Vacío | OK | `/api/precios` devuelve 0 y la sección tiene su estado vacío con explicación |
| Carga | OK | esqueletos con plan B: a los 12 s se convierten en un estado que dice qué pasa |
| Error | OK | los tres caminos de fallo marcan `.estado-vacio.fallo` y dicen cómo salir |
| Visualmente | N-P | hace falta navegador |

## I · Salud

| Función | Resultado | Nota |
|---|---|---|
| Llamadas rotas | OK | ninguna: los 15 endpoints existen y responden |
| `console.*` olvidados | OK | cero en los 12 ficheros del panel |
| Nombres de `.py` a la vista | OK | ninguno en el HTML |
| Errores de consola | N-P | hace falta navegador |
| Responsive claro/oscuro/móvil | N-P | hace falta navegador |

---

## Resumen

**44 comprobaciones: 34 OK · 0 FALLA · 10 N-P.**

No hay ningún fallo funcional. Los diez N-P son todos por la misma razón —
pulsar y mirar necesita un navegador— y ninguno esconde un fallo conocido.

Durante el QA saltaron dos falsos positivos que conviene dejar escritos porque
son trampas fáciles de repetir:

1. **`precio_cliente` es un diccionario que viene siempre**, con
   `{publicable, importe, estado}`. Comprobar si el campo existe da verdadero
   aunque diga `publicable: false`. Lo que hay que mirar es `publicable`, que es
   lo que mira `tests/test_precios.py`.
2. **`/api/resolver` sobre una oferta que la regla ya cerró devuelve 400**, y
   eso es correcto: resolver es para lo que espera una decisión humana. Para
   probarlo hace falta una oferta `A_MANO`, es decir un descuento entre el
   30 % y el 45 %.

### Los diez bancos, en local

Ejecutados de uno en uno, nunca en paralelo: cada uno carga el modelo de
embeddings entero y en paralelo se quedan sin memoria.

| Banco | Resultado | Nota |
|---|---|---|
| `test_ofertas.py` | PASA | |
| `test_precios.py` | PASA | incluye la regresión del Camry |
| `test_mesa.py` | PASA | 45/45 · cada pregunta cae donde se contesta |
| `test_llm.py` | PASA | todo en verde sin llamar al modelo |
| `test_prompt.py` | PASA | 12/12 secciones del prompt |
| `test_ciclo.py` | PASA | las 9 situaciones del ciclo de aprendizaje |
| `test_busqueda.py` | PASA | 80 preguntas · **90 %** a la primera · 99 % en top 3 · guardarraíl 40/40 |
| `test_canales.py` | PASA | 50 correos + 20 conversaciones difíciles |
| `test_conversaciones.py` | PASA | 218 conversaciones |
| `test_frio.py` | **FALLA 1 de 50** | conversación 20, turno 21: la despedida sale corta y sin pedir datos |

Sobre el décimo, que es el único en rojo: se ejecutó **con** la clave de Groq,
así que el texto lo redactó el modelo y no el redactor determinista. Las
guardas del sistema descartaron al modelo 21 veces en esa misma tirada, que es
justo su trabajo. Esa ruta no es reproducible —lo dice el propio workflow de
CI, que por eso manda verificarla dos veces en local— y es también la ruta que
**CI no ejecuta**: sin `GROQ_API_KEY` redacta `07_redactor.py` y el banco es
determinista.

Dicho de otro modo: lo que se rompe es la redacción del modelo en un turno de
mil cuarenta y uno, no una regla del sistema. Ningún invariante se rompió.

### Fuera de alcance, y por qué

**Filtro global de fecha y canal: descartado.** Los datos no tienen esa
dimensión. `/api/actividad` da `fecha · dia · conversaciones · mensajes ·
resueltas · escaladas · ms_mediana`, y `/api/estado` da totales que no se
pueden recalcular por rango sin tocar el backend. No hay campo de canal en
ninguno de los dos. Un filtro que solo moviera dos de doce widgets, o que
fingiera filtrar, sería peor que no tenerlo.

---

## J · Conversaciones tipo y el nuevo «Por qué» (addendum, 02-10-2026)

Las Fases 4-5 de `conversaciones-tipo` (rama) añaden al chat del panel: el
desplegable de **8 tipos / 50 guiones**, el **reproductor** (Reproducir, Paso a
paso, Parar, Velocidad), el **✓/✗ por turno** y el **«Por qué» nuevo** sacado de
la traza del servidor (8 pasos, resumen, barra con umbral, auditorías, diff del
modelo, memoria antes→después, clic en cualquier burbuja).

### Cómo se ha probado (sin navegador)

Igual que el QA original: lo que necesita pulsar y mirar va **N-P**; lo demás se
ha comprobado por API/en proceso, sin tocar los datos de negocio (sesiones
`guion-`/`diag-`, `persistir=False`).

| Función | Resultado | Nota |
|---|---|---|
| Sintaxis del front | OK | `node --check panel/chat.js` sin errores |
| `06_panel.py` compila | OK | `py_compile` de panel + `12_guiones` + `13_traza` |
| `/api/guiones` trae los campos nuevos | OK | `id, tipo, tipos_mezcla, esperado, decision_pendiente, …` · 50 guiones |
| `/api/chat` con `guion:{id,turno}` → `evaluacion` | OK | `{ok, esperado, obtenido, fallos, decision_pendiente}` |
| `/api/chat` aditivo: no quita nada | OK | devuelve `bot, busqueda, memoria, traza` **y** `evaluacion` juntos |
| ✓/✗ del servidor == banco | OK | `evaluar_guion_turno` = `evaluar_turno` en G01, G13, G07, G28 |
| Una sola definición de la evaluación | OK | el servidor reusa `12_guiones.evaluar_turno`; no hay evaluación en JS |
| Traza coherente (C7) | OK | banco de guiones: **541/541** turnos coinciden con la traza |
| Guiones sin rastro en datos (C6) | OK | sesión `guion-…` excluida; recuento 40/42/16 **sin cambios** |
| Compatibilidad «por qué» viejo | OK | si la respuesta no trae `traza`, cae al render anterior (código revisado) |
| Solo tokens existentes (sin colores nuevos) | OK | `--ok/--ambar/--rojo/--cian/--tinta-*`; revisado en `chat.css` |
| Render en navegador (consola, claro/oscuro, 390 px) | **N-P** | hace falta navegador — ver los 5 clics en `GUIONES_informe.md` |
| Reproductor: Parar/Esc, teclado, foco | **N-P** | código revisado; falta pulsarlo |
| Capturas (Playwright) | **N-P** | el panel viejo ocupa el puerto 8420; no verificable desde aquí |

### Aviso para probarlo

Hay un **panel antiguo escuchando en 8420** (devuelve 5 guiones sin `id`).
Ciérralo antes y arranca `py 06_panel.py`, o no se verán los cambios (el propio
servidor avisa si el puerto está ocupado).

### Resultado

Todo lo verificable sin navegador está **OK**. Lo que queda es **N-P por la misma
razón de siempre**: pulsar y mirar necesita un navegador. Ningún N-P esconde un
fallo conocido.
