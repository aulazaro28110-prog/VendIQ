# Protección de datos en VendIQ — checklist ejecutable

Este documento **no es una declaración de intenciones**. Cada punto dice qué se
hace, dónde está en el código y cómo comprobarlo ahora mismo desde una terminal.

La auditoría de partida no se escribió a mano: la hizo
[`scripts/auditar_datos.py`](../scripts/auditar_datos.py), que recorre los
ficheros buscando matrículas, VIN, teléfonos y correos, y lee el código para ver
qué sale de la máquina.

> **Aviso honesto sobre el alcance.** VendIQ es un proyecto formativo con datos
> sintéticos. Esto no es un asesoramiento legal ni un registro de actividades de
> tratamiento: es el trabajo de ingeniería que haría falta para que un despliegue
> real pudiera tener uno.

---

## 1. Qué datos personales hay

| Dato | ¿Hay? | Nota |
|---|---|---|
| **Matrícula / VIN** | **Sí** | El más sensible. Identifica un vehículo y, vía registro, a su titular. |
| Nombre del cliente | Solo si lo escribe él | No se pide ni se deduce. |
| Teléfono | No | El simulador no conecta con WhatsApp: no hay números. |
| Correo | **Sí, sintéticos** | `datos/canales/correos.jsonl` versiona 50 correos con 16 direcciones inventadas por `scripts/generar_canales.py`. No es de nadie, pero la casilla no es "no". |
| Datos de pago | No | El bot **nunca** los pide ni los toca. |
| Catálogo de piezas | No | 5.000 fichas **sintéticas**, sin ninguna persona. |

**Comprobar:**
```
py scripts/auditar_datos.py
```

## 2. Minimización — se recoge y se manda lo mínimo

**La matrícula no sale de la máquina.**

Antes viajaba a Groq (EE. UU.) **tres veces por petición**: en el resumen, en los
turnos literales del historial y en el mensaje del turno. Eso es una transferencia
internacional de un dato personal, y era innecesaria: el modelo no necesita la
matrícula para redactar. Solo necesita saber que el cliente ya la dio, para no
volver a pedírsela.

Lo que se le manda ahora:

```
matrícula: sí, ya la dio — no se la vuelvas a pedir
```

El dato entero se queda en esta máquina. Sale **solo** si el redactor propio ha
decidido decirlo, que ocurre cuando el cliente pide que se lo repitan.

- **Dónde:** `sin_matricula()` en [`08_conversar.py`](../08_conversar.py)
- **Comprobar:** `py tests/test_llm.py` → *«NO manda la matrícula, solo que se
  dio»* y *«ni en ningún otro mensaje de la petición»*

**Otras minimizaciones:**

| | |
|---|---|
| Historial | Se corta a los **12 últimos turnos**. Lo anterior se resume. |
| Ventana al modelo | Solo **6 turnos** viajan literales. |
| Resumen | Se genera de la memoria, **no lo escribe el modelo** — así no puede inventarse una matrícula que nadie dijo. |
| Datos de pago | No se piden nunca. La política es explícita y hay 12 casos de prueba (6 de "no envía sin cobrar" y 6 de "no valida justificantes"). |

## 3. Supresión — el derecho al olvido, ejecutable

```
py scripts/olvidar.py 4521 KBD --ver        # dónde aparece, sin tocar nada
py scripts/olvidar.py 4521 KBD --borrar     # lo borra
```

Un checklist que dice «se atienden las solicitudes de supresión» no vale nada si
atenderlas consiste en que alguien recuerde qué siete ficheros tocar.

Lo que hace el script:

- Busca en los sitios donde **la auditoría demostró** que puede quedar: el
  registro de dudas, el detalle del banco, los datos del panel y las FAQ
  aprendidas.
- Reconoce las tres formas de escribirla: `4521 KBD`, `4521KBD`, `4521-KBD`.
- **Sustituye el dato**, no tira el registro entero. La pregunta que hizo el
  cliente es información de negocio que no identifica a nadie una vez fuera la
  matrícula. Minimizar es quitar el dato personal, no quemar el archivo.
- Valida que el JSON sigue siendo válido antes de escribirlo.
- **Dice lo que él no puede hacer**, que es la parte que se suele callar:
  reconstruir el índice (si no, la matrícula sigue viva dentro de un vector) y
  reiniciar el panel (para vaciar las conversaciones en memoria).

## 4. Acceso — el cliente puede pedir su dato

Funciona dentro de la propia conversación:

```
CLIENTE: ¿cuál era la matrícula que te di?
VENDIQ : Me pasaste la 4521 KBD.
         ¿Seguimos con el alternador?
```

Y si no la ha dado, **no se inventa ninguna**:

```
VENDIQ : Todavía no me has pasado ninguna.
         Mándamela y te digo qué pieza monta tu coche.
```

- **Dónde:** intención `recuerda mi dato` en [`07_redactor.py`](../07_redactor.py)

## 5. Exactitud — no se inventan datos

- **El precio** no puede inventarse: si la búsqueda no lo autoriza, el importe no
  entra en el contexto del modelo. Y se audita el texto final por si acaso.
- **Las respuestas aprendidas** las escribe una persona, se firman con su nombre
  y su fecha, y se dicen **literales**, sin que el modelo las reformule. No hay
  ningún camino por el que una respuesta llegue a la base de conocimiento sin que
  la haya escrito un humano.
- **El resumen** de la conversación se monta con lo que hay en memoria. Cada línea
  o está ahí o no aparece.

**Comprobar:** `py tests/test_conversaciones.py` → 218 casos, invariantes.

## 6. Transferencias internacionales

| | |
|---|---|
| **Único destino** | `api.groq.com` (Groq Inc., EE. UU.) |
| **Para qué** | Redactar el texto del mensaje. Nada más. |
| **Qué viaja** | El rol, la ficha del catálogo, la pregunta del cliente y los últimos turnos — **con la matrícula enmascarada**. |
| **Qué NO viaja** | La matrícula, el VIN, y cualquier importe que la búsqueda no haya autorizado. |
| **Se puede apagar** | Sí. Vacía `GROQ_API_KEY` en `.env` y el sistema funciona entero con su propio redactor. |

Que se pueda apagar es lo que convierte la transferencia en **opcional**: si un
despliegue real no quisiera sacar nada del país, el sistema sigue en pie.

## 7. Seguridad de las credenciales

- La clave vive en `.env`, que está en `.gitignore` y **nunca** se sube.
- `scripts/probar_groq.py` comprueba si la clave sirve **sin enseñarla**: solo los
  cuatro primeros y los cuatro últimos caracteres, que es lo justo para saber cuál
  de tus claves está puesta.
- Si una clave se expone, se revoca en `console.groq.com` y se crea otra. Ya pasó
  una vez en este proyecto y así se resolvió.

## 8. Lo que este proyecto NO tiene

Decirlo es parte del trabajo:

- **Casi no hay almacenamiento duradero, pero no es "nada".** Las conversaciones
  sí viven en memoria y mueren al reiniciar. Las **reservas** no:
  `salida/reservas.json` guarda la matrícula en un campo propio y sobrevive al
  reinicio. Está en `.gitignore`, así que no se publica, y `scripts/olvidar.py`
  ya lo recorre — pero durante un tiempo no lo hizo, y el borrado decía haber
  limpiado una matrícula que seguía ahí. Queda escrito porque el fallo es el
  interesante: una garantía de borrado vale lo que valga su lista de sitios. Un despliegue real necesitaría decidir cuánto guardar, y
  entonces harían falta política de retención, cifrado en reposo y control de
  acceso.
- **No hay autenticación en el panel.** Es un servidor local en `127.0.0.1`. Si se
  publicara, haría falta.
- **No hay registro de actividades de tratamiento** (art. 30), ni contrato de
  encargado con Groq, ni información al interesado en el primer mensaje. Son
  documentos de la empresa, no código.
- **No hay consentimiento ni base jurídica documentada.** En un desguace real, la
  base sería la ejecución del contrato o el interés legítimo, y hay que
  escribirlo.

---

## Comprobarlo todo, en orden

```
py scripts/auditar_datos.py           # qué datos hay y dónde
py scripts/olvidar.py 4521 KBD --ver  # el borrado, en seco
py tests/test_llm.py                  # que la matrícula no sale
py tests/test_conversaciones.py       # 218 casos, invariantes
```
