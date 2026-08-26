# -*- coding: utf-8 -*-
"""EL CICLO DE LA CONVERSACIÓN, FIJADO CASO A CASO.

    py tests/test_ciclo.py

El banco de tests/test_conversaciones.py mide el conjunto: 218 conversaciones y
un porcentaje. Un porcentaje alto esconde bien los fallos de UNO: cuando el bot
volvía a pedir una matrícula que ya tenía, el total seguía diciendo 99%.

Aquí no hay porcentaje. Son las nueve cosas que se han arreglado a mano, cada
una con su conversación concreta, y cada una falla sola y con nombre. Si mañana
alguien toca el enrutado de `redactar()` y una vuelve, esto lo dice.

Se ejecuta SIN LLM a propósito. Lo que se fija es el borrador determinista, que
es el que lleva las reglas; lo que el modelo escriba encima se audita aparte y
con las mismas funciones (ver `rompe_el_guion` en 07_redactor.py, y los casos 4
y 5 de aquí abajo, que la prueban directamente).
"""

import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, ".")
sys.argv = ["x"]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = pathlib.Path(".").resolve()


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    m = importlib.util.module_from_spec(spec)
    sys.modules[alias] = m
    spec.loader.exec_module(m)
    return m


panel = cargar("06_panel.py", "panel")
canales = cargar("11_canales.py", "canales")

S = panel.Sistema()
# Sin LLM: se fija el borrador determinista. Ver el docstring.
S.config_llm = dict(S.config_llm, GROQ_API_KEY="")
red = S.redactor

# Esta prueba NO puede tocar los datos de Álvaro: `chatear()` escribe en la cola
# de no resueltas. Las sesiones "sim-" tampoco dejan reservas.
S.aprender.anotar = lambda *a, **k: None

FALLOS = []


def comprueba(nombre, condicion, detalle=""):
    FALLOS.append(nombre) if not condicion else None
    print(("  OK   " if condicion else "  FALLA") + "  " + nombre)
    if not condicion and detalle:
        print("         " + detalle.replace("\n", "\n         "))


def hablar(sesion, mensajes, perfil="nuevo", nombre=""):
    """Una conversación entera. Devuelve la lista de respuestas del bot."""
    salidas = []
    for i, m in enumerate(mensajes):
        r = S.chatear("sim-ciclo-" + sesion, m, perfil=perfil, nombre=nombre,
                      reiniciar=(i == 0))
        salidas.append(r["bot"]["mensaje"])
    return salidas


print("=" * 78)
print("EL CICLO DE LA CONVERSACIÓN · 9 casos")
print("=" * 78)

# ---------------------------------------------------------------- 1 y 2
# La apertura. Un "buenos días" no es una consulta de pieza, y contestarle "no
# disponemos de esa pieza" es la peor primera frase posible: el cliente no ha
# pedido ninguna todavía.
saludo = hablar("saludo", ["Buenos días!"])[0]
comprueba("1 · saludo suelto: no dice que no tiene la pieza",
          not red.NIEGA_TENERLA.search(saludo), saludo)
comprueba("1 · saludo suelto: pregunta qué necesita",
          "?" in saludo, saludo)

primero = hablar("apertura", ["Hola, necesito un compresor para un Audi A4"])[0]
comprueba("2 · primer mensaje con pieza: se presenta o saluda",
          re.search(r"hola|buenas|encantado|asistente", primero, re.I), primero)
# «Pásame la matrícula y te digo cuál es el tuyo» pide el dato sin signo de
# interrogación, y es una petición perfectamente clara: lo que se comprueba es
# que PIDA algo, no cómo lo puntúa.
comprueba("2 · primer mensaje con pieza: pide el dato que falta",
          "?" in primero or red.PIDE_IDENTIFICADOR.search(primero), primero)

# --------------------------------------------------------------------- 3
# La matrícula que ya está dada. Es el fallo que más caro sale: el cliente te
# manda el dato que le pediste y dos turnos después se lo vuelves a pedir.
turnos = hablar("matricula", [
    "necesito un alternador para un Audi A4",
    "la matrícula es 4521 KBD",
    "y cuánto tardaría en llegar",
])
comprueba("3 · no vuelve a pedir la matrícula que ya tiene",
          not red.IDENTIFICA.search(turnos[-1]), turnos[-1])

# ------------------------------------------------------------------ 4 y 5
# Las dos que rompía el modelo. Se prueban contra `rompe_el_guion`, que es la
# red de seguridad de verdad: el borrador determinista no las rompe nunca, así
# que lo que hay que comprobar es que la guarda las CAZA.
conv = red.Conversacion()
conv.matricula = "4521 KBD"

borrador = ["Eso se lo paso a Álvaro y te contesta él."]
comprueba("4 · caza el «¿a quién se lo remito?» que el borrador no decía",
          red.rompe_el_guion(["¿A quién debo remitirlo?"], borrador, conv)
          is not None)
comprueba("4 · no salta si el borrador ya lo decía (reformular es legal)",
          red.rompe_el_guion(["Se lo paso a Álvaro, él te contesta."],
                             borrador, conv) is None)

comprueba("5 · caza el «descuento» que el borrador no decía",
          red.rompe_el_guion(["Te puedo hacer un descuento."],
                             ["El precio es ese, pero te regalo el envío."],
                             conv) is not None)
comprueba("5 · caza que vuelva a pedir la matrícula ya dada",
          red.rompe_el_guion(["¿Me pasas la matrícula?"],
                             ["Te la busco y te digo algo."], conv) is not None)
comprueba("5 · caza que se invente la motorización del coche",
          red.rompe_el_guion(["Tengo el compresor del A4 3.0 TDI."],
                             ["Tengo un compresor de A4."], conv,
                             dicho_cliente="compresor para mi A4") is not None)
comprueba("5 · deja pasar la motorización que dijo el cliente",
          red.rompe_el_guion(["Ese es el del 2.0 TDI, sí."],
                             ["Es el que me dices."], conv,
                             dicho_cliente="tengo un A4 2.0 TDI") is None)

# --------------------------------------------------------------------- 6
# Escalado pegajoso. Cuando ya está con Álvaro, un "vale" no reabre nada ni
# repite el "te lo paso": eso es lo que delata al bot y cansa al cliente.
esc = hablar("escalado", [
    "el alternador que me mandasteis no funciona",
    "vale",
    "gracias",
])
comprueba("6 · un «vale» tras escalar no repite el «te paso a Álvaro»",
          esc[1].count("paso a Álvaro") == 0, esc[1])
comprueba("6 · un «gracias» tras escalar no vuelve a pedir pieza",
          not re.search(r"qué pieza|que pieza", esc[2], re.I), esc[2])

# --------------------------------------------------------------------- 7
# Venta cerrada. Un "no hace falta" después de comprar remata corto: no pide la
# matrícula otra vez ni re-ofrece lo que ya está vendido.
cerrada = hablar("cerrada", [
    "quiero el alternador con referencia 7891VT72E",
    "sí, me lo quedo",
    "no hace falta, gracias",
])
comprueba("7 · con la venta cerrada no vuelve a pedir la matrícula",
          not red.IDENTIFICA.search(cerrada[-1]), cerrada[-1])
comprueba("7 · con la venta cerrada remata corto",
          len(cerrada[-1].splitlines()) <= 2, cerrada[-1])

# --------------------------------------------------------------------- 8
# El panel. Gmail está al mismo nivel que WhatsApp —misma búsqueda, mismo
# cerrojo de precio— y la tarjeta tiene que decirlo.
js = (BASE / "panel" / "actividad.js").read_text(encoding="utf-8")
tarjeta_gmail = re.search(r"nodoFlujo\(\{titulo: 'Gmail'.*?\}\)", js, re.S)
comprueba("8 · la tarjeta de Gmail existe en pintarRecorrido",
          tarjeta_gmail is not None)
if tarjeta_gmail:
    t = tarjeta_gmail.group(0)
    comprueba("8 · Gmail NO está apagado", "apagado" not in t, t)
    comprueba("8 · Gmail dice que está conectado", "conectado" in t, t)

# --------------------------------------------------------------------- 9
# El enlace de stock en el correo. Solo con identificación inequívoca: un
# enlace es más fuerte que una frase, y quien lo abre da por hecho que esa
# ficha es la suya.
ficha = next((it for it in S.buscador.items
              if it.get("tipo") == "inventario"
              and (it.get("meta") or {}).get("referencia_oem")
              and (it["meta"].get("disponibilidad") or "").lower()
              in S.buscar_mod.DISPONIBILIDAD_VALIDA), None)

if not ficha:
    comprueba("9 · hay una pieza con referencia OEM en stock", False,
              "no se ha encontrado ninguna en el catálogo")
else:
    meta = ficha["meta"]
    con_ref = {"asunto": "Consulta de pieza",
               "cuerpo": f"Buenos días, necesito la pieza con referencia "
                         f"{meta['referencia_oem']}. ¿Precio y disponibilidad?",
               "quien": "Taller Ruiz", "empresa": "Talleres Ruiz SL"}
    texto = canales.texto_de_busqueda(con_ref, S.buscador, S.buscar_mod.normalizar)
    d = S.consultar(texto, coche_identificado=True, registrar=False)
    salida = canales.componer_email(d, con_ref)
    esperado = f"/stock/{meta['id']}"
    comprueba("9 · con referencia exacta, el correo lleva el enlace de la ficha",
              esperado in salida["cuerpo"], salida["cuerpo"][:400])

    # Y el mismo correo sin la referencia: no hay enlace, se pide la referencia.
    sin_ref = {"asunto": "Consulta de pieza",
               "cuerpo": "Buenos días, necesito un alternador para un Audi A4. "
                         "¿Precio y disponibilidad?",
               "quien": "Taller Ruiz", "empresa": "Talleres Ruiz SL"}
    texto2 = canales.texto_de_busqueda(sin_ref, S.buscador, S.buscar_mod.normalizar)
    d2 = S.consultar(texto2, coche_identificado=False, registrar=False)
    salida2 = canales.componer_email(d2, sin_ref)
    comprueba("9 · sin identificación inequívoca NO hay enlace",
              "/stock/" not in salida2["cuerpo"], salida2["cuerpo"][:400])

# --------------------------------------------------------- la ficha de stock
# La página que hay al otro lado del enlace. Se comprueba que la encuentra por
# su número y que el precio que enseña es el que autoriza el buscador, no el
# del CSV por su cuenta.
if ficha:
    pagina = S.ficha_stock(meta["id"])
    comprueba("9 · /stock/<id> encuentra la ficha por su número",
              pagina is not None and pagina["meta"].get("id") == meta["id"])
    comprueba("9 · el precio de la ficha lo autoriza el buscador",
              pagina is not None
              and "referencia exacta" in str(pagina["precio"].get("motivo", "")),
              str(pagina["precio"]) if pagina else "")
    comprueba("9 · un número de stock inventado no devuelve ficha",
              S.ficha_stock("00000000") is None)

print("=" * 78)
if FALLOS:
    print(f"FALLAN {len(FALLOS)} de las comprobaciones:")
    for f in FALLOS:
        print("  · " + f)
    sys.exit(1)
print("Las 9 situaciones se comportan como deben.")
sys.exit(0)
