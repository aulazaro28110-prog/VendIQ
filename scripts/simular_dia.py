"""Genera un «día» SINTÉTICO de trabajo para medir la revisión de la mañana (S21, Fase 6).

Escribe en los archivos de negocio (reservas, ofertas y dudas) registros nuevos con
origen "simulacion", que crm-mcp distingue de las pruebas y de los clientes. Antes de
escribir el día nuevo quita los del día simulado anterior (solo los que tienen
origen "simulacion"), para que cada día se revise por sí solo. No toca ningún otro registro.

Mete A PROPÓSITO urgencias (0-2 piezas reservadas dos veces, reservas de 31+ días, ofertas
que esperan decisión, preguntas nuevas desde ayer) y distractores que NO son urgentes
(reservas recientes, una de 15-25 días, ofertas ya cerradas, una duda de hace 3 días).
La lista exacta de urgencias —la «verdad» del día— va a un archivo aparte, con los mismos
id_aviso que usa parte_del_dia. No la mires hasta haber terminado la revisión.

La semilla fija qué piezas, cuántas urgencias y qué preguntas salen: el mismo número da
siempre el mismo día (las fechas se cuentan hacia atrás desde el momento en que se ejecuta).

Uso:
    py scripts/simular_dia.py --semilla 3 --verdad <archivo.json>   # genera el día 3
    py scripts/simular_dia.py --limpiar                              # quita todo lo simulado
    Opcional: --salida <carpeta>  escribe ahí en vez de en salida/ (p. ej. una copia).
"""
import argparse
import csv
import importlib.util
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ORIGEN = "simulacion"
MOTIVO = "lo ve una persona: el bot no está seguro"

PREGUNTAS = [
    "¿hacéis envíos a Canarias?",
    "¿la garantía cubre la mano de obra?",
    "¿puedo recoger la pieza el sábado por la tarde?",
    "¿me la montáis vosotros?",
    "¿aceptáis pago con Bizum?",
    "¿la pieza viene probada?",
    "¿tenéis factura con IVA desglosado?",
    "¿cuánto tarda un envío a Portugal?",
    "¿me guardáis la pieza una semana?",
    "¿hacéis descuento a talleres?",
    "¿la referencia OEM es la original?",
    "¿puedo devolverla si no me vale?",
]


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / "src" / fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def leer(ruta):
    if not ruta.exists():
        return []
    texto = ruta.read_text(encoding="utf-8-sig").strip()
    return json.loads(texto) if texto else []


def escribir(ruta, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")


def quitar_simulacion(salida):
    """Quita de los tres archivos SOLO lo que tiene origen "simulacion". Devuelve cuántos."""
    quitados = {}
    for nombre in ("reservas.json", "ofertas.json", "no_resueltas.json"):
        filas = leer(salida / nombre)
        quedan = [f for f in filas if f.get("origen") != ORIGEN]
        if len(quedan) != len(filas):
            escribir(salida / nombre, quedan)
        quitados[nombre] = len(filas) - len(quedan)
    return quitados


def generar(semilla, salida, ahora):
    """Escribe el día `semilla` en `salida` y devuelve su verdad (las urgencias metidas)."""
    rng = random.Random(semilla)
    with open(BASE / "datos" / "inventario_sintetico.csv", encoding="utf-8-sig", newline="") as f:
        inventario_filas = list(csv.DictReader(f, delimiter=";"))
    ofertas_mod = cargar("04_ofertas.py", "ofertas")
    ofertas_mod.REGISTRO = salida / "ofertas.json"          # escribe donde diga --salida
    inventario = ofertas_mod.Inventario(inventario_filas)
    con_precio = [p for p in inventario_filas if ofertas_mod.precio_publicado(p["precio"])]
    piezas = iter(rng.sample(con_precio, 20))                # piezas distintas: sin choques sin querer

    ayer = (ahora - timedelta(days=1)).replace(second=0, microsecond=0)

    def a_las(dia, hora=None):
        return dia.replace(hour=hora if hora is not None else rng.randint(9, 20),
                           minute=rng.randint(0, 59)).strftime("%Y-%m-%d %H:%M")

    def reserva(pieza, cuando, i):
        return {"sesion": f"sim-dia{semilla}-r{i}", "cuando": cuando,
                "matricula": f"{rng.randint(1000, 9999)} SIM",   # inventada a propósito
                "vehiculo": f"{pieza['marca']} {pieza['modelo']}", "pieza": pieza["pieza"],
                "id_pieza": pieza["id"], "precio_dicho": pieza["precio"],
                "estado": "pendiente de preparar", "origen": ORIGEN}

    verdad, reservas_nuevas = [], []
    # Urgencia 1: piezas reservadas dos veces (la primera, anteayer; la segunda, ayer).
    for _ in range(rng.randint(0, 2)):
        p = next(piezas)
        reservas_nuevas += [reserva(p, a_las(ayer - timedelta(days=1)), len(reservas_nuevas)),
                            reserva(p, a_las(ayer), len(reservas_nuevas) + 1)]
        verdad.append({"tipo": "conflicto_de_reserva", "id_aviso": f"conflicto:{p['id']}"})
    # Urgencia 2: reservas de 31 a 60 días sin preparar.
    for _ in range(rng.randint(1, 2)):
        p = next(piezas)
        cuando = a_las(ahora - timedelta(days=rng.randint(31, 60)))
        reservas_nuevas.append(reserva(p, cuando, len(reservas_nuevas)))
        verdad.append({"tipo": "reserva_antigua", "id_aviso": f"reserva:{p['id']}:{cuando}"})
    # Distractores: reservas recientes y una de 15-25 días (no llega a 30).
    for _ in range(rng.randint(2, 3)):
        reservas_nuevas.append(reserva(next(piezas), a_las(ayer), len(reservas_nuevas)))
    reservas_nuevas.append(reserva(next(piezas),
                                   a_las(ahora - timedelta(days=rng.randint(15, 25))),
                                   len(reservas_nuevas)))
    escribir(salida / "reservas.json", leer(salida / "reservas.json") + reservas_nuevas)

    # Urgencia 3: ofertas que esperan decisión (un 40 % por debajo -> A_MANO -> pendiente).
    # Distractor: ofertas a precio publicado (ACEPTAR -> cerrada sola).
    for i in range(rng.randint(0, 2)):
        p = next(piezas)
        importe = round(ofertas_mod.precio_publicado(p["precio"]) * 0.60, 2)
        o = ofertas_mod.registrar(inventario, p["id"], importe,
                                  f"Cliente simulado {semilla}-{i}", ORIGEN)
        verdad.append({"tipo": "oferta_pendiente", "id_aviso": f"oferta:{o['n']}"})
    for i in range(rng.randint(1, 2)):
        p = next(piezas)
        ofertas_mod.registrar(inventario, p["id"], ofertas_mod.precio_publicado(p["precio"]),
                              f"Cliente simulado {semilla}-c{i}", ORIGEN)

    # Urgencia 4: preguntas nuevas desde ayer. Distractor: una de hace 3 días.
    dudas = leer(salida / "no_resueltas.json")
    siguiente = max([d.get("n", 0) for d in dudas], default=0) + 1
    textos = rng.sample(PREGUNTAS, 4)
    nuevas = rng.randint(1, 3)
    for i, texto in enumerate(textos[:nuevas + 1]):
        primera = a_las(ayer) if i < nuevas else a_las(ahora - timedelta(days=3))
        dudas.append({"n": siguiente, "pregunta": texto, "motivo": MOTIVO, "decision": "ESCALA",
                      "sesion": f"sim-dia{semilla}-p{i}", "veces": rng.randint(1, 4),
                      "primera": primera, "ultima": primera, "estado": "pendiente",
                      "respuesta": None, "respondida_por": None, "origen": ORIGEN})
        if i < nuevas:
            verdad.append({"tipo": "pregunta_nueva", "id_aviso": f"pregunta:{siguiente}"})
        siguiente += 1
    escribir(salida / "no_resueltas.json", dudas)
    return verdad


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Genera un día sintético (S21, Fase 6)")
    p.add_argument("--semilla", type=int)
    p.add_argument("--verdad", type=Path, help="archivo donde guardar la verdad del día")
    p.add_argument("--salida", type=Path, default=BASE / "salida")
    p.add_argument("--limpiar", action="store_true", help="solo quita lo simulado")
    args = p.parse_args()

    quitados = quitar_simulacion(args.salida)
    if args.limpiar:
        print(f"Quitados los registros simulados: {quitados}")
        return
    if args.semilla is None or args.verdad is None:
        p.error("hacen falta --semilla y --verdad (o --limpiar)")

    ahora = datetime.now()
    verdad = generar(args.semilla, args.salida, ahora)
    args.verdad.parent.mkdir(parents=True, exist_ok=True)
    args.verdad.write_text(json.dumps({"semilla": args.semilla,
                                       "generado": ahora.strftime("%Y-%m-%d %H:%M"),
                                       "urgencias": verdad}, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    # A propósito NO se imprime qué urgencias hay: verlas antes sesgaría la revisión.
    print(f"Día {args.semilla} generado en {args.salida.name}/. "
          f"La verdad está en {args.verdad.name}: no la abras hasta terminar la revisión.")


if __name__ == "__main__":
    main()
