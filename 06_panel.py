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
PUERTO = 8420


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class Sistema:
    """Mantiene cargados el buscador y el motor de ofertas."""

    def __init__(self):
        import csv
        self.buscar_mod = cargar("03_buscar.py", "buscar")
        self.ofertas_mod = cargar("04_ofertas.py", "ofertas")

        print("Cargando el índice y el modelo (una sola vez)...")
        t0 = time.time()
        self.buscador = self.buscar_mod.cargar_buscador()
        with open(BASE / "datos" / "inventario_sintetico.csv",
                  encoding="utf-8-sig", newline="") as f:
            self.filas = list(csv.DictReader(f, delimiter=";"))
        self.inventario = self.ofertas_mod.Inventario(self.filas)
        self.buscador.buscar("calentamiento")      # deja el modelo caliente
        print(f"Listo en {time.time() - t0:.1f}s · {len(self.buscador.items)} fichas indexadas")

        self.consultas_sesion = []                 # lo que se pregunta desde el panel

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
            "peso_lexico": self.buscar_mod.PESO_LEXICO,
            "peso_semantico": self.buscar_mod.PESO_SEMANTICO,
            "marcas": len(set(self.buscador.marcas_conocidas.values())),
            "tipos_pieza": len(self.buscador.tipos_conocidos),
        }
        snapshot["sesion"] = self.consultas_sesion[-40:]
        return snapshot

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
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self):
        ruta = urlparse(self.path).path
        largo = int(self.headers.get("Content-Length", 0))
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "JSON no válido"}, 400)

        try:
            if ruta == "/api/consultar":
                pregunta = (cuerpo.get("pregunta") or "").strip()
                if not pregunta:
                    return self._json({"error": "escribe una consulta"}, 400)
                return self._json(SISTEMA.consultar(pregunta))

            if ruta == "/api/oferta":
                return self._json(SISTEMA.ofertar(cuerpo["id_pieza"],
                                                  float(cuerpo["importe"]),
                                                  cuerpo.get("cliente") or "anónimo"))

            if ruta == "/api/resolver":
                return self._json(SISTEMA.resolver(cuerpo["n"], cuerpo["decision"],
                                                   cuerpo.get("motivo")))
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
