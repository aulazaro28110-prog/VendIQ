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


def detectar_intencion(mensaje: str) -> str:
    """Qué está haciendo el cliente, más allá de qué pieza pide.

    Esto NO mira el catálogo: mira la conversación. Un "me lo quedo" y un "cuánto
    vale" recuperan lo mismo del índice y sin embargo piden respuestas opuestas.
    """
    t = _sin_tildes(mensaje)
    hipotetico = any(h in t for h in HIPOTETICO)
    for intencion, marcas in PALABRAS_INTENCION.items():
        if intencion == "queja" and hipotetico:
            continue        # es una pregunta sobre la política, no una reclamación
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
        self.ultima_pieza = None            # meta de la última ficha ofrecida
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

    @property
    def conocido(self):
        return self.perfil == "conocido"

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
        return opciones[min(n, len(opciones) - 1)]


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
    estado = _estado(meta)
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
        lineas.append(f"Son {precio['importe']} y {_plazo(meta, g)}.")
        lineas.append(f"¿Te {_pron(g)} aparto?")
        reglas.append(("precio publicado",
                       f"{precio['motivo']}. Se dice tal cual, sin redondear"))
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
    intencion = detectar_intencion(consulta.get("pregunta", ""))
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
