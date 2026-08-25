# -*- coding: utf-8 -*-
"""
11_canales.py
=============
EL MISMO BOT POR TRES SITIOS DISTINTOS: WhatsApp, Gmail y Wallapop.

Lo que cambia de un canal a otro es la FORMA, y solo la forma. Un WhatsApp son
tres líneas y un tuteo; un correo es una carta con todo dentro y se firma. Lo
que NO cambia es el fondo:

    el precio sigue necesitando saber de qué coche es la pieza,
    venga la pregunta por donde venga.

Esa frase es la razón de que este módulo no sepa buscar. No mira el catálogo, no
decide precios y no tiene una sola condición sobre cuándo se puede ofrecer algo.
Recibe lo que ya decidió `03_buscar.py` y le da forma. Si el guardarraíl de
precio viviera aquí habría que escribirlo tres veces, y a la tercera copia
alguien se dejaría una condición.

POR QUÉ EL CORREO ES OTRA COSA
------------------------------
Por WhatsApp el primer mensaje casi nunca trae la matrícula, así que la primera
respuesta es siempre una pregunta. Por correo llega todo de golpe —coche,
matrícula, pieza, a veces la referencia OEM— porque quien escribe un correo se
lo ha pensado. Eso permite lo que el WhatsApp no permite: contestar UNA vez y
con todo dentro, que es justo lo que un taller necesita para decidir.

Y cuando no la tenemos, el correo tiene que decirlo y aun así servir para algo.
Ocho de los cincuenta correos del corpus piden cosas que este desguace no lleva
—pastillas, neumáticos, aceite— y ese es el correo difícil de escribir.

WALLAPOP NO NECESITA UN REDACTOR NUEVO
--------------------------------------
Tiene la misma forma que WhatsApp: corto, tuteo, sin emoji. Lo que cambia es
QUIÉN escribe. Por Wallapop llega el que regatea cinco veces, el que enseña la
captura de una transferencia que no existe, el que insiste con una pieza que no
llevamos. Así que aquí no hay redactor de Wallapop: hay un perfil que dice que
se parece a WhatsApp, y un corpus de veinte conversaciones incómodas para
comprobar que el redactor que ya existe aguanta sin ceder y sin perder los
modales. Inventar un redactor por canal habría sido código de adorno.
"""

import re
from pathlib import Path

BASE = Path(__file__).parent
POLITICAS = BASE / "datos" / "politicas.md"


# ---------------------------------------------------------------------------
# LOS PERFILES DE CANAL
# ---------------------------------------------------------------------------
# Solo forma. Ni una regla de negocio: las de negocio están en 03_buscar.py y en
# 07_redactor.py, y valen igual para los tres.
CANALES = {
    "whatsapp": {
        "nombre": "WhatsApp",
        "lineas_max": 3,
        "tutea": True,
        "firma": False,
        "asunto": False,
        "nota": "Tres líneas, tuteo, sin emoji. Se lee en un móvil con una mano.",
    },
    "wallapop": {
        "nombre": "Wallapop",
        "lineas_max": 3,
        "tutea": True,
        "firma": False,
        "asunto": False,
        # La dirección no se da hasta que hay venta: en Wallapop se habla con
        # desconocidos, y la tienda tiene horario y una persona dentro.
        "direccion_antes_de_vender": False,
        "nota": "Como WhatsApp en la forma. Lo que cambia es quién escribe.",
    },
    "email": {
        "nombre": "Gmail",
        "lineas_max": None,        # una carta no se recorta a tres líneas
        "tutea": False,            # de usted, que es como escriben ellos
        "firma": True,
        "asunto": True,
        "nota": "Una sola respuesta con todo: qué hay, cuánto, cuándo, garantía y pago.",
    },
}

FIRMA = ("Un saludo,\n"
         "Álvaro · Desguaces Madrid Norte\n"
         "Alcobendas (Madrid)")


# ---------------------------------------------------------------------------
# LAS POLÍTICAS, LEÍDAS DEL DOCUMENTO
# ---------------------------------------------------------------------------
def cargar_politicas():
    """Las secciones de datos/politicas.md, tal cual están escritas.

    Se leen y NO se reescriben. La tentación en un correo es resumir la garantía
    con palabras propias y queda mejor; el problema es que a partir de ahí hay
    dos versiones de la política —la del documento y la del código— y en cuanto
    Álvaro cambie una, el bot seguirá contando la otra durante meses sin que
    nadie se entere.
    """
    if not POLITICAS.exists():
        return {}
    secciones, actual = {}, None
    for linea in POLITICAS.read_text(encoding="utf-8-sig").splitlines():
        if linea.startswith("## "):
            actual = linea[3:].strip()
            secciones[actual] = []
        elif actual and linea.strip():
            secciones[actual].append(linea.strip())
    return {k: " ".join(v) for k, v in secciones.items()}


def _frases(texto, cuantas=2):
    """Las primeras frases de una sección. Un correo cita, no copia el manual."""
    partes = re.split(r"(?<=\.)\s+", (texto or "").strip())
    return " ".join(partes[:cuantas]).strip()


# ---------------------------------------------------------------------------
# UN CORREO NO ES UNA CONSULTA
# ---------------------------------------------------------------------------
# Esto salió midiendo, y es el hallazgo del canal. Pasando el correo ENTERO a la
# búsqueda, 28 de los 50 no encontraban la pieza. Con la misma pieza y el mismo
# coche en una consulta corta, aparecían de 2 a 4 candidatas:
#
#     correo entero  0 candidatas   <- Cerradura puerta delantera AUDI Q3 2.0 TDI
#     consulta corta 4 candidatas
#
# El motivo es la mitad léxica del buscador: la cobertura se mide sobre lo que
# el cliente escribe, y ochenta palabras de cortesía —«les escribo desde»,
# «quedo a la espera», «trabajamos con factura»— hunden el peso de las cuatro
# que importan. No es un fallo del buscador: es que se le estaba dando de comer
# otra cosa distinta de para lo que se afinó.
#
# Así que el correo se destila antes de buscar. No se resume ni se interpreta:
# se eligen los TROZOS con más vocabulario de catálogo dentro, que es una
# medida, no una opinión.
REF_OEM = re.compile(r"\b[0-9A-Z]{4}[A-Z]{2}[0-9]{2}[A-Z]\b")

# El enlace a la ficha en la web. Es el identificador MÁS fuerte que puede dar
# un cliente y por eso se busca antes que nada: quien escribe un correo ha
# estado mirando la pieza en la web y pega la dirección, y dentro va el número
# de stock. Con él no hay que adivinar cuál de los cuatro alternadores de A4 es
# — la búsqueda tiene un atajo por código exacto y esto entra por ahí.
ENLACE_FICHA = re.compile(r"desguacesmadridnorte\.com/(\d+)-", re.I)


def _trozos(correo):
    """El asunto y cada línea del cuerpo, por separado.

    El asunto entra como un trozo más porque a menudo YA es la consulta ideal
    («¿Tenéis puerta delantera izquierda de RENAULT Megane?»), pero no siempre
    («Petición de pieza y precio»), así que compite con los demás en vez de
    darse por bueno.
    """
    partes = [correo.get("asunto") or ""]
    for linea in (correo.get("cuerpo") or "").splitlines():
        partes += re.split(r"(?<=[.?])\s+", linea)
    return [_sin_etiqueta(p.strip()) for p in partes if p.strip()]


# «Motor: 2.0 TDI» no habla de un motor: es una FICHA de datos del coche, y
# "Motor" ahí es el nombre del campo. Costó un correo: el destilado eligió esa
# línea porque «motor» está en el vocabulario del catálogo, y quien escribía
# pedía un kit de embrague. Una palabra seguida de dos puntos al principio de la
# línea es una etiqueta, no lo que se pide.
ETIQUETA = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ][\wáéíóúñ ]{0,18}:\s*")


def _sin_etiqueta(trozo):
    return ETIQUETA.sub("", trozo)


def texto_de_busqueda(correo, buscador, normalizar):
    """Destila el correo a lo que la búsqueda sabe leer.

    Puntúa cada trozo por cuántas palabras suyas están en el vocabulario que el
    buscador aprendió del catálogo —tipos de pieza y marcas— y se queda con los
    dos mejores. Añade la referencia OEM y la matrícula estén donde estén,
    porque un código exacto vale más que cualquier descripción y no tiene por
    qué caer en la misma frase que el nombre de la pieza.
    """
    entero = (correo.get("asunto") or "") + " " + (correo.get("cuerpo") or "")

    # El enlace manda sobre todo lo demás. Si el cliente ha pegado la ficha, ya
    # nos ha dicho exactamente cuál es: no hay nada que destilar ni que puntuar.
    enlace = ENLACE_FICHA.search(entero)
    if enlace:
        return enlace.group(1)

    marcas = set(getattr(buscador, "marcas_conocidas", {}))
    tipos = set(getattr(buscador, "tipos_conocidos", set()))

    def puntuar(trozo):
        palabras = set(normalizar(trozo))
        # Los tipos de pieza pesan el doble que las marcas: hay muchas fichas de
        # la misma marca y pocas del mismo tipo, así que el tipo discrimina más.
        return 2 * len(palabras & tipos) + len(palabras & marcas)

    trozos = sorted(_trozos(correo), key=puntuar, reverse=True)
    elegidos = [t for t in trozos[:2] if puntuar(t)]

    texto = " ".join(elegidos)
    oem = REF_OEM.search(entero.upper())
    if oem and oem.group(0) not in texto.upper():
        texto += " " + oem.group(0)
    return texto.strip() or entero.strip()


# ---------------------------------------------------------------------------
# EL CORREO
# ---------------------------------------------------------------------------
def _pieza_ofrecida(consulta):
    """La ficha que la búsqueda dio por buena, si dio alguna."""
    for r in consulta.get("resultados") or []:
        if r.get("tipo") == "inventario":
            return r
    return None


def _describir_ficha(meta):
    trozos = [meta.get("pieza") or "la pieza"]
    coche = " ".join(x for x in (meta.get("marca"), meta.get("modelo"),
                                 meta.get("motor")) if x)
    if coche:
        trozos.append("de " + coche)
    if meta.get("anio"):
        trozos.append("(" + str(meta["anio"]) + ")")
    return " ".join(trozos)


def componer_email(consulta, correo, politicas=None):
    """Un correo entero de respuesta, a partir de lo que ya decidió la búsqueda.

    Devuelve asunto, cuerpo y la traza de por qué se ha escrito así — la misma
    idea que en el redactor de WhatsApp: que se pueda enseñar al lado la regla
    que produjo cada párrafo.

    NO decide nada sobre precios. Mira `precio_cliente`, que viene ya resuelto,
    y si dice que no se puede publicar, el correo lo explica en vez de callarse.
    """
    pol = politicas if politicas is not None else cargar_politicas()
    reglas, cuerpo = [], []

    quien = (correo.get("quien") or "").strip()
    empresa = (correo.get("empresa") or "").strip()
    profesional = bool(empresa)

    cuerpo.append("Buenos días" + (", " + quien.split()[0] if quien else "") + ":")
    cuerpo.append("Gracias por escribirnos.")

    ficha = _pieza_ofrecida(consulta)
    precio_dado = None
    escala = False

    # ---------------------------------------------------------- lo que hay
    if ficha:
        meta = ficha.get("meta") or {}
        cuerpo.append("Sí la tenemos: " + _describir_ficha(meta) + ". "
                      "Referencia interna " + str(meta.get("id", "")) + "" +
                      (", referencia OEM " + meta["referencia_oem"]
                       if meta.get("referencia_oem") else "") + ". "
                      "Estado: " + (meta.get("estado") or "desmontada de vehículo")
                      + ".")
        reglas.append(("disponibilidad",
                       "la ficha viene de la búsqueda: no se afirma nada que no "
                       "esté en el catálogo"))

        # -------------------------------------------------------- el precio
        veredicto = ficha.get("precio_cliente") or {}
        if veredicto.get("publicable"):
            precio_dado = veredicto.get("importe")
            cuerpo.append("Precio: " + str(precio_dado) + ".")
            reglas.append(("precio autorizado",
                           "la búsqueda lo dio por publicable: " +
                           str(veredicto.get("motivo", ""))))
        else:
            # Aquí está la parte que importa: el correo NO se inventa un importe
            # ni se lo salta en silencio. Dice por qué no lo lleva, que es lo
            # único que permite al cliente desbloquearlo.
            cuerpo.append("Del precio no puedo darle un importe cerrado en este "
                          "correo: " + str(veredicto.get("motivo",
                          "hace falta confirmarlo")) + ". En cuanto lo tengamos "
                          "claro se lo confirmamos.")
            reglas.append(("precio NO autorizado",
                           "estado " + str(veredicto.get("estado", "?")) +
                           ": el importe no entra en el correo"))
            escala = True

        # -------------------------------------------------------- el plazo
        disponibilidad = (meta.get("disponibilidad") or "")
        if "stock" in disponibilidad.lower():
            cuerpo.append("Plazo: está en stock, sale al día siguiente y llega "
                          "en 24-48 horas a península.")
        else:
            cuerpo.append("Plazo: " + disponibilidad + ". Primero se localiza y "
                          "se comprueba, y después se envía.")
        reglas.append(("plazo", "sale de la disponibilidad de la propia ficha"))

        # ------------------------------------------------------ la garantía
        garantia = meta.get("garantia")
        if garantia:
            cuerpo.append("Garantía: " + garantia + ". " +
                          _frases(pol.get("GARANTIA", ""), 1))
            reglas.append(("garantía", "la de la ficha, más la política tal cual "
                                       "está escrita en datos/politicas.md"))
    else:
        # ------------------------------------------------- no la llevamos
        # El correo difícil. Decirlo claro y seguir sirviendo para algo: quien
        # pide pastillas de freno a un desguace no vuelve si le contestas con un
        # "no" seco, y a lo mejor mañana necesita un faro.
        pedido = (correo.get("espera") or {}).get("pieza") or "esa pieza"
        cuerpo.append("De " + str(pedido).lower() + " no llevamos: somos un "
                      "desguace y trabajamos con piezas desmontadas de vehículo, "
                      "no con recambio nuevo ni consumibles.")
        cuerpo.append("Si necesita cualquier otra pieza del vehículo, dígamelo "
                      "con la matrícula y se lo miro en el momento.")
        reglas.append(("no está en catálogo",
                       "la búsqueda no devolvió ficha: se dice que no en vez de "
                       "ofrecer algo parecido"))
        escala = True

    # ------------------------------------------------------- pago y envío
    pago = _frases(pol.get("FORMAS DE PAGO Y DEVOLUCIONES", ""), 1)
    antes = _frases(pol.get("PAGO ANTES DEL ENVIO", ""), 1)
    if pago:
        cuerpo.append("Pago: " + pago + (" " + antes if antes else ""))
        reglas.append(("pago", "política citada, no reescrita"))

    envio = _frases(pol.get("ENVIO Y PLAZOS", ""), 3)
    if envio:
        cuerpo.append("Envío: " + envio)
        reglas.append(("envío", "incluye el aviso de fuera de península"))

    if profesional:
        cuerpo.append("Emitimos factura sin problema.")
        reglas.append(("factura", "lo pedía un taller: se responde a lo que pide"))

    cuerpo.append("Quedo a la espera de sus noticias.")
    cuerpo.append(FIRMA)

    asunto = "Re: " + (correo.get("asunto") or "Su consulta")

    return {
        "canal": "email",
        "asunto": asunto,
        "cuerpo": "\n\n".join(cuerpo),
        "parrafos": cuerpo,
        "reglas": reglas,
        "precio_dado": precio_dado,
        "escala": escala,
    }


# ---------------------------------------------------------------------------
# LAS COMPROBACIONES DE FORMA, POR CANAL
# ---------------------------------------------------------------------------
# Las de WhatsApp ya viven en 07_redactor.py (`rompe_el_estilo`, y las dos de la
# matrícula y la identificación). Aquí solo están las del correo, que son otras
# porque la forma es otra: un correo de tres líneas sin firma no es un correo.
def rompe_el_correo(salida):
    """Qué hace que un correo NO sea un correo. Devuelve el fallo o None."""
    cuerpo = salida.get("cuerpo") or ""
    if not salida.get("asunto"):
        return "sin asunto"
    if FIRMA.splitlines()[1] not in cuerpo:
        return "sin firma"
    if not re.match(r"Buenos días", cuerpo):
        return "no empieza con un saludo"
    if len(cuerpo) < 200:
        return "demasiado corto para ser una respuesta completa"
    # Un correo se escribe de usted. El tuteo aquí suena a otra empresa.
    if re.search(r"\bte\s+(paso|mando|confirmo|digo|aviso)\b", cuerpo):
        return "tutea en un correo"
    return None


def falta_en_el_correo(salida, hay_pieza):
    """Lo que un correo completo tiene que llevar SIEMPRE.

    Es el motivo por el que existe este canal: si el taller tiene que volver a
    escribir para preguntar el plazo, no hemos contestado, hemos acusado recibo.
    """
    cuerpo = salida.get("cuerpo") or ""
    # Plazo y garantía solo se exigen cuando HAY pieza. Si no la llevamos no hay
    # plazo que dar, y meter uno sería peor que no decir nada: el taller creería
    # que la tenemos. Pago y envío sí van siempre — sirven igual para la próxima.
    obligatorio = [("Pago", "cómo se paga"), ("Envío", "el envío")]
    if hay_pieza:
        obligatorio += [("Plazo", "el plazo"), ("Garantía", "la garantía")]
    faltan = [texto for marca, texto in obligatorio if marca not in cuerpo]
    return faltan


def perfil(canal):
    """El perfil del canal, o el de WhatsApp si no se reconoce.

    Que el desconocido caiga en WhatsApp no es pereza: es el canal más estricto
    de los tres —tres líneas, sin firma— así que equivocarse hacia él nunca
    produce un mensaje de más.
    """
    return CANALES.get(canal, CANALES["whatsapp"])
