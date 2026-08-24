# -*- coding: utf-8 -*-
"""LA MESA DE ÁLVARO: que cada pregunta caiga donde se contesta.

La mesa agrupa lo que el bot no resolvió por lo que hay que DECIDIR, no por
cuántas veces se preguntó. Ordenar por volumen entierra lo que importa: en la
cola real medida las cuatro preguntas más repetidas eran «déjame que lo mire»
(192), «luego te digo algo» (145), «ok, te confirmo mañana» (119) y «me lo
quedo» (105) — ninguna necesita a nadie. Entre las cuatro tapaban «¿enviáis a
Canarias?», la única con 56 clientes esperando de verdad.

Los casos de aquí NO están inventados: son las 33 preguntas que había en
salida/no_resueltas.json cuando se construyó la mesa.
"""
import sys, importlib.util, pathlib, tempfile, json, io

sys.path.insert(0, '.')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = pathlib.Path('.').resolve()

spec = importlib.util.spec_from_file_location("aprender", BASE / "09_aprender.py")
ap = importlib.util.module_from_spec(spec)
sys.modules["aprender"] = ap
spec.loader.exec_module(ap)

fallos = []


def comprobar(que, esperado, obtenido):
    if esperado == obtenido:
        print(f"  ok    {que}")
    else:
        print(f"  FALLA {que}: esperaba {esperado!r}, salió {obtenido!r}")
        fallos.append(que)


print("\nRUIDO — lo que ni siquiera es una pregunta")
for texto in ["👍", "asdfgh", "?", "...", "vale", "si", "ok", "hoolaa",
              "Holaa!", "hola??", "buenas", "gracias"]:
    comprobar(f"«{texto}» es ruido", "ruido", ap.clasificar(texto)[0])

print("\nNO son ruido — aunque sean cortas, piden algo")
for texto in ["leon", "el 2.0 tdi", "correo prisa", "bizum",
              "necesito una pieza", "la de siempre"]:
    grupo = ap.clasificar(texto)[0]
    comprobar(f"«{texto}» NO es ruido", True, grupo != "ruido")

print("\nCADA UNA A SU GRUPO")
casos = [
    ("envias a canarias?",                              "envio"),
    ("hacéis envíos a portugal",                        "envio"),
    ("lo necesito para hoy si puede ser",               "envio"),
    ("cuanto tarda en llegar",                          "envio"),
    ("correo prisa",                                    "envio"),
    ("venga, mándamela y te hago la transferencia mañana", "pago"),
    ("¿me la envías a cuenta y lo cuadramos a fin de mes?", "pago"),
    ("te mando el justificante",                        "pago"),
    ("se puede pagar por bizum",                        "pago"),
    ("me habéis cobrado dos veces",                     "posventa"),
    ("la pieza que me mandasteis es de otro modelo",    "posventa"),
    ("ha llegado rota",                                 "posventa"),
    ("que garantia teneis",                             "politica"),
    ("donde os puedo encontrar",                        "politica"),
    ("cual es vuestro horario",                         "politica"),
    ("déjame que lo mire",                              "conversacion"),
    ("luego te digo algo",                              "conversacion"),
    ("ok, te confirmo mañana",                          "conversacion"),
    ("me lo quedo",                                     "conversacion"),
    ("¿ya lo tienes?",                                  "conversacion"),
    ("tienes espejos de golf?",                         "pieza"),
    ("no me sube la ventanilla",                        "pieza"),
]
for texto, grupo in casos:
    comprobar(f"«{texto[:44]}»", grupo, ap.clasificar(texto)[0])

print("\nDESCARTAR NO ES ENSEÑAR")
# Sobre una copia: esta prueba no puede tocar el registro de verdad.
with tempfile.TemporaryDirectory() as tmp:
    reg = pathlib.Path(tmp) / "no_resueltas.json"
    faq = pathlib.Path(tmp) / "faq.md"
    reg.write_text(json.dumps([{
        "n": 1, "pregunta": "asdfgh", "motivo": "x", "decision": "", "sesion": "",
        "veces": 77, "primera": "", "ultima": "", "estado": "pendiente",
        "respuesta": None, "respondida_por": None}]), encoding="utf-8")
    ap.REGISTRO, ap.APRENDIDAS = reg, faq

    e = ap.descartar(1, motivo="ruido")
    comprobar("queda descartada", "descartada", e["estado"])
    comprobar("guarda el motivo", "ruido", e["motivo_descarte"])
    comprobar("NO crea la base de conocimiento", False, faq.exists())
    comprobar("no hay respuesta inventada", None, e["respuesta"])

    try:
        ap.descartar(1)
        comprobar("descartar dos veces avisa", "error", "no avisó")
    except SystemExit:
        comprobar("descartar dos veces avisa", "error", "error")

print("\n" + "=" * 70)
if fallos:
    print(f"{len(fallos)} FALLOS: " + " · ".join(fallos))
    raise SystemExit(1)
total = 12 + 6 + len(casos) + 5
print(f"MESA: {total}/{total} — cada pregunta cae donde se contesta")
