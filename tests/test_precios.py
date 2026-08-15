"""
tests/test_precios.py
=====================
La regla más delicada del sistema: VendIQ da precios, pero SOLO de piezas que la
empresa tiene de verdad.

Por qué merece su propio banco de pruebas: enseñar una pieza parecida es una molestia;
decir un precio equivocado es un compromiso comercial. El cliente se lo cree, viene a
por ella, y alguien tiene que darle la mala noticia. Este fichero comprueba que eso
no pasa ni por descuido ni por una pieza hermana.

Uso:  python tests/test_precios.py
"""

import csv
import importlib.util
import random
import sys
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("buscar", BASE / "03_buscar.py")
buscar_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(buscar_mod)

fallos = []


def comprobar(descripcion, condicion, detalle=""):
    print(("  OK    " if condicion else "  FALLO") + f" | {descripcion}")
    if not condicion:
        if detalle:
            print(f"          {detalle}")
        fallos.append(descripcion)


buscador = buscar_mod.cargar_buscador()
with open(BASE / "datos" / "inventario_sintetico.csv",
          encoding="utf-8-sig", newline="") as f:
    filas = list(csv.DictReader(f, delimiter=";"))
por_id = {f["id"]: f for f in filas}


def preguntar(fila):
    return (f"¿cuánto vale el {fila['pieza'].lower()} para un {fila['marca'].title()} "
            f"{fila['modelo']} {fila['motor']} del {fila['anio']}?")


def precio_ofrecido(pregunta):
    """Devuelve (importe, id_pieza) del primer precio que el sistema daría, o (None, None)."""
    for _, item in buscador.buscar(pregunta, k=3):
        pc = item.get("precio_cliente") or {}
        if pc.get("publicable"):
            return pc["importe"], (item.get("meta") or {}).get("id")
    return None, None


print("=" * 76)
print("A) CUÁNDO SÍ SE DA PRECIO")
print("=" * 76)

con_precio_y_stock = [f for f in filas
                      if "onsultar" not in f["precio"]
                      and f["disponibilidad"].lower() in buscar_mod.DISPONIBILIDAD_VALIDA]
print(f"  INFO  | {len(con_precio_y_stock)} de {len(filas)} piezas cumplen stock + precio publicado")

random.seed(3)
muestra = random.sample(con_precio_y_stock, min(20, len(con_precio_y_stock)))
dados = sum(1 for f in muestra if precio_ofrecido(preguntar(f))[0] is not None)
comprobar(f"se da precio cuando la pieza está y tiene precio ({dados}/{len(muestra)})",
          dados >= len(muestra) * 0.8, "si baja mucho, el umbral de precio es demasiado duro")

correctos = 0
for f in muestra:
    importe, id_dado = precio_ofrecido(preguntar(f))
    if importe is not None and id_dado == f["id"]:
        correctos += 1
comprobar(f"cuando se da un precio, es el de LA pieza pedida ({correctos}/{dados})",
          correctos == dados, "se ha dado el precio de otra ficha")

print()
print("=" * 76)
print("B) CUÁNDO NO SE DA PRECIO")
print("=" * 76)

sin_precio = [f for f in filas if "onsultar" in f["precio"]]
escapes = [f["id"] for f in random.sample(sin_precio, min(20, len(sin_precio)))
           if precio_ofrecido(preguntar(f))[0] is not None]
comprobar("pieza sin precio publicado -> nunca se inventa un importe",
          not escapes, f"se escapan: {escapes[:5]}")

# Pieza que NO existe: ni precio, ni el de una pieza hermana.
# Las combinaciones se sacan del propio inventario en vez de escribirlas a mano:
# el catálogo cambia (pasó de 100 a 1.000 piezas) y una lista fija se queda vieja
# sin avisar — de hecho es lo que ocurrió, y el test empezó a fallar por eso.
existentes = {(f["pieza"], f["marca"]) for f in filas}
piezas_todas = sorted({f["pieza"] for f in filas})
marcas_todas = sorted({f["marca"] for f in filas})
modelos = {}
for f in filas:
    modelos.setdefault(f["marca"], set()).add(f["modelo"])

random.seed(11)
inexistentes = []
intentos = 0
while len(inexistentes) < 12 and intentos < 3000:
    intentos += 1
    pieza, marca = random.choice(piezas_todas), random.choice(marcas_todas)
    if (pieza, marca) in existentes:
        continue
    modelo = random.choice(sorted(modelos[marca]))
    inexistentes.append(f"¿cuánto vale un {pieza.lower()} para un "
                        f"{marca.title()} {modelo}?")
print(f"  INFO  | {len(inexistentes)} combinaciones pieza+marca que NO existen en catálogo")
fugas = [(q, precio_ofrecido(q)) for q in inexistentes]
fugas = [(q, r) for q, r in fugas if r[0] is not None]
comprobar("pieza que NO está en catálogo -> ningún precio, ni de una parecida",
          not fugas, str(fugas[:3]))

# Consulta vaga: no ha nombrado la pieza, así que no puede haber precio.
vagas = ["busco algo para mi Audi A4",
         "necesito una pieza de un BMW Serie 3",
         "tengo un Seat Ibiza, ¿qué tienes?"]
fugas_vagas = [q for q in vagas if precio_ofrecido(q)[0] is not None]
comprobar("consulta sin nombrar la pieza -> se confirma antes de dar precio",
          not fugas_vagas, str(fugas_vagas))

print()
print("=" * 76)
print("C) DISPONIBILIDAD")
print("=" * 76)

fabricada = dict(por_id[con_precio_y_stock[0]["id"]])
fabricada["disponibilidad"] = "Agotada"
item_falso = {"id": "pieza-test", "tipo": "inventario",
              "texto": "pieza de prueba", "meta": fabricada}
r = buscador.precio_para_cliente(item_falso, 0.99, "dame el precio")
comprobar("una pieza marcada como agotada nunca lleva precio",
          not r["publicable"] and r["estado"] == "sin_stock", str(r))

for estado_disp in ("En stock", "Bajo pedido 24-48h"):
    fabricada2 = dict(fabricada)
    fabricada2["disponibilidad"] = estado_disp
    pieza = fabricada2["pieza"].lower()
    item2 = {"id": f"pieza-{fabricada2['id']}", "tipo": "inventario",
             "texto": "x", "meta": fabricada2}
    r2 = buscador.precio_para_cliente(item2, 0.99, f"cuanto vale el {pieza}")
    comprobar(f"'{estado_disp}' sí permite dar precio", r2["publicable"], str(r2))

print()
print("=" * 76)
print("D) EL MOTIVO SIEMPRE SE EXPLICA")
print("=" * 76)
estados = set()
for q in inexistentes + vagas + [preguntar(f) for f in muestra[:6]]:
    for _, item in buscador.buscar(q, k=3):
        pc = item.get("precio_cliente") or {}
        estados.add(pc.get("estado"))
        if not pc.get("motivo"):
            fallos.append("resultado sin motivo de precio")
comprobar("todo resultado explica por qué lleva o no lleva precio", True)
print(f"  INFO  | estados vistos: {sorted(e for e in estados if e)}")

print()
print("=" * 76)
print(f"RESULTADO: {'PASA' if not fallos else f'NO PASA ({len(fallos)} fallos)'}")
print("=" * 76)
sys.exit(1 if fallos else 0)
