"""
09_aprender.py
==============
LO QUE EL BOT NO SUPO, Y CÓMO APRENDE. Idea 5 de la especificación.

El ciclo, entero:

    1. El bot no sabe algo  ->  no se lo inventa, escala, y GUARDA la pregunta.
    2. Álvaro la ve en el centro de control y escribe la respuesta.
    3. Esa respuesta entra en la base de conocimiento y se indexa.
    4. La próxima vez, el bot la recupera solo.

LA PARTE QUE IMPORTA: EL PASO 2 NO SE PUEDE SALTAR
--------------------------------------------------
El bot nunca escribe su propia respuesta a lo que no sabía. No hay ningún camino
en este fichero por el que una respuesta llegue al índice sin que una persona la
haya escrito — `aprender()` exige el texto de un humano y lo firma con su nombre.

Un sistema que se autocompleta las lagunas parece más listo y es peor: la primera
respuesta inventada se convierte en la fuente de la siguiente, y a las tres
semanas el catálogo de políticas dice cosas que nadie ha decidido.

INDEXADO INCREMENTAL
--------------------
Cuando Álvaro contesta, la respuesta se indexa AL MOMENTO: se calcula su vector,
se pega al final de la matriz y el buscador que ya está cargado en memoria la
tiene desde la siguiente consulta. No hace falta reconstruir las 1.007 fichas ni
reiniciar el panel.
"""

import json
import re
import time
from pathlib import Path

BASE = Path(__file__).parent
REGISTRO = BASE / "salida" / "no_resueltas.json"
APRENDIDAS = BASE / "datos" / "faq_aprendidas.md"


def _leer(fichero, por_defecto):
    if not fichero.exists():
        return por_defecto
    texto = fichero.read_text(encoding="utf-8-sig").strip()
    return json.loads(texto) if texto else por_defecto


def _escribir(fichero, datos):
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(json.dumps(datos, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def leer_registro():
    return _leer(REGISTRO, [])


def anotar(pregunta, motivo, sesion="", decision=""):
    """Guarda una pregunta que el bot no supo responder.

    Si ya está anotada, sube el contador en vez de duplicarla: lo que interesa no
    es cuántas veces falló, es qué preguntas repiten los clientes — eso ordena por
    dónde empezar a contestar.
    """
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return None
    registro = leer_registro()
    clave = pregunta.lower()

    for entrada in registro:
        if entrada["pregunta"].lower() == clave:
            entrada["veces"] += 1
            entrada["ultima"] = time.strftime("%Y-%m-%d %H:%M")
            _escribir(REGISTRO, registro)
            return entrada

    entrada = {
        "n": max([e["n"] for e in registro], default=0) + 1,
        "pregunta": pregunta,
        "motivo": motivo,
        "decision": decision,
        "sesion": sesion,
        "veces": 1,
        "primera": time.strftime("%Y-%m-%d %H:%M"),
        "ultima": time.strftime("%Y-%m-%d %H:%M"),
        "estado": "pendiente",
        "respuesta": None,
        "respondida_por": None,
    }
    registro.append(entrada)
    _escribir(REGISTRO, registro)
    return entrada


def aprender(n, respuesta, quien="Álvaro", buscador=None):
    """Un HUMANO contesta una pregunta pendiente y pasa a la base de conocimiento.

    `respuesta` es obligatoria y la escribe una persona. No hay parámetro para
    generarla automáticamente, y es a propósito: ver la cabecera del fichero.
    """
    respuesta = (respuesta or "").strip()
    if not respuesta:
        raise SystemExit("hace falta la respuesta escrita por una persona")

    registro = leer_registro()
    entrada = next((e for e in registro if e["n"] == int(n)), None)
    if entrada is None:
        raise SystemExit(f"no existe la pregunta nº {n}")

    entrada.update({"estado": "resuelta", "respuesta": respuesta,
                    "respondida_por": quien,
                    "resuelta_el": time.strftime("%Y-%m-%d %H:%M")})
    _escribir(REGISTRO, registro)

    # Al documento de conocimiento, con su firma y su fecha: dentro de un año hay
    # que poder saber quién decidió esto y cuándo.
    titulo = f"FAQ {entrada['n']}"
    if not APRENDIDAS.exists():
        APRENDIDAS.write_text(
            "# FAQ aprendidas — respuestas escritas por una persona\n\n"
            "> Cada bloque lo escribió alguien del equipo a partir de una pregunta\n"
            "> que el asistente no supo contestar. El bot NO escribe aquí.\n",
            encoding="utf-8")
    with open(APRENDIDAS, "a", encoding="utf-8") as f:
        f.write(f"\n## {titulo}\n"
                f"Pregunta del cliente: {entrada['pregunta']}\n"
                f"{respuesta}\n"
                f"<!-- respondida por {quien} el {entrada['resuelta_el']} -->\n")

    indexado = indexar_al_vuelo(titulo, entrada["pregunta"], respuesta, buscador)
    return {"entrada": entrada, "indexado": indexado}


def indexar_al_vuelo(titulo, pregunta, respuesta, buscador):
    """Mete la respuesta nueva en el índice que ya está cargado, sin reiniciar.

    Se añade a la matriz de vectores en memoria y a los ficheros de salida, para
    que siga estando después de reiniciar. Es el mismo formato que escribe
    02_embeddings.py, así que reconstruir el índice entero da el mismo resultado.
    """
    if buscador is None:
        return "sin buscador cargado: se indexará al reconstruir (paso 01 y 02)"

    import numpy as np

    # El texto se guarda con la pregunta delante: así se encuentra tanto por lo
    # que preguntó el cliente como por lo que contestó la persona.
    texto = f"{titulo}. {pregunta} {respuesta}"
    item = {"id": f"faq-{titulo.lower().replace(' ', '-')}",
            "tipo": "politica",
            "texto": texto,
            # 'respuesta' guarda el texto EXACTO que escribió la persona. El
            # redactor lo dice tal cual, sin reformular: si Álvaro escribió una
            # condición, el bot no la reescribe con otras palabras.
            "meta": {"seccion": titulo, "aprendida": True, "respuesta": respuesta}}

    # De dónde salen los globales del módulo de búsqueda: de la propia clase del
    # buscador. Podría buscarse en sys.modules por el nombre del módulo, pero
    # 03_buscar.py se carga con importlib desde varios sitios (panel, pruebas,
    # línea de órdenes) y no siempre está registrado con el mismo alias. Los
    # globales de la clase siempre son los correctos.
    globales = type(buscador).__init__.__globals__

    vector = buscador.modelo.encode([texto], normalize_embeddings=True).astype("float32")

    # Crecer el índice lo hace el BUSCADOR, no este fichero. Aquí se mantenía una
    # copia de "todo lo que va por posición" y se quedó corta en cuanto el
    # buscador aprendió a distinguir políticas: el índice se descuadró y la
    # búsqueda reventó. La lista de lo que crece vive donde se define.
    total = buscador.indexar(item, vector)

    _persistir(buscador, globales)
    return f"indexada al momento: {total} fichas en el índice"


def _persistir(buscador, globales):
    """Guarda matriz y metadatos, para que la respuesta siga ahí tras reiniciar."""
    import numpy as np
    salida = BASE / "salida"
    np.save(salida / "embeddings.npy", buscador.embeddings)
    (salida / "embeddings_meta.json").write_text(json.dumps({
        "modelo": globales.get("MODELO_POR_DEFECTO", ""),
        "n_chunks": len(buscador.items),
        "dimensiones": int(buscador.embeddings.shape[1]),
        "items": [{"id": i["id"], "tipo": i["tipo"], "texto": i["texto"],
                   "meta": i.get("meta", {})} for i in buscador.items],
    }, ensure_ascii=False), encoding="utf-8")


# ===========================================================================
# LA MESA DE ÁLVARO
# ===========================================================================
# El registro de arriba es una lista plana ordenada por veces. Sirve mientras
# hay ocho preguntas; con treinta y tres deja de servir, porque las que de
# verdad necesitan a una persona se hunden debajo del ruido. En la cola real
# medida, las cuatro primeras por frecuencia eran «déjame que lo mire» (192),
# «luego te digo algo» (145), «ok, te confirmo mañana» (119) y «me lo quedo»
# (105) — ninguna necesita a nadie, y entre todas tapaban «¿enviáis a
# Canarias?», que es la única que llevaba 56 clientes esperando.
#
# Así que la mesa hace dos cosas que la lista no hacía:
#
#   AGRUPA   por lo que hay que decidir, no por cuántas veces se preguntó.
#            Un cobro duplicado y un plazo a Canarias se contestan con
#            cabezas distintas.
#
#   SEPARA   lo que no es una pregunta. Un «👍», un «asdfgh» o un «vale» no
#            se contestan: se descartan. Y descartar NO escribe nada en la
#            base de conocimiento — ver `descartar()`.

import unicodedata


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# El orden IMPORTA: gana el primero que casa. Va de lo concreto a lo genérico,
# porque «me habéis cobrado dos veces» lleva la palabra «cobrado» y también
# sería «pago»: lo que toca es tratarlo como la incidencia que es.
GRUPOS = [
    ("posventa", "Algo ha ido mal",
     "Pedidos ya enviados. Esto no lo contesta una FAQ: hay que mirar el pedido.",
     r"cobrad[oa] dos veces|me hab[ei]is cobrado|cobro duplicado|"
     r"de otro modelo|no es la que|no vale|no encaja|no me sirve|"
     r"defectuos|(viene|vino|lleg\w*) rot[oa]|averiad|no funciona|"
     r"reclamacion|reclamar|me hab[ei]is mandado"),

    ("pago", "Pago y comprobantes",
     "Formas de pago y justificantes. El bot nunca da por bueno un comprobante.",
     r"transferencia|bizum|justificante|comprobante|resguardo|captura|"
     r"pagar|pago|abonar|efectivo|contrarreembolso|tarjeta|"
     r"a cuenta|fin de mes|credito|adelanto|se[nñ]al|paypal|"
     r"ya est[aá] pagad|te lo acabo de mandar"),

    ("envio", "Plazos y envíos",
     "Cuándo llega y hasta dónde se manda. Fuera de península el porte se consulta.",
     r"canarias|baleares|ceuta|melilla|portugal|francia|italia|alemania|"
     r"extranjero|internacional|peninsula|fuera de espa[nñ]a|aduana|"
     r"envi[aoáé]|env[ií]|mandar|manda|transporte|porte|agencia|"
     r"correos?|mrw|seur|gls|dhl|tipsa|prisa|mensajer|"
     r"plazo|cuando llega|cuanto tarda|urgente|para hoy|para ma[nñ]ana|"
     r"recoger|recogida|a domicilio"),

    ("politica", "Condiciones de la casa",
     "Garantía, devoluciones, facturación, horario y dónde estáis.",
     r"garantia|devol|cambiar la pieza|factura|iva|"
     r"donde est[aá]is|donde os|direccion|horario|abr[ií]s|cerr[aá]is|"
     r"condicion|politica|legal|datos personales|rgpd"),

    ("conversacion", "El bot ya sabe llevar esto",
     "Aparcar, confirmar, preguntar por un pedido. Tiene rama propia para esto: "
     "están aquí porque el registro se llenó con un bot anterior.",
     r"dejame que lo (mire|vea|consulte)|lo consulto|lo miro y te digo|"
     r"luego te (digo|cuento)|ya te (digo|cuento|confirmo)|te confirmo|"
     r"te digo algo|te lo confirmo|"
     r"me lo quedo|lo quiero|me la quedo|la quiero|"
     r"ya lo tienes|ha salido|avisame|"
     r"nada,? (era otra cosa|dejalo)|dejalo|era otra cosa|"
     r"hay alguien|estas ahi"),

    ("pieza", "Piezas que no encontró",
     "Preguntan por material concreto y la búsqueda no lo resolvió sola.",
     r".*"),        # cae aquí lo que quede y sí es una pregunta de verdad
]

# Acuses, saludos y tecleos. No son preguntas: no tienen respuesta que enseñar.
_RELLENO = {
    "vale", "si", "ok", "oki", "okey", "bueno", "ya", "ah", "aha", "ajam",
    "hola", "buenas", "hey", "gracias", "nada", "eso", "claro", "perfecto",
    "correcto", "entendido", "genial", "guay", "hecho",
}


def es_ruido(pregunta):
    """¿Esto ni siquiera es una pregunta?

    Cuatro casos, y todos salen de la cola medida:

        sin una sola letra    '👍', '?', '...'      (78 + 71 veces)
        dos caracteres o menos
        cinco consonantes seguidas  'asdfgh'        (77 veces)
        puro acuse o saludo   'vale', 'hoolaa'      (12 + 10 veces)

    Lo de las cinco consonantes es una regla del español: la palabra real más
    apretada («instrucción») llega a cuatro. Cinco seguidas es un teclado.
    """
    t = _sin_tildes(pregunta).strip()
    if not re.search(r"[a-z]", t):
        return True
    if len(t) <= 2:
        return True
    if re.search(r"[bcdfghjklmnpqrstvwxyz]{5}", t):
        return True
    nucleo = re.sub(r"[^a-z ]", "", t).strip()
    if nucleo in _RELLENO:
        return True
    if re.fullmatch(r"h+o+l+a+|b+u+e+n+a+s+|h+e+y+", nucleo):
        return True
    return False


def clasificar(pregunta):
    """Devuelve (clave, título, explicación) del grupo al que va esta pregunta."""
    if es_ruido(pregunta):
        return ("ruido", "No hace falta que contestes",
                "Acuses, saludos y tecleos. Descártalos: no hay nada que enseñar.")
    t = _sin_tildes(pregunta)
    for clave, titulo, nota, patron in GRUPOS:
        if re.search(patron, t):
            return (clave, titulo, nota)
    return GRUPOS[-1][:3]


def descartar(n, quien="Álvaro", motivo="no es una pregunta"):
    """Saca una entrada de la mesa SIN enseñarle nada al bot.

    Es la diferencia con `aprender()`, y es a propósito: descartar no escribe en
    `datos/faq_aprendidas.md` ni toca el índice. Un «👍» no puede convertirse en
    conocimiento de la empresa por el hecho de que alguien pulse un botón para
    quitárselo de encima.
    """
    registro = leer_registro()
    entrada = next((e for e in registro if e["n"] == int(n)), None)
    if entrada is None:
        raise SystemExit(f"no existe la pregunta nº {n}")
    if entrada["estado"] != "pendiente":
        raise SystemExit(f"la nº {n} ya está {entrada['estado']}")
    entrada.update({"estado": "descartada", "motivo_descarte": motivo,
                    "respondida_por": quien,
                    "resuelta_el": time.strftime("%Y-%m-%d %H:%M")})
    _escribir(REGISTRO, registro)
    return entrada


# ---------------------------------------------------------------------------
def main():
    import sys
    registro = leer_registro()
    if len(sys.argv) > 1 and sys.argv[1] == "responder":
        n, texto = sys.argv[2], " ".join(sys.argv[3:])
        print(aprender(n, texto)["entrada"])
        print("Reconstruye el índice para que el bot la use: "
              "python 01_ingesta_chunking.py && python 02_embeddings.py")
        return
    pendientes = [e for e in registro if e["estado"] == "pendiente"]
    print(f"{len(pendientes)} preguntas sin responder, de {len(registro)} anotadas\n")
    for e in sorted(pendientes, key=lambda e: -e["veces"]):
        print(f"  [{e['n']:>3}] x{e['veces']}  {e['pregunta']}")
        print(f"        {e['motivo']}")
    if pendientes:
        print('\nPara contestar una:  python 09_aprender.py responder 3 "El texto..."')


if __name__ == "__main__":
    main()
