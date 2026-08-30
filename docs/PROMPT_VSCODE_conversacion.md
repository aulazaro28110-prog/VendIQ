# Prompt para el agente de VS Code — Arreglar la conversación de VendIQ

> Pega esto entero en el agente de VS Code (Copilot Chat / Claude / el que uses), con el
> repo de VendIQ abierto. Está escrito para que trabaje solo, pero **parándose a explicar
> su plan antes de tocar** y **corriendo las pruebas al final**.

---

## ROL

Eres un ingeniero de Python trabajando en **VendIQ**, un asistente RAG de WhatsApp para un
desguace (Desguaces Madrid Norte). Escribe código quirúrgico y conservador: cambios pequeños,
respetando los comentarios y el estilo que ya hay. No reescribas archivos enteros.

**Principio de arquitectura que NO se rompe nunca:** el **CÓDIGO decide la acción**
(RESPONDER / PREGUNTAR / ESCALAR) y el **LLM (Groq) solo REDACTA** dentro de la acción que
el código ya eligió. Nada de meter lógica de negocio, precios ni decisiones en el prompt del
LLM. Si un mensaje sale mal, casi siempre es un problema de enrutado en el código, no del
prompt.

---

## CONTEXTO

- Proyecto formativo, **100% gratis** y con **datos sintéticos** (GDPR, minimización). La
  **matrícula NUNCA se envía al LLM**; es un identificador que el sistema **no resuelve** a
  un coche (no hay consulta a la DGT). Lo que identifica el coche es lo que el cliente
  escribe (marca + modelo), o una **referencia OEM / número de stock exactos**.
- Groq está **encendido** y solo redacta. `.env` tiene la `GROQ_API_KEY` real: **no la
  imprimas, no la subas a git, no toques `.env`**.
- Archivos y piezas clave del pipeline:
  - `07_redactor.py` — `detectar_intencion()`, la clase `Conversacion`, la función grande
    `redactar()` (cadena de `if/elif` que decide el mensaje), `_sin_pieza()`,
    `rompe_la_matricula()`.
  - `06_panel.py` — `chatear()` (memoria del coche y arrastre de contexto), `consultar()`
    (decisión RESPONDE / NO DISPONIBLE / ESCALA) y la función que llama a Groq para redactar
    (busca algo tipo `redactar_con_llm`, imprime "Redacta: Groq (...)").
  - `08_conversar.py` — capa LLM (la llamada real a Groq).
  - `03_buscar.py` — `precio_para_cliente()` (las 5 condiciones para publicar precio) y la
    búsqueda.
  - `tests/test_conversaciones.py` — banco de ~200 conversaciones. Se corre con
    `python tests/test_conversaciones.py`.

---

## LO QUE YA ESTÁ HECHO (verifícalo, NO lo deshagas)

En `07_redactor.py` ya se aplicaron tres arreglos de "ciclo de conversación". Confírmalos y,
si faltara alguno, complétalo. **No los dupliques ni los revuelvas.**

1. **Apertura cálida.** `PRESENTACION = "¡Hola! Soy el asistente de Desguaces Madrid Norte,
   encantado de ayudarte."`
2. **Escalado pegajoso.** En `redactar()`, la rama de escalado ya no reabre con un "sí /
   vale / gracias": responde corto con `variar("sigue_escalado", ...)` y no repite el "te
   paso a Álvaro". La condición usa `decision != "RESPONDE"` para dejar pasar una pieza o
   política nuevas.
3. **Venta cerrada = no reabrir.** Hay una rama nueva (busca `variar("cerrada_corto", ...)`)
   que, cuando `conversacion.estado in (CERRADA, POSVENTA)` y el mensaje no pide una pieza
   nueva, remata corto y **no** vuelve a pedir matrícula ni re-ofrece lo vendido.

---

## TAREAS (en este orden)

### Tarea 1 — Red de seguridad sobre lo que redacta Groq

**Problema:** Groq, al redactar, se sale del guion e **introduce cosas que la versión
determinista NO decía**. Ejemplos reales medidos:
- Pide la matrícula que el cliente **ya había dado**.
- Nombra un coche que el cliente **no dijo** (ofrece un "A4 3.0 TDI" a alguien con un A4 2.0).
- Le pregunta al **cliente** a quién escalar ("¿a quién debo remitirlo?").
- Dice **"descuento"**, que una regla escrita prohíbe expresamente.

**Enfoque (el usuario lo eligió así):** NO candar la redacción (queremos que suene natural),
sino poner una **red de seguridad** por detrás. Regla central, simple y potente:

> El LLM puede **reformular** el borrador determinista, pero **no puede INTRODUCIR** contenido
> prohibido que no estuviera ya en ese borrador. Si lo introduce, se **descarta la salida del
> LLM** y se usa el texto determinista (que es seguro por construcción).

**Qué implementar:**
1. `redactar()` ya devuelve `lineas` (el borrador determinista). Localiza dónde el panel
   llama a Groq para reescribir esas líneas (en `06_panel.py` / `08_conversar.py`).
2. Justo **después** de que Groq devuelva su texto, pásalo por una función nueva, p.ej.
   `def _red_de_seguridad(texto_llm, lineas_deterministas, conv) -> str`, que devuelve el
   texto de Groq si es seguro, o `"\n".join(lineas_deterministas)` si viola una regla.
3. Reglas que disparan el descarte (todas comparando **LLM vs. borrador determinista**):
   - **"descuento" / "rebaja" / "oferta especial"** aparece en el texto del LLM y **no** en el
     borrador.
   - **Re-pide un dato ya dado:** el texto del LLM pide "matrícula" (o "bastidor"/"VIN") y
     `conv.matricula` ya tiene valor, y el borrador determinista **no** lo pedía. (Amplía la
     idea de `rompe_la_matricula()`, que ya existe.)
   - **Inventa un coche:** el texto del LLM contiene una marca+modelo (o motor/año) que **no**
     está ni en el borrador determinista ni en lo que el cliente ha dicho
     (`conv.vehiculo` / historial).
   - **Pregunta al cliente a quién escalar:** patrones tipo "a quién", "a quien", "remitir",
     "remito", "derivar" en el texto del LLM cuando el borrador no los tenía.
4. Cuando se descarte, **regístralo** (un print o al registro de aprendizaje) para que se
   pueda auditar cuántas veces Groq se sale del guion.

**Importante:** no toques el prompt para "pedirle por favor" que no lo haga — eso ya se
intenta y no basta. La red de seguridad es determinista y va **después** de Groq.

### Tarea 2 — El "no" que ofrece la equivalente

**Problema:** cuando no hay la pieza exacta para la versión exacta del coche, el bot suelta un
"no disponemos" seco y esconde que tiene una **muy parecida** (misma pieza, misma marca y
modelo, otra motorización/año), hasta que el cliente afloja. Desde el cliente es lo peor:
primero un "no", luego una sorpresa.

**Qué implementar (en `_sin_pieza()` de `07_redactor.py`, apoyándote en la búsqueda):**
- Si NO hay pieza exacta para la variante del cliente, pero SÍ existe en catálogo la **misma
  pieza para la misma marca+modelo** (distinta motorización/año), el "no" debe, **en la misma
  frase**, mencionar ese casi-encaje **sin afirmar que encaja**. Ejemplo del tono correcto:

  > "No tengo el compresor exacto de tu A4 2.0 gasolina, pero sí un compresor de A4 de otra
  > motorización. Si me pasas la referencia de la pieza, miro si te encaja."

- **Prohibido** afirmar o dar por hecho que la equivalente sirve, y **prohibido** ponerle
  precio. Ofrecer *mirar si encaja* ≠ afirmar que encaja. Esa línea tiene que quedar clara.
- Puede requerir que la capa de búsqueda (`03_buscar.py`) exponga esas "candidatas no
  confirmadas" (mismo `tipo` de pieza + misma marca/modelo, variante distinta). Hazlo de
  forma que no ensucie la ruta normal.

### Tarea 3 — Regla de negocio: identificación inequívoca (lectura A)

Regla confirmada por el dueño del proyecto:

1. Se **ofrece una pieza concreta con precio SOLO** cuando la identificación es **inequívoca**:
   referencia OEM o número de stock exactos (la ruta que en `precio_para_cliente()` ya
   devuelve "identificada por referencia exacta"). En cualquier otro caso, no se ofrece ficha
   concreta ni precio: se pide la **referencia** de la pieza.
2. **Comprobar la compatibilidad SIEMPRE antes de cerrar la venta.** Antes del "lo aparto /
   hecho", si la identificación no fue por referencia exacta, el mensaje de cierre debe
   incluir un paso explícito de confirmar que la pieza encaja (no cerrar a ciegas).

Buena parte de (1) ya vive en `precio_para_cliente()`. Verifícalo y haz explícito el paso de
compatibilidad de (2) en la rama de cierre de `redactar()`.

### Tarea 4 — Gmail: mostrarlo como canal conectado en el panel

**Contexto:** el panel (`panel/actividad.js`, función `pintarRecorrido`, sección "1 · Entra
por") pinta las tarjetas de canal con el estado **cableado a mano**: WhatsApp = "el único
conectado", y Gmail / Wallapop / Otras = "no conectado" (`apagado: true`, borde discontinuo).

**Es incoherente:** el canal de correo SÍ está implementado y funciona en el panel — la
pestaña de Gmail (`panel/canales.js` + el endpoint `/api/correo` de `06_panel.py`) coge un
correo pegado y devuelve la respuesta entera, con la MISMA búsqueda y el MISMO guardarraíl de
precio que WhatsApp. Está al mismo nivel que WhatsApp.

**Qué hacer:** en `pintarRecorrido` de `panel/actividad.js`, pon **Gmail como conectado**
(quita su `apagado: true`, dale un `pie` y un `tono` como WhatsApp, p.ej. `pie: 'correo,
conectado'`). Deja Wallapop / Otras como están salvo que se indique lo contrario.

**Honestidad (no lo maquilles):** ni WhatsApp ni Gmail son una integración EXTERNA en vivo (no
hay bandeja de Gmail real: cero IMAP/SMTP). Son canales del panel sobre el mismo motor. La
etiqueta "conectado" describe el panel de demo, y por eso Gmail merece la misma que WhatsApp.
No escribas un texto que dé a entender una bandeja de Gmail en vivo si no la hay.

### Tarea 5 — URL real de stock en los correos

**Objetivo:** que la respuesta por correo incluya un **enlace a la ficha de stock** para que
quien lo recibe (persona o agente) pueda **confirmar disponibilidad y ver el precio**.

**Estado actual:** no existe ninguna URL de stock. El bot hasta dice "no tengo enlace en la
web". El panel solo sirve en `http://localhost:8420`.

**Qué implementar:**
1. **Página de ficha en el panel.** Añade una ruta en `06_panel.py` (p.ej. `GET
   /stock/<id_stock>`) que devuelva una página simple con la ficha: pieza, coche, estado
   (disponibilidad) y **precio publicado** (el mismo que ya calcula el sistema). Es la ficha
   concreta identificada por su `id_stock`, no una afirmación de que encaje con el coche de
   nadie: no rompe el guardarraíl de precio.
2. **BASE_URL configurable.** Una variable (p.ej. de entorno `VENDIQ_BASE_URL`) que por
   defecto sea `http://localhost:8420`. El enlace se construye como `{BASE_URL}/stock/{id}`.
   En local es un enlace de demo; **solo es "real" (clicable desde fuera) cuando VendIQ esté
   desplegado** en un dominio público — átalo a la variable para que funcione en ambos casos.
3. **Meterlo en el correo.** En `componer_email()` (`11_canales.py`), incluye el enlace de la
   ficha **SOLO cuando la pieza está identificada de forma inequívoca** (referencia exacta),
   coherente con la Tarea 3. Si no está identificada, **no** se pone enlace: el correo pide la
   referencia, como hasta ahora.

**Restricción clave:** el enlace apunta a UNA ficha real del catálogo (por su `id_stock`),
nunca a una inventada. Si no hay ficha segura, no hay enlace.

---

## RESTRICCIONES

- No toques `.env`. No imprimas ni subas la `GROQ_API_KEY`.
- Mantén la arquitectura: **lógica en el código, Groq solo redacta.**
- La **matrícula no viaja al LLM** (GDPR, minimización).
- Máximo **1–3 líneas** por mensaje de WhatsApp.
- **Antes de empezar, haz una copia de seguridad**: `git add -A && git commit -m "checkpoint"`
  (o copia los archivos a `.bak`). Cambios quirúrgicos, respeta los comentarios existentes.
- No metas dependencias nuevas.

---

## RAZONAMIENTO ANTES DE TOCAR

Para **cada** tarea, primero:
1. Localiza y **cita** el sitio exacto (archivo + función + líneas) donde vas a intervenir.
2. Explica tu plan en 3–5 líneas.
3. Recién entonces edita.

No edites nada hasta haber mostrado el plan de las tres tareas.

---

## CRITERIO DE ÉXITO — pruebas de aceptación

Después de implementar, **corre** `python tests/test_conversaciones.py` y comprueba que:
- Los **invariantes** siguen pasando (sobre todo: nunca se publica un precio que la búsqueda
  no autorizó).
- El **porcentaje de acierto por categoría no baja** respecto a la ejecución anterior.

Y los 7 casos siguientes se comportan como se indica (**añádelos como tests de regresión** en
`tests/test_conversaciones.py` o en un archivo nuevo, para que queden fijados):

1. **"Buenos días!"** (primer mensaje, sin pieza) → saluda cálido y pregunta qué pieza; NO
   dice "no disponemos de esa pieza".
2. **"Hola, necesito un compresor para un Audi A4"** → saluda en el primer turno y pide el
   dato que necesita, con tono agradable.
3. Cliente da matrícula y, más tarde, el bot **NO** vuelve a pedir la matrícula que ya tiene.
4. El bot **nunca** le pregunta al cliente **a quién escalar**; escala él solo si lo ve
   necesario.
5. El bot **nunca** menciona **"descuento"**.
6. Tras una pieza fuera de stock (caso escalado), un "sí / vale / gracias" **no reabre** ni
   repite el "te paso a Álvaro".
7. Con la **venta cerrada**, un "no hace falta / genial / ok" **remata corto**: no pide
   matrícula otra vez ni re-ofrece la pieza vendida.
8. En el panel, la tarjeta de **Gmail** aparece **conectada** (mismo nivel que WhatsApp), no
   en gris/discontinuo.
9. Un correo con **referencia exacta** de una pieza en stock incluye un enlace
   `{BASE_URL}/stock/<id>` que abre la ficha con disponibilidad y precio. Un correo **sin**
   identificación inequívoca **no** trae enlace y pide la referencia.

Al terminar, **informa** en un resumen: qué cambiaste por tarea (archivo/función), qué partes
son inseguras o quedaron a medias, y el resultado de las pruebas (antes/después). La
responsabilidad final es del dueño; sé transparente con lo que no estés seguro.
