# VendIQ — Diseño del sistema RAG

**Empresa:** Desguaces Madrid Norte (desguace, Alcobendas · Madrid)
**Qué es:** asistente de ventas que responde a clientes por WhatsApp/email fundándose en los datos reales de la empresa, no en lo que "cree saber".
**Estado:** construido y medido en local. NO desplegado en producción. (Ver "Estado" al final.)
**Aviso:** este documento es el DISEÑO, escrito antes de construir. Las secciones 1-8 describen la arquitectura que efectivamente se levantó; el apartado final dice qué cambió al construirla.

---

## 1. El problema que resuelve

Un asistente genérico se inventa precios, plazos y disponibilidad. VendIQ no: **antes de contestar, busca en los documentos de Desguaces Madrid Norte y responde a partir de lo que encuentra.** Si el dato no está, lo pregunta o lo escala a Álvaro — nunca lo inventa.

> RAG = "mira la carpeta antes de hablar". (RAG = Retrieval Augmented Generation: recuperar información real y luego generar la respuesta sobre ella.)

---

## 2. Fuente de datos

- **Fuente real:** el catálogo de la tienda del cliente — **+50.000 piezas**, cada una con ID, referencia OEM y vehículo (marca/modelo/motor).
- **Forma correcta de alimentarlo:** un **export/feed de productos** de la tienda (CSV o API), **refrescable** — el stock cambia a diario. NO copiar la web página a página ni scrapear.
- **Regla de precio (es la operativa real):** en la web, muchas piezas ponen **"Consultar por WhatsApp"** en vez de precio. VendIQ hace lo mismo: da precio **solo cuando está publicado**; si no, "te confirmo" o escala.
- **Datos de prueba:** ningún dato real. Lo que se indexa es `datos/inventario_sintetico.csv`, un catálogo **sintético** generado por `scripts/generar_catalogo.py` — 5.000 piezas calcadas a la estructura de la tienda, con la misma proporción de piezas sin precio publicado. (El diseño original proveía 100; se subió a 5.000 para medir si la escala rompía la búsqueda, y no la rompió.)

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
- **No dice "no la tengo" sin matrícula.** Es el guardarraíl que más ventas salva y el más fácil de romper sin darse cuenta. Sin identificar el vehículo la búsqueda solo ha comparado palabras: la misma pieza puede estar en el almacén con otro nombre, otro motor u otro año. Primero se pide la matrícula; con ella sí se puede afirmar que no la hay. **Excepción:** cuando escala a una persona no se le exige pedirla — una queja también cae en "no disponible", pero ahí el cliente no está preguntando si la tenemos. Implementado en `07_redactor.py::_sin_pieza()` y protegido por un invariante de `tests/test_conversaciones.py`.

---

## 7. El rol (system prompt — el "cerebro")

> **Revisado el 16-08-2026.** La versión anterior decía *"nunca des un precio ni
> confirmes disponibilidad"*. Era cierta cuando el catálogo no publicaba precios;
> hoy las 1.000 piezas los tienen y el bot sí los pasa — pero solo de lo que hay.
> Un rol que prohíbe dar precios y un sistema que los da son incompatibles, así que
> el rol se ajusta a la regla de negocio nueva.

```
Eres el asistente de Desguaces Madrid Norte, profesional de venta de recambios
de coche con 5 años de experiencia. Te presentas como asistente, no finges
ser una persona.

CON QUIÉN HABLAS: casi siempre profesionales o entendidos del motor. Saben lo
que quieren y suelen haber mirado precios en internet. Trátalos de igual a igual.

CÓMO HABLAS: cercano, comercial, de profesional a profesional. Vas al grano y no
explicas lo obvio. No defiendes tu precio ni presionas; eres fiel a tu producto
porque sabes que es bueno. Mensajes de 1 a 3 líneas, sin firma y sin emojis.

TUS REGLAS SOBRE EL PRECIO (las más importantes):
  - Das el precio SOLO de la pieza exacta que el cliente ha pedido, cuando está
    disponible y tiene precio. Ese precio lo dices tal cual, sin redondear.
  - Si la pieza está pero no tiene precio asignado: "la tengo, el precio te lo
    confirmo enseguida". Nunca te lo inventas ni lo estimas.
  - Si el cliente no ha dicho con claridad qué pieza quiere, NO das precio:
    confirmas primero de cuál habla.
  - Jamás das el precio de una pieza parecida a la pedida. Si pide la puerta
    trasera y solo tienes la delantera, se lo dices; no le pasas el precio de
    la otra.

TUS REGLAS SOBRE LA PIEZA:
  - Si no la tienes, lo dices claro y pides la matrícula o el bastidor para
    buscarla. Puedes conseguir lo que no está en 24-48 h.
  - La compatibilidad final la confirma una persona. Tú acercas la pieza; no
    aseguras que encaja.
  - Si faltan datos, pides UNO por mensaje, y el primero siempre la matrícula.

ESCALAS a una persona cuando: piden rebaja o negocian precio, hay una queja,
preguntan algo que no está en tus documentos, o el cliente se pone tenso.
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

Lo que este apartado daba por caro resultó salir gratis, y conviene dejar constancia de por qué.

- **Diseñar (este documento):** gratis.
- **Construir el RAG:** gratis también. El diseño daba por hecho que haría falta una API de
  pago, y no la hizo falta: los embeddings los calcula un modelo local
  (`paraphrase-multilingual-MiniLM`) y la búsqueda corre en el ordenador. El índice de 5.010
  fichas ocupa 7,7 MB y una consulta tarda entre 50 y 60 ms.
- **Redactar con LLM:** opcional y en capa gratuita (Groq). Sin `GROQ_API_KEY` el sistema no se
  cae: redacta `07_redactor.py` y todo lo demás es idéntico.
- **Lo que sí sigue costando:** la integración viva con WhatsApp y Wallapop, que no está hecha.

---

## 10. Estado

Este apartado se reescribió después de construir el sistema. La versión anterior decía
"prototipo sin probar" y había dejado de ser cierta.

**Hecho y medido.** Diez bancos de pruebas en verde, que el CI vuelve a correr en cada push
reconstruyendo el índice desde el catálogo:

| Lo que el diseño daba por pendiente | Cómo quedó |
|---|---|
| "No se ha probado ni una simulación de cliente" | 218 conversaciones + 50 largas de 20+ mensajes (1.041 turnos) |
| "100 sintéticas ≠ 50.000 reales" | 5.010 fichas indexadas; la escala dejó de ser el problema |
| "Las instrucciones de WhatsApp no están montadas" | `docs/Prompt_Agente_Conversacional.md`, auditado sección a sección por `tests/test_prompt.py` |
| "Construir el RAG necesita API de pago" | Embeddings locales, coste 0 |

**Lo que sigue sin estar hecho, y es lo único:** la integración viva. WhatsApp, Gmail y
Wallapop pasan por `11_canales.py` sobre la misma búsqueda y el mismo guardarraíl de precio,
y están medidos (50 correos y 20 conversaciones de Wallapop en `tests/test_canales.py`), pero
los mensajes entran de un corpus: no hay webhook ni API real detrás. El feed del catálogo real
de la tienda tampoco está conectado; lo que se indexa es un catálogo sintético de 5.000 piezas.

**Lo que cambió respecto al diseño.** Dos cosas que este documento no anticipó: que el
guardarraíl de precio tendría que auditar también **la redacción del LLM** frase a frase (no
basta con controlar qué dato se recupera, hay que comprobar qué escribe el modelo con él), y
que haría falta un ciclo de aprendizaje para lo que el bot no supo contestar.
