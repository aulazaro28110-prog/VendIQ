# Ajustes pendientes — «Conversaciones tipo»

> Lista única de todo lo que queda por decidir o arreglar, para revisarlo juntos.
> Actualizado el 2026-10-01. Lo **hecho y verde** está en `GUIONES_informe.md`; las
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
- [x] Fase 5 · el panel — servidor verificado; **front pendiente de que Álvaro lo abra** (§9.4/C8). 5 clics en `GUIONES_informe.md`.
- [x] Fase 6 · cierre — C5 (11 bancos verdes), C6 (0 rastro), QA_panel + README + decisiones. PARADA 3 en `GUIONES_informe.md`.
- [ ] **← AQUÍ ESTAMOS:** volver a las secciones 1-4 (arreglos del bot y decisiones de datos/git)

---

## 1. Arreglos del bot pendientes (del mapa de la Fase 3)

Orden sugerido por impacto. Ninguno tocado todavía salvo lo que diga «hecho parcial».

- [ ] **P2 · queja escalada bloquea venta nueva** (G28). *Intentado y REVERTIDO: rompía
  C5.* El clasificador de quejas da un falso positivo —«bueno va, otra cosa» cuenta
  como queja— y bloquear ventas con «queja viva» tumbaba 6 conversaciones de
  `test_frio`. **Antes de P2 hay que endurecer el clasificador de quejas** para que no
  se dispare con despidos/muletillas. El flag `queja_abierta` ya está puesto (sin usar).
- [ ] **BOT 1 (resto) · olvidar la pieza.** Hecho lo seguro (saludo + muletilla). Queda:
  - [ ] el **VIN no identifica** como la matrícula (G06): tras dar el bastidor sigue
    pidiendo la pieza.
  - [ ] **varias piezas en un mensaje** (G09, G16): «módulo, airbag y faro» → el bot
    coge una o ninguna.
  - [ ] **`pieza_pedida` no se limpia** al cerrar la venta o al corregir el coche, así
    que el invariante `no_olvida_pieza` salta en falso en «vale»/«ok» tardíos.
- [ ] **BOT 3 · escalado pegajoso** (G15, G19). Tras escalar algo (que NO es una queja),
  el bot no atiende una pieza nueva legítima ni contesta una política. Es el lado
  opuesto de P2: aquí sobra escalado.
- [ ] **BOT 4 · «venta cerrada: no reabrir» tapa de más** (G03·t7, G17·t8). Tras cerrar,
  se come una pieza nueva o un «¿tiene garantía?».
- [ ] **BOT 5 · no escala el regateo indirecto** (G07·t6, G08·t6). «¿me regalas el
  transporte?», «¿sin factura?» → contesta política en vez de escalar.
- [ ] **BOT 6 · «corrige un detalle» se dispara mal** (G06·t2, G13·t2, G18·t2). Lee
  «¿no la tenéis?» o el VIN como una corrección de coche.
- [ ] **Bug latente** `06_panel.py:689`: `pieza_pedida = mensaje` se sobrescribe con
  cualquier mensaje que lleve un tipo de pieza dentro («no sé el motor» → «motor»).

> **Disciplina para cada uno:** test primero (el banco de guiones vale), y re-correr
> TODOS los bancos después (C5). No fiarse solo de `test_conversaciones` y el banco de
> guiones: P2 pasaba esos dos y rompía `test_frio`.

## 2. Fuga de datos (D4) — un fleco

- [ ] **`es_prueba` no cubre el prefijo `aud*`** (sesiones de `test_ciclo`/`test_llm`,
  medido en la línea base). Decidir: añadirlo a `PREFIJOS_PRUEBA` o renombrar esas
  sesiones de test. Hoy esas dos pruebas aún escriben 2 reservas.

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
- [ ] **Commit**: nada commiteado (por tu instrucción). Siguen tus 7 archivos sueltos
  mezclados con lo mío en el árbol de trabajo. Decidir cómo separar cuando toque.
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
Banco de guiones: 68 % → **74 %** (403/541) · 0 fugas · C5 intacto (`test_frio`
reconfirmado verde tras revertir P2).
