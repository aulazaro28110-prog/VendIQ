# Decisiones de negocio — «Conversaciones tipo»

Aquí van las decisiones que el prompt reserva para Álvaro. Mientras no se decidan,
los guiones afectados llevan la marca `decision_pendiente` y **no cuentan para C4**;
el banco enseña lo que hace el bot HOY.

---

## D5 · Las tres preguntas de negocio (DECIDIDAS el 2026-09-30)

> Álvaro decidió P1/P2/P3. Ya no hay turnos `decision_pendiente` en los guiones.
> Falta **implementar en el bot** cada una (va en el lote de arreglos tras la Fase 3).

### P1 · Matrícula sin coche (guiones G44, G14 t7, y en general)
**Situación:** el cliente da una matrícula sin nombrar el coche
(«necesito un alternador, matrícula 1234 BCD»). No hay consulta a la DGT (es
sintético): el sistema no traduce matrícula → vehículo.

**Qué hace hoy:** acusa la matrícula («Anotada, 1234 BCD. Dime qué pieza buscas»)
y, en cuanto el cliente dice el coche («es un audi a4»), **da el precio del A4 con
esa matrícula apuntada** — una matrícula que nunca pudo comprobar contra el coche.

**DECIDIDO (2026-09-30):** si falta el **modelo**, el bot pregunta **«¿Qué modelo
es?»** justo después (NO «¿qué pieza?», que ya la tiene) y **no retiene el precio**:
en cuanto le dan el modelo, da el precio normal.
→ En los guiones: G44·t1 = `pide datos` + `nunca: no_olvida_pieza`.
→ **Bot pendiente de implementar:** hoy contesta «Dime qué pieza buscas» (olvida la
pieza); hay que hacer que pida el MODELO cuando la pieza es conocida y falta el coche.

### P2 · Un caso escalado, ¿bloquea una venta nueva? (guion G28)
**Situación:** el cliente tiene una queja ya escalada a Álvaro y, en la misma
conversación, pide otra pieza para otro cliente/coche.

**Qué hace hoy:** *(a medir en el banco de la Fase 3; el diseño escala la queja y
sigue en «sigue escalado», que acusa corto y no reabre — habría que ver si la
compra nueva llega a darse.)*

**DECIDIDO (2026-09-30):** con una queja escalada viva, **todo queda en manos de
Álvaro**. El bot **no atiende la compra nueva** (no da precio ni cierra): escala.
→ En los guiones: G28·t4 `confirma`→`escala`; t5/t6 `precio`/`cierra`→`escala|cualquiera`.
→ **Bot: intentado y REVERTIDO (rompía C5).** El clasificador de quejas se dispara
con «bueno va, otra cosa» (un descarte, no una queja), así que bloquear ventas con
una «queja viva» tumbaba 6 conversaciones de `test_frio`. P2 necesita **primero**
endurecer ese clasificador. Pendiente para la revisión conjunta.

### P3 · La matrícula es de un coche, no de la conversación (G14, G24, G33, G40)
**Situación:** el cliente habla de un segundo coche en la misma conversación
(«y un faro para un seat león»). `conv.matricula` sigue siendo la del primero.

**Qué hace hoy (medido D5a):** tras dar «4521 KBD» para el Audi A4, al pedir un
faro para un Seat León el bot mantiene `matricula='4521 KBD'`. En el caso medido
preguntó cuál faro (2 encajan) y no llegó a publicar precio, pero **si hubiera
resuelto a una sola ficha, habría publicado el precio del Seat con la matrícula del
Audi**.

**DECIDIDO (2026-09-30):** el bot **no reutiliza la matrícula**. Una matrícula por
coche: al cambiar de coche pide la matrícula nueva. Y **termina la primera consulta
antes de empezar otra** (no lleva dos coches a la vez).
→ En los guiones: G14·t7, G24·t6, G33·t4, G40·t4 = `confirma` + `nunca: sin_precio`
(confirma que la hay, pero no da precio del 2.º coche sin su matrícula).
→ **Bot pendiente de implementar:** hoy `conv.matricula` se queda puesta y podría
publicar el precio del 2.º coche con la matrícula del 1.º.

---

## Expectativas dudosas del Anexo A (Fase 2)

Las marcadas con `(?)` en el Anexo A. **DECIDIDAS por Álvaro el 2026-09-30.**

| Guion · turno | Mensaje del cliente | Antes | Decidido |
|---|---|---|---|
| G02 · 2 | «la referencia de la vieja es {A.oem}, es la misma?» | `cualquiera` | `cualquiera` + **`no_asegura`** (responde sin jurar que encaja) |
| G02 · 4 | «cuantos km tenia» | `sigue\|cualquiera` + `no_inventa` | **sin cambios** (el `no_inventa` basta) |
| G07 · 6 | «y el transporte me lo regalas?» | `escala\|cualquiera` | **`escala`** (regalar portes = rebajar → regateo) |
| G29 · 9 | «vale, hacemos el cambio» | `escala\|cierra` | **`escala`** (un cambio es posventa → persona, coherente con P2) |
| G44 · 1 | «necesito {A.pieza}, matricula {M}» | `pide datos\|confirma` | **`pide datos`** + `no_olvida_pieza` (resuelto por P1) |

> El banco de la Fase 3 mide qué hace el bot contra estas expectativas.

## Guiones con `decision_pendiente`

**Ninguno.** Con P1/P2/P3 decididas, los 6 turnos que estaban pendientes (G14·t7,
G24·t6, G28·t4, G33·t4, G40·t4, G44·t1) ya tienen expectativa fija y cuentan para C4.
La Fase 3 medirá cuáles cumple el bot hoy y cuáles hay que arreglar.

---

## Cómo quedaron (cierre, Fase 6 · 02-10-2026)

| Decisión / expectativa | Estado | Dónde |
|---|---|---|
| **P1** · matrícula sin coche → pide el modelo, no retiene | **Implementada** | `07_redactor`/`chatear` (Fase 3bis) |
| **P3** · una matrícula por coche; no reutiliza la del 1.º | **Implementada** | `chatear()` (Fase 3bis) |
| **P2** · queja escalada bloquea venta nueva | **Decidida, NO implementada** | revertida: rompía C5 (clasificador de quejas con falso positivo). En `GUIONES_pendientes.md` §1 |
| **A** · «¿cuándo llega?» → `recuerda` vale como `política` | **Implementada** | `12_guiones.evaluar_turno` (`_PLAZO`) |
| **B** · `no_hay` t1: pedir matrícula cuenta como «no la tengo» | **Implementada** (por guion) | etiqueta en el turno; afinar `clasificar()` rompía C5 y se descartó |
| Expectativas `(?)` del Anexo A (G02, G07, G29, G44) | **Fijadas** tal como decidiste | `datos/guiones_tipo.json` |

**Resumen:** de las tres preguntas de negocio, **P1 y P3 están en el bot**; **P2 queda
pendiente** porque su arreglo honesto exige primero endurecer el clasificador de quejas
(si no, tumba `test_frio` y rompe C5). No se ha forzado para que pasara el banco: el
turno de G28 que depende de P2 sigue contando como fallo a la espera de ese arreglo.
