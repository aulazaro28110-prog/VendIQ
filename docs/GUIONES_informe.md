# Informe «Conversaciones tipo» — fase por fase

> Registro de ejecución de todas las fases (rama `conversaciones-tipo`). Álvaro lo
> revisa al final y corregimos juntos. **No se ha hecho ningún commit** (por
> instrucción de Álvaro): todo queda en el árbol de trabajo.

---

## FASE 0 — Línea base y reproducción (2026-09-30)

**Qué he hecho.** Leí el prompt entero, aparté la basura de la raíz (`'`, `5`,
`div`, 0 bytes) a `_to_delete/`, creé la rama `conversaciones-tipo`, medí la línea
base (10/10 bancos PASAN, ver `GUIONES_linea_base.md`) y reproduje D1–D5 con un
script aislado (sobre una copia de `salida/`; los datos reales quedaron intactos).

**Números.** Ver `GUIONES_linea_base.md`. Titular: `test_busqueda` 90 % / guardarraíl
100 %; reservas de negocio 33 (todas de prueba, ninguna de cliente).

**D1–D5, confirmados todos:**
- **D1** — 0 combinaciones (pieza,marca) sin palabra en común → el guion «No la
  tenemos» cae en el Ferrari hardcodeado.
- **D2** — tras la matrícula el bot dice «Dime qué pieza buscas» aunque
  `pieza_pedida` tiene la pieza. Pasa con el Ferrari **y** con una ausencia real
  (BMW Serie 3 · alternador). El trabajo sin commitear de Álvaro no arregla este
  camino (porque la pieza SÍ es un tipo conocido, solo que ausente para ese coche).
- **D3** — las 6 ramas de contexto funcionan, pero `porque_accion` es casi siempre
  la frase genérica «contesta con las fichas del catálogo».
- **D4** — `sim-` no escribe; `banco-`, `panel-`, `guion-`, `diag-` sí escriben en
  `reservas.json`. Además hay sesiones `aud*` (bancos) que también escriben.
- **D5** — a) la matrícula del primer coche se queda puesta al hablar de un segundo;
  b) con matrícula antes de nombrar el coche, el precio sale igual con esa matrícula.

**Decisiones pendientes:** las 3 de D5 → `GUIONES_decisiones.md` (P1, P2, P3).

**Qué no me convence / dónde mirar tú.** El acierto de `test_busqueda` está
clavado en 0,90: sin margen para C5. Y la contaminación de +7/+1 en `salida/` sigue
ahí (no la restauro sin tu permiso).

---

## FASE 1 — Arreglos de raíz (2026-09-30)

**Qué he hecho.**
- **1.1 · D2 (la matrícula no borra la pieza).** En `07_redactor.py`, la rama
  `matricula_recien_dada and not hay_pieza` ya no contesta «Dime qué pieza buscas»
  cuando había `pieza_pedida`/`pieza_desconocida`: pasa por `_sin_pieza()` (CASO 1),
  que con la matrícula ya dada dice «no la tengo» de forma legítima y **no ofrece
  una parecida**. Verificado en vivo: antes «Anotada, 4521 KBD. Dime qué pieza
  buscas»; ahora «Con la matrícula (4521 KBD) la buscamos… ¿te la busco?».
- Añadida `rompe_el_olvido_de_pieza(lineas, pieza_pedida)` en `07_redactor.py`: una
  **sola definición** del invariante `no_olvida_pieza`, que reutilizará el banco de
  guiones (Fase 3). En `test_conversaciones.py` añadí las 2 conversaciones de D2
  (Ferrari y BMW Serie 3) con expectativa «no la tengo».
- **1.3 · `es_prueba()` (D4).** Nueva `Sistema.es_prueba(sesion)` con los prefijos
  `sim-, banco-, guion-, diag-, estres`. Usada en `anotar_reserva()`, en el registro
  de dudas (`aprender.anotar`) y en la persistencia (`guardar_sesiones`). `panel-`
  **sigue escribiendo** a propósito. Nuevo `scripts/limpiar_rastro_pruebas.py`
  (simula por defecto; `--borrar` con copia `.bak`).
- **1.2 · generador (D1):** se resuelve en la Fase 2 con `12_guiones.construir()`,
  que falla con el nombre del hueco si no se puede rellenar (no hay reserva del
  Ferrari). El `guiones()` viejo se sustituye allí.
- **1.4 · decisiones D5:** pendientes (ver `GUIONES_decisiones.md`); no implementadas.

**Números (C5 · nada empeora).** Todo verde tras los cambios:
`test_conversaciones` 225/100 % · `test_ciclo` 9/9 · `test_canales` verde ·
`test_prompt` 12/12 · `test_llm` verde. `test_frio` corriendo. **Y ya no
contamina:** correr el banco deja `reservas.json` en 40 (antes +5).

**Qué no me convence / dónde tienes que mirar tú (para «corregir juntos»).**
- El invariante `no_olvida_pieza`, aplicado a TODO el banco viejo, saca 3 casos más
  de «conversación larga»: **123 y 129** parecen olvidos reales (referencias vagas
  «la de siempre», «que te pedí») que mi arreglo de 1.1 **no** cubre (no pasan por
  la rama de la matrícula); **128 es un falso positivo** — `pieza_pedida` se
  sobrescribe con «no sé el motor» porque «motor» es un tipo (bug latente en
  `06_panel:689`). Lo dejé **fuera** del banco viejo para no romper C5; lo cazará el
  banco de guiones. ¿Arreglamos 123/129 y el sobreescrito de `pieza_pedida`?
- **`es_prueba` no cubre `aud*`** (sesiones de `test_ciclo`/`test_llm` que también
  escriben reservas). No lo metí porque no está en la lista del prompt y «aud» es un
  prefijo corto y ambiguo. ¿Lo añadimos, o renombramos esas sesiones de test?
- El Ferrari, al pasar por `_sin_pieza`, oye «te la busco; si la localizo en 24-48 h
  la tienes» — cierto y condicionado, pero para una marca que no trabajamos quizá
  quieras un «esa marca no la llevo» más seco. Anótalo para la Fase 1 fina.

---

## FASE 2 — Los 8 tipos y los 50 guiones (2026-09-30)

**Qué he hecho.**
- **`datos/guiones_tipo.json`**: las 50 plantillas del Anexo A, con huecos y
  expectativas por turno, `"sintetico": true` arriba. Transcritas tal cual (las
  `(?)` sin cambiar → `GUIONES_decisiones.md`).
- **`12_guiones.py`**: el motor. `construir(sistema, semilla=11)` rellena los
  huecos con el catálogo real mediante un **resolutor con backtracking** que elige
  un `{A}` que cumpla lo que cada guion pide (`{A2}`, `{C}`, `{CM}`, `{A.motor_otro}`,
  `{A.modelo_falso}`…). **Si un hueco no se puede rellenar, lanza `GuionError` con
  su nombre** (C2 · adiós reserva silenciosa del Ferrari). `validar()` comprueba
  C1. `evaluar_turno()` es la única definición de la evaluación: importa
  `clasificar()`/`invariantes()` de `test_conversaciones.py` y las reglas de
  `07_redactor.py` (no copia). CLI: `--validar` y `--ver G13`.
- **`Sistema.guiones()`** ahora llama a `construir()`. `/api/guiones` mantiene
  `nombre, perfil, cliente, que_prueba, mensajes` y añade `id, tipo, tipos_mezcla,
  esperado, decision_pendiente`.

**Números.**
```
py 12_guiones.py --validar
  compra 6 · regatea 6 · no_hay 7 · a_medias 6 · posventa 6 · taller 7 · corrige 6 · pago 6
  TOTAL 50 guiones · 13 mezclas · 6 con decisión pendiente (G14,G24,G28,G33,G40,G44)
  VALIDACIÓN: OK
```
Ejemplos rellenados: G13 → «un alternador para un Toyota Corolla» (ausencia real
de modelo, NO el Ferrari); G14 → Ferrari + «Renault Captur / aleta delantera
izquierda»; G35 → «Citroën C4, piloto + radiador, trasero izquierdo». Matrículas
sintéticas (`8239 VDH`…). `Sistema.guiones()` verificado: 50 con los campos nuevos.

**Qué no me convence / dónde tienes que mirar tú.**
- Las 5 expectativas `(?)` y las 6 `decision_pendiente` están en
  `GUIONES_decisiones.md` para tu sí/no.
- Los patrones de texto de las comprobaciones `nunca:` (no_baja, no_envia_sin_pago,
  no_valida_justificante…) son **provisionales**: sus falsos positivos se miden y
  ajustan con el banco real en la Fase 3 (como pide el Anexo B). `no_reabre`,
  `no_inventa` y `ficha_del_coche_anterior` aún **no bloquean** (devuelven None).
- `evaluar_turno` está escrito pero **sin ejercitar todavía** — eso es la Fase 3.

---

## FASE 3 — El banco `tests/test_guiones.py` (2026-09-30)

**Qué he hecho.** `tests/test_guiones.py`: ejecuta los 50 guiones turno a turno con
`Sistema()` (sin persistencia ni LLM), sesiones `banco-guion-<id>` (que `es_prueba`
excluye → **0 contaminación**), evalúa con `12_guiones.evaluar_turno()`, y al final
de cada guion mira el tope de aclaraciones y que una venta cerrada no se reabra.
Salidas: tabla por tipo, lista de fallos, `--json`, `--ver G13`, test de aislamiento
entre sesiones y test de coherencia del «por qué» (pendiente, se activa en Fase 4).

Antes de clasificar arreglé **2 bugs míos de la Fase 2** (no del bot), que hacían
que el guion no probara lo que dice:
- **`{X}` no era una ausencia de verdad:** lo comprobaba solo contra *en stock*, y
  el catálogo tenía la pieza *bajo pedido*, así que el bot la encontraba y le ponía
  precio (el mismo fallo que el Ferrari, al revés). Ahora la ausencia es contra
  **todo** el catálogo.
- **`{A}` con lado / sin precio publicable:** ahora `{A}` (y `{B}`) excluyen piezas
  con lado y **verifican con la búsqueda real** que llevan precio publicable, para
  que un turno que espera «precio» no espere un precio que el bot va a retener.
  (`guiones()` del panel se cachea, porque eso hace búsquedas.)

**Números (primera ejecución del banco).**
```
TOTAL 50 guiones · 541 turnos · 370 OK (68%) · 0 FUGA DE PRECIO · aislamiento OK
por tipo: compra 78% · regatea 74% · no_hay 62% · a_medias 73% · posventa 68%
          · taller 65% · corrige 57% · pago 70%
```
El umbral de salida empieza en 0 % a propósito (el bot aún no está arreglado): el
banco **PASA** porque no hay fugas; el 68 % es el mapa, no un aprobado.

**EL MAPA — 172 turnos a revisar, clasificados:**

*BOT MAL (no lo toco; es lo que decidimos arreglar juntos):*
1. **Olvida la pieza en los seguimientos** (≈25 turnos, `no_olvida_pieza`). «hola de
   nuevo», una pregunta de seguimiento, varias piezas en un mensaje, tras el VIN…
   y el bot vuelve a «¿qué pieza?». Es la familia de D2 más allá de la matrícula.
   **El más gordo.**
2. **Retiene el precio si pieza y matrícula van JUNTAS** (≈20, `precio→confirma`).
   Medido: mismo caso separado en dos turnos → da «85,90 €»; junto en un mensaje →
   «lo tiene que mirar Álvaro». No desambigua con la matrícula en el mensaje combinado.
3. **Escalado pegajoso** (≈17, `sigue escalado` / `política→escala`). Tras escalar,
   el bot no atiende una pieza nueva legítima ni contesta una política (G15, G19).
4. **«Venta cerrada» tapa demasiado** (7). Tras cerrar, se come una pieza nueva o un
   «¿tiene garantía?» (G03·t7, G17·t8).
5. **No escala regateo indirecto** (≈11, `escala→política`). «¿me regalas el
   transporte?», «¿sin factura?» → contesta política en vez de escalar.
6. **«Corrige un detalle» se dispara mal** (4). Lee «¿no la tenéis?» o el VIN como
   una corrección de coche (G06·t2, G13·t2, G18·t2).

*EXPECTATIVA MAL (mi listón; propongo cambio, no lo aplico sin tu OK):*
- **A · «¿cuándo llega?» → `recuerda` vale** (13, `política→recuerda`). El bot da el
  plazo de ESA pieza en vez de citar la política general; es mejor respuesta.
  **Propongo:** esos turnos = `política|recuerda`.
- **B · `no_hay` turno 1: pedir la matrícula cuenta como «no la tengo»** (≈9). El bot
  pide la matrícula (correcto, no dice «no»), pero `clasificar()` lo etiqueta «no la
  tengo» porque la decisión es NO DISPONIBLE. El guardarraíl de verdad
  (`no_dice_no`) **sí pasa**. **Propongo:** aceptar `no la tengo` en esos turnos, o
  afinar `clasificar()` para distinguir «pide matrícula» de «dice no».

*DECISIÓN (ya decidida, el bot aún no la implementa):*
- **P1** (G44), **P2** (G28), **P3** (G14·t7 dio precio con la matrícula del Ferrari,
  `sin_precio`). Son los arreglos de las decisiones D5, pendientes de codificar.

**Qué no me convence / dónde mirar tú.** El mapa de arriba. Los patrones `nunca` de
texto se comportaron sin falsos positivos llamativos salvo lo esperado;
`no_reabre`/`no_inventa`/`ficha_del_coche_anterior` siguen sin bloquear.

---

## FASE 3bis — Arreglos del bot elegidos (BOT 1-2 + P1/P2/P3) (2026-10-01)

Álvaro eligió «lo gordo + las 3 decisiones». Cada arreglo, verde en los bancos.

**Expectativas (A y B, aprobadas):**
- **A** · a «¿cuándo llega?» el plazo de la pieza (`recuerda`) vale como `política`:
  una regla en `evaluar_turno` (`_PLAZO`).
- **B** · en `no_hay` t1, pedir la matrícula cuenta como `no la tengo` (etiqueta
  añadida a esos turnos; el guardarraíl `no_dice_no` sigue). *(El intento de
  afinar `clasificar()` rompía C5 — 100 %→83 %; revertido, hecho por guion.)*

**Bot (test-primero, con el banco de guiones como test):**
- **BOT 2 · precio cuando pieza y matrícula van juntas.** Causa: `pieza_pedida`
  guardaba el mensaje entero (con la matrícula), y buscar con ese ruido bajaba la
  puntuación. Arreglo: `07_redactor.sin_matricula()` limpia el texto de búsqueda
  (la matrícula identifica, no busca). Medido: junto → ahora «85,90 € + IVA».
- **P1 · matrícula sin coche.** Nueva rama: con pieza y matrícula pero sin coche,
  pide «¿de qué coche es?» (el modelo, no la pieza) y no retiene nada raro.
- **P3 · una matrícula por coche.** En `chatear()`, al pasar a OTRO coche (por
  tokens, no una corrección ni el mismo coche), se suelta la matrícula anterior;
  el 2.º coche pide la suya. Las fichas/precios ya vistos se conservan.
- **P2 · queja escalada bloquea venta nueva. → REVERTIDO (rompía C5).** Lo intenté
  con un flag `queja_abierta`, pero el clasificador de quejas tiene un falso
  positivo: «bueno va, otra cosa» cuenta como queja, y entonces P2 bloqueaba una
  pieza nueva legítima («el radiador lo tienes?») y repetía «sigue con Álvaro» en
  la posventa — 6 conversaciones de `test_frio` en rojo. Como C5 manda, lo quité.
  **P2 necesita primero endurecer el clasificador de quejas** (que no se dispare
  con despidos/muletillas); queda para la revisión conjunta. El flag se queda
  puesto pero sin usar, listo para cuando se arregle eso.
- **BOT 1 (parcial) · olvidar la pieza.** Arreglado lo seguro: un «hola de nuevo»
  con pieza sobre la mesa cae a la rama de seguimiento (no reabre), y un «vale»/«ok»
  con pieza no vuelve a pedirla. **Queda para revisar juntos** lo profundo: el VIN
  que no identifica (G06), varias piezas en un mensaje (G09/G16), y que `pieza_pedida`
  no se limpia al cerrar/corregir (falsos positivos del propio invariante).

**Números (medición definitiva tras revertir P2).** Banco de guiones **68 % → 74 %**
(403/541), 0 fugas, aislamiento OK. *(Con P2 a medias marcaba 407/75 %; el revert
cuesta 4 turnos de G28 — lo esperado, esos turnos quedan pendientes de P2.)*
Por tipo: compra 88 % · regatea 79 % · no_hay 70 % · a_medias 80 % · posventa 70 % ·
taller 71 % · corrige 66 % · pago 75 %.
**C5 intacto** en los 10 bancos: `test_frio` **reconfirmado verde tras el revert**
(las 50 conversaciones aguantan, ningún invariante roto, exit 0); el resto
(`test_conversaciones` 225/100 %, `ciclo`, `canales`, `prompt`, `llm`) verdes en este
mismo estado de código (el revert devuelve la condición de escalado a su forma
original y el flag `queja_abierta` queda sin leer → comportamiento idéntico al ya
verificado).

**Qué queda (para la revisión conjunta, sin tocar):** BOT 3 (escalado pegajoso ~17),
BOT 4 (venta cerrada tapa ~7), BOT 5 (regateo indirecto ~11), BOT 6 (corrige se
dispara mal ~4), y el resto de BOT 1.

---

## FASE 4 — La traza del «por qué», registrada donde se decide (2026-10-01)

**Qué he hecho.** El «por qué» se escribe ahora **en el mismo punto del código en
que se toma cada decisión**, no se deduce después a partir de los nombres de las
reglas (era el fallo D3). Nuevo módulo `13_traza.py` + cableado en `chatear()`:

- Cada rama del `if/elif` de contexto de `chatear()` pone **su etiqueta de rama y su
  frase** (`rama_contexto`, `rama_porque`) en la propia rama: `correccion_coche`,
  `coche_de_memoria`, `pieza_de_memoria`, `pieza_referida`, `matricula_desbloquea` o
  `ninguna`. Así la rama que explica el turno es, por construcción, la que de verdad
  completó la búsqueda.
- `elegir_accion()` (en `08_conversar.py`) devuelve un **`porque_accion` concreto**
  que nombra el dato que disparó la acción (qué ficha y su puntuación, qué política,
  cuántas opciones, cuántas aclaraciones). Las frases genéricas de relleno
  («contesta con las fichas del catálogo») quedan prohibidas, como pide §8.2.
- Las **auditorías** se evalúan TODAS para enseñarlas (`estilo, matricula,
  identificacion, apertura, guion, importes`), pero **la decisión no cambia**: sigue
  siendo la primera que falla, en el mismo orden. Solo se calculan cuando redacta el
  LLM; sin LLM, la lista va vacía. El `texto_modelo` descartado se guarda para poder
  comparar lo que escribió el modelo con lo que salió (lo que habría destapado D2).
- El **`resumen`** es una frase **determinista por plantilla** (acción × fuente),
  nunca escrita por el LLM. Nombra las tres cosas que pide §8.2: qué hizo el bot, el
  dato del cliente que lo provocó y la fuente (ficha, política, FAQ, regla o persona).
- La **memoria antes/después** del turno viaja en el paso 8, con la lista de lo que
  cambió. `/api/chat` **solo suma** la clave `traza`: no quita ni renombra `bot`,
  `busqueda` ni `memoria`, así que el panel viejo sigue funcionando (§9.3).
- Todo el montaje va envuelto en `try/except`: si la traza fallara, jamás tumba una
  respuesta real (manda C5); el test C7 lo cazaría.

**Test de coherencia (C7).** Activado en `tests/test_guiones.py`
(`coherencia_turno()`): por cada turno comprueba que la traza existe, que su paso de
acción es igual a `bot.accion`, que las reglas de la traza son iguales a `bot.reglas`
y que el `resumen` no está vacío.

**Números.**
```
py tests/test_guiones.py
  Turnos OK: 403/541 (74%)  ·  Aislamiento entre sesiones: OK
  Coherencia del «por qué» (C7): OK — los 541 turnos coinciden con la traza
  Tiempo total: 150 s  ·  RESULTADO: PASA (sin fugas; C7 verde)
```
C5 intacto: `test_conversaciones.py` PASA, 0 invariantes en 225 casos (la traza es
aditiva y los bancos corren sin LLM, así que el comportamiento no cambia).

**3 trazas reales, una por rama** (deterministas, sesiones `diag-`, 0 contaminación):
```json
{
  "coche_de_memoria": {
    "resumen": "Te ha pedido la matrícula para identificar la pieza porque preguntaste por radiador audi a4: sin saber el coche no puede confirmar cuál monta.",
    "rama_contexto": "coche_de_memoria",
    "por_que_rama": "No repetiste el coche: se usa el AUDI A4 que ya dijiste.",
    "accion": "RESPONDER",
    "por_que_accion": "la ficha de Radiador de un AUDI A4 es la que supera el umbral de confianza (0.84)"
  },
  "matricula_desbloquea": {
    "resumen": "Te ha dado el precio (94,65 € + IVA) de Alternador SEAT León porque diste la matrícula (1234 BCD) y esa ficha del catálogo supera el umbral de confianza (0.85 >= 0.50).",
    "rama_contexto": "matricula_desbloquea",
    "accion": "RESPONDER",
    "por_que_accion": "la ficha de Alternador de un SEAT León es la que supera el umbral de confianza (0.85)"
  },
  "ninguna": {
    "resumen": "Te ha contestado con la política «FORMAS DE PAGO Y DEVOLUCIONES» porque lo preguntaste; la política lo cubre (0.82 >= 0.34).",
    "rama_contexto": "ninguna",
    "accion": "RESPONDER",
    "por_que_accion": "cita la política «FORMAS DE PAGO Y DEVOLUCIONES» porque encaja con lo que preguntaste (0.82)"
  }
}
```

**Qué no me convence / dónde mirar tú.**
- En `matricula_desbloquea`, la frase de la rama arrastra el mensaje entero
  («se vuelve a buscar *buenas, necesito un alternador para un seat leon*…») porque
  `pieza_pedida` guarda el mensaje completo (bug latente `06_panel.py:689`, ya en
  `GUIONES_pendientes.md`). Es **cosmético** en la traza y **no rompe C7**: la traza
  es coherente con lo que el bot hizo. Se arregla con el lote del bot.
- **Commit pendiente** (por tu instrucción, nada commiteado): la Fase 4 son
  `13_traza.py` (nuevo) + los cambios de traza en `06_panel.py` y `08_conversar.py`.

---

## FASE 5 — El panel: desplegable, reproductor y el nuevo «Por qué» (2026-10-01)

**Qué he hecho.** Rework del chat del panel siguiendo §9. **No toqué** el lenguaje
visual: solo tokens de `lenguaje.css`/`sistema.css` (sin colores nuevos), tema claro
y oscuro, y todo funciona con teclado.

- **§9.1 · Desplegable + reproductor** (`index.html`, `chat.js`, `chat.css`). La fila
  de chips se sustituye por dos `<select>` nativos: el 1.º con los **8 tipos** y su
  número de guiones; el 2.º con los guiones de ese tipo, marcando «· mezcla». Debajo:
  **▶ Reproducir**, **⏭ Paso a paso**, **⏸ Parar** y **Velocidad (Normal | Rápida)**,
  más una línea de info del guion (prueba, nº mensajes, trato, mezcla). Reproducir
  manda los mensajes uno a uno por el **mismo `enviar()`**; Paso a paso avanza un
  turno por pulsación; Parar corta al terminar el turno en curso sin dejar el chat
  bloqueado; `Esc` también para. «Rápida» **acorta** las pausas (×0,4), no las quita.
  Durante la reproducción se desactivan el campo de texto, el cambio de perfil y los
  selectores; al acabar o parar, todo vuelve.
- **§9.2 · ✓/✗ por turno.** `enviar()` acepta `guion:{id,turno}` y lo manda en
  `/api/chat`. **El servidor evalúa** con `12_guiones.evaluar_turno()` —la ÚNICA
  definición, la misma del banco— en el nuevo `Sistema.evaluar_guion_turno()`, y
  devuelve `evaluacion:{ok,esperado,obtenido,fallos,decision_pendiente}`. El panel
  **solo pinta**: una marca ✓/✗ bajo cada respuesta con tooltip «esperado:… ·
  obtenido:…», y al terminar el guion una línea «X/Y turnos OK · Z invariantes rotos».
  El chat escrito a mano no manda `guion` y no lleva ✓/✗ (no hay expectativa).
- **§9.3 · El nuevo «Por qué».** Se pinta desde `datos.traza` (Fase 4): cabecera
  (acción, decisión, intención, ms) + resumen en grande + los **8 pasos** en vertical
  (①-⑧), cada uno con icono de estado y plegable para ver los datos; los pasos sin
  contenido salen en gris con «—», no se esconden. El paso ③ lleva la **barra de
  puntuación con la marca del umbral** (ámbar si no llega). El ⑦ lleva una **píldora
  por auditoría** y, si se descartó al modelo, «ver lo que escribió» abre las **dos
  versiones** (modelo descartado vs. enviado). El ⑧ resalta lo que cambió en la
  memoria (`antes → después`). El **sello de precio y la alerta «¡FUGA!»** siguen
  arriba del todo. **Clic (o Enter) en cualquier burbuja del bot** repinta la traza de
  ESE turno (se guardan en el navegador solo para pintarlas; la memoria sigue en el
  servidor). **Compatibilidad:** si una respuesta no trae `traza`, cae al «por qué» de
  siempre sin romperse.
- **C6 · sin rastro.** Los guiones del panel corren en sesión
  `guion-<id>-<marca de tiempo>` (que `es_prueba` excluye); el chat a mano sigue en
  `panel-…` y sigue escribiendo a propósito.

**Qué he verificado (sin navegador).**
- Sintaxis: `node --check panel/chat.js` OK; `py_compile` de `06_panel.py` OK.
- **Servidor == banco:** `evaluar_guion_turno` da el mismo ✓/✗ que el banco en G01,
  G13, G07 y G28 (script de comprobación), reutilizando la única definición.
- **Payload de `/api/chat` con guion** (en proceso): devuelve `bot, busqueda, memoria,
  traza` (8 pasos) **y** `evaluacion`, conviviendo; `/api/guiones` trae
  `id, tipo, tipos_mezcla, esperado, decision_pendiente, …`. Ejemplo G01: t1 saludo
  (pide datos ✓), t2 pieza+coche (confirma ✓, pregunta cuál de 2), t3 matrícula
  (precio 327,73 € ✓).

**Qué NO he podido verificar (tus ojos, §9.4 / C8).** El render en navegador: 0 errores
en consola, tema oscuro y claro, y a 390 px de ancho. **No lo puedo abrir desde aquí.**

> **IMPORTANTE para probarlo:** hay un panel **antiguo ya escuchando en el puerto
> 8420** (devuelve los 5 guiones viejos, sin `id`). Ciérralo antes (Ctrl+C en su
> ventana, o `netstat -ano | findstr 8420` y matar ese PID) y arranca de nuevo
> `py 06_panel.py`, o no verás los cambios (el propio panel te avisará de que el
> puerto está ocupado).

**5 clics para que pruebes tú:**
1. En «Conversaciones tipo», elige tipo **No la tenemos** → guion **G14** (Ferrari) y
   pulsa **▶ Reproducir**: mira los ✓/✗ por turno y la línea de resumen al final.
2. Elige **G13** y usa **⏭ Paso a paso**: avanza turno a turno; comprueba que el campo
   de texto está desactivado y que **Parar** (o `Esc`) lo libera a mitad.
3. En cualquier guion ya reproducido, **haz clic en una burbuja del bot de un turno
   anterior**: el «Por qué» debe repintarse con la traza de ESE turno.
4. Abre el paso **③ Qué ha encontrado**: comprueba la barra de puntuación y la marca
   del umbral (en un turno que dé precio y en uno que lo retenga).
5. Cambia a **tema claro** y estrecha la ventana a **390 px**: revisa que no haya
   errores en consola ni desbordes, y que los 8 pasos se lean.

**Commit pendiente** (por tu instrucción): Fase 5 = `panel/index.html`, `panel/chat.js`,
`panel/chat.css` + el endpoint de evaluación en `06_panel.py`.

---

## FASE 6 — Cierre (PARADA 3 de 3) · 02-10-2026

**Qué he hecho.** El cierre de §10: los bancos contra la línea base (C5), el recuento
de datos (C6), la sección nueva de `docs/QA_panel.md` («Conversaciones tipo y Por
qué»), el párrafo del `README.md` (sin inflar cifras) y el estado de las decisiones en
`docs/GUIONES_decisiones.md`. No he hecho `push` ni commits (por tu instrucción).

**C5 · nada empeora — los 11 bancos contra la línea base (uno a uno):**

| banco | línea base | ahora | ¿igual o mejor? |
|---|---|---|---|
| `test_conversaciones` | 100 % · 0 inv | PASA · 225 · 0 inv | sí |
| `test_busqueda` | acierto@1 0,90 · guardarraíl 1,0 | PASA (umbral intacto) | sí |
| `test_precios` | 5000/5000 | PASA · 5000/5000 | sí |
| `test_ofertas` | PASA | PASA | sí |
| `test_mesa` | 45/45 | 45/45 | sí |
| `test_ciclo` | 9/9 | 9/9 (exit 0) | sí |
| `test_canales` | 50+20 · 209 msg · 0 rep | igual | sí |
| `test_frio` | 50 · 1041 turnos · 0 inv | exit 0 · 0 inv | sí |
| `test_prompt` | 12/12 | 12/12 | sí |
| `test_llm` | PASA | OK | sí |
| `test_guiones` | — (nuevo) | 403/541 (74 %) · 0 fugas · C7 541/541 | n/a |

`test_frio` es el canario: pasa **con la traza corriendo en los 1041 turnos**, así que
la traza (Fase 4) no cuesta ningún invariante ni rompe nada.

**C6 · cero rastro de pruebas:** recuento antes y después de correr TODA la batería:

| fichero | antes | después |
|---|---|---|
| `reservas.json` | 40 | **40** |
| `no_resueltas.json` | 42 | **42** |
| `actividad.json` | 16 | **16** |

Correr los bancos + los 50 guiones **no añade nada**. *(La contaminación histórica de
+7/+1 que ya había en `salida/` —de antes de este trabajo— sigue ahí a la espera de tu
decisión de restaurar; está en `GUIONES_pendientes.md` §4, no la toco sin tu sí.)*

**C1-C8 — cumplido o no, con su número:**

| # | Criterio | Estado |
|---|---|---|
| C1 | 8 tipos · 50 guiones · 10-15 msg · ≥10 mezclas | **OK** (`--validar` OK · 13 mezclas) |
| C2 | ni un hueco sin rellenar ni reserva silenciosa | **OK** (`construir()` lanza `GuionError`) |
| C3 | 0 invariantes rotos en los 50 guiones | **OK** (`test_guiones` exit 0 · 0 fugas) |
| C4 | ≥95 % de turnos cumplen su expectativa | **74 %** · falta arreglar el bot (mapa clasificado; P2 revertida) |
| C5 | nada empeora | **OK** (tabla de arriba) |
| C6 | cero rastro en los datos del negocio | **OK** (recuento sin cambios) |
| C7 | el «por qué» sale del servidor y es coherente al 100 % | **OK** (541/541) |
| C8 | panel: desplegable, reproductor, ✓/✗, «por qué», 0 errores en consola, claro/oscuro, 390 px | **Front hecho; verificación en navegador pendiente de ti** (§9.4) |

**Qué no me convence / dónde tienes que mirar tú.**
- **C8 es lo único que no puedo cerrar yo:** el render en navegador. Los 5 clics
  concretos están en la Fase 5 de este informe. Antes, cierra el panel viejo del
  puerto 8420.
- **C4 está en 74 %, no en 95 %**, a propósito: aplazamos los arreglos del bot (tu
  decisión de orden). El mapa de qué falla y por qué está en la Fase 3 y en
  `GUIONES_pendientes.md` §1. Cuando los ataquemos, el umbral de salida de
  `test_guiones` se sube hacia 0,95.
- **Caso 166 de `test_conversaciones`**: 1 desajuste blando (Ferrari + P1 dice «¿de qué
  coche es?»); el banco PASA igual (0 invariantes). Es efecto de P1/P3, queda para el
  lote del bot.

**Preguntas para ti (sí/no cuando se puede).**
1. ¿Abres el panel y haces los 5 clics de la Fase 5 para cerrar C8? (yo no puedo).
2. ¿Restauro `salida/` desde el backup para quitar la contaminación histórica +7/+1
   (`scripts/limpiar_rastro_pruebas.py`), o lo dejas?
3. Ahora que cerramos 4-5-6, ¿empiezo con los arreglos del bot de
   `GUIONES_pendientes.md` §1 (orden sugerido: endurecer el clasificador de quejas →
   desbloquear P2, luego el resto de BOT 1)?
4. ¿Quieres que prepare los commits por fase (4, 5, 6) cuando digas, o lo dejas todo en
   el árbol de trabajo como hasta ahora?

**Commits:** ninguno (por tu instrucción). Todo en el árbol de trabajo.

---
