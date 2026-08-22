"""
06_panel.py
===========
CENTRO DE CONTROL de VendIQ. Levanta un panel web en local.

    python 06_panel.py          -> abre http://localhost:8420 en el navegador

Por qué un servidor y no un HTML suelto: el panel no enseña una foto de datos, sino
que **opera la herramienta de verdad**. Cuando escribes una consulta de cliente, se
ejecuta la búsqueda real contra el índice; cuando aceptas una oferta, se escribe en
salida/ofertas.json. Un HTML estático no puede hacer ninguna de las dos cosas, porque
el buscador necesita el modelo de embeddings cargado en memoria.

Solo usa la librería estándar de Python (http.server, json). No añade dependencias.
El modelo se carga UNA vez al arrancar y se queda caliente: por eso las consultas
del panel tardan milisegundos y no segundos.
"""

import importlib.util
import json
import mimetypes
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).parent
WEB = BASE / "panel"
PANEL_JSON = BASE / "salida" / "panel.json"
ACTIVIDAD_JSON = BASE / "salida" / "actividad.json"
PRECIOS_FIJADOS = BASE / "salida" / "precios_fijados.json"
PUERTO = 8420


def cargar(fichero, alias):
    """Importa un fichero cuyo nombre empieza por un número (no vale 'import').

    Se registra en sys.modules antes de ejecutarlo, que es el patrón correcto de
    importlib: sin eso, el módulo existe pero es invisible para todo lo que lo
    busque por su nombre, y las herramientas que resuelven la clase de un objeto
    a su módulo fallan con un KeyError que no dice nada.
    """
    import sys
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[alias] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class Sistema:
    """Mantiene cargados el buscador y el motor de ofertas."""

    def __init__(self):
        import csv
        self.buscar_mod = cargar("03_buscar.py", "buscar")
        self.ofertas_mod = cargar("04_ofertas.py", "ofertas")
        self.redactor = cargar("07_redactor.py", "redactor")
        self.conversar = cargar("08_conversar.py", "conversar")
        self.aprender = cargar("09_aprender.py", "aprender")
        self.config_llm = self.conversar.leer_env()

        print("Cargando el índice y el modelo (una sola vez)...")
        t0 = time.time()
        self.buscador = self.buscar_mod.cargar_buscador()
        with open(BASE / "datos" / "inventario_sintetico.csv",
                  encoding="utf-8-sig", newline="") as f:
            self.filas = list(csv.DictReader(f, delimiter=";"))
        self.inventario = self.ofertas_mod.Inventario(self.filas)
        if PRECIOS_FIJADOS.exists():
            # utf-8-sig y no utf-8: si el fichero se ha tocado desde PowerShell o
            # Excel puede llevar un BOM invisible delante, y json.loads revienta.
            texto = PRECIOS_FIJADOS.read_text(encoding="utf-8-sig").strip()
            self.buscador.precios_fijados = json.loads(texto) if texto else {}
        self.buscador.buscar("calentamiento")      # deja el modelo caliente
        print(f"Listo en {time.time() - t0:.1f}s · {len(self.buscador.items)} fichas indexadas")

        self.consultas_sesion = []                 # lo que se pregunta desde el panel
        self.chats = {}                            # conversaciones abiertas del simulador
        self.historiales = {}                      # turnos previos, para el LLM
        print("Redacta: " + ("Groq (" + (self.config_llm.get("GROQ_MODELO")
              or self.conversar.MODELO_POR_DEFECTO) + ")" if self.conversar.hay_llm()
              else "redactor determinista — sin GROQ_API_KEY en .env"))

    # ------------------------------------------------------------- precios
    def precios_pendientes(self):
        """Piezas sin precio, ordenadas por cuántas veces las han preguntado.

        La demanda sale del registro real de consultas: primero lo que más te preguntan,
        porque es donde poner un precio da más dinero por minuto de tu tiempo.
        """
        from collections import Counter
        demanda = Counter()
        if PANEL_JSON.exists():
            registro = json.loads(PANEL_JSON.read_text(encoding="utf-8"))
            for c in registro.get("consultas", []):
                for r in c.get("resultados", []):
                    if r.get("tipo") == "inventario":
                        demanda[str(r.get("id_pieza") or "")] += 1
                        break              # solo la ficha principal de cada consulta

        fijados = self.buscador.precios_fijados
        pendientes = []
        for f in self.filas:
            ya = fijados.get(f["id"])
            sin_precio = "onsultar" in f["precio"]
            if not sin_precio and not ya:
                continue
            pendientes.append({
                "id": f["id"],
                "descripcion": f"{f['pieza']} · {f['marca']} {f['modelo']} {f['motor']} {f['anio']}",
                "disponibilidad": f["disponibilidad"],
                "veces_preguntada": demanda.get(f["id"], 0),
                "precio_fijado": ya,
                "url": f["url"],
            })
        pendientes.sort(key=lambda p: (p["precio_fijado"] is not None,
                                       -p["veces_preguntada"]))
        return pendientes

    def fijar_precio(self, id_pieza, importe):
        """Guarda un precio puesto a mano. El buscador lo usa desde el instante siguiente."""
        id_pieza = str(id_pieza)
        if not any(f["id"] == id_pieza for f in self.filas):
            raise SystemExit(f"la pieza {id_pieza} no está en el inventario")
        importe = float(importe)
        if importe <= 0:
            raise SystemExit("el precio tiene que ser mayor que cero")
        texto = f"{importe:,.2f} € + IVA".replace(",", "X").replace(".", ",").replace("X", ".")
        self.buscador.precios_fijados[id_pieza] = texto
        PRECIOS_FIJADOS.parent.mkdir(parents=True, exist_ok=True)
        PRECIOS_FIJADOS.write_text(
            json.dumps(self.buscador.precios_fijados, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"id": id_pieza, "precio": texto}

    # ---------------------------------------------------------------- API
    def estado(self):
        snapshot = json.loads(PANEL_JSON.read_text(encoding="utf-8")) if PANEL_JSON.exists() else {}
        b = self.buscador
        snapshot["sistema"] = {
            "fichas_indexadas": len(b.items),
            "piezas_catalogo": len(self.filas),
            "dimensiones": int(b.embeddings.shape[1]),
            "umbral_pieza": self.buscar_mod.UMBRAL_PIEZA,
            "umbral_politica": self.buscar_mod.UMBRAL_POLITICA,
            "umbral_precio": self.buscar_mod.UMBRAL_PRECIO,
            "peso_lexico": self.buscar_mod.PESO_LEXICO,
            "peso_semantico": self.buscar_mod.PESO_SEMANTICO,
            "marcas": len(set(self.buscador.marcas_conocidas.values())),
            "tipos_pieza": len(self.buscador.tipos_conocidos),
        }
        snapshot["sesion"] = self.consultas_sesion[-40:]
        snapshot["ejemplos"] = self.ejemplos()
        return snapshot

    def ejemplos(self):
        """Consultas de ejemplo sacadas del catálogo real, no escritas a mano.

        Se eligen a propósito para que enseñen los cuatro comportamientos: encuentra
        y da precio, encuentra por referencia, no la tiene, y pregunta de condiciones.
        """
        import random
        rnd = random.Random(7)
        con_precio = [f for f in self.filas
                      if self.ofertas_mod.precio_publicado(f["precio"])]
        a, b = rnd.sample(con_precio, 2)

        # Para el ejemplo de "no la tengo" no vale cualquier combinación ausente:
        # si la marca tiene otra pieza que empieza por la misma palabra (piden puerta
        # trasera y hay puerta delantera), el buscador ofrece la hermana y el ejemplo
        # deja de enseñar lo que pretende. Se elige una cuya PALABRA PRINCIPAL no
        # exista para esa marca, que es una ausencia inequívoca.
        def cabeza_de(nombre):
            tokens = [t for t in self.buscar_mod.normalizar(nombre)
                      if t not in self.buscar_mod.PALABRAS_VACIAS and len(t) > 2]
            return tokens[0] if tokens else None

        cabezas_por_marca, modelos = {}, {}
        for f in self.filas:
            cabezas_por_marca.setdefault(f["marca"], set()).add(cabeza_de(f["pieza"]))
            modelos.setdefault(f["marca"], set()).add(f["modelo"])

        piezas = sorted({f["pieza"] for f in self.filas})
        marcas = sorted(cabezas_por_marca)
        ausente = None
        for _ in range(4000):
            p, m = rnd.choice(piezas), rnd.choice(marcas)
            if cabeza_de(p) not in cabezas_por_marca.get(m, set()):
                ausente = f"¿tenéis un {p.lower()} para un {m.title()} " \
                          f"{rnd.choice(sorted(modelos[m]))}?"
                break

        return [e for e in [
            f"¿cuánto vale el {a['pieza'].lower()} de un {a['marca'].title()} "
            f"{a['modelo']} {a['motor']}?",
            f"necesito la referencia {b['referencia_oem']}",
            ausente,
            f"busco algo para mi {a['marca'].title()} {a['modelo']}",
            "cuanto tarda en llegar el pedido",
        ] if e]

    def consultar(self, pregunta):
        """Ejecuta la búsqueda REAL y explica la decisión."""
        t0 = time.perf_counter()
        hits = self.buscador.buscar(pregunta, k=4)
        ms = (time.perf_counter() - t0) * 1000

        # Se piden también los candidatos SIN umbral, para poder enseñar qué se
        # descartó y por qué. Es la parte que hace entendible el guardarraíl.
        crudos = self.buscador.buscar(pregunta, k=4, aplicar_umbral=False)

        piezas = [(s, it) for s, it in hits if it["tipo"] == "inventario"]
        politicas = [(s, it) for s, it in hits if it["tipo"] == "politica"]

        # ¿El cliente está pidiendo una PIEZA o preguntando por las condiciones?
        # Se deduce del vocabulario que el buscador aprendió del propio catálogo.
        # Hace falta distinguirlo: si pide un turbo que no tenemos y le devolvemos la
        # política de "mándame la matrícula", el sistema ha hecho lo correcto, pero
        # decir que eso es "RESPONDE" sería mentir en el panel. No le hemos resuelto
        # nada: le hemos dicho que no lo tenemos.
        palabras = set(self.buscar_mod.normalizar(pregunta))
        pide_pieza = bool(palabras & self.buscador.tipos_conocidos
                          or palabras & set(self.buscador.marcas_conocidas))

        if piezas:
            decision = "RESPONDE"
            porque = "hay una ficha del catálogo que supera el umbral de confianza"
        elif pide_pieza:
            decision = "NO DISPONIBLE"
            mejor = crudos[0][0] if crudos else 0.0
            porque = (f"pide una pieza que no está en catálogo. El mejor candidato se "
                      f"queda en {mejor:.2f} y el mínimo para ofrecer una pieza es "
                      f"{self.buscar_mod.UMBRAL_PIEZA:.2f}: no se ofrece nada. "
                      f"Se le pide la matrícula y pasa a una persona")
        elif politicas:
            decision = "RESPONDE"
            porque = "no es una pieza: se responde con la política de la empresa"
        else:
            decision = "ESCALA"
            mejor = crudos[0][0] if crudos else 0.0
            porque = (f"nada supera el umbral (mejor candidato {mejor:.2f}) y no se "
                      f"reconoce ni pieza ni marca en el mensaje: lo ve una persona")

        def empaquetar(lista, aceptado):
            return [{
                "puntuacion": round(s, 3),
                "tipo": it["tipo"],
                "texto": it["texto"],
                "aceptado": aceptado,
                "url": (it.get("meta") or {}).get("url", ""),
                "precio": (it.get("meta") or {}).get("precio", ""),
                "id_pieza": (it.get("meta") or {}).get("id", ""),
                # La ficha entera viaja con el resultado porque el redactor escribe
                # SOLO con esto: si un dato no está aquí, no puede aparecer en el
                # mensaje al cliente. Es lo que hace demostrable el guardarraíl.
                "meta": it.get("meta") or {},
                # La decisión de precio va con cada ficha: es lo más delicado que
                # enseña el panel y nunca debe aparecer un importe sin su motivo.
                "precio_cliente": it.get("precio_cliente"),
            } for s, it in lista]

        aceptados_ids = {id(it) for _, it in hits}
        resultado = {
            "pregunta": pregunta,
            "decision": decision,
            "porque": porque,
            "ms": round(ms, 1),
            "resultados": empaquetar(hits, True),
            "descartados": [r for r in empaquetar(crudos, False)
                            if not any(a["texto"] == r["texto"] for a in empaquetar(hits, True))],
            "hora": time.strftime("%H:%M:%S"),
        }
        self.consultas_sesion.append({k: resultado[k] for k in
                                      ("pregunta", "decision", "ms", "hora", "porque")})
        return resultado

    # ----------------------------------------------------------- simulador
    def _vehiculo_en(self, texto):
        """Qué coche nombra el mensaje, según el vocabulario del propio catálogo.

        Igual que las marcas y los tipos de pieza, los modelos se aprenden de los
        datos: no hay ninguna lista escrita a mano que haya que mantener.
        """
        if not hasattr(self, "_vocab_vehiculo"):
            self._vocab_vehiculo = {}
            for f in self.filas:
                for campo in ("marca", "modelo"):
                    for token in self.buscar_mod.normalizar(f[campo]):
                        if len(token) > 1:
                            self._vocab_vehiculo[token] = f[campo]
        vistos = []
        for token in self.buscar_mod.normalizar(texto):
            canonico = self._vocab_vehiculo.get(token)
            if canonico and canonico not in vistos:
                vistos.append(canonico)
        return " ".join(vistos)

    @staticmethod
    def conversar_cifras(texto):
        """Los importes en euros que aparecen en un texto, normalizados.

        Se compara el NÚMERO, no la cadena: el modelo puede escribir "147,34 €",
        "147.34€" o "147,34 euros" y las tres son el mismo importe. Comparar
        cadenas dejaría pasar exactamente el caso que esto vigila.
        """
        import re
        # Dos formas, y solo dos, para no confundir un importe con una matrícula
        # (4521 KBD), un año (del 2018), un motor (1.6 TDI) ni un plazo (24-48 h):
        #   1) decimal español de dos cifras -> 147,34  ·  2.931,61
        #   2) cualquier número pegado a la moneda -> 150 €  ·  150 euros
        patron = re.compile(r"\d[\d.]*,\d{2}|\d[\d.,]*\s*(?:€|eur\b|euros\b)",
                            re.IGNORECASE)
        cifras = []
        for bruto in patron.findall(texto or ""):
            limpio = re.sub(r"[^\d.,]", "", bruto)
            if "," in limpio and "." in limpio:      # 2.931,61 -> 2931.61
                limpio = limpio.replace(".", "").replace(",", ".")
            elif "," in limpio:                       # 147,34   -> 147.34
                limpio = limpio.replace(",", ".")
            try:
                cifras.append(round(float(limpio), 2))
            except ValueError:
                continue
        return cifras

    def chatear(self, sesion, mensaje, perfil="nuevo", nombre="", reiniciar=False):
        """Un turno de conversación de WhatsApp: busca, redacta y recuerda.

        La conversación vive en el servidor y no en el navegador a propósito: la
        memoria (matrícula dada, pieza ofrecida, garantía ya mencionada) es parte
        del comportamiento del bot, no del pintado. Si viviera en el JS, refrescar
        la página cambiaría lo que responde.
        """
        conv = self.chats.get(sesion)
        if conv is None or reiniciar or conv.perfil != perfil:
            conv = self.redactor.Conversacion(perfil=perfil, nombre=nombre)
            self.chats[sesion] = conv
        conv.registrar(mensaje)

        # MEMORIA DEL COCHE. Un cliente no repite la marca en cada mensaje: dice
        # "para el Ford Fusion" una vez y luego "la puerta, la de siempre". Suelto,
        # ese segundo mensaje no encuentra nada (0.47 y por debajo del umbral);
        # con el coche que ya había dicho, encuentra la pieza correcta a 0.60.
        # Se busca con el contexto añadido, pero se GUARDA el mensaje original: lo
        # que el cliente escribió no se toca.
        # El contexto añade el COCHE, así que solo sirve si el cliente ya ha dicho
        # la PIEZA. Añadirlo siempre fue un error que se vio enseguida: a "¿y de
        # garantía qué me das?" le pegaba "FORD Fusion" detrás y el buscador
        # contestaba con un parachoques de Ford Fusion, que no venía a cuento.
        palabras = set(self.buscar_mod.normalizar(mensaje))
        habla_de_pieza = bool(palabras & self.buscador.tipos_conocidos)
        vehiculo = self._vehiculo_en(mensaje)

        # La conversación tiene DOS mitades y el cliente solo repite una cada vez:
        #   "parachoques trasero para un Clase E Coupé"  ->  "¿y para un Clase A?"
        #   "algo para el Ford Fusion"                   ->  "la puerta, la de siempre"
        # En el primero cambia el coche y mantiene la pieza; en el segundo al revés.
        # Se recuerdan las dos y se completa la que falte. Sin esto, el segundo
        # mensaje se busca a ciegas y devuelve cualquier cosa de ese coche.
        if habla_de_pieza:
            conv.pieza_pedida = mensaje
        if vehiculo:
            conv.vehiculo = vehiculo

        contexto = None
        texto_busqueda = mensaje
        if habla_de_pieza and not vehiculo and conv.vehiculo:
            contexto = conv.vehiculo
            texto_busqueda = f"{mensaje} {conv.vehiculo}"
        elif vehiculo and not habla_de_pieza and getattr(conv, "pieza_pedida", None):
            # Solo la PIEZA del mensaje anterior, no el mensaje entero: arrastrar
            # el coche viejo junto al nuevo confundiría los dos.
            pieza = " ".join(p for p in self.buscar_mod.normalizar(conv.pieza_pedida)
                             if p in self.buscador.tipos_conocidos
                             or p in self.buscar_mod.LADOS)
            if pieza:
                contexto = pieza
                texto_busqueda = f"{mensaje} {pieza}"

        busqueda = self.consultar(texto_busqueda)
        busqueda["pregunta"] = mensaje
        busqueda["contexto"] = contexto
        respuesta = self.redactor.redactar(busqueda, conv)

        # ------------------------------------------------- las tres acciones
        # RESPONDER / PREGUNTAR / ESCALAR. La elige el código a partir de lo que
        # ya han decidido la búsqueda y el redactor; el LLM no la elige.
        # Para los botones se busca MÁS ANCHO que para responder. Con k=4 salen
        # cuatro faros del mismo lado y años distintos, y el bot pregunta por el
        # año cuando lo que falta es el lado. Con k=10 aparecen las hermanas de
        # verdad y la pregunta es la que desbloquea la venta.
        candidatas = {"resultados": [
            {"tipo": it["tipo"], "meta": it.get("meta") or {},
             "precio_cliente": it.get("precio_cliente")}
            for _, it in self.buscador.buscar(texto_busqueda, k=10)]}
        opciones = self.conversar.opciones_desambiguacion(candidatas)
        accion, porque_accion = self.conversar.elegir_accion(
            busqueda, respuesta, opciones, conv.aclaraciones)
        if accion == "PREGUNTAR":
            conv.aclaraciones += 1
        respuesta["accion"] = accion
        respuesta["porque_accion"] = porque_accion
        respuesta["opciones"] = opciones if accion == "PREGUNTAR" else None

        historial = self.historiales.setdefault(sesion, [])

        # El LLM reescribe el mismo contenido con mejor forma. Si no hay clave o
        # falla, se queda el borrador determinista y la conversación sigue.
        # Lo que se sabe de la conversacion viaja con la peticion: si el historial
        # se ha hecho largo, esto es lo que sobrevive al recorte, resumido.
        memoria_llm = {"nombre": conv.nombre, "matricula": conv.matricula,
                       "vehiculo": conv.vehiculo, "precio": conv.ultimo_precio,
                       "garantia_dicha": conv.garantia_dicha,
                       "escalado": conv.escalado,
                       "pieza": (conv.ultima_pieza or {}).get("pieza")}
        # Salvo cuando la respuesta la escribió una persona. 07_redactor.py ya
        # dice que esas se sueltan tal cual, sin reformular, y el LLM se ponía
        # después y las reescribía igual. Medido en la primera tanda real:
        #
        #   escrito por Álvaro: «Si , la reserva se queda hecha 24 horas»
        #   dicho al cliente  : «Sí, te lo apartamos 24 horas, ¿te confirmo la
        #                        reserva ahora?»
        #
        # Suena mejor y por eso es peor: «te confirmo la reserva ahora» es un
        # compromiso que Álvaro no escribió. En la otra FAQ, «nuestro horario está
        # en internet» se convirtió en «¿te paso el enlace?», un enlace que no
        # existe. Cuando la respuesta son las palabras de una persona no hay nada
        # que mejorar de forma: ésas ya son las palabras.
        de_una_persona = any(r["regla"] == "respuesta escrita por una persona"
                             for r in respuesta["reglas"])
        if de_una_persona:
            lineas_llm, nota = None, ("lo escribió una persona: se dice literal, "
                                      "sin pasar por el modelo")
        else:
            lineas_llm, nota = self.conversar.redactar_con_llm(
                busqueda, respuesta, accion, respuesta["opciones"], historial,
                self.config_llm, memoria_llm)
        respuesta["redactor"] = nota
        if lineas_llm:
            respuesta["borrador"] = respuesta["lineas"]
            respuesta["lineas"] = lineas_llm
            respuesta["mensaje"] = "\n".join(lineas_llm)

        historial.append({"cliente": mensaje, "bot": respuesta["mensaje"]})
        del historial[:-12]        # el historial largo se corta, no crece sin fin

        # Lo que no supo contestar se guarda para que lo conteste una persona.
        reglas = " · ".join(r["regla"] for r in respuesta["reglas"])
        if "no se reconoce la consulta" in reglas or "no tiene una respuesta" in reglas:
            self.aprender.anotar(mensaje, porque_accion, sesion, busqueda["decision"])

        # Comprobación en caliente del guardarraíl: el redactor solo puede publicar
        # un importe que el buscador haya marcado publicable. Si alguna vez no
        # cuadrara, el panel lo enseña en rojo en lugar de disimularlo.
        autorizados = {(r.get("precio_cliente") or {}).get("importe")
                       for r in busqueda["resultados"]
                       if (r.get("precio_cliente") or {}).get("publicable")}
        # Los ya autorizados en turnos anteriores siguen valiendo: repetir el mismo
        # importe de la misma pieza cuando el cliente vuelve a preguntar no es
        # publicar un precio nuevo, y prohibirlo obligaría al bot a hacerse el sordo.
        if not hasattr(conv, "precios_autorizados"):
            conv.precios_autorizados = set()
        conv.precios_autorizados |= {p for p in autorizados if p}
        respuesta["precio_autorizado"] = (
            respuesta["precio_dado"] is None
            or respuesta["precio_dado"] in autorizados
            or respuesta["precio_dado"] in conv.precios_autorizados)

        # AUDITORÍA DEL TEXTO FINAL. Lo anterior comprueba lo que el redactor
        # determinista DECIDIÓ decir. Cuando redacta el LLM hay que comprobar lo
        # que de verdad SALE, porque un modelo puede escribir una cifra que nadie
        # le ha dado. Se leen todos los importes del mensaje y se contrastan con
        # los autorizados; si aparece uno que no lo está, se descarta la redacción
        # del modelo entera y sale el borrador, que sí es demostrable.
        # AUDITORÍA DE LA VOZ Y DE LAS REGLAS. Lo mismo que con el precio, pero
        # con lo demás: el redactor determinista las cumple por construcción y el
        # modelo no. Si escribe de usted, mete un emoji, se pasa de tres líneas o
        # —lo más grave— dice que no tenemos la pieza sin haber pedido la
        # matrícula, se tira su redacción y sale el borrador, que sí las cumple.
        #
        # Las dos las rompió el modelo la primera vez que se encendió, y el banco
        # las veía DESPUÉS, cuando al cliente ya le ha llegado el mensaje.
        if lineas_llm:
            roto = (self.redactor.rompe_el_estilo(respuesta["lineas"])
                    or self.redactor.rompe_la_matricula(
                        respuesta["lineas"], busqueda["decision"],
                        bool(conv.matricula), bool(respuesta.get("escala"))))
            if roto:
                respuesta["lineas"] = respuesta["borrador"]
                respuesta["mensaje"] = "\n".join(respuesta["borrador"])
                respuesta["redactor"] = (f"descartada la redacción del modelo: "
                                         f"{roto}")
                respuesta["llm_descartado"] = True

        cifras = self.conversar_cifras(respuesta["mensaje"])
        permitidas = {self.conversar_cifras(p) and self.conversar_cifras(p)[0]
                      for p in (autorizados | conv.precios_autorizados) if p}
        intrusas = [c for c in cifras if c not in permitidas]
        if intrusas and respuesta.get("borrador"):
            respuesta["lineas"] = respuesta["borrador"]
            respuesta["mensaje"] = "\n".join(respuesta["borrador"])
            respuesta["redactor"] = (f"descartada la redacción del modelo: escribió "
                                     f"{intrusas[0]} € y ese importe no está "
                                     f"autorizado")
            respuesta["llm_descartado"] = True
        elif intrusas:
            respuesta["precio_autorizado"] = False

        # Si se ha localizado una pieza, su coche es mejor contexto que lo que el
        # cliente escribió: viene con modelo y motor exactos.
        pieza = conv.ultima_pieza or {}
        if pieza.get("marca"):
            conv.vehiculo = f"{pieza['marca']} {pieza.get('modelo', '')}".strip()

        return {"bot": respuesta, "busqueda": busqueda,
                "memoria": {"turnos": conv.turnos, "matricula": conv.matricula,
                            "perfil": conv.perfil, "nombre": conv.nombre,
                            "vehiculo": conv.vehiculo, "escalado": conv.escalado,
                            "pieza": pieza.get("pieza"),
                            "precio": conv.ultimo_precio,
                            "garantia_dicha": conv.garantia_dicha}}

    def guiones(self):
        """Conversaciones tipo, construidas con piezas REALES del catálogo.

        No están escritas a mano: si el catálogo cambia, los guiones cambian con él
        y siguen funcionando. Cada uno enseña un comportamiento distinto del tono.
        """
        import random
        rnd = random.Random(11)
        con_precio = [f for f in self.filas
                      if self.ofertas_mod.precio_publicado(f["precio"])
                      and f["disponibilidad"].lower() == "en stock"]
        a, b = rnd.sample(con_precio, 2)

        def pedir(f):
            return (f"{f['pieza'].lower()} para un {f['marca'].title()} "
                    f"{f['modelo']} {f['motor']}")

        # Para el guion de "no la tengo" no vale cualquier combinación que falte:
        # tiene que ser una ausencia INEQUÍVOCA. Si el nombre de la pieza comparte
        # una sola palabra con algo que sí tenemos de esa marca (pedir "cerradura
        # puerta delantera" cuando hay "puerta delantera izquierda"), el buscador
        # ofrece la hermana y el guion enseña lo contrario de lo que pretende.
        # Por eso se exige que NINGUNA palabra del nombre exista para esa marca.
        def tokens_de(nombre):
            return {x for x in self.buscar_mod.normalizar(nombre)
                    if x not in self.buscar_mod.PALABRAS_VACIAS and len(x) > 2}

        def cabeza(nombre):
            t = sorted(tokens_de(nombre), key=lambda x: self.buscar_mod
                       .normalizar(nombre).index(x))
            return t[0] if t else None

        vocabulario, modelos = {}, {}
        for f in self.filas:
            vocabulario.setdefault(f["marca"], set()).update(tokens_de(f["pieza"]))
            modelos.setdefault(f["marca"], set()).add(f["modelo"])
        piezas, marcas = sorted({f["pieza"] for f in self.filas}), sorted(vocabulario)
        ausente = "un turbo para un Ferrari F430"
        for _ in range(4000):
            p, m = rnd.choice(piezas), rnd.choice(marcas)
            if not (tokens_de(p) & vocabulario.get(m, set())):
                ausente = (f"un {p.lower()} para un {m.title()} "
                           f"{rnd.choice(sorted(modelos[m]))}")
                break

        return [
            {"nombre": "Compra directa", "perfil": "nuevo", "cliente": "",
             "que_prueba": "Encuentra la pieza, da el precio publicado y cierra.",
             "mensajes": ["buenas, ¿tenéis " + pedir(a) + "?",
                          "vale, ¿y me llega esta semana?",
                          "perfecto, me lo quedo"]},
            {"nombre": "Cliente que regatea", "perfil": "conocido",
             "cliente": "Juan Carlos",
             "que_prueba": "No baja el precio: cede el transporte y avisa a Álvaro.",
             "mensajes": ["buenas! necesito " + pedir(b),
                          "uf, está caro. ¿me lo dejas en algo menos?",
                          "vale, déjame que lo mire"]},
            {"nombre": "No la tenemos", "perfil": "nuevo", "cliente": "",
             "que_prueba": "Dice que no en vez de ofrecer una pieza parecida, y "
                           "pide la matrícula una sola vez.",
             "mensajes": ["hola, busco " + ausente,
                          "mi matricula es 4521 KBD",
                          "y cuanto tarda en llegar"]},
            {"nombre": "Datos a medias", "perfil": "conocido", "cliente": "Roberto",
             "que_prueba": "Con la pieza sin nombrar entera NO da precio: confirma.",
             "mensajes": [f"oye necesito algo para el {a['marca'].title()} "
                          f"{a['modelo']}",
                          f"la {cabeza(a['pieza'])}, la de siempre",
                          "y de garantía qué me das"]},
            {"nombre": "Va mal la pieza", "perfil": "conocido", "cliente": "Roberto",
             "que_prueba": "Una queja no la contesta el bot: la escala entera.",
             "mensajes": ["el alternador que me mandasteis no funciona",
                          "pues vaya faena, lo tengo el coche parado"]},
        ]

    def ofertar(self, id_pieza, importe, cliente):
        oferta = self.ofertas_mod.registrar(self.inventario, id_pieza, importe, cliente)
        return oferta

    def resolver(self, n, decision, motivo):
        return self.ofertas_mod.resolver(int(n), decision, motivo)

    def ofertas(self):
        return self.ofertas_mod.leer_registro()

    def piezas_ejemplo(self, n=12):
        """Piezas con precio publicado, para poder probar ofertas desde el panel."""
        salida = []
        for f in self.filas:
            precio = self.ofertas_mod.precio_publicado(f["precio"])
            if precio:
                tramo, pct = self.inventario.tramo_de(f["id"])
                salida.append({
                    "id": f["id"],
                    "descripcion": f"{f['pieza']} · {f['marca']} {f['modelo']}",
                    "precio": precio,
                    "antiguedad": tramo["nombre"],
                    "percentil": round(pct, 3),
                    "descuento_max": tramo["descuento_max"],
                })
            if len(salida) >= n:
                break
        return salida


SISTEMA = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass                                        # sin ruido en la consola

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = urlparse(self.path).path
        if ruta == "/api/estado":
            return self._json(SISTEMA.estado())
        if ruta == "/api/ofertas":
            return self._json({"ofertas": SISTEMA.ofertas(),
                               "piezas": SISTEMA.piezas_ejemplo()})
        if ruta == "/api/precios":
            return self._json({"pendientes": SISTEMA.precios_pendientes()})
        if ruta == "/api/guiones":
            return self._json({"guiones": SISTEMA.guiones()})
        if ruta == "/api/actividad":
            # Se sirve tal cual lo escribió 10_simular.py, sin recalcular nada.
            # Si el panel tocara estos números dejarían de ser lo que se midió.
            if not ACTIVIDAD_JSON.exists():
                return self._json({"error": "ejecuta antes: python 10_simular.py"}, 404)
            return self._json(json.loads(
                ACTIVIDAD_JSON.read_text(encoding="utf-8-sig")))
        if ruta == "/api/no-resueltas":
            return self._json({"pendientes": SISTEMA.aprender.leer_registro(),
                               "redactor": SISTEMA.conversar.hay_llm()})

        fichero = "index.html" if ruta == "/" else ruta.lstrip("/")
        destino = (WEB / fichero).resolve()
        if not str(destino).startswith(str(WEB.resolve())) or not destino.is_file():
            self.send_error(404)
            return
        tipo = mimetypes.guess_type(destino.name)[0] or "application/octet-stream"
        datos = destino.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{tipo}; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        # Sin esto el navegador cachea el CSS y se queda con la version vieja:
        # tocas la hoja de estilos, recargas y no ves nada. Es un panel local de
        # desarrollo, asi que no cachear no cuesta nada y ahorra confusion.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        ruta = urlparse(self.path).path
        largo = int(self.headers.get("Content-Length", 0))
        try:
            # utf-8 explícito: si el cliente manda otra codificación es un error
            # suyo y toca un 400, no una excepción que ensucie la consola.
            cuerpo = json.loads((self.rfile.read(largo) or b"{}").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._json({"error": f"cuerpo no válido ({e})"}, 400)

        try:
            if ruta == "/api/consultar":
                pregunta = (cuerpo.get("pregunta") or "").strip()
                if not pregunta:
                    return self._json({"error": "escribe una consulta"}, 400)
                return self._json(SISTEMA.consultar(pregunta))

            if ruta == "/api/chat":
                mensaje = (cuerpo.get("mensaje") or "").strip()
                if not mensaje:
                    return self._json({"error": "escribe un mensaje"}, 400)
                return self._json(SISTEMA.chatear(
                    cuerpo.get("sesion") or "demo", mensaje,
                    perfil=cuerpo.get("perfil") or "nuevo",
                    nombre=cuerpo.get("nombre") or "",
                    reiniciar=bool(cuerpo.get("reiniciar"))))

            if ruta == "/api/aprender":
                # La respuesta la escribe una PERSONA. No hay ninguna ruta en el
                # panel que genere el texto sola, y es la regla del proyecto.
                texto = (cuerpo.get("respuesta") or "").strip()
                if not texto:
                    return self._json({"error": "escribe la respuesta"}, 400)
                return self._json(SISTEMA.aprender.aprender(
                    cuerpo["n"], texto, cuerpo.get("quien") or "Álvaro",
                    buscador=SISTEMA.buscador))

            if ruta == "/api/oferta":
                return self._json(SISTEMA.ofertar(cuerpo["id_pieza"],
                                                  float(cuerpo["importe"]),
                                                  cuerpo.get("cliente") or "anónimo"))

            if ruta == "/api/resolver":
                return self._json(SISTEMA.resolver(cuerpo["n"], cuerpo["decision"],
                                                   cuerpo.get("motivo")))

            if ruta == "/api/precio":
                return self._json(SISTEMA.fijar_precio(cuerpo["id_pieza"],
                                                       cuerpo["importe"]))
        except SystemExit as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:                       # nunca tumbar el panel
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        self.send_error(404)


def main():
    global SISTEMA
    if not (WEB / "index.html").exists():
        raise SystemExit(f"ERROR: falta {WEB / 'index.html'}")
    if not PANEL_JSON.exists():
        raise SystemExit("ERROR: falta salida/panel.json.\n"
                         "       Ejecuta antes:  python 05_panel_datos.py")

    SISTEMA = Sistema()
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    url = f"http://localhost:{PUERTO}"
    print(f"\n  VendIQ · Centro de control  ->  {url}")
    print("  (Ctrl+C para parar)\n")
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel detenido.")


if __name__ == "__main__":
    main()
