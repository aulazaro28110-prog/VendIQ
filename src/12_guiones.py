# -*- coding: utf-8 -*-
"""
12_guiones.py
=============
Las CONVERSACIONES TIPO de verdad: 8 tipos, 50 guiones, evaluadas turno a turno.

Los guiones NO se escriben a mano enteros. Las plantillas viven en
`datos/guiones_tipo.json` con huecos (`{A}`, `{M}`, `{X}`…) y las expectativas por
turno; aquí se RELLENAN los huecos con piezas REALES del catálogo, con una semilla
fija, así que los guiones cambian solos si cambia el catálogo y siguen valiendo.

Regla de oro (D1): si un hueco no se puede rellenar, se LANZA un error con su
nombre y el del guion. Nunca se rellena con otra cosa en silencio —eso es lo que
hacía que el guion «No la tenemos» cayera siempre en el Ferrari sin probar nada.

La evaluación por turno (`evaluar_turno`) es la ÚNICA definición: por dentro
reutiliza `clasificar()` e `invariantes()` de `tests/test_conversaciones.py` y las
reglas de la voz de `07_redactor.py`. No se copia ninguna.

Uso:
    py src/12_guiones.py --validar          # comprueba los 50 y el recuento
    py src/12_guiones.py --ver G13          # imprime un guion ya rellenado
"""
import argparse
import importlib.util
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # raíz: el código vive en src/
PLANTILLAS = BASE / "datos" / "guiones_tipo.json"


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, Path(__file__).resolve().parent / fichero)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[alias] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def sin_tildes(t):
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()


class GuionError(Exception):
    """Un hueco que no se puede rellenar. Lleva el hueco y el guion (D1/C2)."""


# Nombres de cliente de confianza, lista sintética fija (Anexo C · {N}).
NOMBRES_CONFIANZA = ["Juan Carlos", "Roberto", "Marisa", "Toñi", "Paco",
                     "Luismi", "Nerea", "Iván"]

# Modelos reales que NO están en el catálogo, para {A.modelo_falso} (Anexo D).
MODELOS_FALSOS = {
    "BMW": "Serie 5", "AUDI": "A6", "VOLKSWAGEN": "Tiguan",
    "MERCEDES-BENZ": "Vito", "RENAULT": "Kadjar", "KIA": "Picanto",
    "HYUNDAI": "Kona", "CITROEN": "C5", "CITROËN": "C5", "TOYOTA": "Yaris",
    "PEUGEOT": "508", "OPEL": "Insignia", "SEAT": "Arona", "FORD": "Kuga",
    "NISSAN": "Micra", "SKODA": "Kodiaq", "ŠKODA": "Kodiaq",
}

CONSONANTES = "BCDFGHJKLMNPRSTVWXYZ"          # matrículas: solo consonantes
VIN_LETRAS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"   # sin I, O ni Q


# ---------------------------------------------------------------------------
# EL CATÁLOGO INDEXADO — todo sale de sistema.filas, no de listas a mano
# ---------------------------------------------------------------------------
class Catalogo:
    def __init__(self, sistema):
        self.sistema = sistema
        self.buscar = sistema.buscar_mod
        self.ofertas = sistema.ofertas_mod
        self.tipos_conocidos = sistema.buscador.tipos_conocidos
        self.filas = sistema.filas

        def precio(f):
            return self.ofertas.precio_publicado(f.get("precio", ""))

        self.en_stock = [f for f in self.filas
                         if f["disponibilidad"].strip().lower() == "en stock"
                         and precio(f)]
        self.bajo_pedido = [f for f in self.filas
                            if "bajo pedido" in f["disponibilidad"].lower()
                            and precio(f)]
        # (marca, modelo) -> fichas en stock con precio
        self.por_modelo = {}
        for f in self.en_stock:
            self.por_modelo.setdefault((f["marca"], f["modelo"]), []).append(f)
        # tokens de pieza por modelo (para ausencias y hermanos)
        self.piezas_de = {k: {self.cabeza(f["pieza"]) for f in v}
                          for k, v in self.por_modelo.items()}
        # cabezas de pieza por modelo en TODO el catálogo (cualquier
        # disponibilidad). Una ausencia {X} tiene que faltar aquí, no solo en
        # stock: si está «bajo pedido» el buscador la encuentra y la pone precio,
        # y el guion de «no la tenemos» dejaría de probar nada (el mismo fallo
        # que la reserva del Ferrari, pero al revés).
        self.piezas_de_todo = {}
        for f in self.filas:
            self.piezas_de_todo.setdefault((f["marca"], f["modelo"]), set()).add(
                self.cabeza(f["pieza"]))
        self.modelos_de_marca = {}
        for (marca, modelo) in self.por_modelo:
            self.modelos_de_marca.setdefault(marca, set()).add(modelo)
        # tipos de una sola palabra que existen en stock en algún modelo
        self.tipos_una_palabra = set()
        for f in self.en_stock:
            toks = self.tok(f["pieza"])
            if len(toks) == 1 and toks[0] in self.tipos_conocidos:
                self.tipos_una_palabra.add(toks[0])

    def tok(self, nombre):
        return [x for x in self.buscar.normalizar(nombre)
                if x not in self.buscar.PALABRAS_VACIAS and len(x) > 2]

    def cabeza(self, nombre):
        t = self.tok(nombre)
        return t[0] if t else ""

    def tiene_lado(self, f):
        return bool({t for t in self.buscar.normalizar(f["pieza"])
                     if t in self.buscar.LADOS})

    def precio_ok(self, f):
        """True si el bot le pone precio publicable a ESTA ficha con su matrícula.

        Lo comprueba con la búsqueda de verdad (no un proxy): un turno que espera
        «precio» solo vale si la pieza puntúa por encima del umbral y es la mejor
        candidata. Así el guion no espera un precio que el bot va a retener.
        """
        try:
            bus = self.sistema.consultar(_pedir(f), coche_identificado=True)
        except Exception:
            return False
        for r in bus.get("resultados", []):
            if r.get("tipo") != "inventario":
                continue
            if not (r.get("precio_cliente") or {}).get("publicable"):
                continue
            if str((r.get("meta") or {}).get("id")) == str(f["id"]):
                return True
        return False


# ---------------------------------------------------------------------------
# RESOLVER DE HUECOS — por guion, en orden de dependencia, con semilla
# ---------------------------------------------------------------------------
class Resolutor:
    def __init__(self, cat, rnd, guion_id):
        self.cat = cat
        self.rnd = rnd
        self.gid = guion_id
        self.cache = {}     # root -> ficha o valor
        self.necesita = set()   # pares (root, sub) que usa el guion

    def fallo(self, hueco):
        raise GuionError(f"{self.gid}: no se puede rellenar «{{{hueco}}}»")

    def _usa(self, root, sub=None):
        return any(r == root and (sub is None or s == sub) for (r, s) in self.necesita)

    # --- entidades base (eligen un candidato que cumpla lo que el guion pide) -
    def _A_sirve(self, f):
        """True si este A permite rellenar todos los huecos A-dependientes."""
        marca, modelo = f["marca"], f["modelo"]
        cab = self.cat.cabeza(f["pieza"])
        otras = {self.cat.cabeza(g["pieza"])
                 for g in self.cat.por_modelo.get((marca, modelo), [])} - {cab}
        if self._usa("A2") and len(otras) < 1:
            return False
        if self._usa("A3") and len(otras) < 2:
            return False
        if self._usa("A", "motor_otro"):
            motores = {g["motor"] for g in self.cat.por_modelo.get((marca, modelo), [])
                       if self.cat.cabeza(g["pieza"]) == cab}
            if len(motores) < 2:
                return False
        if self._usa("A", "modelo_falso") and marca.upper() not in MODELOS_FALSOS:
            return False
        if self._usa("CM"):
            if not any(m != marca and cab in self.cat.piezas_de.get((m, mm), set())
                       for m in self.cat.modelos_de_marca
                       for mm in self.cat.modelos_de_marca[m] if m != marca):
                return False
        if self._usa("C"):
            ok = False
            for m in self.cat.modelos_de_marca.get(marca, set()):
                if m == modelo:
                    continue
                comp = self.cat.piezas_de.get((marca, m), set())
                if cab in comp and len((comp & otras)) >= 1:
                    ok = True
                    break
            if not ok:
                return False
        return True

    def A(self):
        if "A" in self.cache:
            return self.cache["A"]
        # SIN LADO: una pieza con lado («puerta delantera izquierda») tiene
        # hermana (derecha) y el buscador retiene el precio hasta desambiguar, así
        # que el turno que espera «precio» no lo daría. El lado es cosa de {AL}.
        cand = [f for f in self.cat.en_stock
                if self.cat.cabeza(f["pieza"]) in self.cat.tipos_conocidos
                and not self.cat.tiene_lado(f)]
        self.rnd.shuffle(cand)
        intentos = 0
        for f in cand:
            if not self._A_sirve(f):
                continue
            intentos += 1
            if intentos > 120:
                break
            if self.cat.precio_ok(f):
                self.cache["A"] = f
                return f
        self.fallo("A")

    def _otra_del_modelo(self, base, usadas, con_lado=None):
        marca, modelo = base["marca"], base["modelo"]
        cab_usadas = {self.cat.cabeza(u["pieza"]) for u in usadas}
        opciones = [f for f in self.cat.por_modelo.get((marca, modelo), [])
                    if self.cat.cabeza(f["pieza"]) not in cab_usadas]
        if con_lado is True:
            opciones = [f for f in opciones if self.cat.tiene_lado(f)]
        elif con_lado is False:
            opciones = [f for f in opciones if not self.cat.tiene_lado(f)]
        self.rnd.shuffle(opciones)
        return opciones[0] if opciones else None

    def A2(self):
        if "A2" in self.cache:
            return self.cache["A2"]
        a = self.A()
        if self._usa("C"):
            # con C en juego, A2 se elige COMPARTIDA con el hermano que tiene A.pieza
            cab_a = self.cat.cabeza(a["pieza"])
            mios = {self.cat.cabeza(g["pieza"])
                    for g in self.cat.por_modelo[(a["marca"], a["modelo"])]} - {cab_a}
            for m in self.cat.modelos_de_marca.get(a["marca"], set()):
                if m == a["modelo"]:
                    continue
                comp = self.cat.piezas_de.get((a["marca"], m), set())
                if cab_a in comp:
                    compartidas = (comp & mios)
                    if compartidas:
                        for g in self.cat.por_modelo[(a["marca"], a["modelo"])]:
                            if self.cat.cabeza(g["pieza"]) in compartidas:
                                self.cache["A2"] = g
                                return g
        f = self._otra_del_modelo(a, [a])
        if not f:
            self.fallo("A2")
        self.cache["A2"] = f
        return f

    def A3(self):
        if "A3" in self.cache:
            return self.cache["A3"]
        f = self._otra_del_modelo(self.A(), [self.A(), self.A2()])
        if not f:
            self.fallo("A3")
        self.cache["A3"] = f
        return f

    def P(self):
        if "P" in self.cache:
            return self.cache["P"]
        cand = list(self.cat.bajo_pedido)
        self.rnd.shuffle(cand)
        if not cand:
            self.fallo("P")
        self.cache["P"] = cand[0]
        return cand[0]

    def B(self):
        if "B" in self.cache:
            return self.cache["B"]
        marca_a = self.A()["marca"]
        cand = [f for f in self.cat.en_stock if f["marca"] != marca_a
                and self.cat.cabeza(f["pieza"]) in self.cat.tipos_conocidos
                and not self.cat.tiene_lado(f)]
        self.rnd.shuffle(cand)
        for f in cand[:120]:
            if self.cat.precio_ok(f):
                self.cache["B"] = f
                return f
        self.fallo("B")

    def AA(self):
        if "AA" in self.cache:
            return self.cache["AA"]
        cand = [f for f in self.cat.en_stock
                if "alternador" in self.cat.tok(f["pieza"])]
        self.rnd.shuffle(cand)
        if not cand:
            self.fallo("AA")
        self.cache["AA"] = cand[0]
        return cand[0]

    def AL(self):
        if "AL" in self.cache:
            return self.cache["AL"]
        # pieza con lado cuyo OTRO lado también está en stock para ese modelo
        conlado = [f for f in self.cat.en_stock if self.cat.tiene_lado(f)]
        self.rnd.shuffle(conlado)
        for f in conlado:
            lados = {t for t in self.cat.buscar.normalizar(f["pieza"])
                     if t in self.cat.buscar.LADOS}
            cab = self.cat.cabeza(f["pieza"])
            hermanas = [g for g in self.cat.por_modelo.get((f["marca"], f["modelo"]), [])
                        if self.cat.cabeza(g["pieza"]) == cab and g["id"] != f["id"]
                        and {t for t in self.cat.buscar.normalizar(g["pieza"])
                             if t in self.cat.buscar.LADOS} != lados]
            if hermanas:
                self.cache["AL"] = f
                return f
        self.fallo("AL")

    def AL2(self):
        if "AL2" in self.cache:
            return self.cache["AL2"]
        f = self._otra_del_modelo(self.AL(), [self.AL()], con_lado=False)
        if not f:
            self.fallo("AL2")
        self.cache["AL2"] = f
        return f

    def X(self):
        """Una ausencia marca+modelo+pieza (pieza de una sola palabra)."""
        if "X" in self.cache:
            return self.cache["X"]
        modelos = list(self.cat.por_modelo)
        self.rnd.shuffle(modelos)
        for (marca, modelo) in modelos:
            # AUSENTE DE TODO EL CATÁLOGO (ni en stock ni bajo pedido), no solo
            # de lo que hay en stock: si no, el buscador la encuentra bajo pedido.
            presentes_todo = self.cat.piezas_de_todo.get((marca, modelo), set())
            faltan = self.cat.tipos_una_palabra - presentes_todo
            # y que exista EN STOCK en otro modelo de la MISMA marca (para {Xs})
            faltan = [t for t in faltan if any(
                t in self.cat.piezas_de.get((marca, m), set())
                for m in self.cat.modelos_de_marca.get(marca, set()) if m != modelo)]
            # con ≥3 piezas en stock en ese modelo, para {X.otra} y {X.otra2}
            if not faltan or len(self.cat.piezas_de.get((marca, modelo), set())) < 3:
                continue
            tipo = sorted(faltan)[0]
            self.cache["X"] = {"marca": marca, "modelo": modelo, "pieza": tipo}
            return self.cache["X"]
        self.fallo("X")

    def X_otra(self, n):
        x = self.X()
        presentes = [f for f in self.cat.por_modelo[(x["marca"], x["modelo"])]]
        self.rnd.shuffle(presentes)
        if len(presentes) <= n:
            self.fallo("X.otra" + ("2" if n else ""))
        return presentes[n]

    def Xs(self):
        if "Xs" in self.cache:
            return self.cache["Xs"]
        x = self.X()
        for m in self.cat.modelos_de_marca.get(x["marca"], set()):
            if m != x["modelo"] and x["pieza"] in self.cat.piezas_de.get((x["marca"], m), set()):
                self.cache["Xs"] = {"marca": x["marca"], "modelo": m, "pieza": x["pieza"]}
                return self.cache["Xs"]
        self.fallo("Xs")

    def C(self):
        """Hermano de A (misma marca) con A.pieza y A2.pieza en stock."""
        if "C" in self.cache:
            return self.cache["C"]
        a, a2 = self.A(), self.A2()
        ca, ca2 = self.cat.cabeza(a["pieza"]), self.cat.cabeza(a2["pieza"])
        for m in self.cat.modelos_de_marca.get(a["marca"], set()):
            if m == a["modelo"]:
                continue
            piezas = self.cat.piezas_de.get((a["marca"], m), set())
            if ca in piezas and ca2 in piezas:
                self.cache["C"] = {"marca": a["marca"], "modelo": m}
                return self.cache["C"]
        self.fallo("C")

    def CM(self):
        """Modelo de OTRA marca con A.pieza en stock."""
        if "CM" in self.cache:
            return self.cache["CM"]
        a = self.A()
        ca = self.cat.cabeza(a["pieza"])
        marcas = list(self.cat.modelos_de_marca)
        self.rnd.shuffle(marcas)
        for marca in marcas:
            if marca == a["marca"]:
                continue
            for m in self.cat.modelos_de_marca[marca]:
                if ca in self.cat.piezas_de.get((marca, m), set()):
                    self.cache["CM"] = {"marca": marca, "modelo": m, "pieza": a["pieza"]}
                    return self.cache["CM"]
        self.fallo("CM")

    def A_motor_otro(self):
        a = self.A()
        ca = self.cat.cabeza(a["pieza"])
        for f in self.cat.por_modelo.get((a["marca"], a["modelo"]), []):
            if self.cat.cabeza(f["pieza"]) == ca and f["motor"] != a["motor"]:
                return f["motor"]
        self.fallo("A.motor_otro")

    def matricula(self):
        return (f"{self.rnd.randint(0, 9999):04d} "
                + "".join(self.rnd.choice(CONSONANTES) for _ in range(3)))

    def vin(self):
        return "".join(self.rnd.choice(VIN_LETRAS) for _ in range(17))

    def nombre(self):
        return self.rnd.choice(NOMBRES_CONFIANZA)


# ---------------------------------------------------------------------------
# RENDER DE HUECOS
# ---------------------------------------------------------------------------
_GENERO_FEM = ("bomba", "puerta", "rueda", "correa", "junta", "tapa", "luna",
               "bobina", "manguera", "valvula", "culata", "cerradura",
               "centralita", "caja", "bandeja", "polea", "sonda")


def _articulo(pieza):
    cab = sin_tildes(pieza).split()[0] if pieza else ""
    return "una" if cab in _GENERO_FEM else "un"


def _coche(f):
    return f"{f['marca'].title()} {f['modelo']}"


def _pedir(f):
    return f"{f['pieza'].lower()} para un {f['marca'].title()} {f['modelo']} {f['motor']}"


def _render_hueco(root, sub, res, cat):
    """Devuelve el texto de un hueco {root} o {root.sub}."""
    # matrículas, VIN, nombre
    if root == "M":
        return res.cache.setdefault("M", res.matricula())
    if root == "M2":
        return res.cache.setdefault("M2", res.matricula())
    if root == "VIN":
        return res.cache.setdefault("VIN", res.vin())
    if root == "N":
        return res.cache.setdefault("N", res.nombre())

    # entidades tipo ausencia (dicts con marca/modelo/pieza)
    if root in ("X", "Xs"):
        ent = res.X() if root == "X" else res.Xs()
        if sub == "pieza":
            return ent["pieza"].lower()
        if sub == "coche":
            return f"{ent['marca'].title()} {ent['modelo']}"
        if sub == "marca":
            return ent["marca"].title()
        if sub == "modelo":
            return ent["modelo"]
        if sub == "motor":
            filas = cat.por_modelo.get((ent["marca"], ent["modelo"]), [])
            return filas[0]["motor"] if filas else ""
        if sub in ("otra", "otra2"):
            f = res.X_otra(0 if sub == "otra" else 1)
            return f["pieza"].lower()
        if sub is None:   # {X} bare
            return f"{_articulo(ent['pieza'])} {ent['pieza'].lower()} para un {ent['marca'].title()} {ent['modelo']}"
    if root in ("C", "CM"):
        ent = res.C() if root == "C" else res.CM()
        if sub == "modelo":
            return ent["modelo"]
        if sub == "marca":
            return ent["marca"].title()
        if sub == "coche":
            return f"{ent['marca'].title()} {ent['modelo']}"
        if sub == "pieza":
            return ent.get("pieza", "").lower()

    # fichas reales (A, A2, A3, AL, AL2, AA, B, P)
    ficha = {"A": res.A, "A2": res.A2, "A3": res.A3, "AL": res.AL, "AL2": res.AL2,
             "AA": res.AA, "B": res.B, "P": res.P}.get(root)
    if ficha is not None:
        f = ficha()
        if sub is None:
            return _pedir(f)
        if sub == "pieza":
            return f["pieza"].lower()
        if sub == "coche":
            return _coche(f)
        if sub == "marca":
            return f["marca"].title()
        if sub == "modelo":
            return f["modelo"]
        if sub == "motor":
            return f["motor"]
        if sub == "motor_otro":
            return res.A_motor_otro()
        if sub == "oem":
            return f.get("referencia_oem", "")
        if sub == "id":
            return f["id"]
        if sub == "modelo_falso":
            falso = MODELOS_FALSOS.get(f["marca"].upper())
            if not falso:
                res.fallo(f"{root}.modelo_falso")
            return falso
        if sub == "cabeza":     # pieza sin el lado
            toks = [t for t in cat.buscar.normalizar(f["pieza"])
                    if t not in cat.buscar.LADOS]
            return " ".join(toks)
        if sub == "lado":
            toks = [t for t in cat.buscar.normalizar(f["pieza"]) if t in cat.buscar.LADOS]
            return " ".join(toks)
    res.fallo(f"{root}.{sub}" if sub else root)


_HUECO = re.compile(r"\{([A-Za-z]+[0-9]*)(?:\.([a-z_0-9]+))?\}")


def _rellenar(texto, res, cat):
    def sub(m):
        return str(_render_hueco(m.group(1), m.group(2), res, cat))
    return _HUECO.sub(sub, texto)


# ---------------------------------------------------------------------------
# CONSTRUIR
# ---------------------------------------------------------------------------
def _plantillas():
    datos = json.loads(PLANTILLAS.read_text(encoding="utf-8-sig"))
    return datos


def construir(sistema, semilla=11):
    """Los 50 guiones rellenados con el catálogo. Lanza GuionError si un hueco falla."""
    datos = _plantillas()
    cat = Catalogo(sistema)
    guiones = []
    for plantilla in datos["guiones"]:
        rnd = random.Random(f"{semilla}-{plantilla['id']}")
        res = Resolutor(cat, rnd, plantilla["id"])
        # qué huecos usa este guion, para que A/AL/X elijan un candidato válido
        pares = set()
        for turno in plantilla["turnos"]:
            for campo in [turno["cliente"], *(turno.get("mem") or [])]:
                for m in _HUECO.finditer(campo):
                    pares.add((m.group(1), m.group(2)))
        if plantilla.get("perfil") == "conocido":
            pares.add(("N", None))
        res.necesita = pares
        mensajes, esperado = [], []
        for turno in plantilla["turnos"]:
            mensajes.append(_rellenar(turno["cliente"], res, cat))
            esperado.append({
                "esperado": turno.get("esperado", "cualquiera"),
                "nunca": turno.get("nunca", []),
                "mem": [_rellenar(s, res, cat) for s in (turno.get("mem") or [])],
                "decision_pendiente": bool(turno.get("decision_pendiente")),
            })
        guiones.append({
            "id": plantilla["id"],
            "tipo": plantilla["tipo"],
            "tipos_mezcla": plantilla.get("tipos_mezcla", []),
            "nombre": plantilla["nombre"],
            "perfil": plantilla.get("perfil", "nuevo"),
            "cliente": _rellenar("{N}", res, cat) if plantilla.get("perfil") == "conocido" else "",
            "que_prueba": plantilla.get("que_prueba", ""),
            "mensajes": mensajes,
            "esperado": esperado,
            "decision_pendiente": any(e["decision_pendiente"] for e in esperado),
        })
    return guiones


# ---------------------------------------------------------------------------
# VALIDAR (C1, C2)
# ---------------------------------------------------------------------------
TIPOS = ["compra", "regatea", "no_hay", "a_medias", "posventa", "taller",
         "corrige", "pago"]

VOCAB_ESPERADO = {"precio", "confirma", "pide datos", "no la tengo", "escala",
                  "cierra", "política", "aparca", "sigue", "recuerda",
                  "otra cosa", "cualquiera", "recuerda|precio", "sigue|cualquiera"}


def validar(guiones):
    errores = []
    if len(guiones) != 50:
        errores.append(f"hay {len(guiones)} guiones, deben ser 50 (C1)")
    por_tipo = {}
    mezclas = 0
    for g in guiones:
        por_tipo.setdefault(g["tipo"], []).append(g["id"])
        if g["tipo"] not in TIPOS:
            errores.append(f"{g['id']}: tipo desconocido «{g['tipo']}»")
        if g["tipos_mezcla"]:
            mezclas += 1
        n = len(g["mensajes"])
        if not (10 <= n <= 15):
            errores.append(f"{g['id']}: {n} mensajes, deben ser 10-15 (C1)")
        # huecos sin rellenar
        for m in g["mensajes"]:
            if _HUECO.search(m):
                errores.append(f"{g['id']}: hueco sin rellenar en «{m}»")
        # vocabulario de expectativas (Anexo B)
        for e in g["esperado"]:
            for etq in re.split(r"\|", e["esperado"]):
                if etq and etq not in {"precio", "confirma", "pide datos",
                                       "no la tengo", "escala", "cierra",
                                       "política", "aparca", "sigue", "recuerda",
                                       "otra cosa", "cualquiera"}:
                    errores.append(f"{g['id']}: etiqueta esperada desconocida «{etq}»")
    if mezclas < 10:
        errores.append(f"solo {mezclas} guiones mezclan tipos, deben ser ≥10 (C1)")
    for t in TIPOS:
        if t not in por_tipo:
            errores.append(f"falta el tipo «{t}» (C1)")
    return errores


# ---------------------------------------------------------------------------
# EVALUAR_TURNO — la única definición (reusa clasificar/invariantes/redactor)
# ---------------------------------------------------------------------------
# Preguntas de plazo/entrega (EXPECT A).
_PLAZO = re.compile(r"\bcu[aá]ndo\b|cu[aá]nto tarda|tarda en llegar|recojo|recoger",
                    re.IGNORECASE)

_test = None
_redactor = None


def _cargar_evaluadores():
    global _test, _redactor
    if _test is not None:
        return
    _redactor = cargar("07_redactor.py", "redactor")
    _test = cargar(BASE / "tests" / "test_conversaciones.py", "test_conversaciones")
    _test.redactor = _redactor
    _test.conversar = cargar("08_conversar.py", "conversar")


def evaluar_turno(esperado, datos_turno, estado_previo=None):
    """{ok, obtenido, fallos[]} para un turno. `datos_turno` es lo que devuelve
    chatear() más `pieza_pedida` y `matricula_dada` del propio Sistema."""
    _cargar_evaluadores()
    bot = datos_turno["bot"]
    busqueda = datos_turno["busqueda"]
    fallos = []

    obtenido = _test.clasificar(bot, busqueda)
    etiquetas = esperado.get("esperado", "cualquiera").split("|")
    ok_etiqueta = "cualquiera" in etiquetas or obtenido in etiquetas

    # EXPECT A (decidido en la Fase 3): a una pregunta de plazo («¿cuándo llega?»),
    # contestar con el plazo de la pieza que YA está sobre la mesa («recuerda») vale
    # tanto como citar la política general de envíos.
    if (not ok_etiqueta and "política" in etiquetas and obtenido == "recuerda"
            and _PLAZO.search(busqueda.get("pregunta", "") or "")):
        ok_etiqueta = True

    # invariantes de la voz (importe, estilo, matrícula, identificación, repetición)
    rotos = _test.invariantes(bot, datos_turno.get("historial", []),
                              datos_turno.get("matricula_dada"),
                              busqueda["decision"], busqueda)
    fallos += rotos

    # no_olvida_pieza (D2) — reusa la regla de 07_redactor
    olvido = _redactor.rompe_el_olvido_de_pieza(
        bot["lineas"], datos_turno.get("pieza_pedida"))
    if olvido:
        fallos.append(olvido)

    # comprobaciones `nunca:` del turno (Anexo B)
    for comprobacion in esperado.get("nunca", []):
        fallo = _nunca(comprobacion, datos_turno)
        if fallo:
            fallos.append(f"{comprobacion}: {fallo}")

    return {"ok": ok_etiqueta and not fallos, "obtenido": obtenido,
            "esperado": esperado.get("esperado"), "fallos": fallos}


# Patrones para las comprobaciones `nunca:` de texto (Anexo B). Frágiles: sus
# falsos positivos se miden contra el banco real en la Fase 3 y se ajustan.
_PAT = {
    "no_baja": re.compile(r"te lo dejo en|rebaj|descuent[oa] de|precio especial|te hago "
                          r"un precio", re.I),
    "no_envia_sin_pago": re.compile(r"(te lo|la|lo) mando (ya|hoy|sin)|sale (hoy|ya) sin pagar|"
                                    r"env[ií]o antes de|pago al recibir", re.I),
    "no_valida_justificante": re.compile(r"recibido el pago|pago confirmado|ya (lo )?tengo el "
                                         r"(pago|justificante|bizum)|comprobante recibido|"
                                         r"veo (el|tu) (pago|justificante|bizum)", re.I),
    "no_diagnostica": re.compile(r"lo que (te )?falla es|el problema es (el|la|tu)|seguro que es "
                                 r"(el|la)|tienes (roto|estropeado)", re.I),
    "no_promete": re.compile(r"te (devuelvo|reembolso|cambio) el|te mando otro|reembolso garantizado|"
                             r"te lo cambiamos", re.I),
    "no_simula": re.compile(r"[áa]lvaro ya lo ha (visto|mirado|revisado)|ya ha salido|ya te lo "
                            r"he enviado|ya est[áa] en camino", re.I),
}


def _texto(datos_turno):
    return "\n".join(datos_turno["bot"]["lineas"])


def _nunca(nombre, datos_turno):
    bot, busqueda = datos_turno["bot"], datos_turno["busqueda"]
    texto = _texto(datos_turno)
    if nombre == "sin_precio":
        return f"dio precio {bot['precio_dado']!r}" if bot.get("precio_dado") else None
    if nombre == "importe_no_autorizado":
        return None if bot.get("precio_autorizado", True) else "FUGA DE PRECIO"
    if nombre == "no_pide_matricula":
        if datos_turno.get("matricula_dada") and _redactor.rompe_la_matricula and \
                re.search(r"p[áa]same la matr[íi]cula|me la pasas", texto, re.I):
            return "pide la matrícula ya dada"
        return None
    if nombre == "no_dice_no":
        roto = _redactor.rompe_la_matricula(bot["lineas"], busqueda["decision"],
                                            datos_turno.get("matricula_dada"),
                                            bool(bot.get("escala")))
        return roto
    if nombre == "no_olvida_pieza":
        return _redactor.rompe_el_olvido_de_pieza(bot["lineas"],
                                                  datos_turno.get("pieza_pedida"))
    if nombre == "no_parecida":
        # tras un «no», no puede colar otra ficha con precio como si encajara
        reglas = [r["regla"] for r in bot["reglas"]]
        if busqueda["decision"] == "NO DISPONIBLE" and bot.get("precio_dado"):
            return "ofrece un precio tras un «no»"
        return None
    if nombre == "no_asegura":
        return _redactor.rompe_la_identificacion(bot["lineas"], None, False)
    if nombre in _PAT:
        return "patrón detectado" if _PAT[nombre].search(texto) else None
    if nombre in ("no_reabre", "no_inventa", "ficha_del_coche_anterior"):
        # se calibran en la Fase 3 con el banco real; por ahora no bloquean
        return None
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _sistema():
    panel = cargar("06_panel.py", "panel")
    return panel.Sistema()


def _imprimir_guion(g):
    print(f"\n{g['id']} · {g['nombre']}  [{g['tipo']}"
          + (f" + mezcla: {', '.join(g['tipos_mezcla'])}" if g["tipos_mezcla"] else "")
          + "]")
    print(f"  perfil={g['perfil']} cliente={g['cliente'] or '—'} "
          f"decision_pendiente={g['decision_pendiente']}")
    print(f"  prueba: {g['que_prueba']}")
    for i, (m, e) in enumerate(zip(g["mensajes"], g["esperado"]), 1):
        extra = []
        if e["nunca"]:
            extra.append("nunca:" + ",".join(e["nunca"]))
        if e["mem"]:
            extra.append("mem:" + ",".join(e["mem"]))
        if e["decision_pendiente"]:
            extra.append("decision_pendiente")
        print(f"   {i:>2}. {m}")
        print(f"       -> {e['esperado']}" + ("  " + " · ".join(extra) if extra else ""))


def main():
    ap = argparse.ArgumentParser(description="Guiones tipo de VendIQ")
    ap.add_argument("--validar", action="store_true", help="comprueba los 50 guiones")
    ap.add_argument("--ver", metavar="G13", help="imprime un guion ya rellenado")
    args = ap.parse_args()

    sistema = _sistema()
    try:
        guiones = construir(sistema)
    except GuionError as e:
        print(f"ERROR construyendo guiones: {e}")
        return 1

    if args.ver:
        g = next((x for x in guiones if x["id"].lower() == args.ver.lower()), None)
        if not g:
            print(f"no existe el guion {args.ver}")
            return 1
        _imprimir_guion(g)
        return 0

    # por defecto y con --validar: valida y resume
    errores = validar(guiones)
    print("=" * 74)
    print(f"GUIONES TIPO — {len(guiones)} construidos")
    print("=" * 74)
    por_tipo = {}
    for g in guiones:
        por_tipo.setdefault(g["tipo"], []).append(g["id"])
    for t in TIPOS:
        ids = por_tipo.get(t, [])
        mez = [g["id"] for g in guiones if g["tipo"] == t and g["tipos_mezcla"]]
        print(f"  {t:<10} {len(ids):>2} guiones   mezcla: {', '.join(mez) or '—'}")
    total_mez = sum(1 for g in guiones if g["tipos_mezcla"])
    pend = [g["id"] for g in guiones if g["decision_pendiente"]]
    print(f"  {'TOTAL':<10} {len(guiones):>2} guiones · {total_mez} mezclas · "
          f"{len(pend)} con decisión pendiente ({', '.join(pend) or '—'})")
    print()
    if errores:
        print(f"VALIDACIÓN: {len(errores)} ERRORES")
        for e in errores:
            print(f"  - {e}")
        return 1
    print("VALIDACIÓN: OK · 50 guiones, 8 tipos, 10-15 mensajes, ≥10 mezclas, "
          "sin huecos sin rellenar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
