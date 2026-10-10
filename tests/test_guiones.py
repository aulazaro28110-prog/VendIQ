# -*- coding: utf-8 -*-
"""
tests/test_guiones.py
=====================
Banco de los 50 GUIONES TIPO, evaluados TURNO A TURNO.

Ejecuta cada guion con `Sistema()` (sin persistencia y sin LLM por defecto), en
sesiones `banco-guion-<id>` (que `es_prueba` excluye de los datos de negocio), y
evalúa cada turno con `12_guiones.evaluar_turno()` —la única definición, que por
dentro reutiliza `clasificar()`/`invariantes()` y las reglas de `07_redactor.py`.

Al final de cada guion comprueba lo que solo se ve en la conversación entera: el
tope de aclaraciones y que una venta cerrada no se reabra.

NO arregla el bot: saca el mapa de fallos (bot mal / expectativa mal / decisión)
para decidir con Álvaro.

Uso:
    py tests/test_guiones.py                 # tabla + fallos
    py tests/test_guiones.py --ver G13       # una conversación con su «por qué»
    py tests/test_guiones.py --json salida/guiones_banco.json
    py tests/test_guiones.py --con-llm       # opcional, enciende Groq
"""
import argparse
import json
import importlib.util
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# Umbral de turnos OK para el código de salida. EMPIEZA EN 0 a propósito: el bot
# aún no implementa P1/P2/P3 ni los arreglos que salgan de este banco, así que la
# primera ejecución no puede exigir 95 %. Se sube a 0.95 cuando el bot esté
# arreglado (tras la parada de la Fase 3). Un invariante de precio roto SIEMPRE falla.
UMBRAL_TURNOS_OK = 0.0


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / "src" / fichero)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[alias] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def construir_sistema(con_llm=False):
    panel = cargar("06_panel.py", "panel")
    sistema = panel.Sistema()
    if not con_llm:
        # Determinista: sin Groq. Igual que test_conversaciones / test_ciclo.
        sistema.config_llm = dict(sistema.config_llm or {}, GROQ_API_KEY="")
    return sistema


def _datos_turno(sistema, sesion, datos, historial):
    conv = sistema.chats.get(sesion)
    return {
        "bot": datos["bot"],
        "busqueda": datos["busqueda"],
        "historial": list(historial),
        "matricula_dada": datos["memoria"].get("matricula"),
        "pieza_pedida": getattr(conv, "pieza_pedida", None),
        "estado": getattr(conv, "estado", None),
    }


def coherencia_turno(datos):
    """C7 · la traza coincide con lo que el bot hizo de verdad. Devuelve [] si OK.

    Para cada turno comprueba lo que pide el prompt (§6, C7): la traza existe; su
    paso de acción es igual a `bot.accion`; las reglas de la traza son iguales a
    `bot.reglas`; y la rama de contexto es coherente con si de verdad se buscó con
    contexto añadido (`busqueda.contexto`). De regalo, que el resumen no esté vacío.
    Es «por construcción»: la traza se monta con los mismos datos que usó el bot,
    así que esto es una red, no un segundo cálculo del porqué.
    """
    bot = datos["bot"]
    busq = datos["busqueda"]
    traza = datos.get("traza") or {}
    pasos = traza.get("pasos") or []
    if not pasos:
        return ["no hay traza"]
    por_paso = {p.get("paso"): p for p in pasos}
    fallos = []
    pa = por_paso.get("accion") or {}
    if pa.get("accion") != bot.get("accion"):
        fallos.append(f"accion: traza «{pa.get('accion')}» != bot «{bot.get('accion')}»")
    reglas_traza = [r.get("regla")
                    for r in (por_paso.get("reglas") or {}).get("reglas", [])]
    reglas_bot = [r["regla"] for r in bot.get("reglas", [])]
    if reglas_traza != reglas_bot:
        fallos.append("reglas de la traza != reglas del bot")
    rama = (por_paso.get("contexto") or {}).get("rama")
    if bool(busq.get("contexto")) != (rama not in (None, "ninguna")):
        fallos.append(f"rama «{rama}» no cuadra con contexto={busq.get('contexto')!r}")
    if not (traza.get("resumen") or "").strip():
        fallos.append("resumen vacío")
    return fallos


# Frases de oferta de compra: si aparecen DESPUÉS de cerrar, la venta se reabre.
_REOFRECE = ("¿te lo aparto", "¿te la aparto", "¿lo preparo", "¿la preparo",
             "¿te lo quedas", "¿te la quedas", "¿lo dejamos apartado")


def ejecutar(sistema, guiones_mod, guiones, ver=None):
    resultados = []
    for g in guiones:
        if ver and g["id"].lower() != ver.lower():
            continue
        sesion = f"banco-guion-{g['id']}"
        historial, turnos = [], []
        aclaraciones = 0
        cerrada_en = None
        fallos_guion = []
        for i, (msg, esp) in enumerate(zip(g["mensajes"], g["esperado"])):
            datos = sistema.chatear(sesion, msg, perfil=g["perfil"],
                                    nombre=g.get("cliente", ""), reiniciar=(i == 0))
            dt = _datos_turno(sistema, sesion, datos, historial)
            ev = guiones_mod.evaluar_turno(esp, dt)
            coh = coherencia_turno(datos)       # C7
            bot = datos["bot"]
            reglas = [r["regla"] for r in bot["reglas"]]
            if bot.get("accion") == "PREGUNTAR":
                aclaraciones += 1
            # venta cerrada -> no se reabre
            if any("cierre de venta" in r for r in reglas):
                cerrada_en = i
            elif cerrada_en is not None:
                texto = " ".join(bot["lineas"]).lower()
                if any(p in texto for p in _REOFRECE):
                    fallos_guion.append(f"turno {i+1}: reabre una venta ya cerrada")
            historial.append(bot["mensaje"])
            turnos.append({
                "n": i + 1, "cliente": msg, "bot": bot["lineas"],
                "esperado": esp["esperado"], "obtenido": ev["obtenido"],
                "ok": ev["ok"], "fallos": ev["fallos"], "reglas": reglas,
                "decision": datos["busqueda"]["decision"],
                "precio": bot.get("precio_dado"),
                "ms": datos["busqueda"].get("ms"),
                "coherencia": coh,
                "resumen": (datos.get("traza") or {}).get("resumen"),
            })
        # tope de aclaraciones (solo se ve en la conversación entera)
        conversar = sistema.conversar
        if aclaraciones > conversar.TOPE_ACLARACIONES:
            fallos_guion.append(f"pregunta {aclaraciones} veces con botones "
                                f"(tope {conversar.TOPE_ACLARACIONES})")
        turnos_ok = sum(1 for t in turnos if t["ok"])
        fuga = any("FUGA DE PRECIO" in f for t in turnos for f in t["fallos"])
        resultados.append({
            "id": g["id"], "tipo": g["tipo"], "nombre": g["nombre"],
            "tipos_mezcla": g["tipos_mezcla"], "turnos": turnos,
            "turnos_ok": turnos_ok, "n_turnos": len(turnos),
            "fallos_guion": fallos_guion, "fuga": fuga,
        })
    return resultados


def tabla(resultados):
    por_tipo = {}
    for r in resultados:
        d = por_tipo.setdefault(r["tipo"], {"g": 0, "t": 0, "ok": 0, "inv": 0})
        d["g"] += 1
        d["t"] += r["n_turnos"]
        d["ok"] += r["turnos_ok"]
        d["inv"] += (1 if r["fuga"] else 0) + len(r["fallos_guion"])
    print("=" * 78)
    print("BANCO DE GUIONES — por tipo")
    print("=" * 78)
    print(f"{'tipo':<10} {'guiones':>7} {'turnos':>7} {'OK':>7} {'%':>6} {'inv/guion':>10}")
    tt = to = ti = 0
    for tipo in ["compra", "regatea", "no_hay", "a_medias", "posventa",
                 "taller", "corrige", "pago"]:
        d = por_tipo.get(tipo)
        if not d:
            continue
        pct = d["ok"] / d["t"] if d["t"] else 0
        print(f"{tipo:<10} {d['g']:>7} {d['t']:>7} {d['ok']:>7} {pct:>5.0%} {d['inv']:>10}")
        tt += d["t"]; to += d["ok"]; ti += d["inv"]
    print("-" * 78)
    print(f"{'TOTAL':<10} {len(resultados):>7} {tt:>7} {to:>7} "
          f"{(to/tt if tt else 0):>5.0%} {ti:>10}")
    return to, tt


def lista_fallos(resultados, limite=60):
    print("\n" + "=" * 78)
    print("FALLOS — turno a turno (para clasificar: bot mal / expectativa mal / decisión)")
    print("=" * 78)
    n = 0
    for r in resultados:
        for t in r["turnos"]:
            if t["ok"]:
                continue
            n += 1
            if n > limite:
                continue
            motivo = f"esperado «{t['esperado']}» · obtenido «{t['obtenido']}»"
            if t["fallos"]:
                motivo += " · " + "; ".join(t["fallos"])
            print(f"  {r['id']} · turno {t['n']:>2} · {motivo}")
            print(f"       reglas: {t['reglas']}")
            print(f"       cliente: {t['cliente']}")
            print(f"       VendIQ : {' / '.join(t['bot'])}")
        for f in r["fallos_guion"]:
            n += 1
            if n <= limite:
                print(f"  {r['id']} · GUION · {f}")
    if n > limite:
        print(f"  … y {n - limite} más (usa --json para verlos todos)")
    return n


def ver(resultados):
    for r in resultados:
        print("=" * 78)
        print(f"{r['id']} · {r['nombre']}  [{r['tipo']}]"
              f"  {r['turnos_ok']}/{r['n_turnos']} turnos OK")
        print("=" * 78)
        for t in r["turnos"]:
            marca = "OK " if t["ok"] else "XX "
            print(f"\n [{marca}] turno {t['n']} · esperado={t['esperado']} "
                  f"obtenido={t['obtenido']} · {t['decision']} · {t.get('ms')}ms")
            print(f"   CLIENTE: {t['cliente']}")
            for l in t["bot"]:
                print(f"   VENDIQ : {l}")
            print(f"   reglas: {t['reglas']}")
            if t.get("resumen"):
                print(f"   por qué: {t['resumen']}")
            if t["precio"]:
                print(f"   precio: {t['precio']}")
            for f in t["fallos"]:
                print(f"   !!! {f}")
            for f in t.get("coherencia") or []:
                print(f"   !!! C7: {f}")
        for f in r["fallos_guion"]:
            print(f"   !!! GUION: {f}")


def test_aislamiento(sistema, guiones_mod, guiones):
    """Dos guiones intercalados turno a turno = lo mismo que por separado.

    Es lo que garantiza que la persistencia de sesiones no mezcla conversaciones.
    """
    a = next(g for g in guiones if g["id"] == "G01")
    b = next(g for g in guiones if g["id"] == "G13")

    def solo(g, sesion):
        historial = []
        for i, msg in enumerate(g["mensajes"]):
            d = sistema.chatear(sesion, msg, perfil=g["perfil"],
                                nombre=g.get("cliente", ""), reiniciar=(i == 0))
            historial.append(d["bot"]["mensaje"])
        return historial

    ha = solo(a, "banco-guion-aisl-A")
    hb = solo(b, "banco-guion-aisl-B")

    # intercalados en dos sesiones distintas
    ia = {"h": []}
    ib = {"h": []}
    sa, sb = "banco-guion-aisl-iA", "banco-guion-aisl-iB"
    for i in range(max(len(a["mensajes"]), len(b["mensajes"]))):
        if i < len(a["mensajes"]):
            d = sistema.chatear(sa, a["mensajes"][i], perfil=a["perfil"],
                                nombre=a.get("cliente", ""), reiniciar=(i == 0))
            ia["h"].append(d["bot"]["mensaje"])
        if i < len(b["mensajes"]):
            d = sistema.chatear(sb, b["mensajes"][i], perfil=b["perfil"],
                                nombre=b.get("cliente", ""), reiniciar=(i == 0))
            ib["h"].append(d["bot"]["mensaje"])
    ok = (ia["h"] == ha) and (ib["h"] == hb)
    return ok


def main():
    ap = argparse.ArgumentParser(description="Banco de guiones tipo de VendIQ")
    ap.add_argument("--ver", metavar="G13", help="una conversación con su «por qué»")
    ap.add_argument("--json", metavar="RUTA", help="vuelca el detalle completo")
    ap.add_argument("--con-llm", action="store_true", help="enciende Groq (opcional)")
    args = ap.parse_args()

    t0 = time.time()
    sistema = construir_sistema(con_llm=args.con_llm)
    guiones_mod = cargar("12_guiones.py", "guiones")
    try:
        guiones = guiones_mod.construir(sistema)
    except guiones_mod.GuionError as e:
        print(f"ERROR construyendo guiones: {e}")
        return 1

    resultados = ejecutar(sistema, guiones_mod, guiones, ver=args.ver)

    if args.ver:
        ver(resultados)
        return 0

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(resultados, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"detalle en {args.json}")

    ok_t, n_t = tabla(resultados)
    n_fallos = lista_fallos(resultados)
    aisl = test_aislamiento(sistema, guiones_mod, guiones)

    pct = ok_t / n_t if n_t else 0
    fugas = [r["id"] for r in resultados if r["fuga"]]
    pendientes = [r["id"] for r in resultados if r["turnos_ok"] < r["n_turnos"]]
    c7_fallos = [(r["id"], t["n"], t["coherencia"])
                 for r in resultados for t in r["turnos"] if t.get("coherencia")]
    print("\n" + "=" * 78)
    print(f"Turnos OK: {ok_t}/{n_t} ({pct:.0%})  ·  umbral actual {UMBRAL_TURNOS_OK:.0%}")
    print(f"Aislamiento entre sesiones: {'OK' if aisl else 'ROTO'}")
    if c7_fallos:
        print(f"Coherencia del «por qué» (C7): ROTA en {len(c7_fallos)} de {n_t} turnos")
        for gid, n, fs in c7_fallos[:8]:
            print(f"   {gid} · turno {n}: {'; '.join(fs)}")
    else:
        print(f"Coherencia del «por qué» (C7): OK · los {n_t} turnos coinciden con la traza")
    if fugas:
        print(f"FUGA DE PRECIO en: {', '.join(fugas)}")
    print(f"Guiones con algún turno a revisar: {len(pendientes)}")
    print(f"Tiempo total: {time.time() - t0:.0f}s")
    print("=" * 78)

    falla = bool(fugas) or (pct < UMBRAL_TURNOS_OK) or not aisl or bool(c7_fallos)
    print("RESULTADO:", "NO PASA" if falla else "PASA (sin fugas; C7 verde; % por debajo de 95 a la espera de arreglar el bot)")
    return 1 if falla else 0


if __name__ == "__main__":
    sys.exit(main())
