"""
tests/test_origen.py
====================
S21 · Cada reserva, duda y oferta NUEVA nace con su campo `origen`, y lo que ya
estaba escrito no se toca.

Todo se escribe en una carpeta TEMPORAL: esta prueba no toca salida/.

Uso:  python tests/test_origen.py
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

BASE = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / "src" / fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


panel = cargar("06_panel.py", "panel")
aprender = cargar("09_aprender.py", "aprender")
ofertas = cargar("04_ofertas.py", "ofertas")
fallos = []


def comprobar(descripcion, condicion, detalle=""):
    print(("  OK    " if condicion else "  FALLO") + f" | {descripcion}")
    if not condicion:
        if detalle:
            print(f"          {detalle}")
        fallos.append(descripcion)


def leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


tmp = Path(tempfile.mkdtemp(prefix="vendiq_test_origen_"))
panel.RESERVAS = tmp / "reservas.json"          # nada de esto apunta a salida/
aprender.REGISTRO = tmp / "no_resueltas.json"
ofertas.REGISTRO = tmp / "ofertas.json"

# ---------------------------------------------------------------- origen_de
print("=" * 74)
print("ORIGEN SEGÚN LA SESIÓN")
print("=" * 74)
origen_de = panel.Sistema.origen_de
comprobar("sesión de prueba (banco-) -> prueba", origen_de("banco-12") == "prueba")
comprobar("chat del panel (panel-) -> prueba", origen_de("panel-1790539135036") == "prueba")
comprobar("cualquier otra sesión -> cliente", origen_de("web-7") == "cliente")

# ---------------------------------------------------------------- reservas
print("=" * 74)
print("RESERVAS")
print("=" * 74)
antigua = {"sesion": "vieja-1", "id_pieza": "5", "estado": "pendiente de preparar"}
panel.RESERVAS.write_text(json.dumps([antigua]), encoding="utf-8")
# El Sistema completo carga el buscador y el modelo; anotar_reserva solo usa
# es_prueba y origen_de, así que se le pasa un objeto mínimo con esas dos.
sistema = SimpleNamespace(es_prueba=panel.Sistema.es_prueba,
                          origen_de=panel.Sistema.origen_de)
conv = SimpleNamespace(ultima_pieza={"pieza": "Alternador", "id": "1"},
                       matricula="0000XXX", vehiculo="Coche de prueba",
                       precio_de={"1": "100,00 € + IVA"})
for sesion in ("web-7", "panel-1", "banco-1"):
    panel.Sistema.anotar_reserva(sistema, sesion, conv)
reservas = {r["sesion"]: r for r in leer(panel.RESERVAS)}
comprobar("reserva de cliente -> origen 'cliente'",
          reservas.get("web-7", {}).get("origen") == "cliente", reservas.get("web-7"))
comprobar("reserva del chat del panel -> origen 'prueba'",
          reservas.get("panel-1", {}).get("origen") == "prueba", reservas.get("panel-1"))
comprobar("una sesión de prueba sigue sin escribir reservas", "banco-1" not in reservas)
comprobar("la reserva antigua no se reescribe (sigue sin 'origen')",
          reservas.get("vieja-1") == antigua, reservas.get("vieja-1"))

# ---------------------------------------------------------------- dudas
print("=" * 74)
print("DUDAS SIN RESPONDER")
print("=" * 74)
aprender.anotar("¿abrís los sábados?", "motivo", "web-7", "ESCALA", "cliente")
aprender.anotar("¿abrís los sábados?", "motivo", "panel-1", "ESCALA", "prueba")
aprender.anotar("¿abrís los sábados?", "motivo", "web-8", "ESCALA", "cliente")
aprender.anotar("¿hacéis envíos?", "motivo", "web-9", "ESCALA")       # sin origen: como antes
aprender.anotar("¿hacéis envíos?", "motivo", "web-10", "ESCALA")
dudas = leer(aprender.REGISTRO)
sabados = {d.get("origen"): d for d in dudas if d["pregunta"] == "¿abrís los sábados?"}
envios = [d for d in dudas if d["pregunta"] == "¿hacéis envíos?"]
comprobar("la misma pregunta de cliente y de prueba son dos entradas",
          set(sabados) == {"cliente", "prueba"}, list(sabados))
comprobar("las pruebas no suben el contador del cliente",
          sabados.get("cliente", {}).get("veces") == 2, sabados.get("cliente"))
comprobar("sin origen se guarda y se cuenta como antes (una entrada, sin el campo)",
          len(envios) == 1 and envios[0]["veces"] == 2 and "origen" not in envios[0], envios)

# ---------------------------------------------------------------- ofertas
print("=" * 74)
print("OFERTAS")
print("=" * 74)
inv = ofertas.Inventario([{"id": "1", "precio": "100,00 € + IVA", "pieza": "Alternador",
                           "marca": "Marca", "modelo": "Modelo", "motor": "1.6",
                           "anio": "2010"}])
del_panel = ofertas.registrar(inv, "1", 95, "Taller Ficticio", "prueba")
por_linea_de_comandos = ofertas.registrar(inv, "1", 90, "Otro Taller Ficticio", "cliente")
comprobar("la oferta del panel lleva origen 'prueba'", del_panel.get("origen") == "prueba")
comprobar("la oferta por línea de comandos lleva origen 'cliente'",
          por_linea_de_comandos.get("origen") == "cliente")
comprobar("las dos quedan escritas con su origen",
          [o.get("origen") for o in leer(ofertas.REGISTRO)] == ["prueba", "cliente"])

print()
print("=" * 74)
print(f"RESULTADO: {'PASA' if not fallos else f'NO PASA ({len(fallos)} fallos)'}")
print("=" * 74)
sys.exit(1 if fallos else 0)
