"""
tests/test_conversaciones.py
============================
Banco de 100 CONVERSACIONES. No mide la búsqueda: mide el bot entero.

Diferencia con tests/test_busqueda.py: allí se comprueba si encuentra la ficha
correcta. Aquí se comprueba lo que de verdad le llega al cliente — el mensaje
escrito, el trato, si suelta un precio o se calla, y si vuelve a pedir un dato
que ya le dieron. Un buscador con 98% de acierto puede seguir escribiendo
mensajes que pierden ventas.

DOS COSAS DISTINTAS SE MIDEN AQUÍ
---------------------------------
1. INVARIANTES: cosas que NUNCA pueden pasar. Una sola vez que pasen, el banco
   falla entero. La principal: que se publique un precio que la búsqueda no
   autorizó.
2. ACIERTO POR CATEGORÍA: qué proporción de conversaciones acaba como debe.
   Esto sí admite porcentaje, porque hay casos genuinamente ambiguos.

Las conversaciones salen en su mayoría del propio catálogo, así que la respuesta
correcta se conoce sin escribirla a mano y siguen valiendo si el catálogo cambia.

Uso:
    python tests/test_conversaciones.py           # el banco entero
    python tests/test_conversaciones.py --ver     # además, escribe cada diálogo
    python tests/test_conversaciones.py --json salida/conversaciones.json
"""

import importlib.util
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def sin_tildes(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def ensuciar(texto):
    """Como llega de verdad por WhatsApp: sin tildes, sin signos y con prisa."""
    t = sin_tildes(texto).replace("?", "").replace("¿", "").replace(",", "")
    return (t.replace("para un", "pa un").replace("tenéis", "teneis")
             .replace("teneis", "teneis").replace("necesito", "nesecito"))


# ---------------------------------------------------------------------------
# LAS 100 CONVERSACIONES
# ---------------------------------------------------------------------------
# Cada caso: (categoria, perfil, [mensajes...], desenlace_esperado)
# El desenlace se juzga sobre el ÚLTIMO mensaje de la conversación.

def casos_de_catalogo(filas, buscar_mod):
    rnd = random.Random(23)
    casos = []

    def tokens(nombre):
        return {x for x in buscar_mod.normalizar(nombre)
                if x not in buscar_mod.PALABRAS_VACIAS and len(x) > 2}

    def cabeza(nombre):
        t = [x for x in buscar_mod.normalizar(nombre)
             if x not in buscar_mod.PALABRAS_VACIAS and len(x) > 2]
        return t[0] if t else ""

    def publicable(f):
        return ("onsultar" not in f["precio"]
                and f["disponibilidad"].lower() in ("en stock", "bajo pedido 24-48h"))

    vendibles = [f for f in filas if publicable(f)]
    muestra = rnd.sample(vendibles, 63)

    # --- 15 · pide la pieza exacta y espera precio -------------------------
    for f in muestra[:15]:
        casos.append(("precio exacto", "nuevo",
                      [f"¿tenéis {f['pieza'].lower()} para un {f['marca'].title()} "
                       f"{f['modelo']} {f['motor']}?"], "precio"))

    # --- 10 · por referencia OEM ------------------------------------------
    for f in muestra[15:25]:
        casos.append(("referencia OEM", "nuevo",
                      [f"hola, busco la referencia {f['referencia_oem']}"], "precio"))

    # --- 5 · por el número de stock de la web -----------------------------
    for f in muestra[25:30]:
        casos.append(("número de stock", "conocido",
                      [f"buenas, me interesa la pieza {f['id']} que tenéis en la web"],
                      "precio"))

    # --- 10 · mensaje sucio de WhatsApp -----------------------------------
    for f in muestra[30:40]:
        casos.append(("mensaje sucio", "nuevo",
                      [ensuciar(f"tenéis {f['pieza']} para un {f['marca']} "
                                f"{f['modelo']} {f['motor']}")], "precio"))

    # --- 10 · datos a medias ----------------------------------------------
    # El cliente nombra la pieza por su palabra principal y nada más. Si a la pieza
    # le faltan palabras ("faro" de "Faro delantero derecho"), el bot NO puede dar
    # precio: tiene que confirmar cuál. Pero si el nombre entero es esa palabra
    # ("Turbo", "Cárter"), el cliente SÍ la ha nombrado completa y dar el precio es
    # lo correcto. Esperar "confirma" en esos casos era un fallo de esta prueba, no
    # del bot.
    for f in muestra[40:50]:
        completa = len([x for x in buscar_mod.normalizar(f["pieza"])
                        if x not in buscar_mod.PALABRAS_VACIAS and len(x) > 2]) == 1
        casos.append(("datos a medias", "conocido",
                      [f"oye necesito algo para el {f['marca'].title()} {f['modelo']}",
                       f"{cabeza(f['pieza'])}, la que te digo siempre"],
                      "precio" if completa else "confirma"))

    # --- 7 · regatea después de recibir el precio -------------------------
    regateos = ["uf, está caro. ¿me lo dejas en algo menos?",
                "¿me puedes hacer un descuento?",
                "te doy la mitad y me lo llevo hoy",
                "lo he visto más barato en otro sitio",
                "¿ese es el último precio?",
                "es muy caro para lo que es",
                "¿hacemos precio si me llevo dos?"]
    for f, texto in zip(muestra[50:57], regateos):
        casos.append(("regatea", "conocido",
                      [f"¿cuánto vale {f['pieza'].lower()} para un "
                       f"{f['marca'].title()} {f['modelo']} {f['motor']}?", texto],
                      "escala"))

    # --- 4 · cierra la venta ----------------------------------------------
    cierres = ["perfecto, me lo quedo", "vale, lo quiero", "de acuerdo, adelante",
               "me lo llevo, mándamelo al taller"]
    for f, texto in zip(muestra[57:61], cierres):
        casos.append(("cierra la venta", "conocido",
                      [f"¿tenéis {f['pieza'].lower()} para un {f['marca'].title()} "
                       f"{f['modelo']} {f['motor']}?", texto], "cierra"))

    # --- 5 · conversaciones LARGAS ----------------------------------------
    # Aquí es donde se cae un bot: en el turno 6, cuando ya ha contestado lo fácil.
    # Estas prueban las tres cosas que se rompen en cuanto la charla se alarga —
    # que recuerde lo dicho, que no repita la misma frase, y que siga sabiendo de
    # qué pieza se hablaba tres mensajes atrás.
    a, b = muestra[61], muestra[62]
    casos.append(("conversación larga", "conocido", [
        f"buenas! ¿tenéis {a['pieza'].lower()} para un {a['marca'].title()} "
        f"{a['modelo']} {a['motor']}?",
        "¿y está comprobada?",
        "¿me llega esta semana?",
        "la matrícula es 4521 KBD",
        "¿y de garantía qué lleva?",
        "vale, déjame que lo consulte con el cliente",
        "sí, me lo quedo",
    ], "cierra"))
    casos.append(("conversación larga", "nuevo", [
        "hola",
        f"necesito algo para un {b['marca'].title()} {b['modelo']}",
        f"{b['pieza'].lower()}",
        "¿cuánto me costaría?",
        "uf, ¿no me lo puedes dejar mejor?",
        "ya te digo algo",
    ], "cualquiera"))
    casos.append(("conversación larga", "conocido", [
        "buenas, tengo un lío con una pieza",
        "es para un coche que entró ayer",
        "espera que miro la matrícula",
        "4521 KBD",
        f"era {a['pieza'].lower()}",
        "vale gracias",
    ], "cualquiera"))
    casos.append(("conversación larga", "nuevo", [
        f"¿tenéis {b['pieza'].lower()} de {b['marca'].title()} {b['modelo']}?",
        "¿seguro que encaja?",
        "es que no quiero volver a equivocarme",
        "vale, mándame el precio",
        "de acuerdo, adelante",
    ], "cierra"))
    casos.append(("conversación larga", "conocido", [
        f"necesito {a['pieza'].lower()} para un {a['marca'].title()} {a['modelo']}",
        "no, la otra",
        "la de siempre",
        "da igual, mándame la que tengas",
        "y cuánto tarda",
    ], "cualquiera"))

    # --- 15 · piezas que NO existen ---------------------------------------
    # Ausencia inequívoca: ninguna palabra del nombre existe para esa marca.
    # Si compartieran una sola palabra, el buscador podría ofrecer la hermana y
    # entonces el caso mediría otra cosa distinta de la que dice medir.
    vocabulario, modelos = {}, {}
    for f in filas:
        vocabulario.setdefault(f["marca"], set()).update(tokens(f["pieza"]))
        modelos.setdefault(f["marca"], set()).add(f["modelo"])
    piezas = sorted({f["pieza"] for f in filas})
    marcas = sorted(vocabulario)

    ausentes, intentos = [], 0
    while len(ausentes) < 10 and intentos < 8000:
        intentos += 1
        p, m = rnd.choice(piezas), rnd.choice(marcas)
        if tokens(p) & vocabulario.get(m, set()):
            continue
        pareja = (p, m)
        if pareja in ausentes:
            continue
        ausentes.append(pareja)
    for p, m in ausentes:
        casos.append(("no la tenemos", "nuevo",
                      [f"¿tenéis un {p.lower()} para un {m.title()} "
                       f"{rnd.choice(sorted(modelos[m]))}?"], "no la tengo"))

    return casos


def casos_escritos():
    """Conversaciones que no se pueden generar del catálogo: las de trato."""
    return [
        # --- 10 · condiciones de la empresa -------------------------------
        ("condiciones", "nuevo", ["la pieza tiene garantia?"], "política"),
        ("condiciones", "nuevo", ["cuanto tiempo tarda en llegar el pedido"], "política"),
        ("condiciones", "conocido", ["que pasa si la pieza sale defectuosa"], "política"),
        ("condiciones", "nuevo", ["puedo pasar a recogerla a la tienda?"], "política"),
        ("condiciones", "nuevo", ["envias a canarias?"], "política"),
        ("condiciones", "conocido", ["si no me vale la puedo devolver"], "política"),
        ("condiciones", "nuevo", ["que datos necesitas del coche para buscarla"], "política"),
        ("condiciones", "nuevo", ["me puedes hacer un descuento?"], "escala"),
        ("condiciones", "conocido", ["puedo pagar con tarjeta o bizum?"], "política"),
        ("condiciones", "nuevo", ["el precio lleva iva incluido?"], "política"),

        # --- 6 · quejas y devoluciones ------------------------------------
        ("queja", "conocido", ["el alternador que me mandasteis no funciona"], "escala"),
        ("queja", "conocido", ["me ha llegado la pieza rota"], "escala"),
        ("queja", "nuevo", ["esto es una estafa, no me ha llegado nada"], "escala"),
        ("queja", "conocido", ["la puerta que me vendisteis no encaja, quiero devolverla"],
         "escala"),
        ("queja", "nuevo", ["llevo 3 dias esperando y nadie me contesta"], "escala"),
        ("queja", "conocido", ["el motor vino con un golpe, quiero reclamar"], "escala"),

        # --- 4 · mete prisa ------------------------------------------------
        ("prisa", "conocido", ["necesito un turbo para un Seat Ibiza 1.9 TDI, corre prisa"],
         "cualquiera"),
        ("prisa", "nuevo", ["urgente, tengo el coche parado, necesito radiador"],
         "cualquiera"),
        ("prisa", "conocido", ["lo necesito para hoy si puede ser"], "cualquiera"),
        ("prisa", "nuevo", ["es para ya, el cliente me está esperando"], "cualquiera"),

        # --- 4 · ruido y fuera de tema ------------------------------------
        ("ruido", "nuevo", ["hola"], "pide datos"),
        ("ruido", "nuevo", ["buenas tardes, qué tal?"], "pide datos"),
        ("ruido", "nuevo", ["👍"], "pide datos"),
        ("ruido", "conocido", ["gracias!"], "cualquiera"),
    ]


# ---------------------------------------------------------------------------
# JUICIO
# ---------------------------------------------------------------------------

def clasificar(respuesta, busqueda):
    """Qué ha hecho el bot, en una palabra. El orden es la prioridad."""
    reglas = " · ".join(r["regla"] for r in respuesta["reglas"])
    if respuesta["precio_dado"]:
        return "precio"
    if respuesta["escala"] and "escalado a persona" in reglas:
        return "escala"
    if "cierre de venta" in reglas:
        return "cierra"
    if "política de la empresa" in reglas:
        return "política"
    if "precio retenido" in reglas:
        return "confirma"
    if busqueda["decision"] == "NO DISPONIBLE" or "no se ofrece una parecida" in reglas:
        return "no la tengo"
    if ("un dato por mensaje" in reglas or "no se reconoce" in reglas
            or "apertura" in reglas or "no repite la misma frase" in reglas):
        return "pide datos"
    if "memoria de conversación" in reglas:
        return "recuerda"
    return "otra cosa"


PROHIBIDO_TRATO = re.compile(r"\busted\b|\bpáse|\bdíga|\bsuya\b|\ble paso a\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


PIDE_MATRICULA = re.compile(r"pásame la matrícula|me la pasas", re.I)


def invariantes(respuesta, historial, matricula_dada):
    """Cosas que NUNCA pueden pasar. Devuelve la lista de las que se han roto."""
    rotos = []
    if not respuesta["precio_autorizado"]:
        rotos.append(f"FUGA DE PRECIO: publicó {respuesta['precio_dado']} sin permiso")
    if len(respuesta["lineas"]) > 3:
        rotos.append(f"formato: {len(respuesta['lineas'])} líneas (máximo 3)")
    if EMOJI.search(respuesta["mensaje"]):
        rotos.append("lleva emoji y el rol lo prohíbe")
    if PROHIBIDO_TRATO.search(respuesta["mensaje"]):
        rotos.append("trata de usted: sus ejemplos reales tutean siempre")
    if not respuesta["mensaje"].strip():
        rotos.append("mensaje vacío")

    # Regla §8.1: nunca vuelvas a pedir un dato que el cliente YA TE DIO. Ojo a la
    # diferencia — insistir en un dato que aún no ha dado es legítimo; pedirle otra
    # vez el que acaba de darte es lo que hace que se vaya.
    if matricula_dada and PIDE_MATRICULA.search(respuesta["mensaje"]):
        rotos.append("pide la matrícula que el cliente YA le había dado")

    # Repetir el mismo mensaje palabra por palabra es lo que delata a un bot. Dos
    # veces en una conversación puede colar; tres ya es un contestador automático.
    if historial and respuesta["mensaje"] == historial[-1]:
        rotos.append("repite palabra por palabra el mensaje anterior")
    elif historial.count(respuesta["mensaje"]) >= 2:
        rotos.append(f"dice por tercera vez «{respuesta['lineas'][0][:44]}…»")
    return rotos


def ejecutar(sistema, casos, ver=False):
    resultados = []
    for n, (categoria, perfil, mensajes, esperado) in enumerate(casos, start=1):
        sesion = f"banco-{n}"
        historial, turnos, rotos = [], [], []
        for i, mensaje in enumerate(mensajes):
            datos = sistema.chatear(sesion, mensaje, perfil=perfil,
                                    nombre="Juan Carlos" if perfil == "conocido" else "",
                                    reiniciar=(i == 0))
            bot, busqueda = datos["bot"], datos["busqueda"]
            # La matrícula se comprueba ANTES del mensaje del bot: si el cliente la
            # dio en este turno, el bot ya no puede volver a pedirla en su respuesta.
            rotos += invariantes(bot, historial, datos["memoria"]["matricula"])
            historial.append(bot["mensaje"])
            turnos.append({"cliente": mensaje, "bot": bot["lineas"],
                           "decision": busqueda["decision"], "ms": busqueda["ms"],
                           "reglas": [r["regla"] for r in bot["reglas"]],
                           "precio": bot["precio_dado"]})
        obtenido = clasificar(bot, busqueda)
        acierto = esperado == "cualquiera" or obtenido == esperado
        resultados.append({"n": n, "categoria": categoria, "perfil": perfil,
                           "esperado": esperado, "obtenido": obtenido,
                           "acierto": acierto, "rotos": rotos, "turnos": turnos})
        if ver:
            print(f"\n[{n:>3}] {categoria} · cliente {perfil}"
                  f"   esperado={esperado} obtenido={obtenido}"
                  f"{'  <-- FALLA' if not acierto else ''}")
            for t in turnos:
                print(f"      CLIENTE: {t['cliente']}")
                for l in t["bot"]:
                    print(f"      VENDIQ : {l}")
            for r in rotos:
                print(f"      !!! {r}")
    return resultados


def informe(resultados):
    por_cat = {}
    for r in resultados:
        d = por_cat.setdefault(r["categoria"], {"n": 0, "ok": 0})
        d["n"] += 1
        d["ok"] += r["acierto"]

    print("=" * 78)
    print(f"BANCO DE CONVERSACIONES — {len(resultados)} casos")
    print("=" * 78)
    print(f"{'situación':<22} {'n':>4} {'acaba como debe':>18}   fallos")
    for cat in sorted(por_cat):
        d = por_cat[cat]
        malos = [str(r["n"]) for r in resultados
                 if r["categoria"] == cat and not r["acierto"]]
        print(f"{cat:<22} {d['n']:>4} {d['ok']/d['n']:>17.0%}   "
              f"{', '.join(malos[:6]) if malos else '—'}")
    total_ok = sum(r["acierto"] for r in resultados)
    print("-" * 78)
    print(f"{'TOTAL':<22} {len(resultados):>4} {total_ok/len(resultados):>17.0%}")

    rotos = [(r["n"], r["categoria"], x) for r in resultados for x in r["rotos"]]
    print()
    print("=" * 78)
    print("INVARIANTES — lo que NUNCA puede pasar")
    print("=" * 78)
    if not rotos:
        print("  Ninguno roto en los 100 casos.")
        print("  · ni un precio publicado sin autorización de la búsqueda")
        print("  · ningún mensaje de más de 3 líneas, con emoji ni de usted")
    for n, cat, texto in rotos[:20]:
        print(f"  [{n:>3}] {cat}: {texto}")

    fallos = [r for r in resultados if not r["acierto"]]
    if fallos:
        print()
        print(f"Conversaciones que no acaban como deberían: {len(fallos)}")
        for r in fallos[:12]:
            print(f"  [{r['n']:>3}] {r['categoria']:<18} esperaba «{r['esperado']}» "
                  f"y salió «{r['obtenido']}»")
            print(f"        cliente: {r['turnos'][-1]['cliente']}")
            print(f"        VendIQ : {' / '.join(r['turnos'][-1]['bot'])}")

    print()
    ok = not rotos and total_ok / len(resultados) >= 0.85
    print("RESULTADO:", "PASA" if ok else "NO PASA")
    return 0 if ok else 1


def main():
    panel = cargar("06_panel.py", "panel")
    sistema = panel.Sistema()
    buscar_mod = sistema.buscar_mod

    casos = casos_de_catalogo(sistema.filas, buscar_mod) + casos_escritos()
    if len(casos) != 100:
        print(f"AVISO: el banco tiene {len(casos)} casos, no 100")

    resultados = ejecutar(sistema, casos, ver="--ver" in sys.argv)
    codigo = informe(resultados)

    if "--json" in sys.argv:
        destino = BASE / sys.argv[sys.argv.index("--json") + 1]
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        print(f"Detalle escrito en {destino}")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
