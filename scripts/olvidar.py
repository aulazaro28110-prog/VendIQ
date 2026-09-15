# -*- coding: utf-8 -*-
"""
scripts/olvidar.py
==================
DERECHO DE SUPRESIÓN, ejecutable. Borra de VendIQ todo rastro de una matrícula.

    py scripts/olvidar.py 4521 KBD --ver        (enseña qué encontraría)
    py scripts/olvidar.py 4521 KBD --borrar     (lo borra de verdad)

Por qué existe un fichero para esto: un checklist de protección de datos que dice
«se atienden las solicitudes de supresión» no vale nada si atenderlas consiste en
que alguien recuerde qué siete ficheros tocar. O es una orden que se ejecuta, o
es una intención.

QUÉ BORRA, Y POR QUÉ ESOS SITIOS
--------------------------------
La matrícula es el único dato personal que VendIQ llega a guardar. Auditado
fichero a fichero (`scripts/auditar_datos.py` hizo el recorrido), puede acabar en:

  · salida/no_resueltas.json   el mensaje del cliente se guarda literal para que
                               una persona lo conteste, y puede llevarla dentro
  · salida/conversaciones.json detalle del banco de pruebas
  · salida/actividad.json      los ejemplos de mensajes que enseña el panel
  · salida/panel.json          lo que el panel tiene cargado
  · salida/reservas.json       CADA reserva guarda la matrícula en un campo suyo,
                               y a diferencia de las conversaciones esto SÍ
                               sobrevive a reiniciar el panel
  · datos/faq_aprendidas.md    la pregunta original que dio pie a la respuesta

salida/reservas.json se añadió tarde: el script nació antes que las reservas y se
quedaba sin recorrerlas, así que decía haber borrado una matrícula que seguía
viva ahí dentro. Si se añade otro sitio donde acabe una matrícula, va en esta
lista o el borrado vuelve a mentir.

NO toca el catálogo (`datos/inventario_sintetico.csv`): es sintético y no tiene
ni un dato de una persona. Tampoco el índice de embeddings, porque se reconstruye
de los anteriores — pero avisa de que hay que reconstruirlo, que si no la
matrícula seguiría viva dentro de un vector.

LO QUE NO PUEDE BORRAR, Y HAY QUE DECIRLO
-----------------------------------------
Las conversaciones abiertas viven en la memoria del proceso del panel. Se pierden
al reiniciarlo, y este script no puede alcanzarlas: si hay una en curso, reinicia
el panel después.
"""

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Los sitios donde puede haber quedado. Cada uno con cómo se lee y se escribe.
FICHEROS_JSON = [
    BASE / "salida" / "no_resueltas.json",
    BASE / "salida" / "conversaciones.json",
    BASE / "salida" / "actividad.json",
    BASE / "salida" / "panel.json",
    BASE / "salida" / "reservas.json",
]
FICHEROS_TEXTO = [
    BASE / "datos" / "faq_aprendidas.md",
]


def normalizar(matricula):
    """«4521KBD», «4521 kbd» y «4521-KBD» son la misma matrícula."""
    return re.sub(r"[\s-]", "", (matricula or "")).upper()


def patron_de(matricula):
    """Encuentra la matrícula escrita de cualquiera de las formas usuales."""
    limpia = normalizar(matricula)
    if len(limpia) == 7 and limpia[:4].isdigit():
        return re.compile(rf"\b{limpia[:4]}[\s-]?{limpia[4:]}\b", re.I)
    # Antigua (M-1234-AB) o bastidor: se busca con separadores opcionales.
    return re.compile(r"[\s-]?".join(re.escape(c) for c in limpia), re.I)


def buscar(patron):
    """Dónde aparece y cuántas veces. Sin tocar nada."""
    encontrados = []
    for f in FICHEROS_JSON + FICHEROS_TEXTO:
        if not f.exists():
            continue
        texto = f.read_text(encoding="utf-8", errors="replace")
        n = len(patron.findall(texto))
        if n:
            encontrados.append((f, n))
    return encontrados


def borrar(patron, marca="[BORRADA A PETICIÓN DEL TITULAR]"):
    """Sustituye la matrícula por una marca visible y devuelve qué se tocó.

    Se sustituye en vez de borrar el registro entero a propósito. La pregunta que
    hizo el cliente —«¿tenéis un alternador para este coche?»— es información de
    negocio que no identifica a nadie una vez fuera la matrícula, y tirarla
    entera destruiría el registro de dudas sin necesidad. Minimizar es quitar el
    dato personal, no quemar el archivo.
    """
    tocados = []
    for f in FICHEROS_JSON + FICHEROS_TEXTO:
        if not f.exists():
            continue
        texto = f.read_text(encoding="utf-8", errors="replace")
        nuevo, n = patron.subn(marca, texto)
        if n:
            if f in FICHEROS_JSON:
                # Se vuelve a parsear antes de escribir: si la sustitución hubiera
                # roto el JSON, es mejor enterarse aquí que dejar el fichero
                # inservible.
                json.loads(nuevo)
            f.write_text(nuevo, encoding="utf-8")
            tocados.append((f, n))
    return tocados


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    modo_borrar = "--borrar" in sys.argv
    if not args:
        print(__doc__.strip().splitlines()[3])
        print()
        print("    py scripts/olvidar.py 4521 KBD --ver")
        print("    py scripts/olvidar.py 4521 KBD --borrar")
        return 2

    matricula = " ".join(args)
    patron = patron_de(matricula)
    print(f"Matrícula: {matricula}   (se busca también sin espacios ni guiones)")
    print()

    encontrados = buscar(patron)
    if not encontrados:
        print("No aparece en ningún fichero. No hay nada que borrar.")
        print()
        print("Recuerda: las conversaciones en curso viven en la memoria del panel")
        print("y se pierden al reiniciarlo. Este script no llega hasta ahí.")
        return 0

    print("APARECE EN:")
    for f, n in encontrados:
        print(f"   {f.relative_to(BASE).as_posix():<34} {n} vez/veces")
    print()

    if not modo_borrar:
        print("Nada tocado. Para borrarlo de verdad, repite con --borrar.")
        return 0

    tocados = borrar(patron)
    print("BORRADA DE:")
    for f, n in tocados:
        print(f"   {f.relative_to(BASE).as_posix():<34} {n} sustitución/es")
    print()
    print("QUEDA POR HACER, y es importante:")
    print("   1. Reconstruye el índice, o la matrícula sigue viva dentro de un vector:")
    print("        py 01_ingesta_chunking.py  &&  py 02_embeddings.py")
    print("   2. Reinicia el panel, para vaciar las conversaciones en memoria:")
    print("        Ctrl+C  y  py 06_panel.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
