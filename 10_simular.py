"""
10_simular.py
=============
ACTIVIDAD DEL CENTRO DE CONTROL. Fase 3 de docs/VendIQ_Spec_Conversacion.md.

Simula el tráfico de WhatsApp de varios días —150-200 conversaciones diarias— y
lo pasa ENTERO por el sistema real para llenar el panel con números medidos.

LA REGLA DEL PROYECTO, Y POR QUÉ IMPORTA
----------------------------------------
Los mensajes son **sintéticos y se declaran como tales** en todas partes: en el
fichero de salida, en el panel y aquí. Lo que NO es sintético es ni un solo
número: cada decisión, cada milisegundo y cada escalado sale de ejecutar
`Sistema.chatear()` de verdad contra las 5.000 piezas.

Es la diferencia entre "el panel dice que resolvemos el 92%" y "hemos pasado
1.200 conversaciones por el sistema y resolvió 1.104". La primera es una
maqueta bonita; la segunda se puede auditar, y si alguien pregunta "¿y esto de
dónde sale?", la respuesta es este fichero.

Escribir "1.200 consultas" a mano en un JSON habría costado dos minutos y
habría quedado igual de bien en la pantalla. También habría sido mentir.

DE DÓNDE SALEN LAS CONVERSACIONES
---------------------------------
Del mismo generador que el banco de pruebas (tests/test_conversaciones.py), con
semillas distintas. No se escribe tráfico aparte a propósito: si el panel
enseñara conversaciones más fáciles que las que se miden, los porcentajes del
panel serían mejores que los reales y no valdrían para nada.

Lo que sí cambia es la MEZCLA. El banco tiene 25 preguntas de precio y 20 de
piezas que no hay, porque busca cubrir casos. Un día de verdad no se reparte
así: llegan sobre todo peticiones de pieza, y las quejas son raras. Los pesos
de MEZCLA_REAL son la estimación de Álvaro sobre su propio WhatsApp, y están
declarados como estimación.

Uso:
    python 10_simular.py                  # 14 días
    python 10_simular.py --dias 7
    python 10_simular.py --dias 30 --semilla 5
"""

import argparse
import importlib.util
import json
import random
import statistics
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).parent
SALIDA = BASE / "salida" / "actividad.json"

# Cómo se reparte un día real de WhatsApp en un desguace. ES UNA ESTIMACIÓN de
# Álvaro, no un dato medido, y por eso viaja hasta el panel etiquetada como tal.
# Lo que sí es real es lo que el sistema hace con cada mensaje.
MEZCLA_REAL = {
    "precio exacto": 26, "datos a medias": 16, "no la tenemos": 12,
    "condiciones": 11, "mensaje sucio": 9, "conversación larga": 6,
    "referencia OEM": 5, "regatea": 5, "cierra la venta": 4,
    "número de stock": 3, "otro modelo": 3, "queja": 2, "ruido": 2,
    "lado que no hay": 2, "no envía sin cobrar": 1, "no valida justificantes": 1,
    "prisa": 1,
}

# Un desguace no recibe mensajes de madrugada. Peso por hora, de 8 a 20.
HORAS = {8: 4, 9: 9, 10: 13, 11: 13, 12: 11, 13: 7, 14: 3,
         15: 4, 16: 10, 17: 11, 18: 9, 19: 5, 20: 2}
# Sábado a media máquina, domingo cerrado. El volumen de lunes a viernes sale
# siempre dentro de la banda 150-200 que pide la especificación; el factor solo
# recorta el sábado.
FACTOR_DIA = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.45, 6: 0.0}

# Cómo sigue un cliente después de que le contestes. Un mensaje suelto y adiós
# casi no existe: se pregunta el plazo, se lo piensa, o cierra. Estas coletillas
# pasan por el sistema como cualquier otro mensaje — no son decorado, son turnos
# reales que ejercitan las ramas de seguimiento.
COLETILLAS = [
    "vale, gracias", "perfecto", "luego te digo algo", "déjame que lo mire",
    "¿y me lo mandas al taller?", "¿cuánto tarda?", "me lo quedo",
    "¿está comprobada?", "ok, te confirmo mañana", "genial, gracias!",
    "¿me lo apartas?", "lo consulto con el cliente y te digo",
]


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[alias] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def construir_repertorio(sistema, banco, semillas):
    """Muchas conversaciones distintas, agrupadas por situación.

    Se llama al generador del banco con varias semillas porque una sola da 200
    conversaciones y un mes de tráfico necesita miles. Con semillas distintas
    cambian las piezas, los coches y el orden, no el tipo de conversación.
    """
    por_situacion = {}
    for semilla in semillas:
        casos = banco.casos_de_catalogo(sistema.filas, sistema.buscar_mod,
                                        semilla=semilla)
        if semilla == semillas[0]:
            casos += banco.casos_escritos()
        for categoria, perfil, mensajes, _ in casos:
            por_situacion.setdefault(categoria, []).append((perfil, mensajes))
    return por_situacion


def repartir_dia(rnd, total):
    """Reparte las conversaciones del día entre las horas de atención."""
    horas = list(HORAS)
    pesos = [HORAS[h] for h in horas]
    return Counter(rnd.choices(horas, weights=pesos, k=total))


def simular(sistema, repertorio, dias=14, semilla=7):
    rnd = random.Random(semilla)
    situaciones = [s for s in MEZCLA_REAL if s in repertorio]
    pesos = [MEZCLA_REAL[s] for s in situaciones]

    # Una consulta a la basura antes de empezar a cronometrar: la primera de todas
    # paga la inicialización perezosa de numpy y del modelo, y sale diez veces más
    # lenta. Contarla ensuciaría el máximo con un dato que no le pasa a ningún
    # cliente real.
    sistema.chatear("calentamiento", "alternador", reiniciar=True)

    hoy = date.today()
    registro_dias, por_hora = [], Counter()
    acciones, intenciones, motivos = Counter(), Counter(), Counter()
    no_cubierto, precios_estado = Counter(), Counter()
    latencias, muestra = [], []
    n_conv = n_msg = n_escaladas = n_precio = 0

    for atras in range(dias - 1, -1, -1):
        dia = hoy - timedelta(days=atras)
        factor = FACTOR_DIA[dia.weekday()]
        if factor == 0:
            registro_dias.append({"fecha": dia.isoformat(),
                                  "dia": "domingo", "conversaciones": 0,
                                  "mensajes": 0, "resueltas": 0, "escaladas": 0,
                                  "ms_mediana": None})
            continue

        cuantas = rnd.randint(150, 200)
        if factor < 1.0:
            cuantas = round(cuantas * factor)
        reparto = repartir_dia(rnd, cuantas)
        lat_dia, esc_dia, msg_dia = [], 0, 0

        for hora, cuantas_hora in sorted(reparto.items()):
            por_hora[hora] += cuantas_hora
            for _ in range(cuantas_hora):
                situacion = rnd.choices(situaciones, weights=pesos, k=1)[0]
                perfil, mensajes = rnd.choice(repertorio[situacion])
                # La mayoría de las conversaciones siguen después de la primera
                # respuesta. Sin esto salían a 1,5 mensajes por conversación, que
                # no es lo que pasa en un WhatsApp de verdad.
                mensajes = list(mensajes)
                if len(mensajes) < 4:
                    for _ in range(rnd.choices([0, 1, 2], weights=[25, 50, 25])[0]):
                        mensajes.append(rnd.choice(COLETILLAS))
                sesion = f"sim-{n_conv}"
                n_conv += 1
                turnos = []

                for i, mensaje in enumerate(mensajes):
                    # AQUÍ es donde deja de ser simulación: esto ejecuta la
                    # búsqueda contra las 5.000 fichas y el redactor de verdad.
                    datos = sistema.chatear(
                        sesion, mensaje, perfil=perfil,
                        nombre="Juan Carlos" if perfil == "conocido" else "",
                        reiniciar=(i == 0))
                    bot, busqueda = datos["bot"], datos["busqueda"]

                    n_msg += 1
                    msg_dia += 1
                    latencias.append(busqueda["ms"])
                    lat_dia.append(busqueda["ms"])
                    acciones[bot["accion"]] += 1
                    intenciones[bot["intencion"]] += 1
                    if bot["precio_dado"]:
                        n_precio += 1
                    for r in busqueda["resultados"]:
                        pc = r.get("precio_cliente") or {}
                        if pc.get("estado") and pc["estado"] != "no_aplica":
                            precios_estado[pc["estado"]] += 1
                            break
                    if bot["accion"] == "ESCALAR":
                        motivos[bot["porque_accion"]] += 1
                    if busqueda["decision"] == "NO DISPONIBLE":
                        no_cubierto[mensaje.strip().lower()] += 1
                    turnos.append({"cliente": mensaje, "bot": bot["lineas"],
                                   "accion": bot["accion"], "ms": busqueda["ms"]})

                    # El guardarraíl se vigila en TODAS las conversaciones, no en
                    # una muestra: si alguna vez se colara un precio sin permiso,
                    # tiene que salir en el panel y no perderse en el montón.
                    if not bot["precio_autorizado"]:
                        muestra.append({"FUGA": True, "situacion": situacion,
                                        "turnos": turnos})

                if turnos and turnos[-1]["accion"] == "ESCALAR":
                    n_escaladas += 1
                    esc_dia += 1
                # Unas pocas conversaciones enteras para poder leerlas en el panel.
                if len(muestra) < 24 and rnd.random() < 0.004:
                    muestra.append({"situacion": situacion, "perfil": perfil,
                                    "hora": f"{hora:02d}:{rnd.randint(0,59):02d}",
                                    "turnos": turnos})

        registro_dias.append({
            "fecha": dia.isoformat(),
            "dia": ["lunes", "martes", "miércoles", "jueves", "viernes",
                    "sábado", "domingo"][dia.weekday()],
            "conversaciones": cuantas,
            "mensajes": msg_dia,
            "resueltas": cuantas - esc_dia,
            "escaladas": esc_dia,
            "ms_mediana": round(statistics.median(lat_dia), 1) if lat_dia else None,
        })
        print(f"  {dia.isoformat()}  {cuantas:>4} conversaciones · "
              f"{msg_dia:>4} mensajes · {esc_dia:>3} a tu mesa")

    orden = sorted(latencias)

    return {
        # ------------------------------------------------------ la etiqueta
        "sintetico": True,
        "aviso": ("Los MENSAJES son sintéticos: los genera el mismo código que el "
                  "banco de pruebas. Los NÚMEROS no: cada decisión, cada "
                  "milisegundo y cada escalado sale de ejecutar el sistema real "
                  "contra las 5.000 piezas del catálogo."),
        "mezcla_declarada": ("El reparto por tipo de mensaje es una ESTIMACIÓN de "
                             "Álvaro sobre su propio WhatsApp, no un dato medido."),
        "generado": time.strftime("%Y-%m-%d %H:%M"),
        "parametros": {"dias": dias, "conversaciones_dia": "150-200 (lun-vie)",
                       "semilla": semilla, "domingo": "cerrado",
                       "sabado": "45% del volumen"},
        "catalogo": {"piezas": len(sistema.filas),
                     "fichas_indexadas": len(sistema.buscador.items)},

        "resumen": {
            "conversaciones": n_conv,
            "mensajes": n_msg,
            "escaladas": n_escaladas,
            "resueltas_sin_persona": n_conv - n_escaladas,
            "tasa_resolucion": round((n_conv - n_escaladas) / n_conv, 4) if n_conv else 0,
            "precios_dados": n_precio,
            "ms_mediana": round(statistics.median(orden), 1) if orden else 0,
            "ms_p95": round(orden[int(len(orden) * 0.95)], 1) if orden else 0,
            "ms_max": round(orden[-1], 1) if orden else 0,
            "fugas_de_precio": sum(1 for m in muestra if m.get("FUGA")),
        },
        "por_dia": registro_dias,
        "por_hora": [{"hora": h, "conversaciones": por_hora.get(h, 0)}
                     for h in sorted(HORAS)],
        "acciones": dict(acciones.most_common()),
        "intenciones": dict(intenciones.most_common(10)),
        "motivos_escalado": [{"motivo": m, "veces": n}
                             for m, n in motivos.most_common(6)],
        "precios": dict(precios_estado.most_common()),
        "no_cubierto": [{"consulta": c, "veces": n}
                        for c, n in no_cubierto.most_common(8)],
        "muestra": muestra[:24],
    }


def main():
    ap = argparse.ArgumentParser(description="Simula tráfico real por el sistema")
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--con-llm", action="store_true",
                    help="redacta con Groq. Lento y sujeto a su límite por "
                         "minuto: 7 días son ~2.245 mensajes.")
    args = ap.parse_args()

    panel = cargar("06_panel.py", "panel")
    banco = cargar("tests/test_conversaciones.py", "banco")
    sistema = panel.Sistema()

    # SIN LLM salvo que se pida. Lo que mide este fichero son las DECISIONES del
    # sistema —qué encuentra, qué escala, cuánto tarda, si se le escapa un
    # precio—, y ésas no cambian porque el modelo escriba más bonito. Encenderlo
    # aquí solo añadiría 2.245 llamadas, el límite por minuto de Groq de por
    # medio, y unos números que dependerían de cuántos 429 tocaran ese día.
    if not args.con_llm:
        sistema.config_llm = dict(sistema.config_llm or {}, GROQ_API_KEY="")

    print(f"\nConstruyendo el repertorio de conversaciones...")
    repertorio = construir_repertorio(sistema, banco, semillas=[23, 41, 59, 77, 95])
    total = sum(len(v) for v in repertorio.values())
    print(f"  {total} conversaciones distintas en {len(repertorio)} situaciones\n")

    t0 = time.time()
    print(f"Pasando {args.dias} días de tráfico por el sistema REAL:")
    actividad = simular(sistema, repertorio, dias=args.dias, semilla=args.semilla)
    actividad["segundos_de_ejecucion"] = round(time.time() - t0, 1)

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(actividad, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    r = actividad["resumen"]
    print(f"\nOK. {SALIDA.name} generado en {actividad['segundos_de_ejecucion']}s")
    print(f"   {r['conversaciones']} conversaciones · {r['mensajes']} mensajes")
    print(f"   resueltas sin persona: {r['resueltas_sin_persona']} "
          f"({r['tasa_resolucion']:.0%})")
    print(f"   a tu mesa: {r['escaladas']}  ·  precios dados: {r['precios_dados']}")
    print(f"   latencia: mediana {r['ms_mediana']} ms · p95 {r['ms_p95']} ms · "
          f"máx {r['ms_max']} ms")
    print(f"   FUGAS DE PRECIO: {r['fugas_de_precio']}")
    if r["fugas_de_precio"]:
        print("   >>> revisa salida/actividad.json, campo 'muestra'")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
