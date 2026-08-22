"""
diag_canarias.py — ¿por qué "envias a canarias?" escala en vez de responder?
Mide la PUNTUACIÓN real de la política de envío para varias formas de la misma
pregunta. Uso:   py scripts/diag_canarias.py
"""
import importlib.util
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("buscar", BASE / "03_buscar.py")
buscar = importlib.util.module_from_spec(spec); spec.loader.exec_module(buscar)
b = buscar.cargar_buscador()

UMBRAL = buscar.UMBRAL_POLITICA
frases = [
    "¿enviáis a Canarias?",        # la forma que SÍ mediste
    "envias a canarias",           # la forma sucia que guarda el registro
    "mandais a canarias?",
    "hacéis envíos a canarias",
]
print(f"\nUMBRAL_POLITICA = {UMBRAL}\n" + "="*60)
for f in frases:
    pieza = b._habla_de_pieza(f)
    print(f"\n> {f!r}   (_habla_de_pieza={pieza}  -> solo_politicas={not pieza})")
    crudos = b.buscar(f, k=6, aplicar_umbral=False)
    for s, it in crudos:
        marca = ""
        if it["tipo"] == "politica":
            sec = (it.get("meta") or {}).get("seccion", "?")
            ok = "PASA" if s >= UMBRAL else "NO llega"
            marca = f"  <-- POLITICA «{sec}»  [{ok} el umbral {UMBRAL}]"
        etq = it.get("meta", {}).get("seccion") or it.get("meta", {}).get("pieza") or it["tipo"]
        print(f"    {s:6.3f}  {it['tipo']:10} {etq}{marca}")
print("\n" + "="*60)
print("Si la POLITICA «ENVIO Y PLAZOS» sale por debajo del umbral en la")
print("forma sucia, ese es el fallo. Pégame esta salida y lo arreglamos con dato.")
