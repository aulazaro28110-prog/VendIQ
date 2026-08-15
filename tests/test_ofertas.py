"""
tests/test_ofertas.py
=====================
Comprueba que el motor de ofertas decide lo que dice que decide.

Aquí lo que se prueba no es "que no pete", sino REGLAS DE NEGOCIO: cada caso de abajo
es una situación real de mostrador. Si un día se cambia un margen y esto deja de pasar,
es que el cambio tenía consecuencias que no se veían a simple vista.

Uso:  python tests/test_ofertas.py
"""

import csv
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cargar_modulo():
    spec = importlib.util.spec_from_file_location("ofertas", BASE / "04_ofertas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


ofertas = cargar_modulo()
fallos = []


def comprobar(descripcion, condicion, detalle=""):
    print(("  OK    " if condicion else "  FALLO") + f" | {descripcion}")
    if not condicion:
        if detalle:
            print(f"          {detalle}")
        fallos.append(descripcion)


# ---------------------------------------------------------------- precios
print("=" * 74)
print("LECTURA DE PRECIOS")
print("=" * 74)
comprobar("'167,00 € + IVA' -> 167.0",
          ofertas.precio_publicado("167,00 € + IVA") == 167.0)
comprobar("'1.250,00 € + IVA' -> 1250.0 (el punto de millar no cuenta)",
          ofertas.precio_publicado("1.250,00 € + IVA") == 1250.0)
comprobar("'Consultar por WhatsApp' -> None (ausencia de precio, no cero)",
          ofertas.precio_publicado("Consultar por WhatsApp") is None)
comprobar("cadena vacía -> None", ofertas.precio_publicado("") is None)

# ---------------------------------------------------------------- inventario
with open(BASE / "datos" / "inventario_sintetico.csv",
          encoding="utf-8-sig", newline="") as f:
    filas = list(csv.DictReader(f, delimiter=";"))
inv = ofertas.Inventario(filas)

con_precio = [f for f in filas if ofertas.precio_publicado(f["precio"])]
por_percentil = sorted(con_precio, key=lambda f: inv.percentil[f["id"]])
mas_antigua = por_percentil[0]
mas_nueva = por_percentil[-1]

print()
print("=" * 74)
print("ANTIGÜEDAD POR NÚMERO DE STOCK")
print("=" * 74)
comprobar("la pieza con el ID más bajo es la más antigua (percentil 0)",
          inv.percentil[min(filas, key=lambda f: int(f["id"]))["id"]] == 0.0)
comprobar("la pieza con el ID más alto es la más nueva (percentil 1)",
          inv.percentil[max(filas, key=lambda f: int(f["id"]))["id"]] == 1.0)
comprobar("el percentil no depende de la escala de los números",
          ofertas.Inventario([{"id": "10"}, {"id": "20"}, {"id": "30"}]).percentil["30"]
          == ofertas.Inventario([{"id": "900010"}, {"id": "900020"},
                                 {"id": "900030"}]).percentil["900030"],
          "renumerar el almacén no debe cambiar quién es la más antigua")

# ---------------------------------------------------------------- decisiones
print()
print("=" * 74)
print("DECISIONES")
print("=" * 74)

lista_antigua = ofertas.precio_publicado(mas_antigua["precio"])
tramo_antigua, _ = inv.tramo_de(mas_antigua["id"])

r = ofertas.evaluar(inv, mas_antigua["id"], lista_antigua * 0.95)
comprobar("pieza muy antigua, 5 % de descuento -> se acepta sola",
          r["decision"] == "ACEPTAR", f"salió {r['decision']}: {r['motivo']}")

r = ofertas.evaluar(inv, mas_antigua["id"], lista_antigua * (1 - tramo_antigua["descuento_max"] - 0.05))
comprobar("pieza muy antigua, 5 puntos por encima del margen -> contraoferta",
          r["decision"] == "CONTRAOFERTA", f"salió {r['decision']}: {r['motivo']}")
comprobar("la contraoferta es exactamente el mínimo aceptable",
          r.get("contraoferta") == r.get("minimo_aceptable"))

r = ofertas.evaluar(inv, mas_nueva["id"], ofertas.precio_publicado(mas_nueva["precio"]) * 0.90)
comprobar("pieza nueva, 10 % de descuento -> NO se acepta sola",
          r["decision"] != "ACEPTAR", f"salió {r['decision']}")

r = ofertas.evaluar(inv, mas_antigua["id"], lista_antigua * 0.40)
comprobar("oferta del 60 % por debajo -> rechazo automático",
          r["decision"] == "RECHAZAR", f"salió {r['decision']}")

r = ofertas.evaluar(inv, mas_antigua["id"], lista_antigua * 1.10)
comprobar("oferta por encima del precio publicado -> se acepta",
          r["decision"] == "ACEPTAR")

# Se fabrica una pieza sin precio en vez de buscarla en el inventario: el catálogo
# actual las tiene todas con precio, pero la regla tiene que seguir siendo cierta
# el día que entre una pieza recién desmontada y todavía sin tasar.
inv_sin_precio = ofertas.Inventario([
    {"id": "1", "precio": "Consultar por WhatsApp", "pieza": "Motor completo",
     "marca": "BMW", "modelo": "Serie 3", "motor": "320d", "anio": "2013"},
])
r = ofertas.evaluar(inv_sin_precio, "1", 500)
comprobar("pieza SIN precio publicado -> siempre a mano, nunca automática",
          r["decision"] == "A_MANO", f"salió {r['decision']}")

r = ofertas.evaluar(inv, "no-existe", 100)
comprobar("pieza que no está en el inventario -> a mano",
          r["decision"] == "A_MANO")

# El suelo en euros: se fabrica una pieza barata a propósito.
inv_barato = ofertas.Inventario([
    {"id": "1", "precio": "20,00 € + IVA", "pieza": "Tornillo", "marca": "X",
     "modelo": "Y", "motor": "Z", "anio": "2010"},
])
r = ofertas.evaluar(inv_barato, "1", 19.0)
comprobar(f"venta por debajo del suelo de {ofertas.SUELO_EUROS:.0f} € -> a mano "
          "aunque el porcentaje encaje",
          r["decision"] == "A_MANO", f"salió {r['decision']}: {r['motivo']}")

# ---------------------------------------------------------------- coherencia
print()
print("=" * 74)
print("COHERENCIA DE LAS REGLAS")
print("=" * 74)
descuentos = [t["descuento_max"] for t in ofertas.TRAMOS]
comprobar("cuanto más nueva es la pieza, menos descuento se concede",
          descuentos == sorted(descuentos, reverse=True), str(descuentos))
comprobar("los tramos cubren todo el stock (llegan al 100 %)",
          ofertas.TRAMOS[-1]["hasta_percentil"] >= 1.0)
comprobar("el rechazo automático está por encima de cualquier margen concedido",
          ofertas.DESCUENTO_ABSURDO > max(descuentos) + ofertas.MARGEN_CONTRAOFERTA)

# Ninguna oferta puede aceptarse sola por debajo del mínimo de su tramo.
escapes = []
for fila in con_precio:
    lista = ofertas.precio_publicado(fila["precio"])
    tramo, _ = inv.tramo_de(fila["id"])
    # justo un céntimo por debajo del mínimo aceptable
    limite = lista * (1 - tramo["descuento_max"]) - 0.01
    if ofertas.evaluar(inv, fila["id"], limite)["decision"] == "ACEPTAR":
        escapes.append(fila["id"])
comprobar(f"ninguna de las {len(con_precio)} piezas con precio acepta por debajo de su mínimo",
          not escapes, f"se escapan: {escapes[:5]}")

print()
print("=" * 74)
print(f"RESULTADO: {'PASA' if not fallos else f'NO PASA ({len(fallos)} fallos)'}")
print("=" * 74)
sys.exit(1 if fallos else 0)
