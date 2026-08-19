"""
tests/test_busqueda.py
======================
Banco de pruebas de la RECUPERACIÓN de VendIQ.

Para qué sirve: sin un número, "va mejor" es una opinión. Esto mide dos cosas que son
justo las que el negocio necesita que funcionen:

  1. ACIERTO     — ¿encuentra la pieza que el cliente pide?
  2. GUARDARRAÍL — cuando la pieza NO está en catálogo, ¿se calla en vez de ofrecer otra?

Las preguntas se generan desde el propio inventario, así que la respuesta correcta se
conoce de antemano y no hay que escribirla a mano.

Uso:
    python tests/test_busqueda.py            # ejecuta el banco de pruebas
    python tests/test_busqueda.py --calibrar # barrido de umbrales, para reajustar

Requisitos: haber ejecutado 01_ingesta_chunking.py y 02_embeddings.py.
"""

import csv
import importlib.util
import json
import random
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cargar_modulo_busqueda():
    """Importa 03_buscar.py (el nombre empieza por un número, así que no vale 'import')."""
    spec = importlib.util.spec_from_file_location("buscar", BASE / "03_buscar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def leer_inventario():
    with open(BASE / "datos" / "inventario_sintetico.csv",
              encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def ensuciar(texto: str) -> str:
    """Simula cómo llega un mensaje por WhatsApp: sin tildes, en minúsculas, sin signos."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return texto.lower().replace("?", "").replace("¿", "")


def construir_casos(filas, semilla=7):
    """Preguntas con su respuesta correcta. Devuelve (categoria, pregunta, {ids ok}).

    El esperado es un CONJUNTO, no un id. Casi siempre tiene un solo elemento, pero
    hay preguntas que no tienen una única respuesta correcta y medirlas como si la
    tuvieran es medir mal — ver 'datos incompletos' abajo.
    """
    random.seed(semilla)
    muestra = random.sample(filas, 25)
    casos = []

    # Índice de fichas que solo se distinguen por motor y año.
    hermanas = {}
    for f in filas:
        hermanas.setdefault((f["pieza"], f["marca"], f["modelo"]), []).append(f["id"])

    for f in muestra:
        casos.append(("pregunta natural",
                      f"¿tenéis un {f['pieza'].lower()} para un {f['marca'].title()} "
                      f"{f['modelo']} {f['motor']} del {f['anio']}?",
                      {f"pieza-{f['id']}"}))

    # DATOS INCOMPLETOS: el cliente da pieza + marca + modelo, y NO da motor ni año.
    # 487 de las 1.000 fichas comparten esos tres datos con alguna otra, así que la
    # pregunta tiene varias respuestas igual de correctas. Antes se exigía acertar
    # una concreta y la categoría salía al 67% — un número que no medía el buscador,
    # medía la suerte. Se acepta cualquier ficha que encaje con lo que el cliente
    # DIJO; distinguir más no es trabajo del buscador, es pedir la matrícula.
    for f in muestra[:15]:
        casos.append(("datos incompletos",
                      f"busco {f['pieza'].lower()} de {f['marca'].title()} {f['modelo']}",
                      {f"pieza-{i}" for i in
                       hermanas[(f["pieza"], f["marca"], f["modelo"])]}))
    for f in muestra[:15]:
        casos.append(("mensaje sucio WhatsApp",
                      ensuciar(f"tenes {f['pieza']} pa un {f['marca']} {f['modelo']} {f['anio']}"),
                      {f"pieza-{f['id']}"}))
    for f in muestra[:15]:
        casos.append(("referencia OEM",
                      f"necesito la referencia {f['referencia_oem']}",
                      {f"pieza-{f['id']}"}))

    casos += [(c, p, {e}) for c, p, e in [
        ("politica", "cuanto tiempo tarda en llegar el pedido", "politica-envio_y_plazos"),
        ("politica", "la pieza tiene garantia?", "politica-garantia"),
        ("politica", "me puedes hacer un descuento?", "politica-precios_y_descuentos"),
        ("politica", "puedo pagar con tarjeta o bizum?", "politica-formas_de_pago_y_devoluciones"),
        ("politica", "si no me vale la puedo devolver", "politica-formas_de_pago_y_devoluciones"),
        ("politica", "que datos necesitas del coche para buscarla",
         "politica-como_identificar_la_pieza_correcta"),
        ("politica", "envias a canarias?", "politica-envio_y_plazos"),
        ("politica", "puedo pasar a recogerla a la tienda?", "politica-envio_y_plazos"),
        ("politica", "que pasa si la pieza sale defectuosa", "politica-garantia"),
        ("politica", "el precio lleva iva incluido?", "politica-precios_y_descuentos"),
    ]]
    return casos


def construir_fuera_de_catalogo(filas, semilla=11, n=40):
    """Piezas que NO existen. Es el test del guardarraíl.

    LA AUSENCIA CAMBIA DE SITIO AL CRECER EL CATÁLOGO
    -------------------------------------------------
    La primera versión cruzaba pieza + MARCA: "¿tenéis un turbo de Kia?" cuando el
    catálogo tenía turbos y tenía Kias, pero ningún turbo de Kia. Con 1.000 piezas
    funcionaba. Con 5.000 dejó de funcionar de golpe y el test reventó con una
    división por cero, porque **ya no queda ni una combinación pieza+marca libre**:
    37 tipos por 15 marcas son 555 casillas y el catálogo las llena todas.

    No era un fallo del test, era el test quedándose obsoleto por el tamaño. Con más
    stock, al cliente ya no le falta "un turbo de Kia": le falta "un turbo de Kia
    CEED". Así que la ausencia se genera ahora a nivel pieza+marca+modelo, y se
    prueban además los dos casos que a esta escala son los que de verdad engañan:

      - MISMO COCHE, OTRO MODELO — hay catalizador de Audi A3, se pide para el Q3.
      - MISMA PIEZA, OTRO LADO   — hay piloto trasero derecho, se pide el izquierdo.

    En los dos, la ficha equivocada comparte casi todas las palabras con la pedida.
    """
    random.seed(semilla)
    existentes = {(f["pieza"], f["marca"], f["modelo"]) for f in filas}
    piezas = sorted({f["pieza"] for f in filas})
    modelos = {}
    for f in filas:
        modelos.setdefault(f["marca"], set()).add(f["modelo"])
    marcas = sorted(modelos)

    OPUESTAS = {"izquierdo": "derecho", "derecho": "izquierdo",
                "izquierda": "derecha", "derecha": "izquierda"}

    preguntas = []

    # (a) mismo coche, pieza que ese modelo concreto no tiene
    intentos = 0
    while len(preguntas) < n // 2 and intentos < 20000:
        intentos += 1
        pieza, marca = random.choice(piezas), random.choice(marcas)
        modelo = random.choice(sorted(modelos[marca]))
        if (pieza, marca, modelo) in existentes:
            continue
        preguntas.append(f"¿tenéis un {pieza.lower()} para un {marca.title()} {modelo}?")

    # (b) el lado contrario de una pieza que sí tenemos
    lados = [f for f in filas
             if any(p.lower() in OPUESTAS for p in f["pieza"].split())]
    random.shuffle(lados)
    for f in lados:
        if len(preguntas) >= n:
            break
        palabra = next(p for p in f["pieza"].split() if p.lower() in OPUESTAS)
        contraria = f["pieza"].replace(palabra, OPUESTAS[palabra.lower()])
        if (contraria, f["marca"], f["modelo"]) in existentes:
            continue
        preguntas.append(f"¿tenéis un {contraria.lower()} para un "
                         f"{f['marca'].title()} {f['modelo']}?")

    if not preguntas:
        raise SystemExit("no se pudo generar ninguna ausencia: revisa el catálogo")
    return preguntas


def evaluar(buscador, casos, fuera):
    """Ejecuta el banco de pruebas y devuelve (resumen_por_categoria, total, guardarrail)."""
    por_categoria, total = {}, {"n": 0, "r1": 0, "r3": 0}
    fallos = []

    for categoria, pregunta, esperado in casos:
        # sin umbral: aquí medimos si SABE ordenar, no si sabe callarse
        hits = buscador.buscar(pregunta, k=3, aplicar_umbral=False)
        ranking = [item["id"] for _, item in hits]
        acierto1 = bool(ranking) and ranking[0] in esperado
        acierto3 = bool(esperado & set(ranking))

        d = por_categoria.setdefault(categoria, {"n": 0, "r1": 0, "r3": 0})
        for clave, valor in (("n", 1), ("r1", acierto1), ("r3", acierto3)):
            d[clave] += valor
            total[clave] += valor
        if not acierto3:
            fallos.append((categoria, pregunta, esperado, ranking[:1]))

    # Guardarraíl: ante una pieza que NO existe, no debe ofrecer ninguna ficha de
    # inventario. Sí puede devolver una política (p. ej. "cómo identificar la pieza
    # correcta" -> pedir la matrícula): eso es exactamente lo que debe hacer.
    callados = 0
    ejemplos_fuga = []
    for pregunta in fuera:
        piezas_ofrecidas = [(p, it) for p, it in buscador.buscar(pregunta, k=3)
                            if it["tipo"] == "inventario"]
        if not piezas_ofrecidas:
            callados += 1
        elif len(ejemplos_fuga) < 5:
            puntuacion, item = piezas_ofrecidas[0]
            ejemplos_fuga.append((pregunta, puntuacion, item["texto"][:60]))

    return por_categoria, total, (callados, len(fuera), ejemplos_fuga), fallos


def main():
    modulo = cargar_modulo_busqueda()
    buscador = modulo.cargar_buscador()
    filas = leer_inventario()
    casos = construir_casos(filas)
    fuera = construir_fuera_de_catalogo(filas)

    if "--calibrar" in sys.argv:
        calibrar(modulo, buscador, casos, fuera)
        return

    por_categoria, total, guardarrail, fallos = evaluar(buscador, casos, fuera)

    print("=" * 72)
    print("ACIERTO — ¿encuentra la pieza correcta?")
    print("=" * 72)
    print(f"{'tipo de pregunta':<26} {'n':>4} {'acierto@1':>11} {'acierto@3':>11}")
    for categoria in sorted(por_categoria):
        d = por_categoria[categoria]
        print(f"{categoria:<26} {d['n']:>4} {d['r1']/d['n']:>10.0%} {d['r3']/d['n']:>11.0%}")
    print("-" * 72)
    print(f"{'TOTAL':<26} {total['n']:>4} {total['r1']/total['n']:>10.0%} "
          f"{total['r3']/total['n']:>11.0%}")

    callados, n_fuera, fugas = guardarrail

    # El panel leia estas cifras de una constante escrita a mano y se quedaron
    # obsoletas al pasar de 1.000 a 5.000 piezas. Ahora las escribe quien las
    # mide, y el panel las lee de aqui.
    (BASE / "salida").mkdir(parents=True, exist_ok=True)
    (BASE / "salida" / "calidad.json").write_text(json.dumps({
        "acierto_ahora": round(total["r1"] / total["n"], 4),
        "acierto_top3": round(total["r3"] / total["n"], 4),
        "guardarrail": round(callados / n_fuera, 4),
        "preguntas_banco": total["n"],
        "piezas_inexistentes_probadas": n_fuera,
        "fichas_indexadas": len(buscador.items),
        "medido": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fuente": "tests/test_busqueda.py",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("=" * 72)
    print("GUARDARRAÍL — ¿se calla cuando NO tiene la pieza?")
    print("=" * 72)
    print(f"  {callados}/{n_fuera} piezas inexistentes → no devuelve nada ({callados/n_fuera:.0%})")
    for pregunta, puntuacion, texto in fugas:
        print(f"    se le escapa [{puntuacion:.2f}] {pregunta}")
        print(f"                 -> {texto}")

    if fallos:
        print()
        print(f"Preguntas sin acierto en el top 3: {len(fallos)}")
        for categoria, pregunta, esperado, obtenido in fallos[:8]:
            print(f"  [{categoria}] {pregunta}")
            print(f"     esperaba {' o '.join(sorted(esperado))}, primero fue {obtenido}")

    # Estos mínimos son los que ya se han alcanzado: si un cambio futuro los baja,
    # el test falla y te enteras antes de desplegar.
    ok = (total["r1"] / total["n"] >= 0.90
          and total["r3"] / total["n"] >= 0.95
          and callados / n_fuera >= 0.90)
    print()
    print("RESULTADO:", "PASA" if ok else "NO PASA")
    return 0 if ok else 1


def calibrar(modulo, buscador, casos, fuera):
    """Barrido de umbrales: para reajustar los mínimos si cambian los datos."""
    piezas = [(p, e) for c, p, e in casos if c != "politica"]
    politicas = [(p, e) for c, p, e in casos if c == "politica"]

    print("Barrido UMBRAL_PIEZA (piezas encontradas vs inexistentes filtradas)")
    print(f"{'umbral':>8} {'piezas OK':>12} {'filtra fuera':>14}")
    original = modulo.UMBRAL_PIEZA
    for u in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        modulo.UMBRAL_PIEZA = u
        ok = sum(1 for p, _ in piezas if buscador.buscar(p, k=1))
        filtra = sum(1 for p in fuera
                     if not [1 for _, it in buscador.buscar(p, k=3)
                             if it["tipo"] == "inventario"])
        print(f"{u:>8.2f} {ok/len(piezas):>11.0%} {filtra/len(fuera):>13.0%}")
    modulo.UMBRAL_PIEZA = original

    print()
    print("Barrido UMBRAL_POLITICA (políticas encontradas)")
    print(f"{'umbral':>8} {'politicas OK':>14}")
    original = modulo.UMBRAL_POLITICA
    for u in (0.30, 0.34, 0.38, 0.42, 0.46, 0.50):
        modulo.UMBRAL_POLITICA = u
        ok = sum(1 for p, _ in politicas if buscador.buscar(p, k=3))
        print(f"{u:>8.2f} {ok/len(politicas):>13.0%}")
    modulo.UMBRAL_POLITICA = original


if __name__ == "__main__":
    sys.exit(main() or 0)
