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
# 0.34 y no 0.30: el barrido de --calibrar dice que hasta 0.34 se siguen
# encontrando el 100% de las políticas del banco, así que subirlo es gratis y
# deja fuera preguntas que solo se parecían de lejos.
UMBRAL_POLITICA = 0.34    # sobre la similitud de significado

# Las FAQ que escribe una persona (09_aprender.py) se juzgan aparte y por la
# puntuación COMBINADA, no por el significado. Son de una línea, y un chunk de 14
# palabras tiene un vector difuso que se parece un poco a todo: la FAQ 18 sacaba
# 0,36-0,40 de significado igual ante un saludo que ante la pregunta para la que
# se escribió. Eso no es señal. Lo que la distingue es que las palabras estén:
# cobertura 1,00 en su pregunta y 0,00 en las demás — combinada 0,74 contra 0,16.
#
# El listón es alto a propósito. Una FAQ que no salta manda la pregunta a una
# persona, que es de donde salió; una FAQ que salta de más le dice al cliente una
# condición inventada. Los dos errores no cuestan lo mismo.
UMBRAL_FAQ = 0.50         # sobre la puntuación combinada

# Peso discriminante mínimo para fiarse de la señal léxica. Equivale a una palabra
# que aparezca en menos de un tercio de las fichas: por debajo de eso, la pregunta
# está hecha de palabras que comparte medio catálogo y la coincidencia no significa
# nada. Ver _cobertura().
INFORMACION_MINIMA = 1.0

# Los dos ejes de un coche. Un piloto trasero IZQUIERDO y uno DERECHO comparten
# casi todas las palabras, así que para el buscador se parecen muchísimo — y para
# el cliente son piezas distintas que no valen la una por la otra. Esta tabla es
# la única lista escrita a mano del sistema, y es corta a propósito: se limita a
# decir qué palabras se excluyen entre sí.
LADOS = {"izquierdo": "izq", "izquierda": "izq", "izq": "izq",
         "derecho": "der", "derecha": "der", "dcho": "der", "dcha": "der",
         "delantero": "del", "delantera": "del", "delant": "del",
         "trasero": "tra", "trasera": "tra", "tras": "tra"}
OPUESTO = {"izq": "der", "der": "izq", "del": "tra", "tra": "del"}


def _lados(tokens) -> set:
    """Qué lados nombra un texto ya normalizado: {'tra', 'izq'}, o vacío."""
    return {LADOS[t] for t in tokens if t in LADOS}

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
#
# ES LA ÚNICA LISTA A MANO QUE QUEDA, y hace falta explicar por qué. Todo lo demás
# (marcas, modelos, tipos de pieza) se aprende del catálogo, pero estas palabras no
# están en ningún catálogo: son la forma de hablar del cliente. Y no filtrarlas
# cuesta ventas de verdad, porque una palabra que no aparece en ninguna ficha se
# lleva el peso máximo. "colector, la que te digo siempre" perdía contra sí misma:
# 'digo' y 'siempre' pesaban más que 'colector' y la pieza correcta se quedaba en
# 0,31 sobre un mínimo de 0,50.
#
# En un despliegue real esta lista NO se escribe: se saca de los mensajes que ya
# tiene la empresa en WhatsApp, quedándose con las palabras más frecuentes que no
# son de catálogo. Aquí está a mano porque no hay ese registro.
PALABRAS_VACIAS = {
    # gramática
    "que", "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "para", "por", "con", "sin", "y", "o", "a", "al", "en", "es", "son", "me",
    "te", "se", "lo", "mi", "tu", "su", "hay", "tiene", "tienen", "teneis",
    "tenes", "tienes", "tengo", "este", "esta", "esa", "ese", "esos", "esas",
    "otro", "otra", "mismo", "misma", "algo", "nada", "cosa", "aqui", "alli",
    # peticiones
    "busco", "buscando", "necesito", "quiero", "queria", "quisiera",
    "puedo", "puedes", "podeis", "pasame", "dime", "mandame", "ponme",
    # cortesía y muletillas de WhatsApp
    "hola", "buenas", "gracias", "porfa", "favor", "oye", "mira", "pues",
    "bueno", "venga", "vale", "digo", "dices", "sabes", "creo", "siempre",
    "luego", "entonces", "tambien", "ademas", "solo", "ya", "aun", "todavia",
    "muy", "tan", "poco", "mucho", "bien", "mal", "ahora", "hoy", "manana",
    # vocabulario que está en TODAS las fichas y por tanto no distingue nada
    "pieza", "piezas", "coche", "vehiculo", "referencia", "precio", "garantia",
    # interrogativos
    "seria", "sera", "cuanto", "cuanta", "como", "cual", "cuales", "donde",
    "cuando", "si", "no", "mas", "menos",
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
        self.lados_de = []       # por chunk: {'izq'} / {'tra','izq'} / set()
        self.nombre_de = []      # por chunk: nombre completo de la pieza
        # {frozenset({'motor','completo'}): 'Motor completo', ...}
        self.nombres_pieza = {}
        self.modelo_de = []      # por chunk: modelo canónico ('C4', 'Serie 3'...)
        self.marcas_conocidas = {}   # 'bmw' -> 'BMW',  'mercedes' -> 'MERCEDES-BENZ'
        self.modelos_conocidos = {}  # 'c4' -> {'C4'},  'serie' -> {'Serie 3','Serie 5'}
        self.tipos_conocidos = set()
        self.por_codigo = {}     # '69328' / '7891vt72e' -> posición en el índice
        # Máscara por posición: True si el chunk es una política. Se usa para
        # enrutar y se precalcula porque se consulta en cada búsqueda.
        self.es_politica = np.array([it["tipo"] == "politica" for it in self.items])

        for item in self.items:
            meta = item.get("meta") or {}
            marca = meta.get("marca")
            pieza = meta.get("pieza")
            modelo = meta.get("modelo")
            if item["tipo"] != "inventario" or not marca or not pieza:
                self.marca_de.append(None)
                self.modelo_de.append(None)
                self.tipo_pieza_de.append(None)
                self.lados_de.append(set())
                self.nombre_de.append(None)
                continue

            for token in normalizar(marca):
                if len(token) > 1:
                    self.marcas_conocidas[token] = marca
            # Palabras que DISTINGUEN el modelo: sin relleno, y los números
            # cuentan aunque sean de un dígito — el "3" de "Serie 3" es justo lo
            # que lo separa del "Serie 1".
            distintivas = frozenset(
                t for t in normalizar(modelo or "")
                if t not in PALABRAS_VACIAS and (len(t) > 1 or t.isdigit()))
            if distintivas:
                self.modelos_conocidos[modelo] = distintivas

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
            self.modelo_de.append(modelo)
            self.tipo_pieza_de.append(cabeza)
            self.lados_de.append(_lados(tokens))
            self.nombre_de.append(pieza)
            if len(tokens) > 1:
                self.nombres_pieza[frozenset(tokens)] = pieza

            # Índice de códigos exactos. Un código no se parece a otro: o coincide
            # o no. Ver el atajo en buscar().
            for codigo in (meta.get("id"), meta.get("referencia_oem")):
                for token in normalizar(str(codigo or "")):
                    if len(token) >= 4:
                        self.por_codigo[token] = len(self.marca_de) - 1

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
        secuencia = normalizar(pregunta)
        palabras = set(secuencia)
        marcas_pedidas = {self.marcas_conocidas[p] for p in palabras
                          if p in self.marcas_conocidas}
        tipos_pedidos = palabras & self.tipos_conocidos

        # EL MODELO. Pedir un Citroën C4 y recibir un C3 es el mismo error que pedir
        # un catalizador y recibir una bomba de agua.
        #
        # La primera versión unía todos los modelos que compartieran una palabra con
        # la pregunta, para "filtrar solo lo que seguro que no es". Con 5.000 piezas
        # eso soltó dos precios equivocados: quien pedía un MERCEDES CLASE E COUPÉ
        # recibía el precio de un CLASE A, y quien pedía un BMW SERIE 3 recibía el
        # de un SERIE 1. Comparten la palabra "clase" y "serie", y la unión los
        # daba por buenos a los dos.
        #
        # Regla nueva, en dos pasos:
        #   1. Un modelo es candidato solo si TODAS sus palabras distintivas están
        #      en la pregunta. "Serie 1" necesita el "1", y no está.
        #   2. De los que quedan, mandan los que aportan MÁS palabras. Pedir
        #      "Clase E Coupé" deja fuera al "Clase A", que solo aporta "clase".
        candidatos = {m: t for m, t in self.modelos_conocidos.items()
                      if t <= palabras}
        modelos_pedidos = set()
        if candidatos:
            mejor = max(len(t) for t in candidatos.values())
            modelos_pedidos = {m for m, t in candidatos.items() if len(t) == mejor}

        # EL NÚCLEO: cuando el cliente nombra dos tipos de pieza en el mismo mensaje,
        # manda el PRIMERO. En español el núcleo del sintagma va delante y lo que
        # sigue lo complementa: "centralita motor" es una centralita, no un motor;
        # "cerradura puerta delantera" es una cerradura, no una puerta.
        # Sin esta regla el buscador contestaba con un MOTOR DE ARRANQUE a quien
        # pedía una CENTRALITA MOTOR, porque la palabra 'motor' está en los dos.
        nucleo = next((p for p in secuencia if p in self.tipos_conocidos), None)

        # EL NOMBRE COMPLETO manda sobre el núcleo. "Motor completo" y "Motor de
        # arranque" comparten núcleo ('motor') y son piezas que no se parecen en
        # nada: una vale 3.000 € y la otra 60. El núcleo no puede separarlas, y a
        # 5.000 piezas eso se convirtió en las dos únicas fugas del guardarraíl.
        #
        # Si el cliente ha dicho TODAS las palabras de un nombre del catálogo, ya
        # no hay nada que adivinar: quiere esa pieza y ninguna otra. Se busca la
        # coincidencia más larga, por si un nombre estuviera contenido en otro.
        nombre_pedido = None
        for tokens, nombre in self.nombres_pieza.items():
            if tokens <= palabras and (nombre_pedido is None
                                       or len(tokens) > len(nombre_pedido[0])):
                nombre_pedido = (tokens, nombre)
        nombre_pedido = nombre_pedido[1] if nombre_pedido else None

        # EL LADO: si el cliente dice izquierdo y la ficha dice derecho, no es la
        # pieza aunque todo lo demás coincida. Esto también salía de un fallo real.
        lados_pedidos = _lados(secuencia)

        candidatas = np.ones(len(self.items), dtype=bool)
        if not (marcas_pedidas or tipos_pedidos or modelos_pedidos or nombre_pedido):
            return candidatas

        for i, item in enumerate(self.items):
            if item["tipo"] != "inventario":
                continue  # las políticas siempre siguen disponibles
            if marcas_pedidas and self.marca_de[i] not in marcas_pedidas:
                candidatas[i] = False
            elif modelos_pedidos and self.modelo_de[i] not in modelos_pedidos:
                candidatas[i] = False
            elif nombre_pedido and self.nombre_de[i] != nombre_pedido:
                candidatas[i] = False
            elif nucleo and self.tipo_pieza_de[i] != nucleo:
                candidatas[i] = False
            elif tipos_pedidos and self.tipo_pieza_de[i] not in tipos_pedidos:
                candidatas[i] = False
            elif any(OPUESTO[l] in self.lados_de[i] for l in lados_pedidos):
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

    def _cobertura(self, pregunta: str):
        """Cobertura (0..1) de cada chunk, y cuánta información traía la pregunta.

        La cobertura sola engaña cuando TODAS las palabras del cliente aparecen en
        TODAS las fichas. "¿El precio lleva IVA incluido?" es el caso puro: 'precio'
        e 'iva' están en las 1.000 fichas del catálogo, así que las 1.000 cubren el
        100% de la pregunta y todas puntúan altísimo — y la respuesta correcta no es
        ninguna pieza, es la política de precios, que se quedaba fuera.

        Por eso se devuelve también la CONFIANZA LÉXICA: cuánto peso discriminante
        traía la pregunta en total. Si es casi cero, la señal léxica no dice nada y
        hay que fiarse del significado. No es un parche para dos preguntas: es que
        una pregunta hecha solo de palabras que todos comparten no aporta evidencia.
        """
        # Se descarta la CHÁCHARA: palabras cortas que no aparecen en ninguna ficha.
        # Es el fallo que más caro salía en los mensajes reales de WhatsApp. En
        # "teneis intercooler pa un peugeot 208 1.6 hdi", el "pa" no está en ninguna
        # ficha, así que se lleva el peso máximo (7,6, más que 'intercooler') y como
        # nadie puede cubrirlo hunde la puntuación de 0,82 a 0,60 — por debajo del
        # mínimo para dar precio. El cliente escribía bien y se quedaba sin respuesta
        # por una preposición mal escrita.
        #
        # Solo se descartan las CORTAS. Una palabra larga desconocida sí es
        # información ('ferrari' tiene que seguir hundiendo la puntuación de un
        # alternador de BMW: es justo lo que permite decir "esa no la tengo").
        palabras = [p for p in normalizar(pregunta)
                    if p not in PALABRAS_VACIAS and len(p) > 1
                    and not (len(p) <= 3 and self._apariciones.get(p, 0) == 0)]
        if not palabras:
            return np.zeros(len(self.items)), 0.0

        # De las palabras que NO están en ninguna ficha solo cuenta UNA.
        # El motivo: "aquí hay algo que no tenemos" es un hecho binario. Repetirlo
        # no lo hace más cierto, y sí hunde la puntuación de forma acumulativa.
        # Con la regla vieja, "colector, la que te digo siempre" perdía contra su
        # propia charla: 'digo' y 'siempre' se llevaban 15 puntos de peso entre las
        # dos —más que 'colector', 'peugeot' y '208' juntas— y la pieza correcta se
        # quedaba en 0,46, por debajo del umbral. Así el cliente puede hablar como
        # habla, y una marca que no vendemos ('ferrari') sigue hundiendo la
        # puntuación igual que antes, porque con una sola vez basta.
        desconocidas = sorted((p for p in set(palabras)
                               if self._apariciones.get(p, 0) == 0),
                              key=len, reverse=True)
        ignoradas = set(desconocidas[1:])
        pesos = {p: self._peso(p) for p in set(palabras) if p not in ignoradas}
        total = sum(pesos.values())
        confianza = min(1.0, total / INFORMACION_MINIMA)
        cobertura = np.array([
            sum(w for p, w in pesos.items() if p in encontradas) / total
            for encontradas in self.palabras_por_chunk
        ])
        return cobertura, confianza

    def _significado(self, pregunta: str) -> np.ndarray:
        """Similitud coseno (0..1) entre la pregunta y cada chunk."""
        v = self.modelo.encode([pregunta], normalize_embeddings=True)[0].astype("float32")
        return self.embeddings @ v

    def _habla_de_pieza(self, pregunta: str) -> bool:
        """¿Nombra la pregunta algo que identifique una pieza del catálogo?

        Tipo, marca, modelo o código: cualquiera de los cuatro basta. Los cuatro
        vocabularios salen del propio catálogo, no de una lista escrita a mano.
        """
        palabras = set(normalizar(pregunta))
        return bool(palabras & self.tipos_conocidos
                    or palabras & set(self.marcas_conocidas)
                    or palabras & set(self.modelos_conocidos)
                    or any(self.por_codigo.get(p) is not None for p in palabras))

    def buscar(self, pregunta: str, k: int = 3, aplicar_umbral: bool = True) -> list:
        """Devuelve hasta k resultados [(puntuacion, item), ...], el mejor primero.

        Devuelve [] si nada supera el umbral: eso significa "no lo tengo en la carpeta",
        y es la señal para que el asistente pregunte o escale en vez de inventarse algo.
        """
        if not pregunta or not pregunta.strip():
            return []

        cobertura, confianza_lexica = self._cobertura(pregunta)
        significado = self._significado(pregunta)
        puntuaciones = (PESO_LEXICO * confianza_lexica * cobertura
                        + PESO_SEMANTICO * significado)

        # Las fichas incompatibles con lo que ha pedido el cliente quedan fuera de juego.
        puntuaciones = np.where(self._descartar_incompatibles(pregunta), puntuaciones, -1.0)

        # ENRUTADO: ¿esta pregunta va de una PIEZA o de una CONDICIÓN?
        #
        # Era el punto flojo del sistema y la causa estaba medida: el modelo da
        # ~0,47 de parecido a *cualquier* ficha frente a *cualquier* pregunta en
        # español, y la política correcta saca 0,40. Así que "¿el precio lleva
        # IVA?" devolvía una pieza — porque las 5.000 fichas dicen literalmente
        # "Precio:" y "+ IVA".
        #
        # No se puede resolver por vocabulario: se comprobó que NO existe ni una
        # palabra que salga en las políticas y en ninguna ficha. Lo que sí
        # distingue es lo que la pregunta NO dice. Si no nombra tipo de pieza, ni
        # marca, ni modelo, ni código, no está preguntando por una pieza concreta,
        # y las fichas salen de la puja.
        #
        # Los cuatro vocabularios se aprenden del catálogo al indexar: esto no es
        # una lista escrita a mano. Si mañana entran motos, crece solo.
        solo_politicas = not self._habla_de_pieza(pregunta)
        if solo_politicas:
            puntuaciones = np.where(self.es_politica, puntuaciones, -1.0)

        # ATAJO POR CÓDIGO EXACTO. Si el cliente da el nº de stock de la web o la
        # referencia OEM, la pieza está identificada y no hay nada que puntuar: un
        # código no se parece a otro, o coincide o no.
        # Hacía falta porque el resto del mensaje lo estropeaba: "me interesa la
        # pieza 69328 que tenéis en la web" se quedaba en 0,25 —por debajo del
        # umbral— cuando el 69328 identificaba la ficha sin ninguna duda. Las
        # palabras de alrededor no pueden tapar un dato exacto.
        for token in set(normalizar(pregunta)):
            posicion = self.por_codigo.get(token)
            if posicion is not None:
                puntuaciones[posicion] = 1.0

        # El umbral se aplica ANTES de cortar por k, y no después. Parece un detalle
        # y no lo es: el umbral de una política es absoluto (mira el significado, no
        # la posición), así que una política puede merecer respuesta y aun así quedar
        # fuera del top-k por culpa del ruido de las 1.000 fichas de inventario.
        # Pasaba de verdad: "¿y de garantía qué me das?" no encontraba la política de
        # garantía porque tres piezas cualesquiera puntuaban por delante y se comían
        # los tres huecos. Filtrar primero y recortar después lo arregla, y no cambia
        # nada para el inventario, cuyo umbral sí depende de la puntuación.
        orden = np.argsort(puntuaciones)[::-1]
        if aplicar_umbral:
            orden = [i for i in orden
                     if self._es_fiable(self.items[i], puntuaciones[i],
                                        significado[i], solo_politicas)]
        resultados = []
        ya_hubo_pieza = False
        for i in orden[:k]:
            item = self.items[i]
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
    def _es_fiable(item, puntuacion, significado, solo_politicas=False) -> bool:
        """¿Este resultado es lo bastante bueno como para enseñárselo a un cliente?

        Una política se acepta por SIGNIFICADO. Pero cuando el enrutado ya ha
        decidido que la pregunta no va de una pieza, también vale la evidencia
        LÉXICA: ahí las únicas candidatas son políticas, así que la puntuación
        combinada —que pesa las palabras por IDF— es mejor información que el
        significado a secas, y no puede perjudicar a ninguna ficha.

        Salió de un fallo real: «¿enviáis a Canarias?» no encontraba nada, y la
        política de envío dice literalmente «Baleares, Canarias, Ceuta y Melilla
        se consulta aparte». El chunk habla sobre todo de la península y de
        plazos, así que su embedding no se parece a la pregunta — pero la palabra
        está ahí, y es rara, y solo está en ese chunk. Tirar esa evidencia era
        perder una respuesta que sí teníamos.
        """
        # Una FAQ aprendida es una respuesta escrita para UNA pregunta. Si las
        # palabras del cliente no están en ella, no es su respuesta: se exige
        # evidencia léxica y no se acepta por parecido semántico a secas.
        if (item.get("meta") or {}).get("aprendida"):
            return puntuacion >= UMBRAL_FAQ

        if item["tipo"] == "politica":
            if significado >= UMBRAL_POLITICA:
                return True
            # El umbral es el de POLÍTICA, no el de pieza: aquí ya no compite con
            # ninguna ficha, así que exigirle el listón de una pieza no protege de
            # nada y solo tira respuestas buenas. Medido en «¿enviáis a Canarias?»:
            # la política correcta saca 0,376 y la siguiente 0,092 — cuatro veces
            # menos. No había ambigüedad, había un umbral mal elegido.
            return solo_politicas and puntuacion >= UMBRAL_POLITICA
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

        # Condición 4: que el cliente haya nombrado la pieza ENTERA, sin que falte
        # ninguna palabra que la distinga de una hermana.
        #
        # No basta con la palabra principal. Dos fugas reales que lo demostraron:
        #   - "piloto trasero IZQUIERDO" recibía el precio del piloto trasero DERECHO
        #   - "CENTRALITA motor" recibía el precio del MOTOR de arranque, porque la
        #     palabra "motor" aparece en los dos nombres
        # Si falta cualquier palabra del nombre de la ficha, no se da precio: se
        # confirma. Es el lado seguro del error, y el que pidió el negocio.
        palabras = set(normalizar(pregunta))

        # Excepción: si el cliente ha dado la referencia OEM o el número de stock,
        # la pieza está identificada mejor que por su nombre. Ahí no hace falta que
        # además la describa: un código exacto no se parece a nada, o coincide o no.
        codigos = {c for c in (meta.get("referencia_oem"), meta.get("id")) if c}
        if any(c and normalizar(c) and set(normalizar(c)).issubset(palabras)
               for c in codigos):
            return {"publicable": True, "importe": texto_precio, "estado": "publicable",
                    "motivo": f"identificada por referencia exacta y "
                              f"{disponibilidad.lower()}"}

        nombre_ficha = [p for p in normalizar(meta.get("pieza", ""))
                        if p not in PALABRAS_VACIAS and len(p) > 2]
        if not nombre_ficha or not set(nombre_ficha).issubset(palabras):
            faltan = [p for p in nombre_ficha if p not in palabras]
            return no(f"el cliente no ha nombrado la pieza completa (falta: "
                      f"{', '.join(faltan) or 'nada reconocible'}): se confirma antes "
                      f"de dar precio", "sin_confirmar")

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
