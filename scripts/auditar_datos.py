# -*- coding: utf-8 -*-
"""
scripts/auditar_datos.py
========================
QUE DATOS PERSONALES TOCA VendIQ, Y DONDE ACABAN.

    py scripts/auditar_datos.py

Existe porque un checklist de proteccion de datos copiado de una plantilla no
vale nada. Este script no supone: mira los ficheros de salida buscando
matriculas, VIN, telefonos y correos, lee el codigo para ver que se manda fuera,
y comprueba que el catalogo es de verdad sintetico.

Los cinco apartados que saca son los que alimentan docs/GDPR.md. Si manana el
sistema empieza a guardar algo nuevo, esto lo enseña y el documento se queda
obsoleto en voz alta en vez de en silencio.
"""
import io
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MATRICULA = re.compile(r"\b\d{4}\s?[BCDFGHJKLMNPRSTVWXYZ]{3}\b|\b[A-Z]{1,2}-?\d{4}-?[A-Z]{2}\b")
VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
TELEFONO = re.compile(r"\b(?:\+34\s?)?[6789]\d{8}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")

print("=" * 78)
print("1. QUE SE ESCRIBE A DISCO")
print("=" * 78)
for f in sorted((BASE / "salida").glob("*.json")) + sorted((BASE / "datos").glob("*.md")):
    if not f.exists():
        continue
    texto = f.read_text(encoding="utf-8", errors="replace")
    hallazgos = []
    for etiqueta, patron in (("matrículas", MATRICULA), ("VIN", VIN),
                             ("teléfonos", TELEFONO), ("emails", EMAIL)):
        n = len(set(patron.findall(texto)))
        if n:
            hallazgos.append(f"{n} {etiqueta}")
    tam = f.stat().st_size
    print(f"   {f.relative_to(BASE).as_posix():<34} {tam/1024:>8.1f} KB  "
          + (", ".join(hallazgos) if hallazgos else "sin datos personales"))

print()
print("=" * 78)
print("2. QUE SALE DE LA MAQUINA")
print("=" * 78)
conversar = (BASE / "08_conversar.py").read_text(encoding="utf-8")
print("   Único destino externo: api.groq.com (redacción del mensaje).")
print("   Lo que viaja en cada petición, leído de _mensajes():")
for etiqueta, marca in [
    ("el rol y las reglas de estilo", '"role": "system"'),
    ("el resumen (incluye la MATRÍCULA)", "matrícula que dio"),
    ("los últimos turnos, literales", "historial[-VENTANA_TURNOS:]"),
    ("el mensaje del cliente", "MENSAJE DEL CLIENTE"),
    ("la ficha del catálogo", "FICHA ENCONTRADA"),
]:
    print(f"     {'SÍ ' if marca in conversar else 'no '} {etiqueta}")

print()
print("=" * 78)
print("3. CUANTO TIEMPO SE GUARDA")
print("=" * 78)
panel = (BASE / "06_panel.py").read_text(encoding="utf-8")
print(f"   conversaciones en memoria del servidor: "
      f"{'sí (self.chats), se pierden al reiniciar' if 'self.chats = {}' in panel else '?'}")
m = re.search(r"del historial\[:-(\d+)\]", panel)
print(f"   historial por conversación: últimos {m.group(1) if m else '?'} turnos")
print(f"   registro de dudas: {'permanente hasta que se contesta' if 'no_resueltas' in panel else '?'}")

print()
print("=" * 78)
print("4. QUE DICE .gitignore")
print("=" * 78)
for linea in (BASE / ".gitignore").read_text(encoding="utf-8").splitlines():
    if linea.strip() and not linea.startswith("#"):
        print("   " + linea)

print()
print("=" * 78)
print("5. EL CATALOGO: ¿ES SINTETICO?")
print("=" * 78)
import csv
filas = list(csv.DictReader(io.open(BASE / "datos" / "inventario_sintetico.csv",
                                    encoding="utf-8-sig"), delimiter=";"))
print(f"   {len(filas)} piezas · fichero: datos/inventario_sintetico.csv")
print(f"   columnas: {', '.join(filas[0].keys())}")
tiene_personales = any(TELEFONO.search(" ".join(f.values()))
                       or EMAIL.search(" ".join(f.values())) for f in filas)
print(f"   ¿contiene datos de personas? {'SÍ' if tiene_personales else 'NO'}")
