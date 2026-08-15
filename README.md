# VendIQ RAG — ingesta, chunking y búsqueda (prototipo local, coste 0)

Prototipo de la capa de datos de **VendIQ**, un asistente de ventas para un desguace
(Desguaces Madrid Norte) que responde a clientes **fundándose en los datos reales de la empresa**
y no en lo que "cree saber". Este repo cubre la parte de RAG que se puede construir **gratis y en
local**, sin API de pago.

> RAG = *Retrieval Augmented Generation* = "mira la carpeta antes de hablar": primero recupera
> información real de la empresa, y luego genera la respuesta sobre ella.

## Qué hace, en 3 pasos

1. **`01_ingesta_chunking.py`** — reúne los documentos (inventario + políticas) y los **trocea**
   en *chunks* pequeños y buscables. Salida: `salida/chunks.jsonl` (105 chunks: 100 piezas + 5 políticas).
2. **`02_embeddings.py`** — convierte cada chunk en un **embedding** (vector de significado) con un
   modelo local gratuito (`sentence-transformers`) y los guarda. Salida: `salida/embeddings.npy` + `salida/embeddings_meta.json`.
3. **`03_buscar.py`** — dada la pregunta de un cliente, **recupera** los trozos relevantes
   (la parte "retrieval" de RAG).

Y aparte del RAG, **`04_ofertas.py`** — el "haz una oferta" de eBay aplicado al desguace:
decide qué ofertas se aceptan solas y cuáles pasan por Álvaro.

## Cómo busca

La búsqueda **no** es solo por significado. Buscar solo con embeddings no funciona en un catálogo
de recambios: las 100 fichas están redactadas con la misma plantilla, sus vectores se parecen
demasiado, y las palabras que de verdad distinguen una pieza (marca, modelo, tipo) se diluyen.
Medido: solo acertaba el **20 %** de las veces, y a "¿tenéis un alternador para un BMW 320d?"
respondía con un cinturón de seguridad.

Se combinan tres cosas:

- **Cobertura léxica** — qué proporción de las palabras importantes del cliente aparecen
  literalmente en la ficha, pesando más las palabras raras ("alternador" distingue; "delantero", poco).
- **Significado** — el embedding de siempre. Es lo que permite que "cuánto tarda en llegar"
  encuentre la política de envíos sin compartir ni una palabra.
- **Filtro por pieza y marca** — si el cliente pide un *catalizador* de *Audi*, no se le puede
  ofrecer una *bomba de agua* de Audi por muy parecidas que sean las dos fichas. El vocabulario
  de marcas y tipos de pieza se aprende del propio catálogo, no hay listas escritas a mano.

## La regla de precios

VendIQ **sí da precios**, pero solo de piezas que la empresa tiene de verdad. Nunca da el
precio de algo que no está disponible, y nunca da el precio de una pieza *parecida* a la
que han pedido.

Hacen falta **cuatro condiciones**, todas:

1. **Que sea la mejor coincidencia.** Las demás son, por definición, otra pieza.
2. **Que esté disponible** (`En stock` o `Bajo pedido 24-48h`).
3. **Que tenga precio** — publicado en el catálogo o puesto por Álvaro desde el panel.
4. **Que la confianza llegue a 0,65**, más alto que el 0,50 que basta para enseñar una ficha.

Por qué la puerta del precio es más estrecha que la de mostrar una candidata: enseñar una
pieza parecida es una molestia ("no, yo quería la de otro modelo"). **Decir un precio
equivocado es un compromiso comercial** — el cliente se lo cree, viene a por ella, y
alguien tiene que darle la mala noticia. Cuesta dinero y confianza.

La condición 1 salió de un fallo real que detectaron las pruebas: un cliente pedía la
puerta **trasera** izquierda de un Skoda (sin precio publicado) y el sistema le daba el
precio de la puerta **delantera** izquierda del mismo coche. Ambas son "puerta" y ambas
superaban la confianza mínima. Si la mejor coincidencia no tiene precio, la respuesta
correcta es "te lo confirmo", nunca el precio de la de al lado.

Cada resultado lleva **pegada** su decisión de precio y el motivo, así que quien consuma
la búsqueda —el panel hoy, el LLM mañana— no puede olvidarse de mirarla.
Verificado en `tests/test_precios.py`.

## El guardarraíl

Cada resultado tiene una puntuación **absoluta** de 0 a 1. Si nada llega al mínimo,
`buscar()` devuelve una **lista vacía**. Ese vacío es la señal de *"no lo tengo en la carpeta:
pregunta o escala a Álvaro"* — es decir, la regla de "nunca inventes" del documento de diseño,
ya ejecutable en código y no solo escrita en prosa.

Los umbrales están calibrados con medidas, no a ojo (ver `tests/test_busqueda.py --calibrar`).

## Ofertas (`04_ofertas.py`)

Un cliente ofrece 780 € por una pieza publicada a 865 €. El módulo decide una de cuatro cosas:
**aceptar**, **contraofertar**, **rechazar** o **dejarlo a Álvaro**.

El margen que se acepta solo depende de **lo antigua que sea la pieza**: cuanto más tiempo lleva
en la estantería, más interesa darle salida. Como el inventario no tiene fecha de alta
(comprobado: las fichas de la web no publican ninguna), la antigüedad se deduce del **número de
stock**, que se asigna de forma correlativa. Se usa su **percentil** dentro del stock, no el
número en bruto: así la regla sigue funcionando aunque algún día se renumere el almacén.

| Tramo | Parte del stock | Descuento que se acepta solo |
|---|---|---|
| Muy antigua | 25 % más antiguo | 20 % |
| Antigua | 25–50 % | 12 % |
| Reciente | 50–75 % | 7 % |
| Nueva | 25 % más reciente | 0 % (siempre a mano) |

**Estos porcentajes son un punto de partida, no una recomendación.** Cámbialos en `TRAMOS`,
al principio de `04_ofertas.py`: solo tú sabes a cuánto compraste cada pieza.

Lo que nunca hace solo: aceptar sin precio publicado, aceptar por debajo de 30 €, o negociar
dos veces la misma pieza con el mismo cliente (si no, basta con ir bajando la oferta hasta dar
con el umbral). Toda oferta queda registrada en `salida/ofertas.json`, la decida la regla o tú.

```bash
python 04_ofertas.py reglas                       # ver la tabla
python 04_ofertas.py oferta 69183 780 --cliente "Taller Ruiz"
python 04_ofertas.py pendientes                   # lo que espera tu decisión
python 04_ofertas.py aceptar 4 --motivo "lleva tiempo parada"
python 04_ofertas.py historial
```

## Centro de control (`06_panel.py`)

Panel web en local. Es la cara visible del proyecto: enseña cómo está funcionando la
herramienta en lenguaje de negocio, y **opera sobre ella de verdad**.

```bash
python 05_panel_datos.py     # mide una semana de mensajes con el sistema real
python 06_panel.py           # levanta el panel y abre el navegador
```

No añade dependencias: solo `http.server` de la librería estándar. El modelo se carga
una vez al arrancar y se queda caliente, por eso las consultas tardan ~50 ms.

**Por qué un servidor y no un HTML suelto:** el panel no enseña una foto de datos.
Al escribir una consulta se ejecuta la búsqueda real contra el índice; al aceptar una
oferta se escribe en `salida/ofertas.json`. Un fichero estático no puede hacer ninguna
de las dos cosas, porque el buscador necesita el modelo de embeddings en memoria.

Está organizado alrededor de una idea: **el bot resuelve lo obvio, tú decides lo que vale
dinero.** Cada pestaña es una de las cosas que el bot no puede hacer solo.

| Pestaña | Qué resuelve |
|---|---|
| **Cómo va el día** | Diagrama de dónde acaba cada mensaje y las cifras del día |
| **Habla como un cliente** | Escribes como un cliente y ves la búsqueda real: fichas, puntuación, si se puede dar precio y las descartadas |
| **Precios sin poner** | Las piezas sin precio, ordenadas por cuántas veces te las han pedido. Pones el precio y **el bot ya puede venderla** |
| **Mesa de negociación** | Ofertas: lo que la regla cierra sola y lo que espera tu decisión |
| **Lo que te piden y no tienes** | Demanda no cubierta — información de compra |
| **La letra pequeña** | Acierto verificado, parámetros del motor y registro completo con su porqué |

La pestaña de precios cierra un círculo que merece la pena entender: tu trabajo manual no
se queda en resolver un caso, **entra en el sistema**. En cuanto guardas un precio, la
siguiente consulta ya lo usa. El humano no es el plan B del bot: es quien lo alimenta.

Los datos de actividad salen de `05_panel_datos.py`, que simula los **mensajes** (es un
prototipo, no hay clientes reales) pero mide de verdad las decisiones, las puntuaciones
y los tiempos. Si mañana la búsqueda empeora, los números del panel empeoran solos.

## Datos

Se usa **`datos/inventario_sintetico.csv`** (100 piezas *sintéticas*, misma estructura que la web
real) y **`datos/politicas.md`** (garantía, envío, precios, pago, identificación de pieza).
Regla del proyecto: **datos sintéticos, no reales** (privacidad).

## Cómo ejecutarlo

```bash
# 1) Instalar dependencias (una vez). La descarga es grande la primera vez (~150 MB).
pip install -r requirements.txt

# 2) Los 3 pasos
python 01_ingesta_chunking.py
python 02_embeddings.py
python 03_buscar.py "¿tenéis un alternador para un BMW 320d?"

# 3) Comprobar que la búsqueda sigue funcionando bien
python tests/test_busqueda.py
```

Si te saltas un paso, el siguiente te dice cuál falta en vez de reventar con un error críptico.

## Calidad medida

`tests/test_busqueda.py` genera 80 preguntas desde el propio catálogo (así la respuesta correcta
se conoce sin escribirla a mano) y 40 piezas que **no** existen, para comprobar que el sistema
se calla en vez de ofrecer otra cosa.

| Tipo de pregunta | Acierto@1 | Antes |
|---|---|---|
| Natural ("¿tenéis un alternador para un Audi A4 2.0 TDI?") | 100 % | 24 % |
| Datos incompletos ("busco cremallera de Audi A3") | 100 % | 7 % |
| Mensaje sucio de WhatsApp (sin tildes ni signos) | 100 % | 13 % |
| Por referencia OEM | 100 % | 0 % |
| Políticas (garantía, plazos, pago) | 70 % | 70 % |
| **Total** | **96 %** | **20 %** |

Guardarraíl: **39 de 40** piezas inexistentes no devuelven ninguna ficha (98 %).

## Límites conocidos

- **Políticas: 70 %.** Preguntas como "¿el precio lleva IVA?" devuelven una pieza antes que la
  política de precios, porque todas las fichas contienen literalmente "Precio:" y "+ IVA".
- **Piezas parecidas.** Pedir una "bomba de dirección" cuando solo hay una "bomba de agua" del
  mismo coche sí puede colarse: el filtro distingue el tipo de pieza, no todas sus variantes.
- **Preguntas incompletas en un catálogo grande.** Es el límite serio. Medido sobre un catálogo
  sintético de 5.000 piezas: si el cliente da pieza + marca + modelo pero no el motor ni el año,
  hay **5,8 fichas válidas de media** y acertar *la* correcta baja al 28 %. No es un fallo de la
  búsqueda: la pregunta no tiene una sola respuesta. Lo que falta es que el sistema lo detecte y
  **pida la matrícula** en vez de elegir una. Con los datos completos, el acierto se mantiene en
  el 95 % con 5.000 piezas.
- **Escala: no es un problema.** Medido, no estimado: con 5.000 piezas una consulta tarda 40 ms
  (30 de ellos en vectorizar la pregunta, que es coste fijo) y el índice ocupa 7 MB. Proyectado a
  50.000 serían ~100 ms y 73 MB. La búsqueda lineal aguanta de sobra; no hace falta un índice
  vectorial especializado.

## Estado

Prototipo de la **capa de datos** (ingesta + búsqueda + guardarraíl de recuperación).
NO incluye todavía el LLM que redacta la respuesta final ni la integración con WhatsApp; eso
queda para cuando se decida usar API de pago.
