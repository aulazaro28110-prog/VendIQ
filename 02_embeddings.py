"""
02_embeddings.py
================
PASO 2 del sistema RAG de VendIQ: convertir cada chunk en un EMBEDDING y guardarlo.

¿Qué es un embedding? Un embedding es una lista de números (un vector) que representa el
SIGNIFICADO de un texto. Dos textos que quieren decir cosas parecidas tienen vectores
parecidos, aunque no compartan ni una palabra. Ejemplo:
  'alternador para BMW 320d'  y  'generador eléctrico de un BMW Serie 3 diésel'
tendrán vectores cercanos, porque significan casi lo mismo.

Por qué esto importa para VendIQ: el cliente no escribe con tus palabras exactas.
Buscar por significado (embeddings) recupera la pieza correcta aunque la pida "a su manera".

Coste: 0 €. El modelo se descarga una vez y corre EN TU ORDENADOR (local). No usa la API
de Anthropic ni ninguna de pago. No sale ningún dato a internet al hacer las búsquedas.

Entrada:  salida/chunks.jsonl   (lo que generó 01_ingesta_chunking.py)
Salida:   salida/embeddings.npy      (la matriz de vectores, formato NumPy)
          salida/embeddings_meta.json (a qué chunk corresponde cada vector, en orden)

Requisitos (instalar una vez):  pip install sentence-transformers
"""

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent
CHUNKS = BASE / "salida" / "chunks.jsonl"
EMB_NPY = BASE / "salida" / "embeddings.npy"
EMB_META = BASE / "salida" / "embeddings_meta.json"

# Modelo multilingüe pequeño y gratuito. 'Multilingual' = entiende español.
# Es ligero (rápido y poco espacio) y suficiente para este prototipo.
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def cargar_chunks() -> list:
    """Lee el JSONL (un JSON por línea) y devuelve la lista de chunks."""
    if not CHUNKS.exists():
        raise SystemExit(
            f"ERROR: no encuentro {CHUNKS.name}.\n"
            f"       Ejecuta primero:  python 01_ingesta_chunking.py"
        )
    chunks = []
    with open(CHUNKS, encoding="utf-8") as f:
        for linea in f:
            chunks.append(json.loads(linea))
    if not chunks:
        raise SystemExit(f"ERROR: {CHUNKS.name} está vacío. Vuelve a ejecutar el paso 1.")
    return chunks


def main():
    chunks = cargar_chunks()
    textos = [c["texto"] for c in chunks]

    print(f"Cargando el modelo '{MODELO}' (la 1ª vez se descarga; luego es instantáneo)...")
    modelo = SentenceTransformer(MODELO)

    print(f"Calculando embeddings de {len(textos)} chunks...")
    # normalize_embeddings=True deja los vectores de longitud 1. Esto hace que comparar
    # dos vectores con producto escalar sea equivalente a la 'similitud coseno' (0=nada
    # que ver, 1=idénticos en significado). Simplifica la búsqueda del paso siguiente.
    embeddings = modelo.encode(
        textos, normalize_embeddings=True, show_progress_bar=True
    )
    embeddings = np.asarray(embeddings, dtype="float32")

    # Guardamos DOS cosas, en el mismo orden:
    #   1) la matriz de vectores (embeddings.npy)
    #   2) los metadatos de cada chunk (embeddings_meta.json)
    # El vector de la fila i corresponde al chunk i. Así, tras buscar, sabemos qué pieza es.
    np.save(EMB_NPY, embeddings)

    # El JSON no es solo la lista: lleva una CABECERA con el modelo usado y las dimensiones.
    # Por qué importa:
    #   - 03_buscar.py lee de aquí qué modelo usar, en vez de tenerlo escrito otra vez.
    #     Si algún día cambias de modelo, solo se cambia en un sitio y no hay forma de
    #     que la búsqueda use un modelo distinto al del índice (eso daría resultados basura).
    #   - 'n_chunks' permite detectar que los dos ficheros se han desincronizado.
    indice = {
        "modelo": MODELO,
        "n_chunks": len(chunks),
        "dimensiones": int(embeddings.shape[1]),
        "items": [
            {"id": c["id"], "tipo": c["tipo"], "texto": c["texto"], "meta": c.get("meta", {})}
            for c in chunks
        ],
    }
    EMB_META.write_text(json.dumps(indice, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nOK. Guardado:")
    print(f"   - {EMB_NPY.name}  -> matriz {embeddings.shape} (nº chunks x nº dimensiones)")
    print(f"   - {EMB_META.name} -> {len(chunks)} metadatos + modelo usado, en el mismo orden")


if __name__ == "__main__":
    main()
