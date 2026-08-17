"""
09_aprender.py
==============
LO QUE EL BOT NO SUPO, Y CÓMO APRENDE. Idea 5 de la especificación.

El ciclo, entero:

    1. El bot no sabe algo  ->  no se lo inventa, escala, y GUARDA la pregunta.
    2. Álvaro la ve en el centro de control y escribe la respuesta.
    3. Esa respuesta entra en la base de conocimiento y se indexa.
    4. La próxima vez, el bot la recupera solo.

LA PARTE QUE IMPORTA: EL PASO 2 NO SE PUEDE SALTAR
--------------------------------------------------
El bot nunca escribe su propia respuesta a lo que no sabía. No hay ningún camino
en este fichero por el que una respuesta llegue al índice sin que una persona la
haya escrito — `aprender()` exige el texto de un humano y lo firma con su nombre.

Un sistema que se autocompleta las lagunas parece más listo y es peor: la primera
respuesta inventada se convierte en la fuente de la siguiente, y a las tres
semanas el catálogo de políticas dice cosas que nadie ha decidido.

INDEXADO INCREMENTAL
--------------------
Cuando Álvaro contesta, la respuesta se indexa AL MOMENTO: se calcula su vector,
se pega al final de la matriz y el buscador que ya está cargado en memoria la
tiene desde la siguiente consulta. No hace falta reconstruir las 1.007 fichas ni
reiniciar el panel.
"""

import json
import time
from pathlib import Path

BASE = Path(__file__).parent
REGISTRO = BASE / "salida" / "no_resueltas.json"
APRENDIDAS = BASE / "datos" / "faq_aprendidas.md"


def _leer(fichero, por_defecto):
    if not fichero.exists():
        return por_defecto
    texto = fichero.read_text(encoding="utf-8-sig").strip()
    return json.loads(texto) if texto else por_defecto


def _escribir(fichero, datos):
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(json.dumps(datos, ensure_ascii=False, indent=2),
                       encoding="utf-8")


def leer_registro():
    return _leer(REGISTRO, [])


def anotar(pregunta, motivo, sesion="", decision=""):
    """Guarda una pregunta que el bot no supo responder.

    Si ya está anotada, sube el contador en vez de duplicarla: lo que interesa no
    es cuántas veces falló, es qué preguntas repiten los clientes — eso ordena por
    dónde empezar a contestar.
    """
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return None
    registro = leer_registro()
    clave = pregunta.lower()

    for entrada in registro:
        if entrada["pregunta"].lower() == clave:
            entrada["veces"] += 1
            entrada["ultima"] = time.strftime("%Y-%m-%d %H:%M")
            _escribir(REGISTRO, registro)
            return entrada

    entrada = {
        "n": max([e["n"] for e in registro], default=0) + 1,
        "pregunta": pregunta,
        "motivo": motivo,
        "decision": decision,
        "sesion": sesion,
        "veces": 1,
        "primera": time.strftime("%Y-%m-%d %H:%M"),
        "ultima": time.strftime("%Y-%m-%d %H:%M"),
        "estado": "pendiente",
        "respuesta": None,
        "respondida_por": None,
    }
    registro.append(entrada)
    _escribir(REGISTRO, registro)
    return entrada


def aprender(n, respuesta, quien="Álvaro", buscador=None):
    """Un HUMANO contesta una pregunta pendiente y pasa a la base de conocimiento.

    `respuesta` es obligatoria y la escribe una persona. No hay parámetro para
    generarla automáticamente, y es a propósito: ver la cabecera del fichero.
    """
    respuesta = (respuesta or "").strip()
    if not respuesta:
        raise SystemExit("hace falta la respuesta escrita por una persona")

    registro = leer_registro()
    entrada = next((e for e in registro if e["n"] == int(n)), None)
    if entrada is None:
        raise SystemExit(f"no existe la pregunta nº {n}")

    entrada.update({"estado": "resuelta", "respuesta": respuesta,
                    "respondida_por": quien,
                    "resuelta_el": time.strftime("%Y-%m-%d %H:%M")})
    _escribir(REGISTRO, registro)

    # Al documento de conocimiento, con su firma y su fecha: dentro de un año hay
    # que poder saber quién decidió esto y cuándo.
    titulo = f"FAQ {entrada['n']}"
    if not APRENDIDAS.exists():
        APRENDIDAS.write_text(
            "# FAQ aprendidas — respuestas escritas por una persona\n\n"
            "> Cada bloque lo escribió alguien del equipo a partir de una pregunta\n"
            "> que el asistente no supo contestar. El bot NO escribe aquí.\n",
            encoding="utf-8")
    with open(APRENDIDAS, "a", encoding="utf-8") as f:
        f.write(f"\n## {titulo}\n"
                f"Pregunta del cliente: {entrada['pregunta']}\n"
                f"{respuesta}\n"
                f"<!-- respondida por {quien} el {entrada['resuelta_el']} -->\n")

    indexado = indexar_al_vuelo(titulo, entrada["pregunta"], respuesta, buscador)
    return {"entrada": entrada, "indexado": indexado}


def indexar_al_vuelo(titulo, pregunta, respuesta, buscador):
    """Mete la respuesta nueva en el índice que ya está cargado, sin reiniciar.

    Se añade a la matriz de vectores en memoria y a los ficheros de salida, para
    que siga estando después de reiniciar. Es el mismo formato que escribe
    02_embeddings.py, así que reconstruir el índice entero da el mismo resultado.
    """
    if buscador is None:
        return "sin buscador cargado: se indexará al reconstruir (paso 01 y 02)"

    import numpy as np

    # El texto se guarda con la pregunta delante: así se encuentra tanto por lo
    # que preguntó el cliente como por lo que contestó la persona.
    texto = f"{titulo}. {pregunta} {respuesta}"
    item = {"id": f"faq-{titulo.lower().replace(' ', '-')}",
            "tipo": "politica",
            "texto": texto,
            # 'respuesta' guarda el texto EXACTO que escribió la persona. El
            # redactor lo dice tal cual, sin reformular: si Álvaro escribió una
            # condición, el bot no la reescribe con otras palabras.
            "meta": {"seccion": titulo, "aprendida": True, "respuesta": respuesta}}

    # De dónde salen `normalizar` y demás: de los globales de la propia clase del
    # buscador. Podría buscarse en sys.modules por el nombre del módulo, pero
    # 03_buscar.py se carga con importlib desde varios sitios (panel, pruebas,
    # línea de órdenes) y no siempre está registrado con el mismo alias. Los
    # globales de la clase siempre son los correctos.
    globales = type(buscador).__init__.__globals__

    vector = buscador.modelo.encode([texto], normalize_embeddings=True).astype("float32")
    buscador.embeddings = np.vstack([buscador.embeddings, vector])
    buscador.items.append(item)

    # Todo lo que va POR POSICIÓN tiene que crecer a la vez. Si una de estas listas
    # se queda corta, los índices dejan de corresponderse y el filtro estructural
    # empieza a mirar los datos de otra ficha — un fallo silencioso y muy feo.
    palabras = set(globales["normalizar"](texto))
    buscador.palabras_por_chunk.append(palabras)
    buscador.marca_de.append(None)
    buscador.modelo_de.append(None)
    buscador.tipo_pieza_de.append(None)
    buscador.lados_de.append(set())

    # El IDF también cambia: hay una ficha más y palabras nuevas.
    buscador._apariciones.update(palabras)
    buscador._n = len(buscador.items)
    if hasattr(buscador, "_posiciones"):
        buscador._posiciones[item["id"]] = len(buscador.items) - 1

    _persistir(buscador, globales)
    return f"indexada al momento: {len(buscador.items)} fichas en el índice"


def _persistir(buscador, globales):
    """Guarda matriz y metadatos, para que la respuesta siga ahí tras reiniciar."""
    import numpy as np
    salida = BASE / "salida"
    np.save(salida / "embeddings.npy", buscador.embeddings)
    (salida / "embeddings_meta.json").write_text(json.dumps({
        "modelo": globales.get("MODELO_POR_DEFECTO", ""),
        "n_chunks": len(buscador.items),
        "dimensiones": int(buscador.embeddings.shape[1]),
        "items": [{"id": i["id"], "tipo": i["tipo"], "texto": i["texto"],
                   "meta": i.get("meta", {})} for i in buscador.items],
    }, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
def main():
    import sys
    registro = leer_registro()
    if len(sys.argv) > 1 and sys.argv[1] == "responder":
        n, texto = sys.argv[2], " ".join(sys.argv[3:])
        print(aprender(n, texto)["entrada"])
        print("Reconstruye el índice para que el bot la use: "
              "python 01_ingesta_chunking.py && python 02_embeddings.py")
        return
    pendientes = [e for e in registro if e["estado"] == "pendiente"]
    print(f"{len(pendientes)} preguntas sin responder, de {len(registro)} anotadas\n")
    for e in sorted(pendientes, key=lambda e: -e["veces"]):
        print(f"  [{e['n']:>3}] x{e['veces']}  {e['pregunta']}")
        print(f"        {e['motivo']}")
    if pendientes:
        print('\nPara contestar una:  python 09_aprender.py responder 3 "El texto..."')


if __name__ == "__main__":
    main()
