"""
07_redactor.py
==============
Escribe el mensaje que le llega al cliente por WhatsApp.

Hasta aquí el sistema recuperaba fichas. Esto es lo que las convierte en un mensaje
con la voz de Desguaces Madrid Norte (el rol de docs/VendIQ_RAG.md §7 y §8).

POR QUÉ NO ES UN LLM (todavía)
------------------------------
Un modelo de lenguaje redactaría mejor y aguantaría mejor los mensajes sucios. Pero
tiene dos pegas para lo que hace falta hoy: cuesta por uso, y con él los guardarraíles
solo se pueden comprobar estadísticamente — "de 100 pruebas no dijo ningún precio malo"
no es lo mismo que "no puede decirlo".

Este redactor sí puede demostrarlo, porque **no tiene acceso a ningún precio**: solo
usa el importe que el buscador ya marcó como publicable. Si el buscador dice que no,
aquí no hay de dónde sacarlo. Lo comprueban los invariantes de
tests/test_conversaciones.py sobre las 200 conversaciones: ni un solo importe
publicado sin autorización de la búsqueda.

`redactar()` es la única puerta de entrada. El día que se enchufe un LLM, se cambia
esa función y el resto del sistema no se entera.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# EL TONO
# ---------------------------------------------------------------------------
# Todo lo de aquí abajo sale de los mensajes REALES de Álvaro recogidos en
# docs/Prompt_Engineering_Ventas.html (técnica 3, few-shot). No está inventado:
# cada giro viene de un ejemplo suyo.
#
#   «Buenas Juan Carlos, para el Ibiza hay varios motores según versión, así que
#    para no fallar pásame la matrícula y te clavo el que monta exacto.»
#   «Buenos días Juan Carlos! ¿Cómo vas? Ya hemos recibido la caja de cambios que
#    nos pediste, cuando quieras te puedes pasar a por ella o si lo prefieres te la
#    mandamos al taller.»
#   «El alternador que nos pediste es original, lo hemos desmontado del vehículo
#    hace poco y funciona de 10, y como todos nuestros productos tiene un año de
#    garantía. Sobre el precio no puedo hacer maravillas, pero si me lo compras te
#    lo bajo sin coste al taller.»
#   «Buenas Roberto, ¿qué tal? Retomo lo de los amortiguadores del Passat por si
#    sigues dándole vueltas. ¿Sigue en pie o lo aparcamos de momento?»
#
# Cinco cosas que se deducen de ahí y que el redactor respeta:
#   1. TUTEA SIEMPRE. En sus ejemplos no aparece ni un usted, ni con clientes
#      nuevos. Lo que cambia entre conocido y nuevo es la cercanía, no el trato.
#   2. LA EMPRESA HABLA EN PLURAL ("hemos recibido", "nuestros productos") pero
#      lo que hace él va en singular ("te lo consigo", "no puedo hacer maravillas").
#   3. LA GARANTÍA ES ARGUMENTO DE VENTA, no letra pequeña: la menciona sin que
#      se la pidan. Una sola vez por conversación, que si no cansa.
#   4. ANTE EL PRECIO NO BAJA EL MARGEN, DA OTRA COSA: "te lo bajo sin coste al
#      taller". Ceder transporte en vez de dinero.
#   5. CADA MENSAJE TERMINA MOVIENDO LA VENTA: una pregunta, nunca un punto final.

PRESENTACION = "Buenas, soy el asistente de Desguaces Madrid Norte."
SALUDOS_CONOCIDO = ("Buenas {nombre}, ¿qué tal?", "Buenas {nombre}, ¿cómo vas?")

GARANTIA = "Como todos nuestros productos, con un año de garantía."

# Lo que se ofrece cuando el cliente aprieta con el precio: transporte, no margen.
# Y aun así la rebaja la decide una persona — el bot solo pone la alternativa
# encima de la mesa y avisa a Álvaro (política PRECIOS Y DESCUENTOS).
CESION_PRECIO = ("Sobre el precio no puedo hacer maravillas, pero si te {pron} llevas "
                 "te {pron} bajo sin coste al taller.")
ESCALADO_PRECIO = "Cualquier ajuste te lo tiene que decir Álvaro, se lo paso ahora."

# Respuestas cortas a cada política. El texto largo sigue siendo la fuente (se ve
# en el panel); esto es la versión que cabe en un WhatsApp.
POLITICAS = {
    "GARANTIA": "Todas las piezas llevan un año de garantía, nuevas o desmontadas. "
                "Solo hace falta guardar la factura.",
    "ENVIO Y PLAZOS": "Enviamos a toda la península en 24-48 h y lo que está en "
                      "stock sale al día siguiente. Baleares, Canarias, Ceuta y "
                      "Melilla se consultan aparte. También puedes recogerlo en "
                      "Alcobendas.",
    "PRECIOS Y DESCUENTOS": "Los precios que te paso son los publicados y siempre "
                            "van + IVA, sin excepción.",
    "FORMAS DE PAGO Y DEVOLUCIONES": "Puedes pagar con tarjeta, efectivo, "
                                     "transferencia, Bizum, Google Pay o Apple Pay. "
                                     "Y si no te vale, admitimos devolución mientras "
                                     "vuelva sin montar y como salió.",
    "PAGO ANTES DEL ENVIO": "La pieza sale cuando el pago está confirmado, sin "
                            "excepciones: no hacemos contrarreembolso.",
    "JUSTIFICANTES DE PAGO": "El ingreso lo comprueba una persona en la cuenta antes "
                             "de que salga nada. En cuanto lo vea, te aviso.",
    "COMO IDENTIFICAR LA PIEZA CORRECTA": "Con la matrícula o el bastidor te clavo "
                                          "la que monta exacto. Si tienes la "
                                          "referencia de la vieja, mejor todavía.",
}

# El único femenino de la lista es "de vehículo" -> se conjuga con la pieza.
ESTADOS = {
    "comprobada, funcionando": "comprobad{o} y funcionando",
    "desmontada de vehículo": "desmontad{o} de un coche hace poco",
    "sin comprobar": "sin comprobar todavía",
}

PALABRAS_INTENCION = {
    # ------------------------------------------------------- LAS REGLAS DURAS
    # Estas dos van las PRIMERAS y no las decide el bot: son condiciones de la
    # empresa que él solo repite. Están arriba del todo a propósito, para que
    # ninguna otra intención pueda colarse por delante y ablandarlas.
    #
    # El bot NO juzga si alguien intenta colártela. Lo que hace es no moverse de
    # la condición y pasar la conversación a una persona, porque la consecuencia
    # de equivocarse aquí no es una respuesta fea: es una pieza que sale del
    # almacén sin cobrar.
    "pide sin pagar": ("sin pagar", "antes de pagar", "mandamelo y te pago",
                       "mandala y te pago", "te pago cuando", "te pago al recibir",
                       "contrareembolso", "contra reembolso", "contrarreembolso",
                       "fiate de mi", "fiate", "de confianza", "pago luego",
                       "pago despues", "me lo envias ya y",
                       "a cuenta", "fin de mes", "lo cuadramos", "ya te lo abono",
                       "apuntamelo", "a deber", "cuando pueda te pago",
                       # Añadidas midiendo el registro de no resueltas. El cliente
                       # no dice "sin pagar": dice cuándo va a pagar. Lo que delata
                       # la petición es el tiempo verbal —el envío ahora, el pago
                       # después—, y sin estas formas «mándamela y te hago la
                       # transferencia mañana» se colaba por «cierre» y el bot
                       # contestaba «claro, ¿cuál te aparto?».
                       "y te hago la transferencia", "te hago la transferencia manana",
                       "te hago el bizum manana", "te pago manana", "te lo pago manana",
                       "lo pago manana", "pago al recibir", "pagando al recibir",
                       "cuando la reciba te pago", "cuando llegue te pago",
                       "a 30 dias", "a 60 dias"),
    "justificante": ("justificante", "resguardo", "comprobante", "pantallazo",
                     "captura de la transferencia", "captura del pago",
                     "ya te he hecho la transferencia", "ya te he pagado",
                     "ya esta pagado", "te mando el papel", "adjunto el pago"),

    # El orden importa: se evalúan de arriba abajo y gana la primera. Una queja
    # manda sobre todo lo demás; un "me lo quedo" manda sobre un "cuánto vale".
    "queja": ("no funciona", "no va", "roto", "rota", "defectuos", "averiad",
              "reclamacion", "reclamar", "devolver", "devolucion", "mal estado",
              "no me sirve", "no encaja", "estafa", "vergüenza", "verguenza",
              # Un cliente al que nadie contesta ya está enfadado, aunque la
              # pregunta parezca de plazos. Contestarle con la política de envíos
              # es lo peor que se puede hacer: hay que dárselo a una persona.
              "nadie me contesta", "no me contestais", "sigo esperando",
              "dias esperando", "días esperando", "sin noticias",
              "cobrado dos veces", "me habeis cobrado", "cargo duplicado",
              "es de otro modelo", "no es la que pedi", "no es lo que pedi",
              "me habeis mandado otra", "esto no es lo que"),
    # El regateo va ANTES del cierre: "te doy la mitad y me lo llevo hoy" lleva las
    # dos cosas, y lo que hay encima de la mesa es una negociación, no una venta
    # cerrada. Darla por cerrada sería aceptar un precio que nadie ha aprobado.
    "regateo": ("descuento", "rebaja", "mas barato", "más barato", "ultimo precio",
                "último precio", "me lo dejas", "me la dejas", "te doy", "te ofrezco",
                "que menos", "se puede bajar", "puedes bajar", "bajar algo",
                "hacemos precio", "mejor precio", "muy caro", "es caro", "carisimo",
                "la mitad",
                # Todas estas salieron del banco de 200: el cliente regatea sin
                # decir nunca la palabra "descuento". Añadir sinónimos uno a uno no
                # escala, pero estas son las formas que de verdad se usan.
                "quitame el iva", "en efectivo", "en negro",
                "me compro uno nuevo", "por ese dinero", "algo tendras que hacerme",
                "algo me haras", "redondea", "cerramos en", "te lo pago en mano",
                "esta por las nubes", "se te ha ido", "no me cuadra el precio",
                "ajustame", "afinar el precio", "ultima oferta", "mi ultima"),
    "cierre": ("me lo quedo", "me la quedo", "lo quiero", "la quiero", "me lo llevo",
               "me la llevo", "apartamelo", "apartamela", "resérvamelo", "reservamelo",
               "reservamela", "adelante", "tramitalo", "mandamelo", "mandamela",
               "lo compro", "la compro", "de acuerdo",
               # Formas interrogativas/coloquiales que faltaban: el cliente pregunta
               # "¿me lo apartas?" en vez del imperativo "apártamelo". Era el fallo
               # nº1 del registro (150x): un cierre que se escapaba a un humano.
               "me lo apartas", "me la apartas", "apartame", "puedes apartar",
               "me lo reservas", "me la reservas", "puedes reservar",
               "me lo guardas", "me la guardas", "guardamelo", "guardamela"),
    # EL CLIENTE APARCA LA CONVERSACIÓN. No es una pregunta y contestarla con
    # «pásame la matrícula» es lo que más ventas quema: le has entendido al revés
    # justo cuando te estaba diciendo que sigue interesado.
    #
    # Son 318 mensajes a la semana en el registro real, repartidos en cuatro
    # formas de decir exactamente lo mismo. Por eso va aquí y no como FAQ: una
    # FAQ solo dispara con las palabras exactas, y aquí lo que hay son sinónimos.
    # EL CLIENTE PIDE UN DATO SUYO. "¿Cuál era la matrícula que te di?" es, en
    # pequeño, un derecho de acceso: pide que se le devuelva lo que él dio. El bot
    # lo tiene en memoria y se lo dice; nunca hay que hacerse el sordo con esto.
    #
    # Además hacía falta por otra razón. Desde que la matrícula deja de viajar al
    # modelo (minimización), él ya no puede leerla del historial: si no hay una
    # rama que la diga, el bot deja de saber contestar algo que sabe.
    "recuerda mi dato": ("cual era la matricula", "cuál era la matrícula",
                         "que matricula te di", "qué matrícula te di",
                         "que matricula te pase", "qué matrícula te pasé",
                         "cual te di", "cuál te di", "te di la matricula",
                         "que coche te dije", "qué coche te dije",
                         "cual era mi matricula", "cuál era mi matrícula",
                         "me repites la matricula", "que bastidor te di"),

    "aparca": ("dejame que lo mire", "déjame que lo mire", "lo miro y te digo",
               "luego te digo", "despues te digo", "después te digo",
               "te digo algo", "te confirmo manana", "te confirmo mañana",
               "te confirmo luego", "me lo pienso", "lo consulto",
               "lo tengo que mirar", "lo miro", "ya te dire", "ya te diré",
               # Conjugadas. La lista tenia "lo consulto" y el cliente escribio
               # "dejame que lo CONSULTE con el cliente": no casaba, ganaba el
               # "vale" del principio y el bot cerraba una venta que el cliente
               # acababa de aparcar. Un taller siempre consulta con alguien.
               "que lo consulte", "lo consulte", "consultarlo", "que lo pregunte",
               "lo pregunte", "preguntarlo", "que lo hable", "lo hable",
               "hablarlo", "que lo vea", "lo vea con", "con el cliente",
               "con el jefe", "con el dueno", "con el dueño", "que lo mire",
               "nada, era otra cosa", "era otra cosa", "dejalo", "déjalo",
               "ahora no puedo", "estoy liado", "te escribo luego"),

    # PREGUNTA POR ALGO QUE YA ESTÁ EN MARCHA, o pide que se le avise. Solo tiene
    # sentido si el bot recuerda lo que prometió — ver Conversacion.promesas.
    "seguimiento": ("ya lo tienes", "ya la tienes", "lo tienes ya", "alguna novedad",
                    "se sabe algo", "hay novedades", "hay noticias", "novedades",
                    "avisame en cuanto", "avísame en cuanto", "avisame cuando",
                    "avísame cuando", "me avisas", "como va lo", "cómo va lo",
                    "que tal lo de", "qué tal lo de", "sigue en pie",
                    "en que ha quedado", "en qué ha quedado",
                    # Añadidas escribiendo una conversación entera: "sigue
                    # disponible?" contestaba pidiendo la matrícula que el cliente
                    # ya había dado tres turnos antes.
                    "sigue disponible", "siguen disponibles", "sigue disponibles",
                    "siguen estando", "las sigues teniendo", "los sigues teniendo",
                    "sigue estando", "la sigues teniendo",
                    "lo sigues teniendo", "todavia la tienes", "todavía la tienes",
                    "todavia lo tienes", "todavía lo tienes", "sigue ahi",
                    "sigue ahí", "lo tienes todavia", "sigue reservado",
                    "sigue apartado", "sigue guardado"),

    "prisa": ("urge", "urgente", "corre prisa", "mucha prisa", "para ya",
              "parado", "cuanto antes", "para hoy", "para mañana", "es para ya"),
    # Preguntas sobre CUÁNDO llega. Se detectan aquí y no se dejan solo al buscador
    # porque casi siempre llegan de rebote ("¿y me llega esta semana?"), sin nombrar
    # la pieza: el buscador no tiene con qué encontrarlas, la conversación sí.
    "plazo": ("cuando me llega", "cuando llega", "cuanto tarda", "cuánto tarda",
              "me llega", "llega esta semana", "para cuando", "para cuándo",
              "lo tienes ya", "la tienes ya", "cuando lo tengo", "cuando la tengo",
              "me lo mandas", "me la mandas", "puedo pasar a por"),
    # LAS DE SEGUIMIENTO. Van sobre la pieza de la que ya se estaba hablando y
    # llegan sin nombrarla ("¿y está comprobada?"), así que el buscador no puede
    # encontrarlas: la respuesta está en la conversación, no en el índice. Sin
    # estas cuatro, todas caían en la rama de "no te he entendido" y el bot
    # contestaba lo mismo cinco veces seguidas.
    # El kilometraje va aparte del estado a propósito: el catálogo NO lo guarda,
    # y contestar "está comprobada" a "¿cuántos km tiene?" es esquivar la pregunta.
    # Un profesional nota la esquiva en el primer mensaje.
    "kilometros": ("cuantos km", "kilometros", "kilometraje", "que km tiene",
                   "km lleva", "cuanto ha rodado"),
    "estado": ("esta comprobada", "esta comprobado", "está comprobad", "comprobada",
               "comprobado", "funciona bien", "en que estado", "que tal esta",
               "es original", "la habeis probado", "esta probada", "va bien",
               "esta bien la pieza", "seguro que funciona"),
    "precio otra vez": ("cuanto me costaria", "cuanto cuesta", "cuanto vale",
                        "que precio", "mandame el precio", "pasame el precio",
                        "dime el precio", "cuanto seria", "cuanto me dices",
                        "en cuanto se queda", "cuanto me lo dejas"),
    "compatibilidad": ("encaja", "vale para", "sirve para", "es compatible",
                       "seguro que", "equivocarme", "que sea la buena", "que monta",
                       "me vale a mi", "es la mia"),
    "alternativa": ("la otra", "tienes mas", "tienes otra", "alguna otra",
                    "otra opcion", "la que tengas", "da igual", "cual mas"),
    "agradecimiento": ("gracias", "genial", "perfecto", "estupendo", "vale ok"),
    "saludo": ("hola", "buenas", "buenos dias", "buenas tardes", "que tal", "qué tal"),
}


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def detectar_matricula(texto: str):
    """Matrícula española moderna (1234 ABC) o antigua (M-1234-AB), y el bastidor."""
    t = texto.upper().replace("-", " ")
    m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", t)                       # VIN
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{4})\s?([BCDFGHJKLMNPRSTVWXYZ]{3})\b", t)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.search(r"\b([A-Z]{1,2})\s?(\d{4})\s?([A-Z]{2})\b", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


# Preguntar "¿y qué pasa si sale defectuosa?" NO es una queja: es un cliente que
# quiere saber la política de garantía antes de comprar. Tratarlo como reclamación
# y escalarlo pierde la venta y le hace pensar que algo va mal.
HIPOTETICO = ("que pasa si", "y si ", "en caso de", "si sale", "si me sale",
              "si no me", "si viniera", "si llegara", "que pasaria",
              "si me equivoco", "por si acaso", "en el caso de que",
              "puedo devolverla", "puedo devolverlo", "se puede devolver")


# ---------------------------------------------------------------------------
# LAS REGLAS DE ESTILO, EN UN SOLO SITIO
# ---------------------------------------------------------------------------
# Viven aquí, junto a la voz que definen, y las usan tanto el panel —para auditar
# lo que escribe el LLM— como el banco de pruebas. Una sola definición: dos que
# se separen es peor que ninguna.

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")

# Usted sin discusión: la palabra, o un imperativo de usted.
USTED_SEGURO = re.compile(r"\busted(es)?\b|\bpáse|\bdíga|\bhága|\bténga|\bvéa\b",
                          re.I)

# Usted probable, pero NO seguro. En español «le» es dativo de tercera persona y
# sirve igual para usted que para él: «le paso a Álvaro» no trata de usted a
# nadie. Por eso estos marcadores solo cuentan si en el mismo mensaje no hay
# tuteo — quien escribe «te aviso» no está tratando de usted.
USTED_DUDOSO = re.compile(r"\ble\s+(paso|aviso|confirmo|mando|envío|envio|digo)\b"
                          r"|\bsuya\b|\bsu\s+coche\b|\bsu\s+vehículo\b", re.I)

# «tu» sin tilde es el posesivo, y también es tuteo. Faltaba, y por eso se marcaba
# como usted un «le paso ahora mismo tu mensaje» que tutea perfectamente.
TUTEO = re.compile(r"\bt[eúu]\b|\btus\b|\bti\b|\btuyo?\b|\btuya\b|\btienes\b"
                   r"|\bdime\b|\bpásame\b|\bmándame\b|\bquieres\b", re.I)

MAXIMO_LINEAS = 3


def trata_de_usted(mensaje: str) -> bool:
    """¿Este mensaje trata de usted al cliente?

    Salió de un falso positivo con el LLM encendido: «le paso a Álvaro […] te
    aviso» se marcaba como usted, y ese «le» era Álvaro. La señal buena no es el
    marcador suelto, es el marcador SIN tuteo alrededor.
    """
    if USTED_SEGURO.search(mensaje):
        return True
    return bool(USTED_DUDOSO.search(mensaje)) and not TUTEO.search(mensaje)


# ---------------------------------------------------------------------------
# LA REGLA DE LA IDENTIFICACIÓN
# ---------------------------------------------------------------------------
# NUNCA SE OFRECE NADA SIN SABER QUE ES LA PIEZA DEL COCHE DEL CLIENTE.
#
# Es la regla de negocio, dicha por Álvaro con estas palabras: el bot no ofrece
# material antes de pedir matrícula, referencia o VIN. No es prudencia nuestra,
# es que sin uno de esos tres datos la afirmación es falsa. Medido sobre el
# catálogo de 5.000 piezas:
#
#   lo que el cliente escribe          fichas que encajan
#   marca + modelo + pieza             97% comparten descripción con otra
#   marca + modelo + MOTOR + pieza     81% siguen compartiéndola
#   + año                               0% — única
#   referencia OEM                      0% — única
#   número de stock                     0% — única
#
# O sea que ni dar el motor identifica la pieza: hay hasta quince alternadores
# del mismo coche según motor y año. Ofrecer uno es afirmar que encaja, y eso no
# se sabe. El cliente lo dijo mejor que nadie en la primera prueba del chat, al
# turno siguiente de que el bot le ofreciera uno: «¿cómo sé si es el mío?».
#
# TRES DATOS LA CUMPLEN, y los tres son exactos:
#   · MATRÍCULA o VIN  — identifican el coche; los detecta detectar_matricula()
#   · REFERENCIA OEM   — identifica la ficha; la detecta precio_para_cliente()
#   · NÚMERO DE STOCK  — identifica la ficha; ídem
#
# La regla se aplica en TRES sitios, y hacen falta los tres:
#   1. El precio no se autoriza (03_buscar.py, condición 5). El importe no llega
#      ni al redactor ni al modelo: no puede decirse porque no está.
#   2. El redactor no describe la ficha, pide el dato y dice cuántas hay.
#   3. Esta función audita el mensaje FINAL, venga de quien venga. El redactor
#      cumple por construcción; el modelo no, y hay que mirárselo.

# Un importe en el mensaje. Ofrecer precio es ofrecer una ficha concreta.
IMPORTE_EN_TEXTO = re.compile(r"\d[\d.,]*\s*(?:€|eur\b|euros\b)", re.I)

# Pedir el dato que identifica. Cualquiera de los tres vale.
PIDE_IDENTIFICADOR = re.compile(
    r"matr[íi]cula|bastidor|\bvin\b|referencia|n[úu]mero de stock|n[ºo]\s*de\s*stock",
    re.I)


def rompe_la_identificacion(lineas, meta, identificado):
    """¿Este mensaje ofrece una pieza sin saber que es la del cliente?

    `meta` es la ficha que la búsqueda puso encima de la mesa (o None si no hay
    ninguna) e `identificado` dice si la conversación tiene ya matrícula, VIN,
    referencia OEM o número de stock.

    Se miran tres cosas, y las tres son sobre el texto que va a salir:
      · que no lleve un importe,
      · que no cante datos de la ficha que el cliente no ha dado —el motor o el
        año son justamente lo que distingue una hermana de otra—,
      · y que pida el dato, porque si no la conversación se queda parada.
    """
    if identificado or not meta:
        return None

    mensaje = "\n".join(lineas)

    if IMPORTE_EN_TEXTO.search(mensaje):
        return ("da un precio sin saber si la pieza es la de su coche: hace falta "
                "matrícula, referencia o VIN")

    # El motor y el año son los datos que separan una ficha de su hermana. Si el
    # mensaje los dice y el cliente no los ha dado, se está ofreciendo una ficha
    # concreta como si fuera la suya.
    for campo in ("motor", "anio"):
        valor = str((meta or {}).get(campo) or "").strip()
        if valor and valor.lower() in mensaje.lower():
            return (f"describe la ficha por su {campo} ({valor}) sin saber si es la "
                    f"de su coche: hace falta matrícula, referencia o VIN")

    if not PIDE_IDENTIFICADOR.search(mensaje):
        return ("no ofrece la pieza, pero tampoco pide matrícula, referencia ni "
                "VIN: la conversación se queda sin siguiente paso")

    return None


# Afirmar que NO se tiene una pieza. Ojo: «no lo tengo apuntado en la ficha» niega
# un DATO, no la pieza, y es una respuesta correcta. Por eso este patrón solo se
# aplica cuando la búsqueda ya ha decidido NO DISPONIBLE, que es exactamente la
# situación en la que manda la regla de la matrícula.
NIEGA_TENERLA = re.compile(
    r"no (?:la|lo|las|los) tengo"
    r"|no (?:la|lo|me) consta"
    r"|no (?:la|lo|las|los) tenemos"
    r"|no (?:la|lo|las|los) hay"
    r"|no (?:me |nos )?queda[nr]?"
    r"|no est[áa] en (?:el )?(?:cat[áa]logo|almac[ée]n|stock)", re.I)

# Pedir el dato que identifica la pieza. Vale la matrícula o el bastidor: son las
# dos formas que acepta la política COMO IDENTIFICAR LA PIEZA CORRECTA.
IDENTIFICA = re.compile(r"matr[íi]cula|bastidor|vin", re.I)


def rompe_la_matricula(lineas, decision, matricula_dada, escala):
    """La regla de la matrícula: sin ella el bot NUNCA dice «no la tengo».

    Sin identificar la pieza no puede saberlo, y un «no» falso pierde una venta
    que quizá estaba en el almacén con otro nombre. Con matrícula sí puede
    decirlo, y entonces es una respuesta y no una excusa.

    La excepción es escalar. Una queja («el alternador que me mandasteis no
    funciona») también cae en NO DISPONIBLE, porque el cliente nombra una pieza y
    ninguna ficha encaja, pero ahí no está preguntando si la tenemos: pedirle la
    matrícula sería sordo. La regla es «no digas que no sin matrícula», no «pide
    siempre la matrícula».

    Vive aquí y no solo en el banco porque el LLM la rompe. Con el modelo
    encendido, un caso de 200 salió diciendo que no la teníamos sin haber pedido
    nada — la regla que más se cuidó al escribirla, saltada por la capa que solo
    debía mejorar la forma.
    """
    if decision != "NO DISPONIBLE" or matricula_dada or escala:
        return None
    mensaje = "\n".join(lineas)
    if NIEGA_TENERLA.search(mensaje):
        return ("dice que NO la tiene sin matrícula: sin identificar la pieza no "
                "puede saberlo")
    if not IDENTIFICA.search(mensaje):
        return "no tiene la pieza y no pide la matrícula: un «no» sin salida"
    return None


def rompe_el_estilo(lineas):
    """Qué regla de la voz rompe un mensaje, o None si no rompe ninguna.

    Se usa para auditar lo que escribe el LLM antes de que salga. El redactor
    determinista cumple estas reglas por construcción; el modelo, no — así que
    hay que mirárselo, igual que se le miran los precios.
    """
    mensaje = "\n".join(lineas)
    if not mensaje.strip():
        return "mensaje vacío"
    if len(lineas) > MAXIMO_LINEAS:
        return f"{len(lineas)} líneas, el máximo son {MAXIMO_LINEAS}"
    if EMOJI.search(mensaje):
        return "lleva emoji"
    if trata_de_usted(mensaje):
        return "trata de usted al cliente"
    return None


# Señalar una pieza de la que ya se ha hablado, sin volver a nombrarla. En una
# conversación de taller es constante: se piden tres cosas y luego se habla de
# «la otra» o «el que te dije antes». Sin esto, ese mensaje se busca a ciegas.
REFERENCIA_ANTERIOR = re.compile(
    r"(el|la|lo) que te dije|(el|la) anterior|(el|la) primer[oa]?"
    r"|(el|la) otr[oa]|lo de antes|(el|la) de antes|(el|la) de la otra vez"
    r"|(el|la) mism[oa]|como (el|la) de", re.I)


def pieza_referida(conv, mensaje):
    """A cuál de las piezas ya habladas se refiere el cliente, o None.

    No adivina: si no hay ninguna en el hilo, devuelve None y el mensaje se busca
    como cualquier otro. Distingue tres señales, que son las que usa la gente:
    «la otra» es la penúltima, «la primera» es la primera de la conversación, y
    cualquier otra referencia vale para la última.
    """
    if not conv.piezas or not REFERENCIA_ANTERIOR.search(mensaje):
        return None
    t = _sin_tildes(mensaje)
    if "primer" in t:
        return conv.piezas[-1]
    # «La otra», «el de antes», «el anterior», «el que te dije antes»: todas
    # señalan hacia atrás, no a la última. Si solo hay una en el hilo, es esa.
    hacia_atras = ("otro" in t or "otra" in t or "antes" in t or "anterior" in t
                   or "otra vez" in t)
    if hacia_atras and len(conv.piezas) > 1:
        return conv.piezas[1]
    return conv.piezas[0]


def texto_de_pieza(meta):
    """Cómo se busca una ficha ya conocida: por su nombre y su coche."""
    if not meta:
        return ""
    return " ".join(str(meta.get(c) or "") for c in
                    ("pieza", "marca", "modelo", "motor")).strip()


# Decir que sí. Solo se mira cuando el bot acaba de hacer una pregunta de cierre:
# suelta, esta lista no significa nada. Ver `esperando_si` en Conversacion.
AFIRMACION = re.compile(
    r"^\W*(s[ií]|vale|ok|okey|okay|venga|dale|perfecto|genial|claro|correcto"
    r"|eso es|adelante|hecho|de acuerdo|por supuesto|sin problema|guay"
    r"|estupendo|me vale|de lujo|trato hecho)\b", re.I)

# Pedir que se lo manden. Va en el mismo mensaje que el sí muy a menudo —«sí, me
# lo puedes enviar?»— y contestar «¿te lo mando o te pasas tú?» después de eso es
# no haberle leído.
PIDE_ENVIO = re.compile(r"envi|manda|mandes|mandar|traer|traes|lo traes|a domicilio"
                        r"|al taller|a mi taller|por mensajer", re.I)


def dice_que_si(conv, mensaje):
    """¿Es esto un sí a lo último que preguntó el bot?

    Tres condiciones, y hacen falta las tres:
      1. que el bot esté esperando una respuesta (acaba de preguntar si lo aparta),
      2. que el mensaje empiece por una afirmación,
      3. que no sea un «si» condicional — «si no me vale la puedo devolver» empieza
         igual y es una pregunta sobre la política de devoluciones.
    """
    # Vale mientras haya una oferta viva, no solo en el turno siguiente a
    # preguntar. Un taller contesta «sí» tres mensajes después de que le dieras el
    # precio, y por el medio te ha preguntado otras dos cosas: exigir que el sí
    # llegue pegado a la pregunta es no haber visto nunca un WhatsApp.
    #
    # Lo que hace que un «sí» sea una venta es que haya una pieza con precio
    # encima de la mesa. Si no la hay, no cierra nada.
    hay_oferta = conv.estado in (OFRECIENDO, APARCADA) and bool(conv.precio_de)
    if not (getattr(conv, "esperando_si", False) or hay_oferta):
        return False
    if not AFIRMACION.match(mensaje or ""):
        return False
    t = _sin_tildes(mensaje)
    return not any(h in t for h in HIPOTETICO)


# Una dirección de entrega: un tipo de vía y un número, o un código postal. No
# pretende validar direcciones — solo distinguir «calle mayor 3» de una consulta.
DIRECCION = re.compile(
    r"\b(c/|calle|avda|avenida|plaza|pza|paseo|carretera|ctra|camino|poligono"
    r"|polígono|urbanizacion|urbanización|travesia|travesía)\b"
    r"|\b\d{5}\b", re.I)


def detectar_intencion(mensaje: str) -> str:
    """Qué está haciendo el cliente, más allá de qué pieza pide.

    Esto NO mira el catálogo: mira la conversación. Un "me lo quedo" y un "cuánto
    vale" recuperan lo mismo del índice y sin embargo piden respuestas opuestas.
    """
    t = _sin_tildes(mensaje)
    hipotetico = any(h in t for h in HIPOTETICO)
    # "Perfecto", "genial" y "vale" son acuses… salvo cuando van delante de una
    # pregunta. «Perfecto, ¿y si no me vale?» se clasificaba como agradecimiento
    # por la primera palabra y la pregunta se perdía entera: el bot contestaba
    # «a ti, cualquier cosa me dices» a alguien que preguntaba por la devolución.
    pregunta = "?" in mensaje or "¿" in mensaje
    for intencion, marcas in PALABRAS_INTENCION.items():
        if intencion == "queja" and hipotetico:
            continue        # es una pregunta sobre la política, no una reclamación
        if intencion == "agradecimiento" and pregunta:
            continue        # da las gracias y además pregunta: lo que manda es la pregunta
        if any(_sin_tildes(m) in t for m in marcas):
            return intencion
    return "consulta"


# ---------------------------------------------------------------------------
# CONCORDANCIA
# ---------------------------------------------------------------------------
# El catálogo guarda "Alternador" y "Caja de cambios" en la misma columna, pero uno
# es "el ... lo tengo" y el otro "la ... la tengo". Sin esto, el bot escribe como un
# extranjero y se nota más que cualquier fallo de búsqueda.
FEMENINAS_RARAS = {"llave", "luz", "cruz"}      # acaban en consonante y son femeninas


def _genero(pieza: str) -> str:
    """'f' o 'm' a partir del nombre de la pieza. Regla: la palabra principal.

    Acierta en las 37 piezas del catálogo actual (aleta, bomba, caja, centralita,
    cerradura, cremallera, puerta -> femeninas; el resto masculinas), incluidos los
    singulares acabados en -s como "parachoques" o "elevalunas".
    """
    cabeza = _sin_tildes(pieza).split()[0] if pieza.strip() else ""
    if cabeza in FEMENINAS_RARAS or cabeza.endswith(("cion", "dad", "tud")):
        return "f"
    return "f" if cabeza.endswith("a") else "m"


def _art(genero):   return "la" if genero == "f" else "el"
def _pron(genero):  return "la" if genero == "f" else "lo"
def _o(genero):     return "a" if genero == "f" else "o"
def _del(genero):   return "de la" if genero == "f" else "del"


def _describir(meta: dict) -> str:
    """Cómo lo diría un mecánico, no cómo lo guarda la base de datos.

    'Motor completo · FORD · Focus · 2.0 TDCi · 2007'
        -> 'el motor completo de un Ford Focus 2.0 TDCi del 2007'
    """
    pieza = (meta.get("pieza") or "la pieza").strip()
    g = _genero(pieza)
    coche = " ".join(x for x in (str(meta.get("marca", "")).title(),
                                 meta.get("modelo", ""), meta.get("motor", "")) if x)
    anio = meta.get("anio")
    texto = f"{_art(g)} {pieza[0].lower() + pieza[1:]}"
    if coche:
        # "un", siempre: el coche es masculino aunque la marca acabe en -a (Toyota).
        texto += f" de un {coche}"
    if anio:
        texto += f" del {anio}"
    return texto


def _estado(meta: dict) -> str:
    bruto = _sin_tildes(meta.get("estado", "")).strip()
    for clave, plantilla in ESTADOS.items():
        if _sin_tildes(clave) == bruto:
            return plantilla.format(o=_o(_genero(meta.get("pieza", ""))))
    return ""


def _plazo(meta: dict, genero: str) -> str:
    if "stock" in _sin_tildes(meta.get("disponibilidad", "")):
        return f"{_pron(genero)} tengo aquí, si {_pron(genero)} quieres sale mañana"
    return f"{_pron(genero)} tengo en 24-48 h"


# ---------------------------------------------------------------------------
# EL HILO DE LA CONVERSACIÓN
# ---------------------------------------------------------------------------
# Una venta de desguace pasa siempre por los mismos puntos, y el mensaje del
# cliente significa cosas distintas en cada uno. «Vale» en IDENTIFICANDO es un
# acuse; en OFRECIENDO es un cierre. Sin saber dónde estamos hay que adivinarlo
# mensaje a mensaje, y ahí es donde el bot se equivocaba.
#
# Salió de los números del registro de no resueltas: 435 escalados a la semana
# entre «déjame que lo mire» (164), «luego te digo algo» (123), «ok, te confirmo
# mañana» (99) y «nada, era otra cosa» (32). Ninguna es una pregunta. Las cuatro
# dicen lo mismo: *aparco esto y vuelvo*. Un bot que no entiende eso pide la
# matrícula otra vez y quema la venta.

IDENTIFICANDO = "identificando"   # aún no se sabe qué pieza es la suya
OFRECIENDO = "ofreciendo"         # hay ficha y precio encima de la mesa
APARCADA = "aparcada"             # lo va a mirar y vuelve; no hay que empujar
CERRADA = "cerrada"               # ha dicho que sí
POSVENTA = "posventa"             # ya hay venta y pregunta por ella

# Cómo se lee cada estado en el panel y en el resumen que ve el modelo.
ESTADO_EN_CLARO = {
    IDENTIFICANDO: "identificando la pieza",
    OFRECIENDO: "con una pieza y su precio encima de la mesa",
    APARCADA: "aparcada: dijo que lo miraba y volvía",
    CERRADA: "cerrada: ha dicho que sí",
    POSVENTA: "posventa: pregunta por algo ya vendido",
}


class Conversacion:
    """Lo que el cliente ya ha contado. Sirve para no volver a pedírselo.

    Es la regla §8.1 del diseño: 'nunca vuelvas a pedir un dato que ya te dio'.
    Sin esto, un bot pregunta tres veces la matrícula y el cliente se va.
    """

    def __init__(self, perfil="nuevo", nombre=""):
        self.perfil = perfil                # "nuevo" | "conocido"
        self.nombre = nombre
        self.matricula = None
        self.presentado = False
        self.garantia_dicha = False
        self.turnos = 0
        self.ultimo_precio = None           # importe publicado, si llegó a darse
        self.datos_pedidos = set()          # qué se le ha pedido ya
        self.escalado = False               # ya está en manos de una persona
        self.matricula_recien_dada = False   # la ha dado en este mismo mensaje
        # Regla dura activa: mientras haya una encima de la mesa, el bot no se
        # mueve de ella aunque el cliente cambie de argumento. Ver redactar().
        self.regla_dura = None
        self.veces_dicho = {}               # cuántas veces se ha usado cada frase
        # Cuántas veces se le ha lanzado una pregunta de aclaración con botones.
        # El diseño pone el tope en dos: a la tercera ya no estás aclarando, estás
        # interrogando, y el cliente se va.
        self.aclaraciones = 0
        # Coche del que se está hablando. Lo rellena el panel al reconocerlo, y sirve
        # para que "la puerta, la de siempre" siga encontrando la pieza correcta.
        self.vehiculo = None
        # Lo último que pidió el cliente, para cuando cambie de coche y no repita
        # la pieza ("y para un Clase A?").
        self.pieza_pedida = None

        # --------------------------------------------------------- EL HILO
        # 1. EN QUÉ PUNTO VA LA VENTA. Lo que significa un mensaje depende de
        #    aquí: "vale" identificando es un acuse, ofreciendo es un cierre.
        self.estado = IDENTIFICANDO

        # 2. LO QUE SE LE HA PROMETIDO. Cada vez que el bot dice "te aviso" o
        #    "lo miro y te digo", queda anotado. Sin esto, un "¿ya lo tienes?"
        #    tres días después no se entiende: el bot no sabe que hay algo
        #    pendiente y contesta pidiendo la matrícula. En el registro son 99
        #    mensajes a la semana entre las dos formas de preguntarlo.
        self.promesas = []                  # [{"que":…, "pieza":…, "turno":…}]

        # 3. TODAS LAS PIEZAS HABLADAS, no solo la última. Un taller pide tres
        #    cosas del mismo coche en el mismo hilo; con una sola en memoria, las
        #    dos primeras se pierden y hay que repetírselas.
        self.piezas = []                    # metas, la más reciente primero
        # Y el precio de cada una. Con un solo `ultimo_precio`, preguntar por la
        # pieza de antes contestaba «te lo confirmo» de algo ya cotizado: el
        # importe existía, pero pertenecía a otra ficha.
        self.precio_de = {}                 # {id de ficha: importe dicho}

        # 4. QUÉ CONDICIONES YA SE LE HAN EXPLICADO. Repetir el párrafo de envío
        #    tres veces es lo que delata a un bot; y al modelo hay que decírselo,
        #    porque él no se acuerda.
        self.temas_tratados = set()

        # Fichas cuya descripción entera ya se le ha soltado. Repetirla es lo que
        # más delata a un bot.
        self.descritas = set()

        # ¿El bot acaba de preguntar si lo aparta? Es lo que convierte un «sí» en
        # una venta. Sin esto, «sí» no significa nada: no es una intención, es la
        # respuesta a una pregunta concreta que hay que recordar haber hecho.
        self.esperando_si = False

    @property
    def conocido(self):
        return self.perfil == "conocido"

    # La última pieza es la primera de la lista. Se mantiene como propiedad y no
    # como atributo suelto para que no puedan desincronizarse: todo el código que
    # ya existía sigue leyendo `ultima_pieza` sin enterarse de que ahora hay
    # varias, y quien las quiera todas mira `piezas`.
    @property
    def ultima_pieza(self):
        return self.piezas[0] if self.piezas else None

    @ultima_pieza.setter
    def ultima_pieza(self, meta):
        self.recordar_pieza(meta)

    def recordar_pieza(self, meta):
        """Pone esta pieza al frente del hilo, sin duplicarla ni perder las otras.

        Se identifican por el ID de la ficha: el cliente puede volver a nombrar la
        misma con otras palabras y no es una pieza nueva.
        """
        if not meta:
            return
        ident = str((meta or {}).get("id") or "")
        self.piezas = [p for p in self.piezas
                       if str((p or {}).get("id") or "") != ident]
        self.piezas.insert(0, meta)
        del self.piezas[4:]        # cuatro son más de las que nadie pide a la vez

    def prometer(self, que, pieza=None):
        """Anota algo que el bot acaba de decir que haría.

        Que el bot recuerde lo que prometió es la diferencia entre una
        conversación y una sucesión de mensajes. Cuando el cliente vuelve tres
        días después con «¿ya lo tienes?», esto es lo único que hace que la
        respuesta tenga sentido.
        """
        nombre = (pieza or {}).get("pieza") if pieza else None
        # Se compara por QUÉ y por QUÉ PIEZA, nunca por el turno: prometer lo
        # mismo dos veces es seguir debiendo una cosa, no dos.
        if any(p["que"] == que and p["pieza"] == nombre for p in self.promesas):
            return
        self.promesas.append({"que": que, "turno": self.turnos, "pieza": nombre})

    def promesa_viva(self):
        """La última promesa pendiente, o None."""
        return self.promesas[-1] if self.promesas else None

    def cumplir_promesas(self):
        """Se dan por cerradas: ya se le ha contestado a lo que esperaba."""
        self.promesas = []

    def registrar(self, mensaje):
        self.turnos += 1
        encontrada = detectar_matricula(mensaje)
        # Se anota si la acaba de dar EN ESTE turno. Cuando un cliente te manda el
        # dato que le has pedido y le contestas otra cosa, da por hecho que no le
        # has leído — y ese es el momento en el que se va.
        self.matricula_recien_dada = bool(encontrada and encontrada != self.matricula)
        if encontrada:
            self.matricula = encontrada
        return encontrada

    def variar(self, clave, opciones):
        """Devuelve una frase distinta cada vez que se pasa por el mismo sitio.

        No es adorno. Un bot que contesta 'Esa no la tengo ahora mismo' cuatro
        veces seguidas se delata en el segundo mensaje, y el cliente deja de leer.
        Rota en orden fijo (no al azar) para que las pruebas sean reproducibles.
        """
        n = self.veces_dicho.get(clave, 0)
        self.veces_dicho[clave] = n + 1
        # CICLA, no se queda en la última. Antes era `min(n, len-1)`, así que a
        # partir de la tercera vez repetía el último párrafo palabra por palabra
        # — y justo en las situaciones donde el cliente insiste, que son las que
        # más veces pasan por aquí: el que quiere que le manden sin pagar pasó
        # cuatro veces por la misma frase.
        return opciones[n % len(opciones)]


# ---------------------------------------------------------------------------
# EL REDACTOR
# ---------------------------------------------------------------------------

def _apertura(conv, reglas):
    """La primera línea. Solo aparece una vez por conversación."""
    if conv.presentado:
        return None
    conv.presentado = True
    if conv.conocido and conv.nombre:
        reglas.append(("cliente conocido", "saluda por su nombre y sin presentarse: "
                                           "ya sabe con quién habla"))
        return SALUDOS_CONOCIDO[conv.turnos % len(SALUDOS_CONOCIDO)].format(
            nombre=conv.nombre)
    reglas.append(("cliente nuevo", "se identifica como asistente en el primer "
                                    "mensaje, no finge ser una persona (rol §7)"))
    return PRESENTACION


def _describir_corto(meta):
    """El nombre de la pieza y su coche, sin motor, año ni estado.

    Para cuando ya se la ha descrito entera y volver a hacerlo sonaría a
    contestador: «el radiador del A4» en vez de los siete datos otra vez.
    """
    pieza = (meta.get("pieza") or "la pieza").lower()
    coche = f"{(meta.get('marca') or '').title()} {meta.get('modelo') or ''}".strip()
    return f"el {pieza} del {coche}" if coche else f"el {pieza}"


# Una línea que NO aporta un dato: saludo, empujón de venta, muletilla. Repetirla
# es lo que delata a un bot. Una línea con un hecho dentro —un precio, un plazo,
# una matrícula, una referencia— sí puede repetirse: si el cliente vuelve a
# preguntar cuánto vale, la respuesta correcta es el precio otra vez.
LLEVA_UN_DATO = re.compile(r"\d")


def _OTRA_MANERA_DE_DECIRLO(conv):
    """Qué decir cuando todo lo que tocaba decir ya se había dicho.

    Depende de dónde esté la conversación, porque «sigo en lo mismo» significa
    cosas distintas según lo que haya encima de la mesa.
    """
    if conv.regla_dura:
        return ["Lo dicho, en eso no me puedo mover.",
                "Sigo en lo mismo, y no es cosa mía.",
                "Es la condición de la casa, no la decido yo."]
    if conv.estado in (CERRADA, POSVENTA):
        return ["Todo sigue igual por aquí, tranquilo.",
                "Sin novedad todavía; en cuanto la haya te escribo.",
                "Sigue en marcha, no hace falta que hagas nada."]
    if conv.ultima_pieza:
        return ["Ahí sigue, cuando quieras.",
                "Sin prisa, me dices y seguimos.",
                "Aquí estoy para lo que necesites."]
    return ["Dime y lo miro.",
            "Cuéntame y te digo.",
            "Tú dirás."]


def _sin_repetir(lineas, conv, reglas):
    """Quita lo que ya se había dicho igual. Es la red, no el plan.

    El plan es `variar()`: quien escribe una frase le pone alternativas. El
    problema de un plan así es que depende de acordarse, y en cinco
    conversaciones largas aparecieron dieciséis líneas repetidas — todas de
    frases que nadie había pensado en variar.

    Esto lo comprueba al final, para todas, venga la línea de donde venga. Si el
    mensaje entero ya se dijo, o si una línea de relleno ya se dijo, se cae.
    Nunca se queda vacío: si no sobrevive ninguna, se deja la primera.
    """
    if not lineas:
        return lineas
    if not hasattr(conv, "lineas_dichas"):
        conv.lineas_dichas = set()

    limpias, quitadas = [], 0
    for l in lineas:
        clave = " ".join(l.lower().split())
        if clave not in conv.lineas_dichas or LLEVA_UN_DATO.search(l):
            limpias.append(l)
            continue

        # Hay una línea que NO se puede quitar aunque se repita: la que pide el
        # dato que identifica el coche. La regla de la identificación exige que
        # todo mensaje que no ofrece la pieza pida matrícula, referencia o VIN, y
        # quitarla dejaba la conversación sin siguiente paso — se vio en el banco,
        # dos veces en la misma conversación larga.
        #
        # Así que se pide otra vez, pero de otra manera. Que es lo que haría una
        # persona: no callarse, y no repetir la misma frase.
        if PIDE_IDENTIFICADOR.search(l):
            limpias.append(conv.variar("pedir_identificador", [
                "Pásame la matrícula y te lo confirmo.",
                "Con la matrícula te digo cuál es exactamente.",
                "Dime la matrícula (o la referencia de la vieja) y lo miro.",
                "Si me pasas el bastidor o la matrícula, te lo clavo.",
            ]))
            quitadas += 1
            continue

        quitadas += 1

    if not limpias:
        # TODO lo que iba a decir ya lo había dicho. Repetirlo es lo peor que
        # puede hacer y callarse tampoco vale, así que se dice otra cosa: que
        # sigue en lo mismo. Es lo que haría una persona a la que le insisten.
        #
        # Sale sobre todo con las reglas duras. El cliente que quiere que le
        # manden sin pagar lo intenta cuatro veces con cuatro argumentos
        # distintos, y las cuatro veces la respuesta correcta es la misma
        # condición — pero no las mismas palabras.
        limpias = [conv.variar("en_vez_de_repetir", _OTRA_MANERA_DE_DECIRLO(conv))]
        quitadas = len(lineas)

    if quitadas:
        reglas.append(("no repite lo ya dicho",
                       f"{quitadas} línea(s) que ya se habían dicho igual en esta "
                       f"conversación: se quitan en vez de soltarlas otra vez"))

    for l in limpias:
        conv.lineas_dichas.add(" ".join(l.lower().split()))
    return limpias


def _con_pieza(consulta, conv, reglas, salida):
    """Hay una ficha del catálogo por encima del umbral.

    `salida` es el diccionario de la respuesta: aquí se anota el precio SI se ha
    llegado a decir. Es el dato que la prueba mira para comprobar que el redactor
    nunca publica un importe que el buscador no autorizó.
    """
    piezas = [r for r in (consulta.get("resultados") or [])
              if r.get("tipo") == "inventario"]
    ficha = piezas[0]
    meta = ficha.get("meta") or {}
    precio = ficha.get("precio_cliente") or {}
    g = _genero(meta.get("pieza", ""))
    conv.ultima_pieza = meta

    lineas = []

    # REGLA DURA (coche desconocido): si la marca/modelo de la ficha no está en lo
    # que el cliente ha dicho, NO se nombra la ficha ni se da precio. Tener la
    # matrícula no dice qué coche es (el sistema no la resuelve). Se pide el coche.
    if precio.get("estado") == "sin_coche":
        conv.ultima_pieza = None      # no es su coche: no se recuerda ni se cierra
        pieza = (meta.get("pieza") or "la pieza").lower()
        conv.piezas = [p for p in conv.piezas
                       if str((p or {}).get("id") or "") != str(meta.get("id") or "")]
        if conv.matricula:
            lineas.append(f"De {pieza} tengo, pero necesito confirmar el coche.")
            lineas.append(f"La matrícula ({conv.matricula}) la revisa una persona; "
                          f"dime marca y modelo y te digo cuál te vale y el precio.")
        else:
            lineas.append(f"De {pieza} tengo, pero depende del coche.")
            lineas.append("Dime marca y modelo (o pásame la matrícula) y te confirmo "
                          "cuál monta el tuyo y lo que cuesta.")
        reglas.append(("no le inventa el coche",
                       "la marca/modelo de la ficha no está en lo que ha dicho el "
                       "cliente: nombrarla sería adivinarle el coche (regla dura)"))
        reglas.append(("precio retenido", precio.get("motivo", "")))
        return lineas

    # LA MATRÍCULA ES EL PRIMER PASO. Sin ella no se ofrece una ficha concreta ni
    # se dice su precio: ofrecer «el alternador de un A4 2.0 TFSI del 2019» a
    # alguien que solo ha dicho «un alternador para un A4» es afirmar que encaja,
    # y eso no se sabe. En la primera prueba con el chat el cliente lo dijo él
    # solo, al turno siguiente: «¿cómo sé si es el mío?».
    #
    # Lo que se dice en su lugar no es un «no»: es cuántas hay y por qué hace
    # falta el dato. Sale del catálogo, así que es verdad y además vende — un
    # cliente que oye «de alternador para A4 tengo tres según motor y año» sabe
    # que hay stock y entiende para qué le piden la matrícula.
    if precio.get("estado") == "sin_matricula":
        conv.ultima_pieza = meta
        n = ficha.get("variantes") or 1
        pieza = (meta.get("pieza") or "la pieza").lower()
        coche = f"{(meta.get('marca') or '').title()} {meta.get('modelo') or ''}".strip()

        # NI SIQUIERA SABEMOS DE QUÉ COCHE HABLA. Si el cliente solo ha dicho
        # «necesito un alternador», la búsqueda devuelve el alternador que mejor
        # puntúe —de un Passat, pongamos— y nombrarlo sería inventarle un coche
        # que él no ha mencionado.
        #
        # Es la misma regla de la identificación un paso antes: allí no sabíamos
        # cuál de las quince fichas era la suya; aquí no sabemos ni la marca. Se
        # vio en una conversación real: «necesito un alternador» / «de alternador
        # para un Volkswagen Passat tengo 6 referencias distintas».
        if not conv.vehiculo:
            # Y NO se guarda en el hilo. La ficha que ha salido es la que más
            # puntúa entre todos los alternadores del catálogo, no la suya:
            # recordarla haría que volviera sola tres turnos después, cuando el
            # cliente ya ha dicho que su coche es otro. Pasó en la primera
            # conversación larga — se ofrecía un Passat a alguien con un A4.
            conv.piezas = [p for p in conv.piezas
                           if str((p or {}).get("id") or "") != str(meta.get("id") or "")]
            lineas.append(f"De {pieza} tengo, pero depende del coche.")
            lineas.append("Pásame la matrícula y te digo cuál monta el tuyo y lo "
                          "que vale.")
            reglas.append(("no le inventa el coche",
                           "el cliente no ha dicho de qué vehículo es: nombrar el "
                           "de la ficha que más puntúa sería adivinárselo"))
            reglas.append(("precio retenido", precio.get("motivo", "")))
            return lineas

        if n > 1:
            lineas.append(f"De {pieza} para un {coche} tengo {n} referencias "
                          f"distintas, según el motor y el año.")
        else:
            lineas.append(f"De {pieza} para un {coche} tengo una, pero tiene que "
                          f"cuadrarte el motor y el año.")
        lineas.append(f"Pásame la matrícula y te digo cuál es "
                      f"{'la tuya' if g == 'f' else 'el tuyo'} y lo que vale.")
        reglas.append(("la matrícula va primero",
                       "sin identificar el coche no se sabe si la pieza encaja: no "
                       "se ofrece una ficha concreta ni su precio (regla del negocio)"))
        reglas.append(("precio retenido", precio.get("motivo", "")))
        return lineas

    estado = _estado(meta)
    # Si acaba de dar la matrícula, se le acusa recibo EN LA MISMA LÍNEA. Que un
    # cliente mande el dato que le has pedido y le contestes como si no lo hubieras
    # visto es el momento en el que se va. Va pegado y no en una línea aparte
    # porque el mensaje son tres líneas como mucho, y la que se perdería es la que
    # empuja la venta.
    ident = str(meta.get("id") or "")
    ya_descrita = ident and ident in conv.descritas
    conv.descritas.add(ident)

    if conv.matricula_recien_dada:
        lineas.append(f"Con la matrícula te lo confirmo: tengo {_describir(meta)}"
                      + (f", {estado}." if estado else "."))
        reglas.append(("acusa recibo del dato",
                       "ha dado la matrícula en este mismo turno: se le reconoce "
                       "antes de nada"))
    elif ya_descrita:
        # YA SE LA HABÍA DESCRITO. Repetir la ficha entera —marca, modelo, motor,
        # año, estado— es lo que más delata a un bot: una persona diría «el faro
        # ese» y seguiría. Se la nombra corta y se va a lo que ha preguntado.
        corto = _describir_corto(meta)
        lineas.append(f"{corto[:1].upper()}{corto[1:]}, el que te decía.")
        reglas.append(("no repite la ficha",
                       "ya se la había descrito en esta conversación: se nombra "
                       "corta en vez de soltar los datos otra vez"))
    else:
        lineas.append(f"Tengo {_describir(meta)}" + (f", {estado}." if estado else "."))
    reglas.append(("pieza localizada",
                   f"la ficha ID {meta.get('id', '?')} supera el umbral de confianza"))

    if not conv.garantia_dicha:
        lineas[-1] += " " + GARANTIA
        conv.garantia_dicha = True
        reglas.append(("garantía como venta",
                       "la menciona sin que se la pidan, una sola vez por conversación"))

    if precio.get("publicable"):
        # El importe viene del buscador. Aquí no hay ningún catálogo del que sacarlo.
        conv.ultimo_precio = salida["precio_dado"] = precio["importe"]
        conv.precio_de[str(meta.get("id") or "")] = precio["importe"]
        # Hay pieza y precio encima de la mesa: la venta cambia de punto, y a
        # partir de aquí un «vale» del cliente es un sí y no un acuse.
        conv.estado = OFRECIENDO
        lineas.append(f"Son {precio['importe']} y {_plazo(meta, g)}.")
        # La llamada al cierre, distinta cada vez. Cuatro «¿te lo aparto?»
        # seguidos en el mismo chat es lo que hace que el cliente deje de leer:
        # el contenido es correcto y el efecto es de contestador automático.
        lineas.append(conv.variar("cierre_pregunta", [
            f"¿Te {_pron(g)} aparto?",
            f"¿{_pron(g).capitalize()} preparo?",
            "¿Sigo con ello?",
            "¿Lo dejamos apartado?",
        ]))
        conv.esperando_si = True
        reglas.append(("precio publicado",
                       f"{precio['motivo']}. Se dice tal cual, sin redondear"))
    elif conv.precio_de.get(ident):
        # A ESTA PIEZA YA SE LE PUSO PRECIO EN ESTA CONVERSACIÓN. La búsqueda de
        # este turno lo retiene porque el cliente ya no la nombra entera —dice «el
        # que te dije antes»— pero el importe ya salió y era el suyo. Callárselo
        # ahora sería contestar «te lo confirmo» de algo que él ya tiene escrito
        # más arriba en el chat.
        #
        # No es publicar un precio nuevo: es repetir uno autorizado, que es lo
        # mismo que ya hacía la comprobación en caliente del panel.
        conv.ultimo_precio = salida["precio_dado"] = conv.precio_de[ident]
        lineas.append(f"Son {conv.precio_de[ident]}, {_plazo(meta, g)}.")
        lineas.append(conv.variar("cierre_pregunta", [
            f"¿Te {_pron(g)} aparto?",
            f"¿{_pron(g).capitalize()} preparo?",
            "¿Sigo con ello?",
            "¿Lo dejamos apartado?",
        ]))
        conv.esperando_si = True
        reglas.append(("repite el precio ya dado",
                       "es el mismo importe que ya se le dio para esta ficha en "
                       "esta conversación, no uno nuevo"))

    elif precio.get("estado") == "sin_confirmar":
        lineas.append("Dime exactamente cuál montas y te paso el precio, que no "
                      "quiero pasarte el de otra.")
        reglas.append(("precio retenido", precio.get("motivo", "")))
    else:
        # "el precio" es masculino pase lo que pase con la pieza: aquí no se conjuga.
        lineas.append("El precio te lo confirmo enseguida, que lo tiene que mirar "
                      "Álvaro.")
        reglas.append(("precio retenido", precio.get("motivo", "sin precio publicado")))
    return lineas


def _sin_pieza(conv, reglas):
    """Sin matrícula NO se dice 'no la tengo': no se puede saber. Regla de negocio:
    primero se identifica la pieza con la matrícula; solo con ella se afirma que
    no la hay."""
    # CASO 1: ya tenemos la matrícula -> la pieza está identificada y aun así no
    # aparece. Ahí sí es legítimo decir que no la tenemos y ofrecer buscarla.
    if conv.matricula:
        lineas = [conv.variar("sin_pieza", [
            "Esa no la tengo puesta ahora mismo.",
            "Esa no me consta en el almacén.",
        ])]
        reglas.append(("no se ofrece una parecida",
                       "ninguna ficha supera el umbral: antes que colar una pieza "
                       "hermana, se dice que no"))
        lineas.append(f"Con la matrícula que me pasaste ({conv.matricula}) te la "
                      f"busco; si la localizo, en 24-48 h la tienes.")
        reglas.append(("memoria de conversación",
                       f"ya dio la matrícula ({conv.matricula}): no se le vuelve a pedir"))
        lineas.append("¿Te la busco?")
        return lineas

    # CASO 2: NO hay matrícula -> NO se afirma que no la haya. Sin identificar la
    # pieza exacta no se puede saber. SIEMPRE se pide la matrícula primero.
    if "matricula" in conv.datos_pedidos:
        # Ya se la pedí y no la ha dado. No se repite la misma frase (delata al bot):
        # se insiste de otra forma y se ofrece la alternativa de la referencia vieja.
        lineas = ["Para saber si la tengo necesito identificarla, y sin la matrícula "
                  "voy a ciegas. Si la tienes a mano me la pasas, o si no la "
                  "referencia de la pieza vieja."]
        reglas.append(("identificar antes de decir que sí o que no",
                       "sin matrícula no se afirma disponibilidad: primero se "
                       "identifica la pieza (rol §7)"))
        reglas.append(("no repite la misma frase",
                       "es la segunda vez que hace falta el mismo dato: se insiste "
                       "de otra forma y se ofrece una alternativa"))
        return lineas

    lineas = ["Para decirte si la tengo necesito la matrícula: con eso identifico la "
              "pieza exacta que monta tu coche y no te mando la que no es."]
    conv.datos_pedidos.add("matricula")
    reglas.append(("identificar antes de decir que sí o que no",
                   "sin matrícula no se puede saber si la hay: se pide la matrícula "
                   "primero (política CÓMO IDENTIFICAR LA PIEZA / rol §7)"))
    reglas.append(("un dato por mensaje",
                   "se pide la matrícula y ningún otro dato (rol §8.3)"))
    return lineas


SEGUIMIENTO = ("estado", "kilometros", "precio otra vez", "compatibilidad",
               "alternativa")


def _seguimiento(intencion, conv, reglas, salida):
    """Contesta sobre la pieza que ya está sobre la mesa, sin volver a buscar."""
    meta = conv.ultima_pieza
    g = _genero(meta.get("pieza", ""))
    nombre = meta.get("pieza", "la pieza").lower()

    if intencion == "kilometros":
        # El catálogo no guarda kilometraje. Decirlo es mejor que contestar otra
        # cosa: el cliente ha preguntado algo concreto y se da cuenta de la esquiva.
        reglas.append(("dice lo que NO sabe",
                       "el kilometraje no está en la ficha: no se inventa ni se "
                       "responde con otro dato"))
        return conv.variar("km", [
            [f"El kilometraje exacto no lo tengo apuntado en la ficha.",
             f"Si te hace falta el dato, lo miro en el coche y te digo."],
            ["Eso tendría que mirarlo físicamente, no me consta en el sistema.",
             "¿Te lo compruebo?"],
        ])

    if intencion == "estado":
        estado = _estado(meta) or "en buen estado"
        lineas = [conv.variar("estado", [
            f"{_art(g).capitalize()} {nombre} está {estado}.",
            f"Sí, {_art(g)} {nombre} está {estado}, sin sorpresas.",
            f"Te lo confirmo: {estado}.",
        ])]
        if "desmontad" in estado:
            lineas[-1] += " Sale de un coche que entró hace poco y va de 10."
        if not conv.garantia_dicha:
            lineas.append(GARANTIA)
            conv.garantia_dicha = True
        reglas.append(("responde con la ficha que ya tenía",
                       f"pregunta por el estado sin nombrar la pieza: contesta por "
                       f"{nombre}, la ficha ID {meta.get('id', '?')}"))
        return lineas

    if intencion == "precio otra vez":
        if conv.ultimo_precio:
            # Repetir un precio que la búsqueda YA autorizó no es publicar uno nuevo.
            salida["precio_dado"] = conv.ultimo_precio
            reglas.append(("repite el precio ya dado",
                           "el mismo importe de la misma ficha, no uno nuevo"))
            return [f"Son {conv.ultimo_precio}, {_plazo(meta, g)}.",
                    f"¿Te {_pron(g)} aparto?"]
        reglas.append(("precio retenido",
                       "esa ficha no tiene precio publicado: lo confirma Álvaro"))
        return ["El precio te lo confirmo enseguida, que lo tiene que mirar Álvaro.",
                "En cuanto lo tenga te digo algo."]

    if intencion == "compatibilidad":
        # Regla del rol §7: el bot acerca la pieza, la compatibilidad la firma una
        # persona. Aquí no se promete que encaje, se explica cómo asegurarlo.
        reglas.append(("no asegura la compatibilidad",
                       "el bot acerca la pieza; que encaje lo confirma una persona "
                       "con la matrícula (rol §7)"))
        if conv.matricula:
            return conv.variar("compat", [
                [f"Con la matrícula que me diste ({conv.matricula}) lo miro y te lo "
                 f"confirmo antes de mandar nada.", "Así no te la juegas."],
                ["Ya te digo que lo compruebo yo antes de que salga de aquí.",
                 "Si no encaja, no te lo mando."],
            ])
        conv.datos_pedidos.add("matricula")
        return conv.variar("compat", [
            ["Para no fallar necesito la matrícula: con eso te clavo la que monta "
             "exacto.", "Si tienes la referencia de la vieja, mejor todavía."],
            ["Te entiendo, por eso no te digo que sí a ciegas.",
             "Con la matrícula en la mano te lo confirmo yo antes de mandarlo."],
            ["Lo comprobamos antes de que salga, no te preocupes por eso.",
             "En cuanto tengas la matrícula lo cierro."],
        ])

    # alternativa
    reglas.append(("ofrece buscar otra",
                   "el cliente descarta la que se le ha ofrecido: no se insiste, "
                   "se pide el dato que permite acertar"))
    return [conv.variar("alternativa", [
        f"¿Cuál necesitas entonces? Dime el lado o la referencia de la vieja y "
        f"te digo si {_pron(g)} tengo.",
        "Pásame la referencia de la que llevas montada y te busco la que encaja.",
        "Con la matrícula te digo exactamente cuáles te valen.",
    ])]


def _faq_aprendida(consulta):
    """La primera política encontrada, si resulta que la escribió una persona."""
    for r in (consulta.get("resultados") or []):
        if r.get("tipo") == "politica":
            meta = r.get("meta") or {}
            if meta.get("aprendida") and meta.get("respuesta"):
                return meta
            return None
    return None


def _politica(consulta, conv, reglas):
    politicas = [r for r in (consulta.get("resultados") or [])
                 if r.get("tipo") == "politica"]
    if not politicas:
        return None
    meta = politicas[0].get("meta") or {}
    seccion = (meta.get("seccion")
               or politicas[0]["texto"].split(".")[0]).strip().upper()

    # Las FAQ que ha contestado una persona se dicen TAL CUAL. No se resumen ni se
    # reformulan: si Álvaro escribió la condición con esas palabras, esas son las
    # palabras. Reescribirlas sería el bot decidiendo, que es justo lo que no hace.
    if meta.get("aprendida") and meta.get("respuesta"):
        reglas.append(("respuesta escrita por una persona",
                       f"la contestó {meta.get('seccion', 'alguien del equipo')} y "
                       f"se dice literal, sin reformular"))
        return [meta["respuesta"]]

    texto = POLITICAS.get(seccion)
    if not texto:
        return None

    # Se anota qué condición se le ha explicado. Sirve para dos cosas: no
    # repetírsela (eso ya lo hacía `veces_dicho`) y, sobre todo, para que el
    # resumen que ve el modelo lo sepa — él no se acuerda de nada.
    conv.temas_tratados.add(seccion)

    # Si ya se ha contestado esa misma política en esta conversación, no se vuelve
    # a soltar el párrafo entero. Repetir la condición palabra por palabra suena a
    # contestador; lo que toca es empujar hacia el siguiente paso.
    if conv.veces_dicho.get(f"pol-{seccion}"):
        reglas.append(("no repite la política",
                       f"«{seccion}» ya se explicó en esta conversación: se avanza "
                       f"en vez de repetirla"))
        return conv.variar(f"pol2-{seccion}", [
            ["Como te decía, en eso no hay problema.",
             "¿Seguimos con la pieza?"],
            ["Eso lo tienes cubierto.",
             "Dime qué necesitas y lo cerramos."],
        ])

    conv.veces_dicho[f"pol-{seccion}"] = 1
    reglas.append(("responde con la política de la empresa",
                   f"sección «{seccion}» del documento de condiciones"))
    return [texto]


def redactar(consulta: dict, conversacion: Conversacion) -> dict:
    """Convierte el resultado de la búsqueda en un mensaje de WhatsApp.

    `consulta` es lo que devuelve el buscador a través del panel: decision,
    resultados (cada uno con su precio_cliente ya decidido) y el porqué. Aquí NO se
    vuelve a mirar el catálogo: lo que no venga en `consulta` no existe.

    Devuelve el mensaje y la traza de por qué se ha escrito así, para que el panel
    la enseñe al lado y Álvaro sepa qué regla se ha aplicado en cada frase.
    """
    lineas, reglas = [], []
    mensaje_cliente = consulta.get("pregunta", "")
    intencion = detectar_intencion(mensaje_cliente)

    # UN «SÍ» ES UNA VENTA, pero solo si el bot acaba de preguntar. «Sí» no
    # significa nada por sí solo: significa que sí a lo último que se preguntó, y
    # en «si no me vale la puedo devolver» ni siquiera es un sí.
    #
    # Por eso no basta con meter «si» en la lista de cierre y hay que mirarlo
    # aquí, con el hilo de la conversación delante. Salió de verlo fallar en el
    # peor turno posible: «¿Te lo aparto?» / «Sí, ¿me lo puedes enviar?» y el bot
    # contestando «sin prisa, lo dejo apuntado por si acaso».
    # Y solo cuando el mensaje no dice otra cosa más clara. «Vale, déjame que lo
    # mire con el cliente» empieza por «vale» y NO es un sí: es lo contrario. Una
    # intención explícita —aparcar, regatear, quejarse, pedir sin pagar— manda
    # siempre sobre una afirmación suelta, porque la afirmación es lo que se lee
    # cuando no hay nada mejor que leer.
    SIN_INTENCION_PROPIA = ("consulta", "saludo", "agradecimiento", "prisa")

    # Y tampoco cuando el mismo mensaje pide OTRA pieza. «Vale, y también el
    # radiador» empieza por «vale» y no está cerrando nada: está añadiendo una
    # pieza al pedido. Se nota en que la búsqueda ha encontrado una ficha distinta
    # de la que había encima de la mesa.
    _piezas = [r for r in (consulta.get("resultados") or [])
               if r.get("tipo") == "inventario"]
    _otra_pieza = bool(_piezas) and conversacion.ultima_pieza is not None and (
        str((_piezas[0].get("meta") or {}).get("id") or "")
        != str((conversacion.ultima_pieza or {}).get("id") or ""))

    if (intencion in SIN_INTENCION_PROPIA
            and not _otra_pieza
            and dice_que_si(conversacion, mensaje_cliente)
            and conversacion.ultima_pieza):
        intencion = "cierre"
        reglas.append(("responde que sí a lo que se le preguntó",
                       "el bot había preguntado si lo apartaba y el cliente dice "
                       "que sí: eso es un cierre, no una consulta nueva"))

    # La pregunta ya está contestada, sea lo que sea lo que haya respondido.
    conversacion.esperando_si = False

    escala = False
    salida = {"precio_dado": None}

    apertura = _apertura(conversacion, reglas)
    if apertura:
        lineas.append(apertura)

    decision = consulta.get("decision")
    hay_pieza = any(r.get("tipo") == "inventario"
                    for r in (consulta.get("resultados") or []))

    # ------------------------------------------------------------ escalado
    # Si ya está en manos de Álvaro, el bot no vuelve a meterse por el medio.
    # Sin esto, el mensaje siguiente a una queja recibía un alegre "¿qué pieza
    # necesitas?" que es justo lo que enfada a un cliente enfadado.
    # Las reglas duras se saltan este atajo a propósito: si el cliente insiste en
    # que le mandes la pieza sin pagar, la respuesta correcta es repetirle la
    # condición, no un "ya se lo he pasado a Álvaro" que suena a que cede.
    if (conversacion.escalado
            and intencion not in ("cierre", "consulta", "pide sin pagar",
                                  "justificante")):
        escala = True
        lineas.append("Ya se lo he pasado a Álvaro, te contesta él en cuanto lo vea.")
        reglas.append(("sigue escalado",
                       "la conversación ya está con una persona: el bot no se "
                       "vuelve a poner por delante"))

    # ------------------------------------------------------- reglas duras
    # Ninguna de las dos las decide el bot. Repite la condición, no la discute, y
    # avisa a una persona. Si el cliente insiste, la condición no cambia — por eso
    # las frases están escritas para poder repetirse sin sonar a disco rayado.
    elif intencion == "pide sin pagar":
        escala = True
        conversacion.escalado = True
        conversacion.regla_dura = "pide sin pagar"
        lineas += conversacion.variar("sin_pagar", [
            ["La pieza sale cuando el pago está confirmado, eso no lo puedo saltar yo.",
             "Puedes pagar con tarjeta, transferencia, Bizum, Google Pay o Apple Pay, "
             "lo que te venga mejor."],
            ["En eso no me puedo mover, es condición de la casa y no depende de mí.",
             "Le paso tu mensaje a Álvaro por si él lo ve de otra forma."],
        ])
        reglas.append(("condición de la empresa, no criterio del bot",
                       "no se envía sin pago confirmado (política PAGO ANTES DEL "
                       "ENVIO). El bot la repite y no la negocia"))
        reglas.append(("escalado a persona",
                       "insiste en una condición que el bot no puede levantar"))

    elif intencion == "justificante":
        escala = True
        conversacion.escalado = True
        conversacion.regla_dura = "justificante"
        lineas.append("Gracias, se lo paso a Álvaro para que compruebe el ingreso.")
        lineas.append("En cuanto lo vea en la cuenta te aviso y sale la pieza.")
        reglas.append(("el bot NO valida justificantes",
                       "un resguardo no es un pago: la única confirmación válida es "
                       "ver el ingreso, y eso lo mira una persona (política "
                       "JUSTIFICANTES DE PAGO)"))
        reglas.append(("escalado a persona",
                       "la decisión tiene consecuencia económica real"))

    # ---------------------------------------------------------------- queja
    elif intencion == "queja":
        escala = True
        conversacion.escalado = True
        lineas.append("Vaya, siento el problema. Esto lo lleva Álvaro directamente, "
                      "le paso ahora mismo tu mensaje.")
        lineas.append("Si tienes la factura a mano, mándamela y le ahorramos un paso.")
        reglas.append(("escalado a persona",
                       "hay una queja: el bot no gestiona reclamaciones (rol §7)"))

    # --------------------------------------------------------------- cierre
    # ------------------------------------- ha dicho dónde quiere la pieza
    elif (conversacion.estado in (CERRADA, POSVENTA)
          and DIRECCION.search(mensaje_cliente or "")):
        # Después de cerrar, un mensaje con una calle y un número es la dirección
        # de entrega, no una consulta nueva. Sin esto se buscaba «calle mayor 3»
        # en el catálogo de piezas, no se encontraba nada, y el cliente recibía un
        # «dime qué necesitas» justo después de haber comprado.
        conversacion.estado = POSVENTA
        lineas.append("Apuntado, se lo paso a Álvaro para que lo prepare.")
        lineas.append("En cuanto salga te aviso con el seguimiento.")
        reglas.append(("toma la dirección de entrega",
                       "la venta está cerrada y el mensaje trae una dirección: es "
                       "dónde quiere la pieza, no una consulta"))

    # --------------------------------------- le devuelve un dato que él dio
    elif intencion == "recuerda mi dato":
        if conversacion.matricula:
            lineas.append(f"Me pasaste la {conversacion.matricula}.")
            pieza = conversacion.ultima_pieza
            # Sin repetir el coche: acaba de decirlo él y ya está en la matrícula.
            if pieza:
                nombre = (pieza.get("pieza") or "").lower()
                art = "la" if _genero(pieza.get("pieza", "")) == "f" else "el"
                lineas.append(f"¿Seguimos con {art} {nombre}?")
            else:
                lineas.append("¿Seguimos con lo tuyo?")
            reglas.append(("le devuelve un dato suyo",
                           "pide el dato que él mismo dio: se le dice, que está en "
                           "la memoria de la conversación"))
        else:
            lineas.append("Todavía no me has pasado ninguna.")
            lineas.append("Mándamela y te digo qué pieza monta tu coche.")
            reglas.append(("no consta ese dato",
                           "no se inventa una matrícula que nadie dio"))

    # ------------------------------------------------- el cliente lo aparca
    elif intencion == "aparca":
        # NO se le empuja y NO se le vuelve a pedir nada. Ha dicho que sigue
        # interesado y que vuelve; el error caro aquí es contestarle con la
        # matrícula, porque le dice que no le has leído justo cuando te estaba
        # diciendo que sí.
        #
        # Lo que se dice depende de dónde está la venta, y por eso hace falta el
        # estado: con un precio encima de la mesa se le sujeta la pieza (eso es
        # lo que hace que vuelva); sin nada, solo se queda a la espera.
        conversacion.estado = APARCADA
        pieza = conversacion.ultima_pieza
        if pieza and conversacion.ultimo_precio:
            g = _genero(pieza.get("pieza", ""))
            lineas += conversacion.variar("aparca_con_pieza", [
                [f"Sin prisa. {_pron(g).capitalize()} dejo apuntad{'a' if g == 'f' else 'o'} "
                 f"a tu nombre y aquí sigue.",
                 "Cuando lo tengas claro me dices y lo cerramos."],
                ["Tú tranquilo, no se mueve de aquí.",
                 "Me escribes cuando quieras y seguimos."],
            ])
            conversacion.prometer("guardarle la pieza hasta que conteste", pieza)
            reglas.append(("el cliente aparca la conversación",
                           "no es una pregunta: dice que lo mira y vuelve. Se le "
                           "sujeta la pieza en vez de volver a pedirle datos"))
        else:
            lineas += conversacion.variar("aparca_sin_pieza", [
                ["Sin problema, aquí estoy cuando lo tengas.",
                 "Con la matrícula te lo miro en un momento."],
                ["Cuando quieras me dices y lo vemos.",
                 "No corre prisa."],
            ])
            conversacion.prometer("quedar a la espera de su respuesta")
            reglas.append(("el cliente aparca la conversación",
                           "aún no hay pieza concreta: se queda a la espera sin "
                           "insistir"))

    # ------------------------------------- pregunta por algo ya en marcha
    elif intencion == "seguimiento":
        # Solo se puede contestar bien si el bot recuerda lo que prometió. Si no
        # hay nada pendiente, se pregunta por qué en vez de inventarse un pedido.
        pendiente = conversacion.promesa_viva()
        if conversacion.estado == CERRADA or conversacion.escalado:
            conversacion.estado = POSVENTA
        if pendiente:
            que = pendiente.get("pieza")
            suyo = "tu " + que.lower() if que else "lo tuyo"
            if conversacion.estado == POSVENTA:
                # Ya ha comprado. Preguntar por su pedido no es lo mismo que
                # preguntar por un presupuesto, y contestarle lo mismo suena a que
                # no te has enterado de que te ha pagado.
                lineas.append(f"{suyo.capitalize()} está apartado a tu nombre "
                              f"y en preparación.")
                lineas.append("En cuanto salga te paso el aviso.")
            else:
                lineas.append(f"Sigo con lo de {suyo}, no se me ha olvidado.")
                lineas.append("En cuanto Álvaro me lo confirme te escribo yo.")
            # No se vuelve a prometer: ya estaba pendiente. Anotarla otra vez
            # la duplicaba en el resumen y hacía parecer que se le debían dos
            # cosas cuando solo se le debe una.
            reglas.append(("recuerda lo que prometió",
                           f"quedó pendiente «{pendiente['que']}»: se le contesta "
                           f"por eso y no se le pide nada otra vez"))
        else:
            lineas.append("Dime de qué pieza me hablas y te digo cómo va.")
            lineas.append("Con la matrícula o el número de pedido lo veo enseguida.")
            reglas.append(("pregunta por algo que no consta",
                           "no hay nada pendiente en esta conversación: se pregunta "
                           "cuál en vez de dar por hecho un pedido"))

    elif _faq_aprendida(consulta) and not (intencion == "cierre"
                                           and conversacion.ultima_pieza):
        # Lo que escribió una persona para ESTA pregunta gana a lo que decidiría
        # el bot. Para eso se escribió: si la respuesta está en la base y el bot
        # contesta otra cosa, el ciclo de aprender no sirve de nada.
        #
        # Va aquí y no más arriba a propósito. Por encima quedan las reglas duras
        # y las quejas: una FAQ no puede ablandar una condición de la empresa ni
        # quedarse una reclamación que tiene que ver una persona. Y por encima
        # queda también cerrar una venta que ya tiene una pieza concreta encima
        # de la mesa, que es el objetivo de todo esto. Medido: «me lo llevo,
        # mándamelo al taller» contestaba lo del taller y se dejaba el cierre.
        #
        # Salió de un fallo real: Álvaro contestó «¿me lo apartas?» y el cliente
        # seguía oyendo «claro, ¿cuál te aparto?». La búsqueda la encontraba la
        # primera; la intención «cierre» miraba antes y la pisaba.
        lineas += _politica(consulta, conversacion, reglas) or []

    elif (intencion == "cierre" and not conversacion.ultima_pieza
          and not conversacion.regla_dura):
        # GUARDARRAÍL: si hay una regla dura viva (pago sin confirmar), NO entra
        # aquí — lo coge más abajo la rama que mantiene la condición. Si no,
        # quiere cerrar pero no se ha hablado de ninguna pieza concreta (p.ej.
        # "me lo quedo" de entrada). En vez de gastar a una persona, el bot pide
        # cuál: mantiene la venta viva y la resuelve él si el cliente responde.
        lineas.append("Claro, ¿cuál te aparto?")
        lineas.append("Pásame la pieza o la matrícula y te lo confirmo.")
        reglas.append(("cierre sin pieza identificada",
                       "el cliente quiere cerrar pero aún no hay una pieza concreta "
                       "sobre la mesa: se pregunta cuál en vez de escalar"))

    elif intencion == "cierre" and conversacion.ultima_pieza:
        meta = conversacion.ultima_pieza
        g = _genero(meta.get("pieza", ""))
        # ¿Ya estaba cerrada? Un cliente que confirma dos veces —«vale» y luego
        # «sí, me lo quedo»— recibía el mismo mensaje copiado, que es la señal más
        # clara de que está hablando con una máquina. La venta ya está hecha: lo
        # que toca es reconocerlo, no volver a hacerla.
        ya_estaba = conversacion.estado in (CERRADA, POSVENTA)
        conversacion.estado = CERRADA
        # Las promesas de antes de la venta ya no valen —«te lo guardo mientras lo
        # piensas» se acabó—, pero cerrar no es acabar: ahora lo pendiente es
        # prepararlo y avisarle. Sin esta línea, un «¿ya lo tienes?» del cliente
        # que acaba de comprar recibía un «dime de qué pieza me hablas».
        conversacion.cumplir_promesas()
        conversacion.prometer("prepararle la pieza y avisarle cuando salga", meta)
        if ya_estaba:
            lineas.append(f"Sí, {_pron(g)} tengo apartad{'a' if g == 'f' else 'o'} "
                          f"a tu nombre desde antes.")
            lineas.append("Dime dónde la quieres y la preparo."
                          if g == "f" else "Dime dónde lo quieres y lo preparo.")
            reglas.append(("la venta ya estaba cerrada",
                           "vuelve a confirmar algo que ya estaba hecho: se le "
                           "reconoce en vez de repetirle el mismo mensaje"))
        elif PIDE_ENVIO.search(mensaje_cliente or ""):
            # Si en el mismo mensaje ya ha dicho que se lo mandes, preguntarle «¿te
            # lo mando o te pasas tú?» es no haberle leído. Se le confirma el envío
            # y se le pide lo único que falta de verdad: dónde.
            lineas.append(f"Hecho, {_pron(g)} aparto a tu nombre.")
            lineas.append("Te lo preparo para envío, ¿a qué dirección te lo mando?")
            reglas.append(("ya ha dicho cómo lo quiere",
                           "pide el envío en el mismo mensaje: no se le vuelve a "
                           "preguntar, se le pide la dirección"))
        else:
            lineas.append(f"Hecho, {_pron(g)} aparto a tu nombre.")
            lineas.append(f"¿Te {_pron(g)} mandamos al taller o te pasas tú a por "
                          f"{'ella' if g == 'f' else 'él'}?")
        reglas.append(("cierre de venta",
                       "el cliente acepta: se reserva y se ofrece la entrega, que es "
                       "el siguiente paso real (así lo escribe Álvaro)"))

    # -------------------------------------------------------------- regateo
    elif intencion == "regateo":
        escala = True
        g = _genero((conversacion.ultima_pieza or {}).get("pieza", ""))
        lineas.append(CESION_PRECIO.format(pron=_pron(g)))
        lineas.append(ESCALADO_PRECIO)
        reglas.append(("no baja el precio, da otra cosa",
                       "cede el transporte en vez del margen — su jugada real"))
        reglas.append(("escalado a persona",
                       "cualquier rebaja la decide Álvaro, nunca el bot "
                       "(política PRECIOS Y DESCUENTOS)"))

    # ------------------------------------------- la regla dura sigue en pie
    # El cliente insiste, pero cambiando de argumento: "venga, mándamela y te hago
    # la transferencia mañana", "es auténtico, compruébalo tú mismo". Ninguna de
    # esas frases lleva las palabras que disparan la regla, y sin esto el bot
    # contestaba "pásame la matrícula" — que suena exactamente a que ha cedido.
    #
    # No se arregla añadiendo más palabras a la lista: siempre habrá una forma
    # nueva de insistir. Se arregla recordando que la condición sigue encima de la
    # mesa hasta que se resuelva.
    # "cierre" entra aquí porque "mándamela y te hago la transferencia mañana" se
    # lee como un cierre y no lo es: es la misma petición de antes con otra ropa.
    # Un cierre de verdad —con una pieza concreta encima de la mesa— ya lo ha
    # cogido la rama de arriba, así que esto solo pilla los que no tienen pieza.
    elif conversacion.regla_dura and not hay_pieza and intencion in (
            "consulta", "prisa", "alternativa", "cierre"):
        escala = True
        lineas += conversacion.variar("insiste", [
            ["Te entiendo, pero eso no lo decido yo y no me puedo saltar la norma.",
             "Álvaro ya tiene tu mensaje; si él lo ve de otra forma, te lo dice él."],
            ["Sigo en lo mismo, no por desconfianza: es como trabajamos con todos.",
             "En cuanto esté el pago confirmado, sale la pieza el mismo día."],
        ])
        reglas.append(("la condición sigue en pie",
                       f"insiste con otras palabras sobre «{conversacion.regla_dura}»: "
                       f"la condición no cambia porque cambie el argumento"))
        reglas.append(("escalado a persona", "sigue en manos de Álvaro"))

    # ------------------------------------------ acaba de dar la matrícula
    # Le pediste un dato, te lo manda, y le contestas de otra cosa: ahí es donde el
    # cliente decide que está hablando con una máquina. Se acusa recibo siempre.
    elif conversacion.matricula_recien_dada and not hay_pieza:
        matricula = conversacion.matricula
        reglas.append(("acusa recibo del dato",
                       f"el cliente acaba de dar la matrícula ({matricula}): se "
                       f"confirma que ha llegado antes de seguir"))
        if conversacion.ultima_pieza:
            g = _genero(conversacion.ultima_pieza.get("pieza", ""))
            lineas.append(f"Anotada, {matricula}.")
            lineas.append(f"Con eso compruebo que es {_art(g)} tuy{_o(g)} antes de "
                          f"mandar nada. ¿Te {_pron(g)} aparto?")
        else:
            lineas.append(f"Anotada, {matricula}.")
            lineas.append("Dime qué pieza buscas y te digo si la tengo.")

    # ------------------------------------------- seguimiento sobre lo hablado
    # Todo este bloque responde con la ficha que ya está sobre la mesa. Es la
    # diferencia entre un buscador y una conversación: el cliente pregunta "¿y
    # está comprobada?" sin decir de qué, porque da por hecho que te acuerdas.
    elif conversacion.ultima_pieza and intencion in SEGUIMIENTO and not hay_pieza:
        lineas += _seguimiento(intencion, conversacion, reglas, salida)

    # ---------------------------------------------------- plazo de lo hablado
    # "¿y me llega esta semana?" no nombra ninguna pieza, así que el buscador no
    # tiene con qué encontrarla. La respuesta está en la conversación, no en el
    # índice: hablamos de UNA pieza concreta hace dos mensajes.
    elif intencion == "plazo" and conversacion.ultima_pieza and not hay_pieza:
        meta = conversacion.ultima_pieza
        g = _genero(meta.get("pieza", ""))
        lineas.append(f"{_plazo(meta, g).capitalize()}.")
        lineas.append(f"Te {_pron(g)} mando al taller o te {_pron(g)} dejo "
                      f"preparad{_o(g)} aquí, como prefieras.")
        reglas.append(("memoria de conversación",
                       f"pregunta por el plazo sin nombrar la pieza: se responde "
                       f"por {meta.get('pieza', 'la pieza').lower()}, de la que se "
                       f"venía hablando"))

    # ---------------------------------------------------------------- pieza
    elif decision == "RESPONDE" and hay_pieza:
        lineas += _con_pieza(consulta, conversacion, reglas, salida)

    elif decision == "NO DISPONIBLE":
        lineas += _sin_pieza(conversacion, reglas)

    # -------------------------------------------------------------- política
    elif decision == "RESPONDE":
        respuesta = _politica(consulta, conversacion, reglas)
        if respuesta:
            lineas += respuesta
        else:
            escala = True
            lineas.append("Eso prefiero que te lo confirme Álvaro, se lo paso.")
            reglas.append(("escalado a persona",
                           "la política recuperada no tiene una respuesta corta fiable"))

    # ------------------------------------------------- saludo o no se entiende
    elif intencion in ("saludo", "agradecimiento") and conversacion.turnos <= 1:
        lineas.append("¿Qué pieza necesitas y para qué coche?")
        reglas.append(("apertura",
                       "solo hay saludo: se pregunta lo mínimo para poder buscar"))

    elif intencion == "agradecimiento":
        lineas.append("A ti. Cualquier cosa me dices.")
        reglas.append(("cierre cordial", "no hay nada que buscar: no se fuerza venta"))

    # Ya se estaba hablando de una pieza y el mensaje no encaja en nada. No es un
    # cliente perdido: es uno que se lo está pensando. Volver a pedirle la matrícula
    # aquí es el error clásico del bot, y suena a que no te ha escuchado.
    elif conversacion.ultima_pieza:
        meta = conversacion.ultima_pieza
        g = _genero(meta.get("pieza", ""))
        nombre = meta.get("pieza", "pieza").lower()
        lineas += conversacion.variar("seguimiento", [
            [f"Sin prisa, {_pron(g)} dejo apuntad{_o(g)} por si acaso.",
             f"¿Sigue en pie lo {_del(g)} {nombre} o lo aparcamos de momento?"],
            [f"Tú me dices y {_pron(g)} preparo.",
             "¿Necesitas que te confirme algo más antes?"],
            [f"Aquí sigue {_art(g)} {nombre} cuando la quieras.",
             "Si te sale otra cosa del mismo coche, dímelo y lo miro."],
        ])
        reglas.append(("seguimiento sin presionar",
                       "no se entiende el mensaje pero había una pieza sobre la "
                       "mesa: se retoma sin volver a pedir datos ya dados"))

    else:
        escala = True
        if conversacion.matricula:
            lineas.append("Dime qué pieza necesitas y te digo si la tengo.")
            reglas.append(("memoria de conversación",
                           "ya tiene la matrícula: pide la pieza, no repite el dato"))
        else:
            lineas += conversacion.variar("pide_datos", [
                ["Pásame la matrícula del coche y qué pieza buscas, y te digo si "
                 "la tengo."],
                ["Cuéntame qué coche es y qué necesitas y lo miro."],
                ["Dime la pieza y la matrícula y te lo confirmo en un momento."],
            ])
            conversacion.datos_pedidos.add("matricula")
            reglas.append(("no se reconoce la consulta",
                           "no hay pieza ni política clara: se piden los datos "
                           "mínimos y lo mira una persona"))

    # -------------------------------------------------------------- urgencia
    if intencion == "prisa" and len(lineas) < 3:
        lineas.append("Y si corre prisa, dímelo y le doy prioridad.")
        reglas.append(("detecta urgencia", "el cliente mete prisa: se reconoce"))

    # El rol pide de 1 a 3 líneas. Si se pasa, se recorta por el final: la primera
    # línea siempre lleva la información, las últimas son el empujón comercial.
    if len(lineas) > 3:
        lineas = lineas[:3]
        reglas.append(("formato WhatsApp", "recortado a 3 líneas (rol §8.2)"))

    lineas = _sin_repetir(lineas, conversacion, reglas)

    return {
        "mensaje": "\n".join(lineas),
        "lineas": lineas,
        "reglas": [{"regla": r, "detalle": d} for r, d in reglas],
        "intencion": intencion,
        "escala": escala,
        "perfil": conversacion.perfil,
        "matricula": conversacion.matricula,
        "precio_dado": salida["precio_dado"],
    }
