# -*- coding: utf-8 -*-
"""
tests/test_llm.py
=================
LA LLAMADA A GROQ, PROBADA SIN CLAVE Y SIN RED.

08_conversar.py era el único módulo del proyecto sin una sola ejecución, y es
el que habla con una API de fuera. Esta prueba cubre todo lo que NO depende de
la red, que es casi todo: cómo sale la petición, qué ve el modelo, y qué pasa
cuando la API falla.

LO QUE DE VERDAD SE COMPRUEBA AQUÍ
----------------------------------
El guardarraíl del precio. No se comprueba que el modelo "no diga" un importe
no autorizado —eso solo se puede medir por estadística—, se comprueba que el
importe NO ESTÁ en ninguno de los mensajes que se le mandan. No puede decirlo
porque no lo tiene. Es la diferencia entre una promesa y una propiedad.

Y que un desguace no se queda sin contestar porque una API esté caída: 401, 429,
404, sin red, timeout y respuesta vacía caen todos de pie en 07_redactor.py.

Se sustituye urllib.request.urlopen por un doble que guarda lo que se le manda.
No sale ni un byte a internet, así que esto corre en cualquier sitio y no gasta
cuota.
"""
import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# La consola de Windows en español es cp1252 y revienta con los guiones largos.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def cargar(f, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / f)
    m = importlib.util.module_from_spec(spec); sys.modules[alias] = m
    spec.loader.exec_module(m); return m


conv = cargar('08_conversar.py', 'conv')

fallos = []


def comprobar(que, condicion, detalle=""):
    print(f"   {'OK  ' if condicion else 'FALLA'}  {que}" + (f"  · {detalle}" if detalle else ""))
    if not condicion:
        fallos.append(que)


# --------------------------------------------------------------- el doble
class RespuestaFalsa:
    def __init__(self, texto):
        self._cuerpo = json.dumps({
            "choices": [{"message": {"content": texto}}]
        }).encode("utf-8")

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


capturado = {}


def urlopen_falso(peticion, timeout=None):
    capturado["url"] = peticion.full_url
    capturado["cabeceras"] = dict(peticion.headers)
    capturado["cuerpo"] = json.loads(peticion.data.decode("utf-8"))
    capturado["timeout"] = timeout
    return RespuestaFalsa("Lo tengo, sí.\nSon 240 €.\n¿Te lo aparto?")


# ------------------------------------------------------- datos de entrada
CONFIG = {"GROQ_API_KEY": "clave-de-mentira", "GROQ_MODELO": "openai/gpt-oss-120b"}

CONSULTA_CON_PRECIO = {
    "pregunta": "¿tenéis un alternador para un Seat Ibiza 1.9 TDI?",
    "resultados": [{
        "tipo": "inventario",
        "texto": "Alternador Seat Ibiza",
        "meta": {"pieza": "Alternador", "marca": "Seat", "modelo": "Ibiza",
                 "motor": "1.9 TDI", "anio": "2008", "estado": "Usado",
                 "disponibilidad": "En stock", "garantia": "1 año", "id": "42"},
        "precio_cliente": {"publicable": True, "importe": "240 €"},
    }],
}
CONSULTA_SIN_PRECIO = json.loads(json.dumps(CONSULTA_CON_PRECIO))
CONSULTA_SIN_PRECIO["resultados"][0]["precio_cliente"] = {
    "publicable": False, "importe": "240 €", "motivo": "confianza baja"}

RESPUESTA = {"mensaje": "Lo tengo. ¿Te lo aparto?", "reglas": [], "escala": False}

print("=" * 74)
print("1. LA PETICION QUE SALE HACIA GROQ")
print("=" * 74)
urllib.request.urlopen = urlopen_falso
lineas, nota = conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER",
                                     None, [], CONFIG)
comprobar("va a la URL de Groq", capturado["url"] == conv.URL_GROQ, capturado["url"])
comprobar("manda el Bearer", capturado["cabeceras"].get("Authorization") == "Bearer clave-de-mentira")
comprobar("Content-Type json", capturado["cabeceras"].get("Content-type") == "application/json")
comprobar("respeta el tiempo maximo", capturado["timeout"] == conv.TIEMPO_MAXIMO,
          f"{capturado['timeout']}s")
c = capturado["cuerpo"]
comprobar("modelo el del .env", c["model"] == "openai/gpt-oss-120b", c["model"])
comprobar("temperatura y tope",
          c["temperature"] == 0.4 and c["max_tokens"] == conv.TOPE_RESPUESTA,
          f"max_tokens={c['max_tokens']}")
# El tope es 600 y no 220 por una razon medida: los modelos que razonan cuentan
# los tokens de pensar contra el mismo presupuesto. Con 220 gastaban 218
# pensando y devolvian el mensaje vacio. Ver la cabecera de TOPE_RESPUESTA.
comprobar("pide poco razonamiento a un modelo que razona",
          c.get("reasoning_effort") == conv.ESFUERZO, str(c.get("reasoning_effort")))
comprobar("primer mensaje = rol system", c["messages"][0]["role"] == "system")
comprobar("corta a 3 lineas como mucho", len(lineas) <= 3, f"{len(lineas)} lineas")
print(f"   nota: {nota}")

print()
print("=" * 74)
print("2. EL GUARDARRAIL: ¿puede el modelo decir un precio no autorizado?")
print("=" * 74)
conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER", None, [], CONFIG)
contexto_con = json.dumps(capturado["cuerpo"]["messages"], ensure_ascii=False)
comprobar("con precio publicable, el importe SI entra", "240" in contexto_con)

conv.redactar_con_llm(CONSULTA_SIN_PRECIO, RESPUESTA, "RESPONDER", None, [], CONFIG)
contexto_sin = json.dumps(capturado["cuerpo"]["messages"], ensure_ascii=False)
comprobar("con precio retenido, el importe NO entra en NINGUN mensaje",
          "240" not in contexto_sin)
comprobar("y se le dice que no lo tiene", "NO DISPONIBLE" in contexto_sin)
print("   -> no es que se le pida que calle: no lo tiene.")

print()
print("=" * 74)
print("3. EL RESUMEN: ¿entra cuando la conversacion se alarga?")
print("=" * 74)
historial = [{"cliente": f"mensaje {i}", "bot": f"respuesta {i}"} for i in range(10)]
memoria = {"nombre": "Juan", "matricula": "1234 ABC", "pieza": "alternador",
           "precio": "240 €", "garantia_dicha": True}
conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER", None,
                      historial, CONFIG, memoria)
msgs = capturado["cuerpo"]["messages"]
systems = [m["content"] for m in msgs if m["role"] == "system"]
turnos = [m for m in msgs if m["role"] != "system"]
comprobar("hay un segundo system con el resumen", len(systems) == 2)
comprobar("dice cuantos mensajes resume", "4 mensajes anteriores" in systems[1],
          systems[1].splitlines()[0] if len(systems) > 1 else "")
# MINIMIZACIÓN. El resumen dice que la matrícula se dio, pero NO la dice: el
# modelo no la necesita para escribir el mensaje y Groq está en EE. UU. Esta
# comprobación estaba escrita al revés y era correcta cuando se escribió.
comprobar("NO manda la matrícula, solo que se dio",
          "1234 ABC" not in systems[1] and "ya la dio" in systems[1])
todo = json.dumps(msgs, ensure_ascii=False)
comprobar("  ni en ningún otro mensaje de la petición", "1234 ABC" not in todo)
comprobar("solo van los ultimos 6 turnos", len(turnos) == conv.VENTANA_TURNOS * 2 + 1,
          f"{len(turnos)} mensajes")
comprobar("el resumen NO lo escribe el modelo",
          conv.resumir(memoria, 4) == systems[1])

print()
print("=" * 74)
print("4. CUANDO GROQ FALLA, ¿se queda el desguace sin contestar?")
print("=" * 74)


def falla_con(excepcion):
    def _f(peticion, timeout=None):
        raise excepcion
    urllib.request.urlopen = _f
    return conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER",
                                 None, [], CONFIG)


for etiqueta, exc in [
    ("clave invalida (401)", urllib.error.HTTPError(conv.URL_GROQ, 401, "no", {}, None)),
    ("cuota agotada (429)", urllib.error.HTTPError(conv.URL_GROQ, 429, "no", {}, None)),
    ("modelo retirado (404)", urllib.error.HTTPError(conv.URL_GROQ, 404, "no", {}, None)),
    ("sin red", urllib.error.URLError("sin red")),
    ("se corta a medias", TimeoutError("agotado")),
]:
    l, n = falla_con(exc)
    comprobar(etiqueta + " -> no rompe", l is None, n)

urllib.request.urlopen = lambda p, timeout=None: RespuestaFalsa("   \n  \n")
l, n = conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER", None, [], CONFIG)
comprobar("respuesta vacia -> no rompe", l is None, n)

urllib.request.urlopen = lambda p, timeout=None: RespuestaFalsa("una\ndos\ntres\nCUATRO")
l, n = conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER", None, [], CONFIG)
comprobar("mas de 3 lineas -> se recorta", l == ["una", "dos", "tres"], str(l))

l, n = conv.redactar_con_llm(CONSULTA_CON_PRECIO, RESPUESTA, "RESPONDER", None, [],
                             {"GROQ_API_KEY": ""})
comprobar("sin clave -> redacta el determinista", l is None, n)


print()
print("=" * 74)
print("5. LA SEGUNDA BARRERA: ¿y si el modelo se inventa un precio?")
print("=" * 74)
# La primera barrera es de construcción: al modelo no se le pasa el importe si la
# búsqueda no lo ha autorizado (punto 2). Ésta es la de por si acaso: se leen los
# importes del mensaje que SALE y se contrastan con los autorizados. Nunca se
# había disparado, porque hasta ahora no había ningún modelo redactando.
#
# Esto carga el sistema entero —índice y modelo de embeddings—, así que tarda unos
# segundos más que el resto del fichero. Vale la pena: es la comprobación que de
# verdad importa antes de apuntar a un modelo de fuera.
panel = cargar("06_panel.py", "panel")
S = panel.Sistema()
S.config_llm = {"GROQ_API_KEY": "clave-de-mentira", "GROQ_MODELO": "modelo-falso"}


def groq_dice(texto):
    urllib.request.urlopen = lambda peticion, timeout=None: RespuestaFalsa(texto)


PREGUNTA = "tienes un alternador para un seat ibiza 1.9 tdi?"
MATRICULA = "la matrícula es 4521 KBD"


def conversacion(sesion, texto_del_modelo):
    """Deja la conversación en el punto donde HAY un precio autorizado.

    Hacen falta dos turnos, no uno: sin matrícula, referencia o VIN no se autoriza
    ningún importe (regla de la identificación), así que el primer turno pide el
    dato y el segundo es el que ofrece la pieza. Es el mismo flujo que ve un
    cliente, y es donde tiene sentido comprobar la barrera del precio.
    """
    groq_dice("Lo tengo.\n¿Te lo aparto?")
    S.chatear(sesion, PREGUNTA, perfil="nuevo", reiniciar=True)
    groq_dice(texto_del_modelo)
    return S.chatear(sesion, MATRICULA, perfil="nuevo")


d = conversacion("b0", "Lo tengo.\n¿Te lo aparto?")
autorizados = [(r.get("precio_cliente") or {}) for r in d["busqueda"]["resultados"]
               if (r.get("precio_cliente") or {}).get("publicable")]
importe = autorizados[0]["importe"] if autorizados else None
comprobar("con matrícula, la búsqueda autoriza un importe", importe is not None,
          str(importe))

# Y sin ella no lo autoriza: la otra mitad de la regla, que si no esto no prueba
# nada — un importe autorizado siempre haría pasar la comprobación de arriba.
groq_dice("Lo tengo.\n¿Te lo aparto?")
sin = S.chatear("b0-sin", PREGUNTA, perfil="nuevo", reiniciar=True)
comprobar("sin matrícula NO autoriza ninguno",
          not any((r.get("precio_cliente") or {}).get("publicable")
                  for r in sin["busqueda"]["resultados"]),
          (sin["busqueda"]["resultados"][0].get("precio_cliente") or {}).get("motivo", "")
          if sin["busqueda"]["resultados"] else "")

INVENTADO = "Lo tengo, sí.\nSon 999 €, te sale bien.\n¿Te lo aparto?"
for etiqueta, texto, debe_descartar in [
    ("un precio inventado se descarta entero", INVENTADO, True),
    ("el precio autorizado pasa", f"Lo tengo, sí.\nSon {importe}.\n¿Te lo aparto?", False),
    ("sin ningún precio, pasa", "Lo tengo, sí.\n¿Te lo aparto?", False),
]:
    b = conversacion(f"b-{etiqueta}", texto)["bot"]
    comprobar(etiqueta, bool(b.get("llm_descartado")) == debe_descartar, b["redactor"])
    if debe_descartar:
        comprobar("  y al cliente le llega el borrador demostrable",
                  "999" not in b["mensaje"], b["lineas"][-1][:60])

print()
print("=" * 74)
print(("TODO EN VERDE: solo falta la clave." if not fallos
       else f"FALLAN {len(fallos)}: " + " · ".join(fallos)))
print("=" * 74)
sys.exit(1 if fallos else 0)
