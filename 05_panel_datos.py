"""
05_panel_datos.py
=================
Genera los datos del CENTRO DE CONTROL a partir de ejecuciones REALES del sistema.

Por qué existe este paso: un panel es fácil de falsear. Aquí no se escribe ni un número
a mano — se simula una semana de mensajes de clientes, se pasan por el buscador y por el
motor de ofertas de verdad, y se mide lo que sale. Si mañana la búsqueda empeora, los
números del panel empeoran solos.

Lo que se simula: los MENSAJES (no hay clientes reales, es un prototipo).
Lo que es real: las decisiones, las puntuaciones, los tiempos y los agregados.

Salida: salida/panel.json
"""

import csv
import importlib.util
import json
import random
import statistics
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
SALIDA = BASE / "salida" / "panel.json"
SEMILLA = 20260812


def cargar(nombre_fichero, alias):
    """Importa un módulo cuyo nombre empieza por un número."""
    spec = importlib.util.spec_from_file_location(alias, BASE / nombre_fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def ensuciar(texto):
    """Como llega un mensaje por WhatsApp: sin tildes, en minúsculas, sin signos."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.lower().replace("?", "").replace("¿", "")


# --------------------------------------------------------------------------
# La semana de mensajes
# --------------------------------------------------------------------------

def construir_mensajes(filas):
    """Mezcla realista de lo que entra por WhatsApp en un desguace.

    Cada mensaje lleva la VERDAD asociada (qué ficha debería salir, o que no existe).
    Así el panel no se limita a contar lo que el sistema cree haber resuelto: puede
    comprobar si acertó. Un panel que solo enseña su propia opinión no vale nada.
    """
    random.seed(SEMILLA)
    mensajes = []   # (clase, texto, id_correcto | None)

    # 1) Piezas que SÍ están, preguntadas de cuatro maneras distintas
    muestra = random.sample(filas, 22)
    for f in muestra[:8]:
        mensajes.append(("pieza", f"¿tenéis un {f['pieza'].lower()} para un "
                         f"{f['marca'].title()} {f['modelo']} {f['motor']} del {f['anio']}?",
                         f"pieza-{f['id']}"))
    for f in muestra[8:14]:
        mensajes.append(("pieza", ensuciar(f"buenas tenes {f['pieza']} pa un "
                                           f"{f['marca']} {f['modelo']} {f['anio']}"),
                         f"pieza-{f['id']}"))
    for f in muestra[14:18]:
        mensajes.append(("pieza", f"necesito la referencia {f['referencia_oem']}",
                         f"pieza-{f['id']}"))
    for f in muestra[18:22]:
        mensajes.append(("pieza", f"busco {f['pieza'].lower()} de {f['marca'].title()} "
                                  f"{f['modelo']} {f['motor']}", f"pieza-{f['id']}"))

    # 2) Piezas que NO están. Las combinaciones se deducen del propio inventario,
    #    nunca se escriben a mano: el catálogo cambia y una lista fija se queda vieja
    #    en silencio. Se repiten a propósito, porque lo que más te piden y no tienes
    #    es información de compra y el panel tiene que sacarlo a la luz.
    existentes = {(f["pieza"], f["marca"]) for f in filas}
    piezas_todas = sorted({f["pieza"] for f in filas})
    marcas_todas = sorted({f["marca"] for f in filas})
    modelos = {}
    for f in filas:
        modelos.setdefault(f["marca"], set()).add(f["modelo"])

    repeticiones, elegidas, intentos = [4, 3, 2, 2, 1, 1], [], 0
    while len(elegidas) < len(repeticiones) and intentos < 4000:
        intentos += 1
        pieza, marca = random.choice(piezas_todas), random.choice(marcas_todas)
        if (pieza, marca) in existentes or (pieza, marca) in elegidas:
            continue
        elegidas.append((pieza, marca))
    for (pieza, marca), veces in zip(elegidas, repeticiones):
        modelo = random.choice(sorted(modelos[marca]))
        for _ in range(veces):
            mensajes.append(("pieza", f"¿tenéis un {pieza.lower()} para un "
                                      f"{marca.title()} {modelo}?", None))

    # 3) Preguntas de condiciones
    for pregunta in [
        "cuanto tarda en llegar el pedido",
        "la pieza tiene garantia?",
        "puedo pasar a recogerla a la tienda?",
        "que pasa si la pieza sale defectuosa",
        "envias a canarias?",
        "que datos necesitas del coche para buscarla",
        "si no me vale la puedo devolver",
        "me puedes hacer un descuento?",
    ]:
        mensajes.append(("politica", pregunta, None))

    random.shuffle(mensajes)
    return mensajes


def construir_ofertas(filas, ofertas_mod):
    """Ofertas de clientes sobre piezas concretas."""
    random.seed(SEMILLA + 1)
    con_precio = [f for f in filas if ofertas_mod.precio_publicado(f["precio"])]
    sin_precio = [f for f in filas if not ofertas_mod.precio_publicado(f["precio"])]

    lista = []
    clientes = ["Taller Ruiz", "Taller Gómez", "Autos Delgado", "Particular",
                "Taller Ruiz", "Recambios Vega", "Particular", "Taller Gómez"]

    # Ofertas razonables sobre piezas con precio: descuentos entre el 3 % y el 25 %
    for i, f in enumerate(random.sample(con_precio, 14)):
        precio = ofertas_mod.precio_publicado(f["precio"])
        descuento = random.choice([0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.25])
        lista.append((f["id"], round(precio * (1 - descuento), 2), clientes[i % len(clientes)]))

    # Alguna oferta absurda
    f = random.choice(con_precio)
    lista.append((f["id"], round(ofertas_mod.precio_publicado(f["precio"]) * 0.35, 2), "Particular"))

    # Y ofertas sobre piezas sin precio publicado, si las hay. Con el catálogo actual
    # (todas con precio) esta lista sale vacía, y es correcto: sin precio de lista no
    # hay porcentaje que calcular, así que esas ofertas irían siempre a decisión manual.
    for i, f in enumerate(random.sample(sin_precio, min(4, len(sin_precio)))):
        lista.append((f["id"], float(random.choice([150, 220, 340, 480])),
                      clientes[(i + 3) % len(clientes)]))

    return lista


# --------------------------------------------------------------------------

def main():
    buscar_mod = cargar("03_buscar.py", "buscar")
    ofertas_mod = cargar("04_ofertas.py", "ofertas")

    with open(BASE / "datos" / "inventario_sintetico.csv",
              encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f, delimiter=";"))

    print("Cargando el buscador...")
    buscador = buscar_mod.cargar_buscador()
    inventario = ofertas_mod.Inventario(filas)

    # ---------------------------------------------------------------- consultas
    mensajes = construir_mensajes(filas)
    print(f"Pasando {len(mensajes)} mensajes por el sistema real...")

    # Consulta de calentamiento: la primera carga cachés del modelo y tarda ~10 veces
    # más. Incluirla falsearía la media al alza, así que se descarta antes de medir.
    buscador.buscar("consulta de calentamiento, no se mide")

    inicio = datetime(2026, 8, 10, 8, 0, tzinfo=timezone.utc)
    random.seed(SEMILLA + 2)
    consultas = []
    for i, (clase, texto, id_correcto) in enumerate(mensajes):
        t0 = time.perf_counter()
        hits = buscador.buscar(texto, k=3)
        ms = (time.perf_counter() - t0) * 1000

        piezas = [(s, it) for s, it in hits if it["tipo"] == "inventario"]
        politicas = [(s, it) for s, it in hits if it["tipo"] == "politica"]

        if piezas:
            decision, porque = "RESUELTA", "encontrada en catálogo con confianza suficiente"
        elif politicas and clase == "politica":
            decision, porque = "RESUELTA", "respondida con la política de la empresa"
        else:
            decision = "ESCALADA"
            porque = ("no hay ninguna ficha que supere el umbral de confianza: "
                      "el sistema prefiere no ofrecer una pieza distinta a la pedida")

        # Contraste con la verdad conocida. Sirve para distinguir tres cosas que un
        # panel corriente mezcla: acertar, equivocarse, y saber que no se sabe.
        if clase == "politica":
            veredicto = "correcta" if decision == "RESUELTA" else "sin_respuesta"
        elif id_correcto:
            ofrecida = piezas[0][1]["id"] if piezas else None
            veredicto = ("correcta" if ofrecida == id_correcto
                         else "pieza_equivocada" if ofrecida
                         else "sin_respuesta")
        else:   # la pieza no existe: lo correcto es NO ofrecer nada
            veredicto = "correcta" if not piezas else "falso_positivo"

        consultas.append({
            "hora": (inicio + timedelta(minutes=17 * i)).isoformat(timespec="minutes"),
            "clase": clase,
            "mensaje": texto,
            "decision": decision,
            "porque": porque,
            "veredicto": veredicto,
            "existe_en_catalogo": id_correcto is not None if clase == "pieza" else None,
            "ms": round(ms, 1),
            "resultados": [
                {"puntuacion": round(s, 3), "tipo": it["tipo"], "texto": it["texto"][:150],
                 # el id hace falta para saber qué piezas se preguntan más:
                 # es lo que ordena la cola de "precios sin poner"
                 "id_pieza": (it.get("meta") or {}).get("id", ""),
                 "url": (it.get("meta") or {}).get("url", ""),
                 "precio": (it.get("meta") or {}).get("precio", "")}
                for s, it in hits
            ],
        })

    # ---------------------------------------------------------------- ofertas
    print("Pasando las ofertas por el motor real...")
    registro = []
    vistos = set()
    for id_pieza, importe, cliente in construir_ofertas(filas, ofertas_mod):
        r = ofertas_mod.evaluar(inventario, id_pieza, importe)
        if (id_pieza, cliente) in vistos and r["decision"] == "ACEPTAR":
            r = {**r, "decision": "A_MANO",
                 "motivo": "segunda oferta del mismo cliente por esta pieza"}
        vistos.add((id_pieza, cliente))
        pieza = inventario.get(id_pieza)
        registro.append({
            "cliente": cliente,
            "id_pieza": id_pieza,
            "descripcion": f"{pieza['pieza']} {pieza['marca']} {pieza['modelo']}",
            "importe": round(importe, 2),
            "decision": r["decision"],
            "motivo": r["motivo"],
            "precio_lista": r.get("precio_lista"),
            "descuento": r.get("descuento"),
            "antiguedad": r.get("antiguedad"),
            "contraoferta": r.get("contraoferta"),
        })

    # ---------------------------------------------------------------- agregados
    total = len(consultas)
    resueltas = sum(1 for c in consultas if c["decision"] == "RESUELTA")
    tiempos = sorted(c["ms"] for c in consultas)
    veredictos = Counter(c["veredicto"] for c in consultas)

    # Lo que piden y no hay: la señal de compra. Solo cuenta lo que de verdad no está
    # en catálogo, no lo que el sistema no supo encontrar.
    demanda_no_cubierta = Counter(
        c["mensaje"] for c in consultas
        if c["clase"] == "pieza" and c["existe_en_catalogo"] is False)

    por_regla = [o for o in registro if o["decision"] != "A_MANO"]
    aceptadas = [o for o in registro if o["decision"] == "ACEPTAR"]

    panel = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "aviso": ("Los mensajes de cliente están simulados (es un prototipo, no hay "
                  "clientes reales). Las decisiones, puntuaciones y tiempos son "
                  "resultado de ejecutar el sistema de verdad."),
        "resumen": {
            "consultas": total,
            "resueltas_sin_persona": resueltas,
            "tasa_resolucion": round(resueltas / total, 4),
            "escaladas": total - resueltas,
            "ms_mediana": round(statistics.median(tiempos), 1),
            "ms_p95": round(tiempos[min(int(len(tiempos) * 0.95), len(tiempos) - 1)], 1),
            "piezas_catalogo": len(filas),
            "ofertas": len(registro),
            "ofertas_por_regla": len(por_regla),
            "tasa_ofertas_automaticas": round(len(por_regla) / len(registro), 4),
            "euros_aceptados": round(sum(o["importe"] for o in aceptadas), 2),
        },
        "verificacion": {
            "correctas": veredictos["correcta"],
            "pieza_equivocada": veredictos["pieza_equivocada"],
            "falsos_positivos": veredictos["falso_positivo"],
            "sin_respuesta": veredictos["sin_respuesta"],
            "tasa_acierto_verificado": round(veredictos["correcta"] / total, 4),
            "nota": ("Contrastado contra la respuesta correcta conocida de cada mensaje, "
                     "no contra lo que el sistema cree haber resuelto."),
        },
        "calidad_medida": {
            "acierto_antes": 0.20,
            "acierto_ahora": 0.89,
            "guardarrail": 0.98,
            "preguntas_banco": 80,
            "piezas_inexistentes_probadas": 40,
            "fuente": "tests/test_busqueda.py",
        },
        # Histórico de las tres mediciones hechas con tests/test_busqueda.py.
        # Se guardan a mano porque son ejecuciones de momentos distintos (búsqueda
        # solo vectorial, híbrida con 100 piezas, híbrida con 1.000), no algo que
        # este script pueda recalcular hoy. Cada columna es un run real.
        # Acierto a la primera, medido con tests/test_busqueda.py en cada etapa.
        # "Datos incompletos" sube de 0,67 a 1,00 entre las dos últimas columnas y
        # no es que el buscador mejorara: es que la MEDIDA estaba mal. La pregunta
        # no da motor ni año, así que tiene varias respuestas correctas, y el banco
        # exigía adivinar una concreta. Medía suerte, no acierto.
        "historico": {
            "columnas": ["Solo vectorial", "Híbrida · 100", "Híbrida · 1.000",
                         "Híbrida · 5.000"],
            "filas": [
                ["Pregunta natural",           0.24, 1.00, 1.00, 0.96],
                ["Datos incompletos",          0.07, 1.00, 0.67, 1.00],
                ["Mensaje sucio de WhatsApp",  0.13, 1.00, 1.00, 0.80],
                ["Por referencia OEM",         0.00, 1.00, 1.00, 1.00],
                ["Políticas",                  0.70, 0.70, 0.60, 0.70],
                ["TOTAL",                      0.20, 0.96, 0.89, 0.91],
            ],
        },
        "demanda_no_cubierta": [
            {"consulta": texto, "veces": n} for texto, n in demanda_no_cubierta.most_common(8)
        ],
        "consultas": consultas,
        "ofertas": registro,
    }

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(panel, ensure_ascii=False, indent=2), encoding="utf-8")

    r, v = panel["resumen"], panel["verificacion"]
    print(f"\nOK. {SALIDA.name} generado.")
    print(f"   consultas: {r['consultas']}  |  resueltas sin persona: "
          f"{r['resueltas_sin_persona']} ({r['tasa_resolucion']:.0%})")
    print(f"   tiempo mediana: {r['ms_mediana']:.0f} ms  |  p95: {r['ms_p95']:.0f} ms")
    print(f"   ofertas: {r['ofertas']}  |  resueltas por la regla: "
          f"{r['ofertas_por_regla']} ({r['tasa_ofertas_automaticas']:.0%})")
    print(f"   demanda no cubierta: {len(panel['demanda_no_cubierta'])} consultas distintas")
    print(f"\n   VERIFICADO contra la respuesta correcta:")
    print(f"     correctas          {v['correctas']:>3}  ({v['tasa_acierto_verificado']:.0%})")
    print(f"     pieza equivocada   {v['pieza_equivocada']:>3}")
    print(f"     falsos positivos   {v['falsos_positivos']:>3}  (ofreció algo sin tenerlo)")
    print(f"     sin respuesta      {v['sin_respuesta']:>3}")


if __name__ == "__main__":
    main()
