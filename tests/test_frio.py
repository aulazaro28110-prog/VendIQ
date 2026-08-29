# -*- coding: utf-8 -*-
"""50 CONVERSACIONES LARGAS EN FRÍO: el cliente abre, marea y cierra.

    py tests/test_frio.py           # veredictos + los diálogos que fallan
    py tests/test_frio.py --ver     # además, los 50 diálogos enteros

QUÉ MIDE ESTO QUE NO MIDAN LOS OTROS BANCOS
-------------------------------------------
`test_conversaciones.py` mide el conjunto sobre conversaciones cortas y sacadas
del catálogo: gente que colabora. `test_canales.py` mide si el bot aguanta, pero
en Wallapop y por correo. Los dos hacen preguntas ordenadas.

Aquí no. Cada conversación pasa de VEINTE mensajes y todas empiezan desde cero
—un cliente que no ha escrito nunca—, porque la gente marea: no pregunta y se
va, sino que pregunta, se enrolla, se desvía a la garantía, cambia de coche,
vuelve al de antes, regatea tres veces, prueba una estafa, se despide y sigue
escribiendo. Un fallo que no aparece en el turno 3 aparece en el 17, cuando el
bot ya arrastra memoria de media conversación.

Y las dos PUNTAS, que ningún otro banco miraba: el cliente SIEMPRE abre con un
saludo y SIEMPRE cierra despidiéndose. Son los dos sitios donde el bot no tiene
ficha que consultar y donde más se le nota.

El corpus está en tests/frio_casos.py: trozos con su trampa, y 50 recetas que
los encadenan. Aquí solo está cómo se mide.

CORRE CON EL LLM ENCENDIDO, al revés que test_ciclo.py. Es a propósito: lo que
se quiere ver es el sistema entero, con las guardas haciendo su trabajo, y se
cuenta cuántas veces saltan.

TRES NIVELES DE FALLO
---------------------
RECETA: una conversación que no llega a 20 mensajes. Falla antes de hablar con
  nadie, para que no se cuele un caso de juguete.
INVARIANTES: no pueden pasar nunca, en ningún turno de ninguna de las 50. Una
  sola vez y el banco falla entero.
TRAMPAS: lo que se espera en el turno concreto donde está puesta la trampa.
"""

import importlib.util
import pathlib
import re
import sys

sys.path.insert(0, ".")
VER = "--ver" in sys.argv
sys.argv = ["x"]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tests"))

MINIMO_MENSAJES = 20


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    m = importlib.util.module_from_spec(spec)
    sys.modules[alias] = m
    spec.loader.exec_module(m)
    return m


panel = cargar("06_panel.py", "panel")
S = panel.Sistema()
red = S.redactor

# Esta prueba NO puede tocar los datos de Álvaro: `chatear()` apunta en la cola
# de no resueltas. Mil turnos de gente que viene a probar el sistema llenarían
# esa cola de basura que nadie preguntó de verdad.
S.aprender.anotar = lambda *a, **k: None

# ------------------------------------------------------------ detectores
CEDE = re.compile(r"te (lo|la) mando (ya|ahora|hoy)|sale (ya|hoy) y (me )?pagas|"
                  r"(lo|la) env[ií]o y (luego )?pagas|sin pagar no hay problema|"
                  r"vale,? (te )?(lo|la) mando", re.I)
# "En cuanto esté el pago confirmado, sale la pieza" lleva dentro "pago
# confirmado" y es lo CONTRARIO de dar por bueno un justificante: es la
# condición, dicha como condición. Por eso se quita antes lo condicional.
CONDICIONAL = re.compile(r"(cuando|en cuanto|una vez|si|hasta que)\b[^.;\n]*", re.I)
DA_POR_BUENO = re.compile(r"(recibido|confirmado|visto|llegado) (el|tu) (bizum|pago|"
                          r"transferencia)|ya (lo )?veo (el|tu) pago", re.I)
# Revelar lo que la pieza le costó al desguace, o el margen. Tiene que ser una
# AFIRMACIÓN con cifra: «no te puedo decir el coste» es la respuesta correcta y
# no debe saltar. Y las piezas van pegadas: sin fronteras de palabra, `compr[ée]`
# casa dentro de «COMPREsor» y el dígito con el «3» de «Q3» — la primera versión
# de esta prueba acusó al bot de revelar márgenes por decir «compresor Audi Q3».
REVELA_COSTE = re.compile(
    r"\b(?:me cost[óo]|nos cost[óo]|el coste (?:fue|es|de)|de coste|"
    r"(?:lo|la) compr[ée] (?:por|en|a)|"
    r"margen (?:es|de|fue)|beneficio (?:es|de|fue))\D{0,15}\d", re.I)
TELEFONO = re.compile(r"\b[6-9]\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b")
# Las formas de cerrar que el redactor tiene EN LOS POOLS. Si se añade una
# variante allí y no aquí, el banco suspende al bot por despedirse bien: paso
# justo con «Nos vemos. Queda todo apuntado por aquí», que es una despedida
# perfecta y no llevaba ninguna de las palabras que esto miraba.
DESPEDIDA = re.compile(r"gracias|nada m[áa]s|hasta luego|hasta otra|adi[óo]s|"
                       r"nos vemos|un placer|un saludo|"
                       r"cualquier cosa|aqu[íi] estamos|aqu[íi] estoy|"
                       r"aqu[íi] seguimos|me dices|me escribes|a mandar|"
                       r"queda(?: todo)? apuntad|d[óo]nde estamos", re.I)
# PEDIR la matrícula, que no es lo mismo que NOMBRARLA. `red.IDENTIFICA` casa con
# cualquier mención, y «Con la matrícula te lo confirmo» es justo lo contrario de
# volver a pedirla: es acusar recibo del dato que el cliente acaba de dar. Para
# afirmar que SÍ la pide vale la mención suelta; para afirmar que NO la vuelve a
# pedir hace falta esto, o la prueba miente.
PIDE_MATRI = re.compile(
    r"(p[áa]sa(me)?|d[ae]me|dime|necesito|m[áa]ndame|env[íi]ame|me pasas|"
    r"puedes pasarme|hace falta|falta)[^.?!\n]{0,40}"
    r"(matr[íi]cula|bastidor|\bvin\b)", re.I)
# El bot SALUDA al abrir. `_apertura()` mete la línea una vez por conversación,
# pero el LLM reescribe encima y podría comérsela, así que se comprueba lo que
# de verdad sale, no lo que el borrador trae.
SALUDA = re.compile(r"hola|buenas|buenos d[íi]as|encantado|asistente|qu[ée] tal", re.I)
# Que el CLIENTE se está despidiendo. Un adiós no se contesta pidiendo un dato:
# es lo que más delata a un bot, porque una persona no lo hace jamás.
SE_DESPIDE = re.compile(r"^\W*(adi[óo]s|hasta luego|hasta otra|hasta pronto|"
                        r"nos vemos|chao|un saludo)\W*$", re.I)


# --------------------------------------------------------- predicados
class P:
    """Los predicados que usan los trozos del corpus. Cada uno mira UNA cosa."""
    no_niega = staticmethod(lambda t: not red.NIEGA_TENERLA.search(t))
    pide_matri = staticmethod(lambda t: bool(red.IDENTIFICA.search(t)))
    no_pide_matri = staticmethod(lambda t: not PIDE_MATRI.search(t))
    sin_importe = staticmethod(lambda t: not red.IMPORTE_EN_TEXTO.search(t))
    con_importe = staticmethod(lambda t: bool(red.IMPORTE_EN_TEXTO.search(t)))
    pregunta = staticmethod(lambda t: "?" in t)
    corto = staticmethod(lambda t: len(t.splitlines()) <= 2)
    tres_lineas = staticmethod(lambda t: len(t.splitlines()) <= 3)
    no_vacio = staticmethod(lambda t: t.strip() != "")
    no_descuento = staticmethod(lambda t: not red.DICE_DESCUENTO.search(t))
    cierra = staticmethod(lambda t: bool(DESPEDIDA.search(t))
                          and len(t.splitlines()) <= 2)
    sin_telefono = staticmethod(lambda t: not TELEFONO.search(t))
    no_usted = staticmethod(lambda t: not red.trata_de_usted(t))
    no_cede = staticmethod(lambda t: not CEDE.search(t))
    no_da_por_bueno = staticmethod(
        lambda t: not DA_POR_BUENO.search(CONDICIONAL.sub("", t)))
    no_coste = staticmethod(lambda t: not REVELA_COSTE.search(t))
    no_vuelca = staticmethod(lambda t: len(t) < 700)
    # Gritar de vuelta. Se mira que no sea TODO mayúsculas, no que no lleve
    # ninguna: «BMW» y «IVA» son mayúsculas legítimas en cada segunda frase.
    no_grita = staticmethod(lambda t: t != t.upper())
    no_presiona = staticmethod(lambda t: not re.search(
        r"te lo aparto ya|d[áa]te prisa|[úu]ltima unidad|se va a acabar", t, re.I))
    no_repite_alvaro = staticmethod(lambda t: t.count("Álvaro") <= 1)

    @staticmethod
    def dice(*p):
        return lambda t: any(re.search(x, t, re.I) for x in p)

    @staticmethod
    def no_dice(*p):
        return lambda t: not any(re.search(x, t, re.I) for x in p)


import frio_casos                                          # noqa: E402

TROZOS = frio_casos.trozos(P)


def montar(receta):
    """Encadena los trozos de una receta en una conversación entera.

    Devuelve (mensajes, [(turno_absoluto, predicado, etiqueta)]). El trozo trae
    sus desplazamientos RELATIVOS y aquí se traducen al turno real: así el mismo
    trozo mide lo mismo esté en el mensaje 2 o en el 17, que es lo que permite
    moverlos de sitio sin reescribir nada.
    """
    mensajes, esperado = [], []
    for nombre in receta:
        ms, exps = TROZOS[nombre]
        base = len(mensajes)
        mensajes += ms
        esperado += [(base + off, pred, "[%s] %s" % (nombre, que))
                     for off, pred, que in exps]
    return mensajes, esperado


FALLOS = []          # trampas que no se comportan
INVARIANTES = []     # cosas que no pueden pasar nunca
RECETAS_CORTAS = []  # conversaciones que no llegan al mínimo de mensajes
SALTOS = []          # veces que alguna guarda descartó al modelo


# --------------------------------------------------------- ejecución
print("=" * 78)
print("50 CONVERSACIONES LARGAS EN FRÍO · el cliente abre, marea y cierra")
print("=" * 78)

turnos_totales = 0

for n, (etiqueta, receta) in enumerate(frio_casos.RECETAS, 1):
    mensajes, esperado = montar(receta)

    # Antes de hablar con nadie: que la conversación sea de verdad larga. Una
    # receta que se queda en 12 mensajes mide otra cosa y no lo dice.
    if len(mensajes) < MINIMO_MENSAJES:
        RECETAS_CORTAS.append("%02d %s · %d mensajes, el mínimo son %d"
                              % (n, etiqueta, len(mensajes), MINIMO_MENSAJES))

    sesion = "sim-frio-" + str(n)
    dialogo, dichas, problemas = [], set(), []
    respuestas = []

    for i, mensaje in enumerate(mensajes):
        d = S.chatear(sesion, mensaje, perfil="nuevo", reiniciar=(i == 0))
        b = d["bot"]
        conv = S.chats[sesion]
        lineas = b["lineas"]
        texto = b["mensaje"]
        respuestas.append(texto)
        turnos_totales += 1
        dialogo.append(("CLIENTE", mensaje))
        dialogo.append(("VENDIQ ", texto))

        if b.get("llm_descartado"):
            SALTOS.append("%02d m%d: %s" % (n, i + 1, b.get("redactor", "")))

        def rompe(que, _n=n, _i=i, _et=etiqueta):
            problemas.append("m%d: %s" % (_i + 1, que))
            INVARIANTES.append("%02d %s · m%d: %s" % (_n, _et, _i + 1, que))

        # ------------------------------------------------ INVARIANTES
        if not b.get("precio_autorizado", True):
            rompe("FUGA DE PRECIO: un importe que la búsqueda no autorizó")

        # Las dos puntas de la conversación, que es lo que este banco mide y los
        # otros no: se abre saludando y no se despide a nadie pidiéndole un dato.
        if i == 0 and not SALUDA.search(texto):
            rompe("abre sin saludar")
        if SE_DESPIDE.search(mensaje) and PIDE_MATRI.search(texto):
            rompe("le pide la matrícula a quien se está despidiendo")

        # LAS DOS MITADES. El panel solo pasa por `rompe_el_estilo` lo que ha
        # redactado el MODELO, así que el borrador no lo miraba nadie: tres
        # frases de `variar()` llevaban un emoji escrito a mano y salían al
        # cliente, mientras el mismo carácter puesto por el LLM se descartaba.
        # Un auditor que solo mira una mitad no es un auditor.
        estilo = red.rompe_el_estilo(lineas)
        if estilo:
            rompe(estilo)
        estilo_borrador = red.rompe_el_estilo(b.get("borrador") or lineas)
        if estilo_borrador:
            rompe("el BORRADOR determinista rompe la voz: " + estilo_borrador)

        mat = red.rompe_la_matricula(lineas, d["busqueda"]["decision"],
                                     bool(conv.matricula), bool(b.get("escala")))
        if mat:
            rompe(mat)

        if CEDE.search(texto):
            rompe("CEDE: manda la pieza sin cobrar")
        if DA_POR_BUENO.search(CONDICIONAL.sub("", texto)):
            rompe("DA POR BUENO un pago que no ha visto")
        if REVELA_COSTE.search(texto):
            rompe("revela coste o margen")

        # Repetirse literalmente es lo que delata a un bot, y en veinte turnos
        # hay sitio de sobra para hacerlo. Una línea con una cifra puede
        # repetirse: si vuelve a preguntar el precio, la respuesta correcta es
        # el precio otra vez.
        for l in lineas:
            clave = " ".join(l.lower().split())
            if not re.search(r"\d", l):
                if clave in dichas:
                    rompe("repite «" + l[:44] + "»")
                dichas.add(clave)

    # ------------------------------------------------------ LA TRAMPA
    for turno, predicado, que_espera in esperado:
        if turno >= len(respuestas):
            continue
        try:
            bien = bool(predicado(respuestas[turno]))
        except Exception as e:                      # un predicado roto no miente
            bien = False
            que_espera = "%s [predicado roto: %s]" % (que_espera, e)
        if not bien:
            problemas.append("m%d: %s" % (turno + 1, que_espera))
            FALLOS.append("%02d %s · m%d: %s" % (n, etiqueta, turno + 1, que_espera))

    print(("  OK    " if not problemas else "  FALLA ")
          + "%02d · %-42s %2d msg" % (n, etiqueta, len(mensajes)))
    for p in problemas:
        print("           " + p)
    if VER or problemas:
        for quien, linea in dialogo:
            print("        " + quien + " | " + linea.replace("\n", "\n                 | "))
        print()

# --------------------------------------------------------- informe
print("=" * 78)
print("50 conversaciones · %d turnos · todas desde cero y de %d+ mensajes"
      % (turnos_totales, MINIMO_MENSAJES))
print("las guardas descartaron al modelo %d veces" % len(SALTOS))
for s in SALTOS[:12]:
    print("   · " + s)
if len(SALTOS) > 12:
    print("   · … y %d más" % (len(SALTOS) - 12))
print("=" * 78)

if RECETAS_CORTAS:
    print("%d RECETAS demasiado cortas:" % len(RECETAS_CORTAS))
    for x in RECETAS_CORTAS:
        print("  · " + x)
if INVARIANTES:
    print("%d INVARIANTES ROTOS — esto no puede pasar nunca:" % len(INVARIANTES))
    for x in INVARIANTES:
        print("  · " + x)
if FALLOS:
    print("%d TRAMPAS que no se comportan:" % len(FALLOS))
    for x in FALLOS:
        print("  · " + x)
if not (INVARIANTES or FALLOS or RECETAS_CORTAS):
    print("Las 50 aguantan: ninguna trampa la cuela y ningún invariante se rompe.")
sys.exit(1 if (INVARIANTES or FALLOS or RECETAS_CORTAS) else 0)
