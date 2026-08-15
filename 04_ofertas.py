"""
04_ofertas.py
=============
Motor de OFERTAS de VendIQ (el "haz una oferta" de eBay, aplicado al desguace).

El cliente propone un precio por una pieza. Este módulo decide qué hacer con esa
oferta, y deja constancia de todas para que Álvaro tenga la última palabra.

CUATRO DECISIONES POSIBLES
--------------------------
  ACEPTAR      la oferta entra dentro del margen permitido para esa pieza -> se acepta sola
  CONTRAOFERTA se pasa un poco: se propone el precio mínimo que sí se aceptaría
  RECHAZAR     se pasa tanto que no merece ni consultarse
  A_MANO       no se puede decidir con una regla -> decide Álvaro

CÓMO SE MIDE LA ANTIGÜEDAD DE UNA PIEZA
---------------------------------------
Cuanto más tiempo lleva una pieza en la estantería, más interesa venderla: ocupa sitio
y ya está amortizada. Pero el inventario NO tiene fecha de alta (comprobado en la web:
las fichas no publican ninguna fecha). Lo único que ordena las piezas en el tiempo es
el número de stock: se van asignando de forma correlativa, así que un número bajo
significa que entró antes.

Aquí no se usa el número en bruto, sino su PERCENTIL dentro del stock actual:
"esta pieza está entre el 20 % más antiguo". Se hace así por dos motivos:
  - Funciona con cualquier numeración. En la web conviven dos números distintos por
    pieza (el del listado y el de la ficha); mientras el elegido sea correlativo en el
    tiempo, el percentil sale bien igual.
  - No se rompe si algún día se renumera el almacén o se migra de sistema. Un umbral
    escrito como "ID < 69500" sí se rompería, y en silencio.

LO QUE ESTE MÓDULO NUNCA HACE SOLO
----------------------------------
  - No acepta ofertas sobre piezas SIN precio publicado. Si el precio es "Consultar por
    WhatsApp" no hay base sobre la que calcular un porcentaje: va a Álvaro. Hoy en la web
    real esto es la inmensa mayoría del catálogo.
  - No acepta nada por debajo del suelo absoluto (SUELO_EUROS).
  - No negocia dos veces la misma pieza con el mismo cliente sin pasar por Álvaro.

Uso:
    python 04_ofertas.py reglas                      # ver la tabla de márgenes
    python 04_ofertas.py oferta 69109 150 --cliente "Juan"
    python 04_ofertas.py pendientes                  # lo que espera decisión de Álvaro
    python 04_ofertas.py aceptar 3
    python 04_ofertas.py rechazar 3 --motivo "por debajo de coste"
    python 04_ofertas.py historial
"""

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
CSV_INVENTARIO = BASE / "datos" / "inventario_sintetico.csv"
REGISTRO = BASE / "salida" / "ofertas.json"

# ---------------------------------------------------------------------------
# REGLAS DE NEGOCIO — esto lo decide Álvaro, no el código.
# Los números de abajo son un punto de partida razonable, NO una recomendación
# de márgenes: nadie salvo él sabe a cuánto compró cada pieza.
# ---------------------------------------------------------------------------

# Cuánto descuento se acepta solo, según lo antigua que sea la pieza.
# 'hasta_percentil' = 0.25 significa "el 25 % más antiguo del stock".
TRAMOS = [
    {"nombre": "muy antigua", "hasta_percentil": 0.25, "descuento_max": 0.20},
    {"nombre": "antigua",     "hasta_percentil": 0.50, "descuento_max": 0.12},
    {"nombre": "reciente",    "hasta_percentil": 0.75, "descuento_max": 0.07},
    {"nombre": "nueva",       "hasta_percentil": 1.01, "descuento_max": 0.00},
]

# Si el cliente se pasa del margen pero no mucho, se le contraoferta en vez de
# rechazar sin más. Por encima de esto, ni se contraoferta: decide Álvaro.
MARGEN_CONTRAOFERTA = 0.10      # 10 puntos porcentuales por encima del tramo

# Por debajo de esto la oferta es tan baja que se rechaza directamente.
DESCUENTO_ABSURDO = 0.45        # 45 % por debajo del precio publicado

# Ninguna aceptación automática por debajo de esta cantidad, pase lo que pase.
SUELO_EUROS = 30.0


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def precio_publicado(texto: str):
    """Convierte '1.250,00 € + IVA' en 1250.0. Devuelve None si no hay precio.

    En el catálogo real la mayoría de piezas ponen "Consultar por WhatsApp": eso NO es
    un precio, es la ausencia de uno, y hay que tratarlo como tal en vez de asumir cero.
    """
    if not texto or "onsultar" in texto:
        return None
    limpio = re.sub(r"[^\d,.]", "", texto).replace(".", "").replace(",", ".")
    try:
        valor = float(limpio)
    except ValueError:
        return None
    return valor if valor > 0 else None


class Inventario:
    """Las piezas y su posición de antigüedad dentro del stock."""

    def __init__(self, filas, campo_id="id"):
        self.campo_id = campo_id
        self.por_id = {f[campo_id]: f for f in filas}

        # Percentil de antigüedad: 0.0 = la más antigua del stock, 1.0 = la más nueva.
        # Se ordena por el número de stock, que es lo único correlativo en el tiempo.
        ordenadas = sorted(filas, key=lambda f: int(f[campo_id]))
        total = max(len(ordenadas) - 1, 1)
        self.percentil = {f[campo_id]: i / total for i, f in enumerate(ordenadas)}

    def get(self, id_pieza):
        return self.por_id.get(str(id_pieza))

    def tramo_de(self, id_pieza):
        p = self.percentil[str(id_pieza)]
        for tramo in TRAMOS:
            if p <= tramo["hasta_percentil"]:
                return tramo, p
        return TRAMOS[-1], p


def evaluar(inventario: Inventario, id_pieza, importe: float) -> dict:
    """Decide qué hacer con una oferta. Devuelve el desglose completo del porqué."""
    pieza = inventario.get(id_pieza)
    if pieza is None:
        return {"decision": "A_MANO", "motivo": f"la pieza {id_pieza} no está en el inventario"}

    lista = precio_publicado(pieza["precio"])
    if lista is None:
        return {
            "decision": "A_MANO",
            "motivo": "la pieza no tiene precio publicado ('Consultar por WhatsApp'), "
                      "así que no hay base sobre la que calcular un porcentaje",
            "precio_lista": None,
        }

    if importe <= 0:
        return {"decision": "A_MANO", "motivo": "importe no válido"}

    tramo, percentil = inventario.tramo_de(id_pieza)
    descuento = 1 - (importe / lista)
    minimo_aceptable = round(lista * (1 - tramo["descuento_max"]), 2)

    base = {
        "precio_lista": lista,
        "oferta": round(importe, 2),
        "descuento": round(descuento, 4),
        "antiguedad": tramo["nombre"],
        "percentil_antiguedad": round(percentil, 3),
        "descuento_max_automatico": tramo["descuento_max"],
        "minimo_aceptable": minimo_aceptable,
    }

    # El cliente ofrece igual o más que el precio de lista: no hay nada que negociar.
    if descuento <= 0:
        return {**base, "decision": "ACEPTAR",
                "motivo": "la oferta iguala o supera el precio publicado"}

    if descuento >= DESCUENTO_ABSURDO:
        return {**base, "decision": "RECHAZAR",
                "motivo": f"{descuento:.0%} por debajo del precio publicado, "
                          f"muy lejos de lo negociable"}

    if descuento <= tramo["descuento_max"]:
        if importe < SUELO_EUROS:
            return {**base, "decision": "A_MANO",
                    "motivo": f"entra en el margen, pero {importe:.2f} € está por debajo "
                              f"del suelo de {SUELO_EUROS:.0f} €"}
        return {**base, "decision": "ACEPTAR",
                "motivo": f"pieza {tramo['nombre']} (entre el {percentil:.0%} más antiguo): "
                          f"se acepta hasta un {tramo['descuento_max']:.0%} y pide un "
                          f"{descuento:.0%}"}

    if descuento <= tramo["descuento_max"] + MARGEN_CONTRAOFERTA:
        return {**base, "decision": "CONTRAOFERTA",
                "motivo": f"pide un {descuento:.0%} y el máximo automático para una pieza "
                          f"{tramo['nombre']} es {tramo['descuento_max']:.0%}",
                "contraoferta": minimo_aceptable}

    return {**base, "decision": "A_MANO",
            "motivo": f"pide un {descuento:.0%}, demasiado por encima del "
                      f"{tramo['descuento_max']:.0%} automático: lo decides tú"}


# ---------------------------------------------------------------------------
# Registro: toda oferta queda escrita, se decida sola o a mano.
# ---------------------------------------------------------------------------

def leer_registro() -> list:
    if not REGISTRO.exists():
        return []
    # utf-8-sig: tolera el BOM invisible que dejan PowerShell o Excel si alguien
    # abre o reinicia el fichero a mano. Con utf-8 a secas, json.loads reventaría.
    texto = REGISTRO.read_text(encoding="utf-8-sig").strip()
    return json.loads(texto) if texto else []


def escribir_registro(ofertas):
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(ofertas, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar(inventario, id_pieza, importe, cliente):
    ofertas = leer_registro()

    # Un mismo cliente no negocia dos veces la misma pieza sin pasar por Álvaro:
    # si no, basta con ir bajando la oferta hasta dar con el umbral.
    repetida = any(o["id_pieza"] == str(id_pieza) and o["cliente"] == cliente
                   for o in ofertas)

    resultado = evaluar(inventario, id_pieza, importe)
    if repetida and resultado["decision"] == "ACEPTAR":
        resultado = {**resultado, "decision": "A_MANO",
                     "motivo": "segunda oferta del mismo cliente por esta pieza: "
                               "lo revisas tú"}

    pieza = inventario.get(id_pieza)
    oferta = {
        "n": len(ofertas) + 1,
        "fecha": ahora(),
        "cliente": cliente,
        "id_pieza": str(id_pieza),
        "descripcion": (f"{pieza['pieza']} {pieza['marca']} {pieza['modelo']} "
                        f"{pieza['motor']} {pieza['anio']}") if pieza else "(desconocida)",
        "importe": round(float(importe), 2),
        **{k: v for k, v in resultado.items() if k != "decision"},
        "decision": resultado["decision"],
        "estado": "pendiente" if resultado["decision"] == "A_MANO" else "cerrada",
        "resuelta_por": "regla" if resultado["decision"] != "A_MANO" else None,
    }
    ofertas.append(oferta)
    escribir_registro(ofertas)
    return oferta


def resolver(n, decision, motivo=None):
    ofertas = leer_registro()
    for o in ofertas:
        if o["n"] == n:
            if o["estado"] != "pendiente":
                raise SystemExit(f"La oferta {n} ya está cerrada ({o['decision']}).")
            o["decision"] = decision
            o["estado"] = "cerrada"
            o["resuelta_por"] = "Álvaro"
            o["motivo"] = motivo or "decisión manual"
            o["fecha_resolucion"] = ahora()
            escribir_registro(ofertas)
            return o
    raise SystemExit(f"No existe la oferta {n}.")


# ---------------------------------------------------------------------------
# Interfaz de línea de comandos
# ---------------------------------------------------------------------------

def cargar_inventario():
    if not CSV_INVENTARIO.exists():
        raise SystemExit(f"ERROR: no encuentro {CSV_INVENTARIO}.")
    with open(CSV_INVENTARIO, encoding="utf-8-sig", newline="") as f:
        return Inventario(list(csv.DictReader(f, delimiter=";")))


def mostrar(oferta):
    print(f"\n  Oferta #{oferta['n']} — {oferta['descripcion']}")
    print(f"  Cliente: {oferta['cliente']}")
    if oferta.get("precio_lista"):
        print(f"  Publicado: {oferta['precio_lista']:.2f} €   "
              f"Ofrece: {oferta['importe']:.2f} €   "
              f"({oferta['descuento']:.0%} menos)")
        print(f"  Antigüedad: {oferta['antiguedad']} "
              f"(entre el {oferta['percentil_antiguedad']:.0%} más antiguo del stock)")
    else:
        print(f"  Ofrece: {oferta['importe']:.2f} €   (pieza sin precio publicado)")
    print(f"  >> {oferta['decision']}: {oferta['motivo']}")
    if oferta.get("contraoferta"):
        print(f"  >> Contraoferta sugerida: {oferta['contraoferta']:.2f} €")


def cmd_reglas(_):
    print("Márgenes que se aprueban solos, según antigüedad de la pieza:\n")
    print(f"  {'tramo':<14} {'parte del stock':<22} {'descuento máximo':>17}")
    anterior = 0.0
    for t in TRAMOS:
        hasta = min(t["hasta_percentil"], 1.0)
        rango = f"del {anterior:.0%} al {hasta:.0%} más antiguo"
        print(f"  {t['nombre']:<14} {rango:<22} {t['descuento_max']:>16.0%}")
        anterior = hasta
    print(f"\n  Contraoferta hasta {MARGEN_CONTRAOFERTA:.0%} por encima del margen.")
    print(f"  Rechazo automático a partir del {DESCUENTO_ABSURDO:.0%} de descuento.")
    print(f"  Nunca se acepta sola una venta por debajo de {SUELO_EUROS:.0f} €.")
    print("\n  Sin precio publicado -> siempre decides tú.")
    print("  Estos números son un punto de partida: cámbialos en TRAMOS, al principio")
    print("  del fichero. Solo tú sabes a cuánto compraste cada pieza.")


def cmd_oferta(args):
    inventario = cargar_inventario()
    mostrar(registrar(inventario, args.id_pieza, args.importe, args.cliente))


def cmd_pendientes(_):
    pendientes = [o for o in leer_registro() if o["estado"] == "pendiente"]
    if not pendientes:
        print("No hay ofertas esperando tu decisión.")
        return
    print(f"{len(pendientes)} oferta(s) esperando tu decisión:")
    for o in pendientes:
        mostrar(o)
    print(f"\n  Para cerrarlas:  python 04_ofertas.py aceptar <n>  |  rechazar <n>")


def cmd_aceptar(args):
    mostrar(resolver(args.n, "ACEPTAR", args.motivo))


def cmd_rechazar(args):
    mostrar(resolver(args.n, "RECHAZAR", args.motivo))


def cmd_historial(_):
    ofertas = leer_registro()
    if not ofertas:
        print("Todavía no hay ofertas registradas.")
        return
    print(f"{'#':>3} {'pieza':>8} {'ofrece':>10} {'decisión':<13} {'quién':<8} descripción")
    for o in ofertas:
        print(f"{o['n']:>3} {o['id_pieza']:>8} {o['importe']:>9.2f}€ "
              f"{o['decision']:<13} {(o['resuelta_por'] or '-'):<8} {o['descripcion'][:38]}")
    cerradas = [o for o in ofertas if o["resuelta_por"] == "regla"]
    print(f"\n  {len(cerradas)} de {len(ofertas)} resueltas por la regla, sin molestarte.")


def main():
    p = argparse.ArgumentParser(description="Motor de ofertas de VendIQ")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reglas", help="ver la tabla de márgenes").set_defaults(func=cmd_reglas)

    o = sub.add_parser("oferta", help="registrar una oferta de un cliente")
    o.add_argument("id_pieza")
    o.add_argument("importe", type=float)
    o.add_argument("--cliente", default="anónimo")
    o.set_defaults(func=cmd_oferta)

    sub.add_parser("pendientes", help="ofertas que esperan tu decisión").set_defaults(func=cmd_pendientes)

    a = sub.add_parser("aceptar", help="aceptar una oferta pendiente")
    a.add_argument("n", type=int)
    a.add_argument("--motivo")
    a.set_defaults(func=cmd_aceptar)

    r = sub.add_parser("rechazar", help="rechazar una oferta pendiente")
    r.add_argument("n", type=int)
    r.add_argument("--motivo")
    r.set_defaults(func=cmd_rechazar)

    sub.add_parser("historial", help="todas las ofertas").set_defaults(func=cmd_historial)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
