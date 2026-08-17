"""
01_ingesta_chunking.py
=======================
PASO 1 del sistema RAG de VendIQ: reunir los documentos y TROCEARLOS (chunking).

Idea en una frase: antes de que un asistente pueda "mirar la carpeta antes de hablar",
hay que cortar esa carpeta en trozos pequeños y buscables. Cada trozo = un chunk.

¿Por qué trocear y no meter el documento entero?
  - Un buscador por significado (el paso 2, embeddings) funciona mejor con trozos cortos
    y centrados en UNA cosa (una pieza, una cláusula de garantía) que con un documento gigante.
  - Cuando el cliente pregunte "¿tenéis un alternador para un BMW 320d?", queremos recuperar
    SOLO el trozo de esa pieza, no las 100 piezas de golpe.

Entrada:
  - datos/inventario_sintetico.csv   (100 piezas sintéticas, separador ';')
  - datos/politicas.md               (garantía, envío, precios... separadas por cabeceras '## ')

Salida:
  - salida/chunks.jsonl              (un chunk por línea, en formato JSON)

No instala nada: solo usa la librería estándar de Python (csv, json, re, pathlib).
"""

import csv
import json
import re
from pathlib import Path

# Rutas relativas a la carpeta de este script (así funciona desde cualquier sitio).
BASE = Path(__file__).parent
CSV_INVENTARIO = BASE / "datos" / "inventario_sintetico.csv"
MD_POLITICAS = BASE / "datos" / "politicas.md"
# Las respuestas que ha escrito una persona a preguntas que el bot no supo
# contestar (ver 09_aprender.py). Se leen aquí para que sobrevivan a una
# reconstrucción del índice: si no, cada vez que se ejecutan los pasos 01 y 02 se
# perdería todo lo que Álvaro ha ido contestando, que es lo más valioso que hay.
MD_APRENDIDAS = BASE / "datos" / "faq_aprendidas.md"
SALIDA = BASE / "salida" / "chunks.jsonl"


def chunk_de_pieza(fila: dict) -> dict:
    """Convierte UNA fila del CSV en un chunk de texto natural.

    ¿Por qué texto natural y no la fila cruda del CSV?
    Porque el buscador por significado entiende mejor una frase como
    'Alternador para BMW Serie 3 320d de 2013...' que 'id;ref;pieza;marca;...'.
    Ejemplo de entrada (fila):  {'pieza':'Alternador','marca':'BMW','modelo':'Serie 3',...}
    Ejemplo de salida (texto):  'Alternador para BMW Serie 3 320d (2013). Estado: ...'
    """
    texto = (
        f"{fila['pieza']} para {fila['marca']} {fila['modelo']} "
        f"{fila['motor']} ({fila['anio']}). "
        f"Referencia interna: {fila['id']}. "     # el cliente a veces da el nº de la web
        f"Referencia OEM: {fila['referencia_oem']}. "
        f"Estado: {fila['estado']}. "
        f"Garantía: {fila['garantia']}. "
        f"Disponibilidad: {fila['disponibilidad']}. "
        f"Precio: {fila['precio']}."
    )
    return {
        "id": f"pieza-{fila['id']}",   # id único del chunk
        "tipo": "inventario",           # de dónde viene (útil para depurar y filtrar)
        "texto": texto,                 # esto es lo que se buscará por significado
        "meta": fila,                   # guardamos la fila entera por si hace falta el dato exacto
    }


def leer_inventario() -> list:
    """Lee el CSV y devuelve una lista de chunks, uno por pieza."""
    chunks = []
    # encoding utf-8-sig quita el carácter invisible (BOM) que a veces mete Excel al inicio.
    with open(CSV_INVENTARIO, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f, delimiter=";")  # el CSV usa ';' como separador
        for fila in lector:
            chunks.append(chunk_de_pieza(fila))
    return chunks


def leer_politicas() -> list:
    """Trocea politicas.md por sus cabeceras '## '. Cada sección = un chunk.

    Estrategia de troceado para documentos de texto: cortar por su estructura natural
    (aquí, los títulos de sección). Así cada chunk trata de UN tema (garantía, envío...).
    """
    texto = MD_POLITICAS.read_text(encoding="utf-8")
    chunks = []
    # re.split con lookahead '(?=^## )' corta justo ANTES de cada línea que empieza por '## '.
    secciones = re.split(r"(?=^## )", texto, flags=re.MULTILINE)
    for sec in secciones:
        sec = sec.strip()
        if not sec.startswith("## "):
            continue  # nos saltamos el encabezado del archivo (lo de antes del primer '## ')
        lineas = sec.splitlines()
        titulo = lineas[0].replace("## ", "").strip()          # p.ej. 'GARANTIA'
        cuerpo = " ".join(l.strip() for l in lineas[1:]).strip()
        chunks.append({
            "id": f"politica-{titulo.lower().replace(' ', '_')}",
            "tipo": "politica",
            "texto": f"{titulo}. {cuerpo}",
            "meta": {"seccion": titulo},
        })
    return chunks


def leer_aprendidas() -> list:
    """Las FAQ que ha contestado una persona. Mismo formato que las políticas.

    El texto de la respuesta se guarda aparte en `meta['respuesta']` porque el
    redactor lo dice LITERAL: si alguien del equipo escribió una condición con
    esas palabras, el bot no la reformula.
    """
    if not MD_APRENDIDAS.exists():
        return []
    chunks = []
    for sec in re.split(r"(?=^## )", MD_APRENDIDAS.read_text(encoding="utf-8"),
                        flags=re.MULTILINE):
        lineas = [l.strip() for l in sec.strip().splitlines()]
        if not lineas or not lineas[0].startswith("## "):
            continue
        titulo = lineas[0].replace("## ", "").strip()
        pregunta, respuesta = "", []
        for linea in lineas[1:]:
            if linea.startswith("<!--") or not linea:
                continue
            if linea.startswith("Pregunta del cliente:"):
                pregunta = linea.split(":", 1)[1].strip()
            else:
                respuesta.append(linea)
        respuesta = " ".join(respuesta).strip()
        if not respuesta:
            continue
        chunks.append({
            "id": f"faq-{titulo.lower().replace(' ', '-')}",
            "tipo": "politica",
            "texto": f"{titulo}. {pregunta} {respuesta}",
            "meta": {"seccion": titulo, "aprendida": True, "respuesta": respuesta},
        })
    return chunks


def main():
    chunks = leer_inventario() + leer_politicas() + leer_aprendidas()

    # Guardamos en formato JSONL = 'un JSON por línea'. Es el formato estándar para
    # datasets de este tipo: fácil de leer trozo a trozo sin cargar todo en memoria.
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Pequeño resumen para saber que salió bien (verificar el artefacto, no fiarse).
    n_inv = sum(1 for c in chunks if c["tipo"] == "inventario")
    n_apr = sum(1 for c in chunks if (c.get("meta") or {}).get("aprendida"))
    n_pol = sum(1 for c in chunks if c["tipo"] == "politica") - n_apr
    print(f"OK. {len(chunks)} chunks escritos en {SALIDA.name}")
    print(f"   - inventario: {n_inv}")
    print(f"   - politicas:  {n_pol}")
    print(f"   - FAQ contestadas por una persona: {n_apr}")
    print("\nEjemplo de chunk de inventario:")
    print("  ", next(c['texto'] for c in chunks if c['tipo'] == 'inventario'))
    print("Ejemplo de chunk de politica:")
    print("  ", next(c['texto'] for c in chunks if c['tipo'] == 'politica')[:120], "...")


if __name__ == "__main__":
    main()
