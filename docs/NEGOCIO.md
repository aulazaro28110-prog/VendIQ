# VendIQ — qué resuelve y qué datos toca

Documento **de negocio**. Sin código. Para leerlo antes de una demo, o para
entender en cinco minutos qué hace el sistema y qué hace con los datos de la
gente.

La parte técnica está en [`README.md`](../README.md). El detalle de protección de
datos, en [`GDPR.md`](GDPR.md).

---

## El problema

Un desguace vende recambios usados por WhatsApp. Las preguntas llegan a todas
horas y casi todas son la misma: *¿tenéis esta pieza para este coche y cuánto
vale?*

Contestarlas tiene tres costes que no se ven en la factura:

- **El tiempo.** Cada mensaje obliga a parar lo que se esté haciendo, buscar en el
  catálogo y volver. Con 150-200 conversaciones al día, es una jornada entera.
- **Las que se pierden.** Lo que se contesta cuatro horas más tarde ya se ha
  comprado en otro sitio.
- **Los errores caros.** Una pieza que se manda sin comprobar que encaja vuelve, y
  la devolución cuesta más que el margen de la venta.

## Lo que hace VendIQ

Contesta esas preguntas **con los datos reales de la empresa** y pasa a una
persona lo que no le corresponde decidir.

Sobre 7 días de tráfico simulado y pasado por el sistema real:

| | |
|---|---|
| Conversaciones | 930 · 2.558 mensajes |
| **Resueltas sin una persona** | **94 %** (878) |
| Van a Álvaro | 52 |
| Tiempo de respuesta | 74 ms de mediana |
| **Precios dichos sin autorización** | **0** |

Ese último número es el importante y se explica abajo.

## Las tres reglas del negocio, escritas en el código

No son buenas intenciones: son condiciones que el sistema **no puede** saltarse,
y hay pruebas automáticas que fallan si alguien las rompe.

### 1. Sin identificar el coche, no se ofrece nada

El bot no da una pieza ni su precio hasta tener **matrícula, VIN, referencia OEM o
número de stock**. No es prudencia: es que describir el coche no identifica la
pieza. Medido sobre el catálogo de 5.000 piezas:

| lo que escribe el cliente | fichas que encajan |
|---|---|
| marca + modelo + pieza | **97 %** comparten descripción con otra |
| marca + modelo + **motor** + pieza | **81 %** siguen compartiéndola |
| + año | 0 % — única |
| referencia OEM o nº de stock | 0 % — única |

Hay hasta quince alternadores del mismo coche según motor y año. Ofrecer uno es
afirmar que encaja, y eso **no se sabe**. Lo que dice el bot en su lugar sale del
catálogo, así que es verdad y además vende:

> *De alternador para un Audi A4 tengo 15 referencias distintas, según el motor y
> el año. Pásame la matrícula y te digo cuál es el tuyo y lo que vale.*

### 2. Sin matrícula nunca dice «no la tengo»

Decir que no sin haber identificado la pieza es adivinar, y adivinar en contra
pierde una venta que quizá estaba en el almacén con otro nombre.

### 3. La pieza no sale sin el pago confirmado

Un justificante, una captura o una promesa no son un pago. El bot **no juzga** si
alguien intenta colártela: no se mueve de la condición y pasa la conversación a
una persona. La consecuencia de equivocarse aquí no es una respuesta fea, es una
pieza que sale del almacén sin cobrar.

## Por qué el precio no se le puede escapar

El sistema puede escribir los mensajes con un modelo de lenguaje (Groq), que suena
mejor. Los modelos de lenguaje se inventan cosas. Aquí no puede inventarse un
precio, y no porque se le pida que no lo haga:

**Si la búsqueda no ha autorizado el importe, ese importe no entra en lo que se le
manda al modelo.** No puede decirlo porque no lo tiene.

Y por si acaso, hay una segunda barrera: se leen todos los importes del mensaje
que va a salir y se contrastan con los autorizados. Si aparece uno que no lo está,
se tira lo que escribió el modelo y sale el borrador que sí es demostrable. El
centro de control lo dice en rojo en vez de disimularlo.

Lo mismo se aplica al trato (nunca de usted), a la longitud (tres líneas como
mucho) y a las tres reglas de arriba.

**Si Groq se cae, el desguace no se queda mudo:** contesta el redactor propio y la
conversación sigue igual. Está probado con 401, 429, 404, sin red, timeout y
respuesta vacía.

## Qué NO hace, y es a propósito

- **No detecta fraude.** No juzga si un justificante es falso: mantiene la
  condición y avisa a una persona.
- **No decide descuentos.** Cualquier rebaja la decide Álvaro.
- **No gestiona reclamaciones.** Una queja va a una persona desde el primer
  mensaje.
- **No se inventa respuestas a lo que no sabe.** Lo guarda para que lo conteste
  una persona, y solo entonces entra en la base de conocimiento — firmado y con
  fecha. Un sistema que se autocompleta las lagunas parece más listo y es peor: la
  primera respuesta inventada se convierte en la fuente de la siguiente.

---

# Tratamiento de datos

## Los datos con los que trabaja

**El catálogo es sintético.** `datos/inventario_sintetico.csv` son 5.000 piezas
generadas para el proyecto: id, referencia, pieza, marca, modelo, motor, año,
estado, garantía, disponibilidad, precio y url. **Ni un dato de una persona.**
Verificado con `scripts/auditar_datos.py`.

Las políticas de empresa (`datos/politicas.md`) son condiciones comerciales:
tampoco identifican a nadie.

## El único dato personal que aparece

**La matrícula** (o el VIN). Identifica un vehículo y, a través del registro de
tráfico, a su titular. Es dato personal aunque no venga con un nombre.

Llega porque el cliente la escribe, y es imprescindible: sin ella el sistema no
puede saber qué pieza monta su coche. Es exactamente la regla 1.

## Qué se hace con ella

| | |
|---|---|
| **Dónde se guarda** | En la memoria del proceso mientras dura la conversación. Se pierde al reiniciar el panel. |
| **Qué se escribe a disco** | Puede quedar en el registro de dudas y en los datos del panel, porque el mensaje del cliente se guarda literal para que una persona lo conteste. |
| **Qué sale de la máquina** | **La matrícula NO.** Al modelo se le manda que el cliente ya la dio, no cuál es. |
| **Cuánto se guarda** | El historial de cada conversación se corta a 12 turnos. Lo anterior se resume, y el resumen tampoco lleva la matrícula. |
| **Se puede borrar** | Sí, con una orden: `py scripts/olvidar.py 4521 KBD --borrar` |

El detalle, con el checklist punto por punto, está en [`GDPR.md`](GDPR.md).

## Dónde se ejecuta

Todo en local salvo una cosa. El catálogo, los embeddings, la búsqueda, las
reglas y el centro de control corren en la máquina del desguace, sin coste y sin
enviar nada a ningún sitio.

La **única** conexión de salida es a `api.groq.com`, y solo para escribir el texto
del mensaje. Se puede apagar quitando la clave del `.env`: el sistema sigue
funcionando entero, con sus propios mensajes.
