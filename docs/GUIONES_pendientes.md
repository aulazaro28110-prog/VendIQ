# Ajustes pendientes — «Conversaciones tipo»

> Lista única de todo lo que queda por decidir o arreglar, para revisarlo juntos.
> Actualizado el 2026-10-04. Lo **hecho y verde** está en `GUIONES_informe.md`; las
> **decisiones de negocio** en `GUIONES_decisiones.md`. Aquí solo lo PENDIENTE.
>
> Regla que manda sobre todo: **C5 · nada empeora** (los 10 bancos verdes). Varios
> arreglos del bot se quedaron fuera porque rompían C5; se anotan aquí, no se fuerzan.

---

## 0. Orden de trabajo acordado (2026-10-01)

Álvaro decide la secuencia: **todo lo «pendiente / bloqueado» (secciones 1, 2 y 3 de
este documento: arreglos del bot, el fleco D4 de `aud*` y la calibración de patrones)
cuenta como trabajo pendiente y se queda aquí anotado.** Pero **no se toca todavía**.

**Primero las fases que faltan: 4 → 5 → 6** (sección 5). Cuando estén cerradas,
reabrimos este documento y rematamos las modificaciones del bot punto por punto.

- [x] Registrado el orden: Fases 4, 5 y 6 antes que los arreglos del bot.
- [x] Fase 4 · traza del «por qué» — C7 verde (541/541), C5 intacto. En `GUIONES_informe.md`.
- [x] Fase 5 · el panel — servidor verificado y **front cerrado** (reproductor, ✓/✗ por turno y «por qué» paso a paso). Commit `7bc6813`.
- [x] Fase 6 · cierre — C5 (11 bancos verdes), C6 (0 rastro), QA_panel + README + decisiones. PARADA 3 en `GUIONES_informe.md`.
- [x] Extra del panel (03/04-10): barra lateral trasplantada del portfolio (plegable, memoria, scroll-spy), encuadre simétrico y 8 correos de ejemplo en la bandeja. Commits `7bc6813` y `ec4c5b3`.
- [x] Árbol limpio y commiteado: borrada la basura de ficheros-fragmento; el trabajo del panel, en dos commits. (Resuelve el punto «Commit» de la sección 4.)
- [x] **G06 cerrado (04-10):** arreglo quirúrgico en dos partes —`CORRIGE` excluye
  «no tengo…/no la tenéis» (el VIN ya da precio) y `dice_que_si` cede ante una
  afirmación-pregunta («vale, …sale hoy?» = política, no cierre)— más el pool
  `ultima_pieza` 6→10 que mata la repetición de la conv 24 en `test_frio`. **Banco
  403→406, G06 6→9, los 11 bancos verdes.** Commits `3039551` (arreglo) + flecos.
- [x] **Fleco D4 (`aud*`) cerrado (04-10):** `test_prompt` se autolimpia sus reservas
  `aud*` al terminar (§23 sigue comprobando la escritura real). Detalle en §2.
- [ ] **← AQUÍ ESTAMOS:** sigue la sección 1 (BOT 1 «varias piezas» G09/G16 y el bug
  latente de `pieza_pedida`; BOT 3/4/5; P2) y la sección 3 (expectativas). Queda
  suelto el fleco G06·t6 (la política de recogida, soft miss sin fallo).

---

## 1. Arreglos del bot pendientes (del mapa de la Fase 3)

Orden sugerido por impacto. Ninguno tocado todavía salvo lo que diga «hecho parcial».

- [ ] **P2 · queja escalada bloquea venta nueva** (G28). *Intentado y REVERTIDO: rompía
  C5.* El clasificador de quejas da un falso positivo —«bueno va, otra cosa» cuenta
  como queja— y bloquear ventas con «queja viva» tumbaba 6 conversaciones de
  `test_frio`. **Antes de P2 hay que endurecer el clasificador de quejas** para que no
  se dispare con despidos/muletillas. El flag `queja_abierta` ya está puesto (sin usar).
- [ ] **BOT 1 (resto) · olvidar la pieza.** Hecho lo seguro (saludo + muletilla).
  **Causa raíz localizada (02-10):** los **17** turnos de «vuelve a preguntar qué
  pieza» caen en el `else` final del redactor ([07_redactor.py:2897-2907]) con una
  pieza ya sobre la mesa. No hay un arreglo de una línea: cada familia necesita una
  respuesta distinta (seguimiento que responde por la ficha en G06; «no» que no
  re-pregunta en G13/G14/G16/G18; retomar en el «aparca y vuelve» de G48), y está
  **enredado con el bug de `pieza_pedida`** (guarda el mensaje entero, [06_panel.py:689]),
  así que para mostrar/usar la pieza hay que arreglar antes ese bug. Es un cambio de
  diseño del redactor con riesgo C5 → test-primero + banco entero, revisión conjunta.
  Queda:
  - [x] el **VIN no identifica** como la matrícula (G06): HECHO (04-10). No era el
    VIN —se detecta bien—, era `CORRIGE` leyendo «no tengo la matrícula» como una
    corrección de coche. Arreglado en `07_redactor.py` (commit `3039551`).
  - [x] **varias piezas en un mensaje** (G09, G16, G34, G50…): HECHO (04-10). El panel
    parte el mensaje en piezas (partidor con guarda estricta: solo con 2+ tipos
    distintos; validado 0 falsos positivos en 652 mensajes), busca cada una por
    separado y el redactor contesta por todas en ≤3 líneas, con el precio de cada una
    autorizado pieza a pieza. Se recuerdan todas —incluida la que falta— para «la
    primera/segunda/de en medio» y «me quedo las dos». **Banco 406→414, 11 bancos
    verdes.** Quedan sueltos **G34·t5 «las tres»** (cierre demasiado genérico para
    patrón global) y **G16·t3 «las otras dos cuánto»** (recordar precio de las dos),
    como soft miss sin fallo.
  - [ ] **`pieza_pedida` no se limpia** al cerrar la venta o al corregir el coche, así
    que el invariante `no_olvida_pieza` salta en falso en «vale»/«ok» tardíos.
- [~] **BOT 3 · escalado pegajoso** (G15, G19) — PARCIAL (05-10). Con algo escalado que
  NO es queja, una pregunta de CONDICIONES («¿y tarda?») ahora se contesta en vez de
  «sigue con Álvaro» (nuevo respaldo `_politica_por_tema` en la rama de escalado, con
  `queja_abierta` como candado para no tocar P2). **G15 6→7.** Queda para v1.1: las
  piezas NUEVAS legítimas y los cierres «vale, ese/esa» siguen tapados por el escalado
  (es el cambio de fondo del estado `escalado`, que choca con P2); G19 no se movió.
- [x] **BOT 4 · «venta cerrada: no reabrir» tapa de más** (G17·t8) — HECHO (05-10). Una
  pregunta de condiciones en posventa («¿tiene garantía?») se contesta con la política
  en vez de «¡perfecto!» (mismo respaldo `_politica_por_tema` en la rama de venta
  cerrada). **G17 9→10.** Queda **G03·t7** en v1.1: la pieza nueva tras cerrar retiene
  el precio (la ficha concreta del catálogo no lo publica; es dato, no lógica).
- [x] **BOT 5 · no escala el regateo indirecto** (G07, G08) — HECHO (04-10). «¿me
  regalas el transporte?», «¿sin factura?», «X euros menos y me lo llevo», «clientes
  de siempre» ya se leen como regateo (van ANTES del cierre en `PALABRAS_INTENCION`),
  así que escalan en vez de contestar la política o cerrar. **G07 8→10, G08 8→10, banco
  414→418, 11 bancos verdes.**
- [x] **BOT 6 · «corrige un detalle» se dispara mal** (G06·t2) — HECHO (04-10). Leía
  «no tengo la matrícula» / «¿no la tenéis?» como una corrección de coche. El lookahead
  de `CORRIGE` ([07_redactor.py:855]) ahora excluye **sólo los patrones exactos** (tengo
  la/el/ning…, la/lo/las tenéis/tienes/tengo), sin el «tengo» amplio que el primer
  intento usó y que arrastraba falsos negativos a `test_frio`. Al dar precio el VIN,
  quedó al descubierto un segundo bug (t5: «vale, …sale hoy?» cerraba la venta en vez de
  dar política): se arregló en `dice_que_si`. Y la repetición de la conv 24 se mató
  subiendo el pool `ultima_pieza` 6→10. **Banco 403→406, G06 6→9, 11 bancos verdes**
  (commit `3039551`). Queda **G06·t2 en G13/G18** (otras plantillas) y **G06·t6** (la
  política de recogida) como soft miss sin fallo. El diff del banco sólo movió G06;
  G13/G18 no cambiaron con este arreglo (si su t2 fallaba, habrá que mirarlo aparte).
- [ ] **Bug latente** `06_panel.py:718`: `pieza_pedida = mensaje` guarda el mensaje
  entero (afecta al invariante `no_olvida_pieza` y a la rama `matricula_desbloquea`).
  **Intentado (04-10) filtrar en origen a sólo tipo+lado: REGRESÓ el banco 403→391.**
  La rama `matricula_desbloquea` ([06_panel.py:875]) usa el crudo como contexto y, al
  filtrar, pierde el coche embebido («…para un audi a4») con el que acertaba. Revertido.
  El arreglo real es **por-rama** (filtrar sólo donde el coche estorba, no en la de la
  matrícula) o endurecer el invariante aparte — es parte de BOT 1, **revisión conjunta**.

> **Disciplina para cada uno:** test primero (el banco de guiones vale), y re-correr
> TODOS los bancos después (C5). No fiarse solo de `test_conversaciones` y el banco de
> guiones: P2 pasaba esos dos y rompía `test_frio`.

## 2. Fuga de datos (D4) — un fleco

- [x] **La fuga `aud*` cerrada (04-10).** El origen no era `test_ciclo`/`test_llm`
  (usan `sim-ciclo-` y `b…`, no dejan rastro), sino **`test_prompt`**: su §23 («lo que
  dice que hace, lo hace») cierra una venta real y relee `reservas.json` para comprobar
  que se escribió, así que NO puede usar un prefijo de prueba (silenciaría la escritura
  que verifica). En vez de la whitelist, `test_prompt` **se autolimpia sus filas `aud*`
  al terminar**, cuando ningún caso va a volver a leer el fichero. Cierra D4 sin tocar
  la comprobación. Reservas `aud6`/`aud10` ya borradas.

## 3. Expectativas y evaluación

- [ ] **Patrones `nunca` de texto sin calibrar del todo** (`no_baja`, `no_envia_sin_pago`,
  `no_valida_justificante`, `no_diagnostica`, `no_promete`, `no_simula`): medir falsos
  positivos contra el banco real y ajustar (Anexo B lo pide).
- [ ] **`no_reabre`, `no_inventa`, `ficha_del_coche_anterior`** aún devuelven `None` (no
  bloquean). Implementarlos cuando el bot esté más arreglado.
- [ ] **`clasificar()` no distingue** «pide la matrícula» de «dice que no» cuando la
  decisión es NO DISPONIBLE (de ahí EXPECT B, resuelto por guion). Si se quiere afinar
  `clasificar()`, hacerlo con cuidado: el intento directo rompió `test_conversaciones`
  (100 %→83 %).

## 4. Datos y git (decisiones tuyas)

- [ ] **Restaurar `salida/`**: la línea base dejó +7 reservas y +1 no_resuelta de prueba.
  Hay backup en el scratchpad y está `scripts/limpiar_rastro_pruebas.py --simular`. No lo
  toco sin tu sí.
- [x] **Commit** (04-10): árbol limpio (borrada la basura de ficheros-fragmento de 0 bytes)
  y el trabajo del panel en dos commits (`7bc6813` barra+front, `ec4c5b3` correos). Los
  tres docs sueltos de la raíz (`CIERRE_VendIQ_Prompt`, `PROMPT_VSCODE_conversaciones_
  tipo_y_porque`, `VendIQ_Manual_Conversacion_Multiturno`) a `.gitignore` (04-10): son
  notas de trabajo, no documentación del sistema.
- [ ] **Frase del Ferrari** (vía `_sin_pieza`): dice «te la busco; si la localizo en
  24-48 h la tienes». Para una marca que no trabajamos quizá quieras algo más seco.
- [ ] **`rompe_el_guion` con el LLM encendido**: la Fase 1.1 pedía revisar por qué tiró
  la redacción correcta. Con el borrador determinista arreglado ya no pasa, pero no se
  verificó con Groq encendido (los bancos corren sin LLM).

## 5. Fases que faltan

- [ ] **Fase 4 · la traza del «por qué»**: objeto `traza` en `/api/chat`, registrado
  donde se decide cada cosa, + el test de coherencia (C7).
- [ ] **Fase 5 · el panel**: desplegable de 8 tipos y 50 guiones, reproductor, ✓/✗ por
  turno y el nuevo «Por qué». **No verificable en navegador desde aquí** — necesita tus
  ojos.
- [ ] **Fase 6 · cierre**: `docs/QA_panel.md`, párrafo en `README.md`, repaso final de
  C1-C8 y recuento de datos de negocio.

---

### Estado de lo YA hecho y verde (resumen, detalle en `GUIONES_informe.md`)
Fase 0 (línea base + D1-D5) · Fase 1 (D2, `es_prueba`) · Fase 2 (50 guiones + motor) ·
Fase 3 (banco + mapa) · arreglos del bot BOT 2, P1, P3 y BOT 1 parcial.
Banco de guiones: 68 % → **78 %** (420/541, tras G06, «varias piezas», BOT 5, BOT 4 y
BOT 3 parcial) · 0 fugas ·
C5 intacto (los 11 bancos verdes; `test_frio` 0 trampas y 0 invariantes rotos).
