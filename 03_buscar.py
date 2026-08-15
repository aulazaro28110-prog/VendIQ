"""
03_buscar.py
============
PASO 3: buscar en la base de conocimiento de VendIQ.

Esto es el "retrieval" de RAG: dada la pregunta de un cliente, recuperar los trozos
más relevantes. Todavía NO redacta la respuesta final (eso sería el LLM encima);
aquí se resuelve la parte que se rompe primero y que lo condiciona todo.

CÓMO BUSCA (búsqueda híbrida = dos criterios sumados)
-----------------------------------------------------
Buscar solo por significado (embeddings) NO funciona en un catálogo de recambios.
Motivo: las 100 fichas están redactadas con la misma plantilla, así que sus vectores
se parecen muchísimo entre sí, y las tres palabras que de verdad distinguen una pieza
(marca, modelo y nombre de la pieza) se diluyen. El resultado medido era que a la
pregunta "¿tenéis un alternador para un BMW 320d?" devolvía un cinturón de seguridad.

Por eso se combinan DOS señales:

  1. COBERTURA (léxica). ¿Qué proporción de las palabras importantes del cliente
     aparecen literalmente en la ficha? Cada palabra pesa según lo rara que sea:
     "alternador" distingue mucho, "delantero" distingue poco. Es lo que garantiza
     que la marca y la pieza pedidas estén de verdad en el resultado.

  2. SIGNIFICADO (semántica). El embedding de siempre. Es lo que permite que
     "cuánto tarda en llegar" encuentre la política de envíos sin compartir palabras.

Se usan en distinta proporción según el tipo de documento, porque se buscan distinto:
una PIEZA se identifica por datos exactos (marca, modelo, referencia), y una POLÍTICA
se pregunta con otras palabras ("¿me lo puedes rebajar?" -> política de precios).

EL UMBRAL (el guardarraíl)
--------------------------
La versión anterior devolvía SIEMPRE 3 resultados, aunque no tuviera nada que ver.
Pedirle un airbag de Ford Focus (que no está en catálogo) devolvía un airbag de
Mercedes con confianza alta. Sobre eso, un LLM redactaría una respuesta falsa.

Ahora cada resultado tiene una puntuación ABSOLUTA de 0 a 1, y si nada llega al
mínimo, `buscar()` devuelve una lista VACÍA. Ese vacío es la señal de "no lo tengo,
pregunta o escala a Álvaro" — es decir, el guardarraíl del diseño, ya ejecutable.

Uso:
    python 03_buscar.py "¿tenéis un alternador para un BMW 320d?"
Si no pasas pregunta, usa unos ejemplos por defecto.

Requisitos: haber ejecutado antes 01_ingesta_chunking.py y 02_embeddings.py.
"""

import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent
EMB_NPY = BASE / "salida" / "embeddings.npy"
EMB_META = BASE / "salida" / "embeddings_meta.json"

# Modelo por defecto SOLO para índices antiguos que no guardaban el nombre.
# El nombre real se lee de embeddings_meta.json, que lo escribe 02_embeddings.py.
MODELO_POR_DEFECTO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Cuánto pesa cada señal al ORDENAR. Es una fórmula única para todos los documentos:
# si cada tipo puntuara con pesos distintos, sus puntuaciones no serían comparables
# entre sí y ganaría siempre el tipo mejor ponderado, no el más relevante.
PESO_LEXICO = 0.60
PESO_SEMANTICO = 0.40

# Mínimos para considerar un resultado fiable. Son DOS reglas distintas a propósito,
# porque cada tipo de documento se encuentra de una manera:
#   - Una PIEZA se pide con datos exactos, así que se exige la puntuación combinada.
#   - Una POLÍTICA se pregunta con otras palabras ("¿me lo rebajas?" -> precios), así
#     que la cobertura léxica es baja aunque el trozo sea el correcto: ahí lo que vale
#     es el significado.
# Ambos números están calibrados midiendo preguntas contra piezas que SÍ están en
# catálogo y contra piezas que NO están (ver tests/test_busqueda.py).
UMBRAL_PIEZA = 0.50       # sobre la puntuación combinada
UMBRAL_POLITICA = 0.30    # sobre la similitud de significado

# ---------------------------------------------------------------------------
# REGLA DE PRECIO (la más delicada del sistema)
# ---------------------------------------------------------------------------
# VendIQ SÍ da precios, pero solo de piezas que la empresa tiene de verdad.
# Nunca da el precio de algo que no está disponible, y nunca da el precio de una
# pieza PARECIDA a la que han pedido.
#
# Por qué se exige más para dar un precio que para enseñar una candidata:
# enseñar una ficha parecida es una molestia ("no, yo quería el de otro modelo").
# Decir un precio equivocado es un compromiso comercial: el cliente se lo cree,
# viene a por ella, y alguien tiene que decirle que no. Cuesta dinero y confianza.
# Por eso el precio pasa por una puerta más estrecha, con TRES condiciones.
UMBRAL_PRECIO = 0.65      # más alto que UMBRAL_PIEZA a propósito

# Qué se considera "disponible". Lo que no esté aquí, no lleva precio.
DISPONIBILIDAD_VALIDA = {"en stock", "bajo pedido 24-48h"}

# Palabras de relleno: aparecen en cualquier mensaje y no ayudan a distinguir nada.
PALABRAS_VACIAS = {
    "que", "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "para", "por", "con", "sin", "y", "o", "a", "al", "en", "es", "son", "me",
    "te", "se", "lo", "mi", "tu", "su", "hay", "tiene", "tienen", "teneis",
    "tenes", "tienes", "tengo", "busco", "buscando", "necesito", "quiero",
    "queria", "quisiera", "hola", "buenas", "gracias", "porfa", "favor",
    "pieza", "piezas", "coche", "vehiculo", "seria", "sera", "cuanto", "cuanta",
    "como", "cual", "cuales", "donde", "cuando", "si", "no", "mas", "menos",
    "este", "esta", "esa", "ese", "vale", "puedo", "puedes", "podeis",
}


def normalizar(texto: str) -> list:
    """Parte un texto en palabras comparables: sin tildes, en minúsculas, sin signos.

    Es lo que hace que 'garantía' y 'garantia' cuenten como la misma palabra —
    imprescindible cuando los mensajes llegan por WhatsApp escritos deprisa.
    """
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", texto.lower())


class Buscador:
    """Guarda el índice ya preparado y responde consultas."""

    def __init__(self, embeddings, items, modelo):
        self.embeddings = embeddings
        self.items = items
        self.modelo = modelo
        # Precios que Álvaro fija a mano desde el centro de control: {id_pieza: "120,00 € + IVA"}
        self.precios_fijados = {}

        # Preparamos la parte léxica UNA vez, no en cada consulta.
        self.palabras_por_chunk = [set(normalizar(it["texto"])) for it in items]
        n = len(items)
        apariciones = Counter()
        for palabras in self.palabras_por_chunk:
            apariciones.update(palabras)
        self._apariciones = apariciones
        self._n = n
        # Peso máximo: el de una palabra que no aparece en NINGUNA ficha.
        self._idf_max = math.log(1 + (n + 0.5) / 0.5)

        self._preparar_vocabulario()

    def _preparar_vocabulario(self):
        """Aprende del propio catálogo qué marcas y qué tipos de pieza existen.

        No hay ninguna lista escrita a mano: sale de los datos, así que el día que
        entren piezas o marcas nuevas esto se actualiza solo al re-ejecutar el paso 2.
        """
        self.marca_de = []      # por chunk: marca canónica, o None si no es una pieza
        self.tipo_pieza_de = []  # por chunk: palabra que nombra la pieza ('alternador'...)
        self.marcas_conocidas = {}   # 'bmw' -> 'BMW',  'mercedes' -> 'MERCEDES-BENZ'
        self.tipos_conocidos = set()

        for item in self.items:
            meta = item.get("meta") or {}
            marca = meta.get("marca")
            pieza = meta.get("pieza")
            if item["tipo"] != "inventario" or not marca or not pieza:
                self.marca_de.append(None)
                self.tipo_pieza_de.append(None)
                continue

            for token in normalizar(marca):
                if len(token) > 1:
                    self.marcas_conocidas[token] = marca

            # La palabra que nombra la pieza es la primera con contenido:
            # 'Bomba de agua' -> 'bomba', 'Puerta delantera derecha' -> 'puerta'.
            # Lo que sigue ('delantera', 'derecha') solo matiza, y el cliente puede
            # omitirlo o decirlo de otra manera.
            tokens = [t for t in normalizar(pieza)
                      if t not in PALABRAS_VACIAS and len(t) > 2]
            cabeza = tokens[0] if tokens else None
            if cabeza:
                self.tipos_conocidos.add(cabeza)

            self.marca_de.append(marca)
            self.tipo_pieza_de.append(cabeza)

    def _descartar_incompatibles(self, pregunta: str) -> np.ndarray:
        """Máscara: qué fichas siguen siendo candidatas después de leer la pregunta.

        Aquí está la regla de negocio que el umbral solo no puede cubrir: si el cliente
        pide un CATALIZADOR de AUDI, no se le puede ofrecer una BOMBA DE AGUA de Audi
        por muy parecidas que sean las dos fichas. Antes pasaba exactamente eso.

        Solo se filtra por lo que el cliente ha dicho de forma reconocible. Si usa una
        palabra que no está en el catálogo ('generador' en vez de 'alternador'), no se
        filtra nada y la búsqueda funciona como antes: nunca deja al cliente sin respuesta
        por no usar el vocabulario exacto de la empresa.
        """
        palabras = set(normalizar(pregunta))
        marcas_pedidas = {self.marcas_conocidas[p] for p in palabras
                          if p in self.marcas_conocidas}
        tipos_pedidos = palabras & self.tipos_conocidos

        candidatas = np.ones(len(self.items), dtype=bool)
        if not marcas_pedidas and not tipos_pedidos:
            return candidatas

        for i, item in enumerate(self.items):
            if item["tipo"] != "inventario":
                continue  # las políticas siempre siguen disponibles
            if marcas_pedidas and self.marca_de[i] not in marcas_pedidas:
                candidatas[i] = False
            elif tipos_pedidos and self.tipo_pieza_de[i] not in tipos_pedidos:
                candidatas[i] = False
        return candidatas

    def _peso(self, palabra: str) -> float:
        """Cuánto distingue una palabra (IDF). Rara = pesa mucho; común = pesa poco.

        Ojo al caso importante: si la palabra no está en NINGUNA ficha (p. ej. 'ferrari'),
        pesa el máximo. Así, pedir un alternador de Ferrari nunca puede puntuar alto
        con el alternador de un BMW: la marca que falta arrastra la puntuación abajo.
        Esto es justo lo que permite responder "esa no la tengo".
        """
        n = self._apariciones.get(palabra, 0)
        if n == 0:
            return self._idf_max
        return math.log(1 + (self._n - n + 0.5) / (n + 0.5))

    def _cobertura(self, pregunta: str) -> np.ndarray:
        """Proporción (0..1) del peso de la pregunta que cubre cada chunk."""
        palabras = [p for p in normalizar(pregunta)
                    if p not in PALABRAS_VACIAS and len(p) > 1]
        if not palabras:
            return np.zeros(len(self.items))
        pesos = {p: self._peso(p) for p in set(palabras)}
        total = sum(pesos.values())
        return np.array([
            sum(w for p, w in pesos.items() if p in encontradas) / total
            for encontradas in self.palabras_por_chunk
        ])

    def _significado(self, pregunta: str) -> np.ndarray:
        """Similitud coseno (0..1) entre la pregunta y cada chunk."""
        v = self.modelo.encode([pregunta], normalize_embeddings=True)[0].astype("float32")
        return self.embeddings @ v

    def buscar(self, pregunta: str, k: int = 3, aplicar_umbral: bool = True) -> list:
        """Devuelve hasta k resultados [(puntuacion, item), ...], el mejor primero.

        Devuelve [] si nada supera el umbral: eso significa "no lo tengo en la carpeta",
        y es la señal para que el asistente pregunte o escale en vez de inventarse algo.
        """
        if not pregunta or not pregunta.strip():
            return []

        cobertura = self._cobertura(pregunta)
        significado = self._significado(pregunta)
        puntuaciones = PESO_LEXICO * cobertura + PESO_SEMANTICO * significado

        # Las fichas incompatibles con lo que ha pedido el cliente quedan fuera de juego.
        puntuaciones = np.where(self._descartar_incompatibles(pregunta), puntuaciones, -1.0)

        resultados = []
        ya_hubo_pieza = False
        for i in np.argsort(puntuaciones)[::-1][:k]:
            item = self.items[i]
            if aplicar_umbral and not self._es_fiable(item, puntuaciones[i], significado[i]):
                continue
            es_mejor = item["tipo"] == "inventario" and not ya_hubo_pieza
            if item["tipo"] == "inventario":
                ya_hubo_pieza = True
            # La decisión de precio viaja PEGADA a cada resultado. Así quien consuma
            # la búsqueda (el panel hoy, el LLM mañana) no puede olvidarse de mirarla:
            # le llega junto al dato, no en una llamada aparte que se pueda saltar.
            enriquecido = dict(item)
            enriquecido["precio_cliente"] = self.precio_para_cliente(
                item, float(puntuaciones[i]), pregunta, es_mejor_candidata=es_mejor)
            resultados.append((float(puntuaciones[i]), enriquecido))
        return resultados

    @staticmethod
    def _es_fiable(item, puntuacion, significado) -> bool:
        """¿Este resultado es lo bastante bueno como para enseñárselo a un cliente?"""
        if item["tipo"] == "politica":
            return significado >= UMBRAL_POLITICA
        return puntuacion >= UMBRAL_PIEZA

    def precio_para_cliente(self, item, puntuacion, pregunta,
                            es_mejor_candidata=True) -> dict:
        """¿Se le puede decir el precio de esta pieza al cliente? Y si no, por qué no.

        Devuelve siempre el motivo, no solo un sí/no: el asistente tiene que poder
        explicárselo al cliente ("esa la tengo pero sin precio publicado, te confirmo")
        y Álvaro tiene que poder ver en el panel por qué no salió el precio.

        CUATRO condiciones, y hacen falta las cuatro:
          1. Que sea la mejor candidata. Las demás son, por definición, otras piezas.
          2. Que la pieza esté disponible. Si no la tenemos, no hay precio que dar.
          3. Que tenga precio publicado. "Consultar por WhatsApp" no es un precio.
          4. Que estemos SEGUROS de que es la pieza que pidió, no una parecida.

        La condición 1 sale de un fallo real detectado en las pruebas: un cliente pedía
        la puerta TRASERA izquierda de un Skoda (sin precio publicado) y el sistema le
        daba el precio de la puerta DELANTERA izquierda del mismo coche, que salía
        segunda. Ambas son "puerta" y ambas superaban la confianza mínima. Si la mejor
        coincidencia no tiene precio, la respuesta correcta es "te lo confirmo",
        nunca el precio de la de al lado.
        """
        no = lambda motivo, estado: {"publicable": False, "importe": None,
                                     "estado": estado, "motivo": motivo}

        if item["tipo"] != "inventario":
            return no("no es una pieza", "no_aplica")

        if not es_mejor_candidata:
            return no("hay otra ficha que encaja mejor con lo que ha pedido: "
                      "no se da el precio de una pieza parecida", "no_es_la_mejor")

        meta = item.get("meta") or {}
        disponibilidad = (meta.get("disponibilidad") or "").strip()
        if disponibilidad.lower() not in DISPONIBILIDAD_VALIDA:
            return no(f"no disponible ({disponibilidad or 'sin dato'}): "
                      f"no se da precio de lo que no se tiene", "sin_stock")

        # Un precio que Álvaro haya fijado desde el centro de control manda sobre el
        # del catálogo. Es lo que convierte su trabajo manual en conocimiento del
        # sistema: en cuanto pone el precio de una pieza, el bot ya puede venderla.
        texto_precio = (self.precios_fijados.get(str(meta.get("id")))
                        or meta.get("precio") or "").strip()
        if "onsultar" in texto_precio or not texto_precio:
            return no("sin precio publicado: lo confirma Álvaro", "precio_pendiente")

        # Condición 3: seguridad de que es LA pieza pedida, no una hermana.
        # Se exige puntuación alta Y que el cliente haya nombrado el tipo de pieza
        # de forma reconocible. Sin lo segundo, un "busco algo para mi Audi" podría
        # acabar dando el precio de una pieza cualquiera de Audi.
        palabras = set(normalizar(pregunta))
        tipo_pedido = palabras & self.tipos_conocidos
        indice = self._indice_de(item)
        tipo_ficha = self.tipo_pieza_de[indice] if indice is not None else None

        if not tipo_pedido or tipo_ficha not in tipo_pedido:
            return no("el cliente no ha nombrado la pieza con claridad: se confirma "
                      "antes de dar precio", "sin_confirmar")

        if puntuacion < UMBRAL_PRECIO:
            return no(f"confianza {puntuacion:.2f}, por debajo de {UMBRAL_PRECIO:.2f}: "
                      f"podría ser una pieza parecida", "confianza_baja")

        return {"publicable": True, "importe": texto_precio, "estado": "publicable",
                "motivo": f"pieza identificada con confianza {puntuacion:.2f} y "
                          f"{disponibilidad.lower()}"}

    def _indice_de(self, item):
        """Posición del item en el índice (para consultar sus datos derivados)."""
        if not hasattr(self, "_posiciones"):
            self._posiciones = {it["id"]: i for i, it in enumerate(self.items)}
        return self._posiciones.get(item["id"])


def cargar_buscador() -> Buscador:
    """Carga el índice del paso 2, comprobando que está completo y coherente."""
    if not EMB_NPY.exists() or not EMB_META.exists():
        raise SystemExit(
            "ERROR: falta el índice de búsqueda.\n"
            "       Ejecuta antes, en este orden:\n"
            "         python 01_ingesta_chunking.py\n"
            "         python 02_embeddings.py"
        )

    embeddings = np.load(EMB_NPY)
    datos = json.loads(EMB_META.read_text(encoding="utf-8"))

    # Formato nuevo: un objeto con cabecera. Formato antiguo: una lista pelada.
    if isinstance(datos, dict):
        items = datos["items"]
        nombre_modelo = datos.get("modelo", MODELO_POR_DEFECTO)
    else:
        items = datos
        nombre_modelo = MODELO_POR_DEFECTO

    # Comprobación de coherencia. Sin esto, si re-ejecutas el paso 1 y olvidas el 2,
    # la búsqueda devolvería los datos de OTRA pieza sin dar ningún error: el peor
    # tipo de fallo, porque no se ve.
    if len(embeddings) != len(items):
        raise SystemExit(
            f"ERROR: el índice está desincronizado "
            f"({len(embeddings)} vectores frente a {len(items)} fichas).\n"
            f"       Vuelve a ejecutar:  python 02_embeddings.py"
        )

    modelo = SentenceTransformer(nombre_modelo)
    dim_indice = embeddings.shape[1]
    # El nombre del método cambió en versiones recientes de sentence-transformers.
    obtener_dim = (getattr(modelo, "get_embedding_dimension", None)
                   or modelo.get_sentence_embedding_dimension)
    dim_modelo = obtener_dim()
    if dim_indice != dim_modelo:
        raise SystemExit(
            f"ERROR: el índice se creó con otro modelo "
            f"({dim_indice} dimensiones frente a {dim_modelo}).\n"
            f"       Vuelve a ejecutar:  python 02_embeddings.py"
        )

    return Buscador(embeddings, items, modelo)


def main():
    buscador = cargar_buscador()

    if len(sys.argv) > 1:
        preguntas = [" ".join(sys.argv[1:])]
    else:
        preguntas = [
            "¿tenéis un alternador para un BMW 320d?",
            "cuanto tiempo tarda en llegar el pedido",
            "la pieza tiene garantia?",
            "quiero un airbag de un Ford Focus 2011",   # NO está en catálogo
        ]

    for pregunta in preguntas:
        print(f"\nCLIENTE: {pregunta}")
        resultados = buscador.buscar(pregunta)
        if not resultados:
            print("VendIQ NO tiene esto en su carpeta.")
            print("  -> debe preguntar por más datos o escalar a Álvaro. Nunca inventar.")
            continue
        print("VendIQ recuperaría estos trozos (más relevante primero):")
        for puntuacion, item in resultados:
            print(f"  [{puntuacion:.2f}] ({item['tipo']}) {item['texto'][:100]}")


if __name__ == "__main__":
    main()
