# VendIQ — Diseño del sistema RAG

**Empresa:** Desguaces Madrid Norte (desguace, Alcobendas · Madrid)
**Qué es:** asistente de ventas que responde a clientes por WhatsApp/email fundándose en los datos reales de la empresa, no en lo que "cree saber".
**Estado:** diseño + prototipo sin probar. NO desplegado. (Ver "Estado y próximos pasos".)

---

## 1. El problema que resuelve

Un asistente genérico se inventa precios, plazos y disponibilidad. VendIQ no: **antes de contestar, busca en los documentos de Desguaces Madrid Norte y responde a partir de lo que encuentra.** Si el dato no está, lo pregunta o lo escala a Álvaro — nunca lo inventa.

> RAG = "mira la carpeta antes de hablar". (RAG = Retrieval Augmented Generation: recuperar información real y luego generar la respuesta sobre ella.)

---

## 2. Fuente de datos

- **Fuente real:** `desguacesmadridnorte.com` — tienda **PrestaShop** (desarrollada por su desarrollador web) con **+50.000 piezas**, cada una con ID, referencia OEM y vehículo (marca/modelo/motor).
- **Forma correcta de alimentarlo:** un **export/feed de productos** de la tienda (CSV o API), **refrescable** — el stock cambia a diario. NO copiar la web página a página ni scrapear.
- **Regla de precio (es la operativa real):** en la web, muchas piezas ponen **"Consultar por WhatsApp"** en vez de precio. VendIQ hace lo mismo: da precio **solo cuando está publicado**; si no, "te confirmo" o escala.
- **Datos de prueba:** `VendIQ_inventario_PRUEBA_sintetico_100.csv` — 100 productos **sintéticos** (regla del proyecto: datos sintéticos, no reales), calcados a la estructura de la web (33 con precio, 67 "Consultar por WhatsApp").

---

## 3. Base de conocimiento (la "carpeta" de VendIQ)

| Documento | Contenido | ¿Existe? |
|---|---|---|
| **A. Inventario / catálogo** | pieza, vehículos compatibles, estado (comprobada, km), precio | En la web (feed pendiente) |
| **B. Compatibilidades** | qué pieza encaja con qué coche | En la web |
| **C. Precios y descuentos** | política: hasta cuánto se mueve un precio y cuándo | Crear |
| **D. Envío y recogida** | plazos (día siguiente península), recogida vs envío | Página web |
| **E. Garantía** | 1 año en todos los productos | Página web |
| **F. FAQs generales** | pago, devoluciones, original vs 2ª mano | Página web |

---

## 4. Preguntas reales de los clientes → documento que las responde

| Pregunta del cliente | Documento |
|---|---|
| ¿Tienes esta pieza? + matrícula | Inventario + Compatibilidades (matrícula → identifica modelo/motor → cruza pieza) |
| ¿Me puedes rebajar algo? | Política de precios (el "sí" final lo decide Álvaro) |
| ¿Cuánto tarda en llegar? | Condiciones de envío y plazos |
| ¿Me puedo pasar ya a por ella? | Estado de stock + horario tienda |
| ¿Está la pieza comprobada? | Ficha de la pieza (en Inventario) |
| ¿Cuánta garantía tiene? | Política de garantía (1 año) |

---

## 5. Arquitectura

### Fase 1 · Preparación (una vez)
1. **Reunir** los documentos A–F en texto.
2. **Trocear** cada documento en pedazos pequeños (un trozo = una pieza del inventario, una cláusula de garantía…).
3. **Indexar** los trozos en un buscador (vector index / embeddings) para encontrarlos por significado, no solo por palabra exacta.

### Fase 2 · En caliente (cada mensaje de cliente)
4. **Extraer** los datos del mensaje: pieza, vehículo, matrícula… (técnica prompt: extracción con etiquetas). Si falta un dato clave, VendIQ lo pide.
5. **Buscar** en el índice los trozos relevantes (la pieza, su precio, la garantía…).
6. **Responder**: se pasan a Claude los trozos encontrados + el rol (system prompt) → contesta con la voz de Álvaro, fundado en los datos.
7. **Barrera**: si el dato no está o es una decisión de negocio → no inventa: pregunta o escala.

> **Nota de escala:** para +50.000 piezas hace falta RAG (no caben en un prompt). Para un set pequeño (p. ej. 100 piezas de prueba) **no hace falta RAG**: el CSV entero cabe en el prompt, así que se puede probar en un Proyecto de claude.ai pegando rol + CSV. Gratis.

---

## 6. Guardarraíles (lo que VendIQ NUNCA hace solo)

- **No inventa precio, stock ni estado.** Si no está en el inventario → pregunta o escala. (La web ya funciona así: "Consultar por WhatsApp".)
- **No concede rebajas por su cuenta.** Informa de la política; el "sí, te lo bajo" final es decisión de Álvaro (su margen).
- **No promete plazos que no puede confirmar.** Da el plazo estándar; si depende del proveedor, dice "te confirmo".

---

## 7. El rol (system prompt — el "cerebro", validado)

```
Eres el asistente de Desguaces Madrid Norte, profesional de venta de recambios
de coche con 5 años de experiencia.

CON QUIÉN HABLAS: casi siempre profesionales o entendidos del motor. Saben lo
que quieren y suelen haber mirado precios en internet. Trátalos de igual a igual.

CÓMO HABLAS: cercano, comercial, de profesional a profesional. Vas al grano y no
explicas lo obvio. No defiendes tu precio ni presionas; eres fiel a tu producto
porque sabes que es bueno.

TUS REGLAS (siempre): cuando el cliente te dé los datos del vehículo, dile que
vas a buscar justo el recambio que necesita al mejor precio. Nunca des un precio
ni confirmes disponibilidad hasta verificarlo tú. Si no lo tienes en el momento
(lo habitual), dile que puedes conseguirlo en 24-48 h.
```

---

## 8. Instrucciones para WhatsApp (pendiente de añadir al rol)

Añadir estas reglas para que funcione en un chat real:

1. **Memoria de conversación:** recuerda lo que el cliente ya te dijo; nunca vuelvas a pedir un dato que ya te dio.
2. **Formato WhatsApp:** 1-3 líneas cortas, sin asunto, sin firma.
3. **Un dato por mensaje:** si faltan varios, pide primero la matrícula.
4. **Interpretar mensajes sucios:** erratas, sin puntuar, notas de voz. Si es ambiguo, confirma en vez de asumir.
5. **Escalado a Álvaro:** cuando pidan rebaja/negocien precio, haya queja, pregunten algo fuera de los documentos, o el cliente se ponga tenso.
6. **Registro según cliente:** conocido → tono de confianza; nuevo → algo más neutro.
7. **Orientación a cierre:** cada respuesta mueve la venta (consigue el dato → da info → propón siguiente paso).

**Decisiones pendientes de Álvaro:** (a) qué más escalar; (b) ¿el bot se identifica como bot? (recomendado: transparente); (c) ¿usa emojis?

---

## 9. Alcance y coste

- **Diseñar (este documento):** gratis.
- **Probar el prototipo** (rol + CSV de 100 en claude.ai): gratis.
- **Construir el RAG real** (feed de +50.000 piezas + embeddings + integración WhatsApp): necesita API + código Python + integración = coste por uso. Aparcado por decisión "gratis total".

---

## 10. Estado y próximos pasos

**Hecho:** diseño completo, rol validado, guardarraíles, CSV de prueba (100 piezas sintéticas).

**NO hecho (por qué aún no está "listo"):**
- No se ha probado ni una simulación de cliente todavía.
- Las instrucciones de WhatsApp no están montadas en el rol (faltan 3 decisiones de Álvaro).
- El feed de productos real no está conectado (100 sintéticas ≠ 50.000 reales).
- Sin desplegar en WhatsApp (un Proyecto de claude.ai = copiar-pegar manual, "v0").

**Próximo paso concreto:** montar el Proyecto de prueba en claude.ai (rol + CSV) y hacer de cliente hasta validar que encuentra la pieza, respeta el "consultar precio" y pide la matrícula. "Listo" se gana pasando pruebas, no se declara.

---

*Borrador para iterar.*
