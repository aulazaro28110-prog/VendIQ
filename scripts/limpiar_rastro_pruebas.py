"""Enseña (y SOLO con --borrar, quita) el rastro de las sesiones de PRUEBA en los
datos de negocio: reservas y dudas que dejaron el banco, el simulador, los guiones,
el estrés y el diagnóstico, y que no son de ningún cliente (D4).

Por defecto SIMULA: no toca nada. Borrar datos de `salida/` es decisión de Álvaro,
así que hay que pedírselo con --borrar (y aun así hace una copia .bak antes).

    py scripts/limpiar_rastro_pruebas.py            # simula (por defecto)
    py scripts/limpiar_rastro_pruebas.py --borrar   # quita de verdad, con copia .bak

La lista de prefijos de prueba NO se escribe aquí: se lee de `Sistema.es_prueba`,
para que haya una sola definición (la misma que usa el panel al no escribir).
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def cargar(fichero, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / fichero)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


panel = cargar("06_panel.py", "panel")      # solo para la lista de prefijos
es_prueba = panel.Sistema.es_prueba

FICHEROS = [BASE / "salida" / "reservas.json",
            BASE / "salida" / "no_resueltas.json"]


def sesion_de(entrada):
    if not isinstance(entrada, dict):
        return ""
    return entrada.get("sesion") or entrada.get("session") or entrada.get("id") or ""


def main():
    # La consola de Windows es cp1252 y alguna duda de cliente lleva un emoji
    # (p. ej. 👍): sin esto, imprimir el rastro revienta con UnicodeEncodeError.
    # Forzamos UTF-8 en la salida (errors=replace por si el terminal aún no puede).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    borrar = "--borrar" in sys.argv
    print("=" * 74)
    print("LIMPIAR RASTRO DE PRUEBAS  ·  MODO:",
          "BORRAR DE VERDAD" if borrar else "SIMULACION (no toca nada)")
    print("prefijos de prueba:", ", ".join(panel.Sistema.PREFIJOS_PRUEBA),
          "  (panel- NO se toca: es el cliente de prueba de Álvaro)")
    print("=" * 74)
    total_prueba = 0
    for f in FICHEROS:
        if not f.exists():
            print(f"\n  {f.name}: no existe")
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"\n  {f.name}: no se puede leer ({e})")
            continue
        if not isinstance(data, list):
            print(f"\n  {f.name}: no es una lista, lo salto")
            continue
        prueba = [e for e in data if es_prueba(sesion_de(e))]
        quedan = [e for e in data if not es_prueba(sesion_de(e))]
        total_prueba += len(prueba)
        print(f"\n  {f.name}: {len(data)} entradas · {len(prueba)} de prueba · "
              f"quedarían {len(quedan)}")
        for e in prueba[:60]:
            etiqueta = e.get("pieza") or str(e.get("pregunta", ""))[:40]
            print(f"     - {sesion_de(e)!r:16} {etiqueta!r}")
        if borrar and prueba:
            shutil.copy2(f, f.with_suffix(".json.bak"))
            f.write_text(json.dumps(quedan, ensure_ascii=False, indent=2),
                         encoding="utf-8")
            print(f"     -> quitadas {len(prueba)}; copia de seguridad en {f.name}.bak")
    print()
    if borrar:
        print(f"  Hecho. Quitadas {total_prueba} entradas de prueba (con copia .bak).")
    else:
        print(f"  Se quitarían {total_prueba} entradas de prueba. Nada tocado.")
        print("  Para quitarlo de verdad: --borrar (hará copia .bak antes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
