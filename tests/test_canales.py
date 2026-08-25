# -*- coding: utf-8 -*-
"""GMAIL Y WALLAPOP: la forma cambia, el fondo no.

Los 50 correos y las 20 conversaciones de datos/canales/ pasan por el sistema
REAL —la misma búsqueda, el mismo guardarraíl de precio, el mismo redactor— y se
comprueba lo que cada canal tiene que cumplir.

Lo que se mide es distinto en cada uno, a propósito:

  GMAIL     que la respuesta esté COMPLETA. Si el taller tiene que volver a
            escribir para preguntar el plazo, no hemos contestado: hemos acusado
            recibo. Y que los ocho correos que piden algo que no llevamos lo
            digan claro y sin inventarse un sustituto.

  WALLAPOP  que AGUANTE. Aquí no se mide si acierta, se mide si cede: si acaba
            diciendo que manda la pieza antes de cobrar, si da por bueno un
            pantallazo, si se le escapa un precio sin saber de qué coche es, o
            si a los quince mensajes empieza a repetirse.

Y en los dos, el invariante de siempre: NI UN IMPORTE que la búsqueda no haya
autorizado.

    python tests/test_canales.py
"""
import importlib.util
import json
import pathlib
import re
import sys

sys.path.insert(0, ".")
sys.argv = ["x"]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = pathlib.Path(".").resolve()
CANALES_DIR = BASE / "datos" / "canales"


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    m = importlib.util.module_from_spec(spec)
    sys.modules[alias] = m
    spec.loader.exec_module(m)
    return m


def jsonl(fichero):
    with open(fichero, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


panel = cargar("06_panel.py", "panel")
canales = cargar("11_canales.py", "canales")

S = panel.Sistema()
# Sin LLM: lo que se comprueba aquí es el borrador determinista, que es el que
# lleva las reglas. Si el modelo lo reescribe, el panel lo audita aparte con
# estas mismas funciones.
S.config_llm = dict(S.config_llm, GROQ_API_KEY="")
red = S.redactor

# Esta prueba NO puede tocar los datos de Álvaro. `chatear()` escribe: apunta en
# el registro de no resueltas y crea reservas. Las sesiones "sim-" ya no dejan
# reservas, y `anotar` se desactiva aquí — 209 mensajes de gente difícil
# inflarían la cola con basura que nadie preguntó de verdad.
S.aprender.anotar = lambda *a, **k: None

PRECIO = re.compile(r"\d+[.,]\d{2}\s*€|\d+\s*€")
CEDE = re.compile(r"te (lo|la) mando (ya|ahora|hoy)|sale (ya|hoy) y (me )?pagas|"
                  r"(lo|la) env[ií]o y (luego )?pagas|sin pagar no hay problema|"
                  r"vale,? (te )?(lo|la) mando", re.I)
# Ojo con lo que se busca aqui. "En cuanto este el pago confirmado, sale la
# pieza" contiene "pago confirmado" y es exactamente lo CONTRARIO de dar por
# bueno un justificante: es la condicion, puesta como condicion. Por eso se
# excluyen las formas condicionales antes de mirar nada mas.
CONDICIONAL = re.compile(r"(en cuanto|cuando|hasta que|una vez|sin que)[^.]*", re.I)
DA_POR_BUENO = re.compile(r"pago recibido|ya (est[aá]|veo) (el )?pagad|"
                          r"he visto el ingreso|justificante (correcto|v[aá]lido)|"
                          r"doy por (bueno|pagado)", re.I)

fallos = []


def falla(donde, que):
    fallos.append(donde + ": " + que)
    print("  FALLA  " + donde + " — " + que)


# ===========================================================================
print("\n" + "=" * 78)
print("GMAIL · 50 correos, una sola respuesta con todo dentro")
print("=" * 78)

correos = jsonl(CANALES_DIR / "correos.jsonl")
con_precio = sin_precio = sin_stock = 0

for c in correos:
    donde = "correo " + str(c["n"])
    esperado = c["espera"]

    # El correo trae el coche y la matrícula, así que el coche SÍ está
    # identificado: es la diferencia con el primer mensaje de un WhatsApp.
    texto = canales.texto_de_busqueda(
        c, S.buscador, S.buscar_mod.normalizar)
    d = S.consultar(texto, coche_identificado=True, registrar=False)
    salida = canales.componer_email(d, c)
    cuerpo = salida["cuerpo"]

    roto = canales.rompe_el_correo(salida)
    if roto:
        falla(donde, "no parece un correo — " + roto)

    hay_pieza = bool(canales._pieza_ofrecida(d))
    faltan = canales.falta_en_el_correo(salida, hay_pieza)
    if faltan:
        falla(donde, "incompleto, falta " + " y ".join(faltan))

    if red.EMOJI.search(cuerpo):
        falla(donde, "lleva emoji")

    # EL INVARIANTE. Un importe en el cuerpo solo si la búsqueda lo autorizó.
    importes = PRECIO.findall(cuerpo)
    autorizado = bool(salida["precio_dado"])
    if importes and not autorizado:
        falla(donde, "importe sin autorizar: " + importes[0])
    if autorizado:
        con_precio += 1
    else:
        sin_precio += 1

    # Los ocho que piden lo que no llevamos.
    if not esperado["en_catalogo"]:
        sin_stock += 1
        if "no llevamos" not in cuerpo:
            falla(donde, "pide algo que no tenemos y no lo dice")
        if importes:
            falla(donde, "da un precio de algo que no tenemos")

print("  " + str(len(correos)) + " correos · " + str(con_precio) + " con precio · "
      + str(sin_precio) + " sin precio · " + str(sin_stock) + " piden lo que no hay")

# Un correo de muestra, para poder leerlo y no solo contarlo.
muestra = next(c for c in correos if c["espera"]["en_catalogo"])
d = S.consultar(canales.texto_de_busqueda(
    muestra, S.buscador, S.buscar_mod.normalizar),
                coche_identificado=True, registrar=False)
ejemplo = canales.componer_email(d, muestra)
print("\n  --- muestra: " + ejemplo["asunto"] + " ---")
for linea in ejemplo["cuerpo"].splitlines():
    print("  | " + linea)

# ===========================================================================
print("\n" + "=" * 78)
print("WALLAPOP · 20 conversaciones difíciles, 209 mensajes")
print("=" * 78)

conversaciones = jsonl(CANALES_DIR / "wallapop.jsonl")
turnos = repeticiones = 0

for conv_datos in conversaciones:
    sesion = "sim-wallapop-" + str(conv_datos["n"])
    donde = "wallapop " + str(conv_datos["n"]) + " (" + conv_datos["guion"] + ")"
    dichas = set()
    problemas_aqui = []

    for i, mensaje in enumerate(conv_datos["mensajes"], 1):
        d = S.chatear(sesion, mensaje, perfil="nuevo", reiniciar=(i == 1))
        b = d["bot"]
        conv = S.chats[sesion]
        lineas = b["lineas"]
        turnos += 1

        roto = (red.rompe_el_estilo(lineas)
                or red.rompe_la_matricula(lineas, d["busqueda"]["decision"],
                                          bool(conv.matricula), bool(b.get("escala"))))
        if roto and roto not in problemas_aqui:
            problemas_aqui.append(roto)
            falla(donde + " m" + str(i), roto)

        if not b.get("precio_autorizado", True):
            falla(donde + " m" + str(i), "FUGA DE PRECIO")

        texto = " ".join(lineas)
        if CEDE.search(texto):
            falla(donde + " m" + str(i), "CEDE: acepta enviar sin cobrar")
        if DA_POR_BUENO.search(CONDICIONAL.sub("", texto)):
            falla(donde + " m" + str(i), "DA POR BUENO un justificante")

        # Repetirse literalmente es lo que delata a un bot. Una línea con un dato
        # dentro puede repetirse: si vuelve a preguntar el precio, la respuesta
        # correcta es el precio otra vez.
        for l in lineas:
            clave = " ".join(l.lower().split())
            if not re.search(r"\d", l):
                if clave in dichas:
                    repeticiones += 1
                    falla(donde + " m" + str(i), "repite «" + l[:44] + "»")
                dichas.add(clave)

print("  " + str(len(conversaciones)) + " conversaciones · " + str(turnos)
      + " mensajes · " + str(repeticiones) + " líneas repetidas")

# Una conversación entera, la del que quiere que se la manden sin pagar.
dura = next(c for c in conversaciones if "sin pagar" in c["guion"])
print("\n  --- muestra: " + dura["guion"] + " ---")
for i, mensaje in enumerate(dura["mensajes"], 1):
    d = S.chatear("sim-muestra", mensaje, perfil="nuevo", reiniciar=(i == 1))
    print("  CLIENTE | " + mensaje)
    for l in d["bot"]["lineas"]:
        print("  VENDIQ  | " + l)

# ===========================================================================
print("\n" + "=" * 78)
if fallos:
    print(str(len(fallos)) + " FALLOS")
    for f in fallos[:25]:
        print("   " + f)
    raise SystemExit(1)
print("CANALES EN VERDE")
print("  · 50 correos completos: qué hay, cuánto, cuándo, garantía, pago y envío")
print("  · 20 conversaciones difíciles sin ceder, sin fugas y sin repetirse")
print("  · ni un importe que la búsqueda no haya autorizado, en ningún canal")
print("=" * 78)
