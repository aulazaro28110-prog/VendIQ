# -*- coding: utf-8 -*-
"""
scripts/probar_groq.py
======================
¿Está bien la clave de Groq? Se ejecuta y te lo dice, sin enseñar la clave.

    py scripts/probar_groq.py

Existe porque diagnosticar esto a ojo sale caro. En la primera conexión real se
perdió un buen rato entre un 403 que no era la clave (era el User-Agent: Groq
está detrás de Cloudflare) y un mensaje vacío que tampoco era la clave (el modelo
se gastaba el presupuesto entero razonando). Esto separa las tres preguntas:

    1. ¿está la clave en el .env y con qué pinta?
    2. ¿la acepta Groq?
    3. ¿existe el modelo que le estamos pidiendo, y contesta?

Nunca imprime la clave entera: solo los cuatro primeros y los cuatro últimos
caracteres, que es lo justo para saber CUÁL de tus claves es la que hay puesta.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ENV = BASE / ".env"
URL = "https://api.groq.com/openai/v1"
AGENTE = "VendIQ/1.0 (+https://github.com/)"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def leer_env():
    valores = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def llamar(ruta, clave, cuerpo=None):
    peticion = urllib.request.Request(
        f"{URL}/{ruta}",
        data=json.dumps(cuerpo).encode("utf-8") if cuerpo else None,
        headers={"Authorization": f"Bearer {clave}",
                 "Content-Type": "application/json",
                 "User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(peticion, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo_error = e.read().decode("utf-8", "replace")
        try:
            cuerpo_error = json.loads(cuerpo_error)["error"]["message"]
        except Exception:
            pass
        return e.code, cuerpo_error
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def main():
    config = leer_env()
    clave = config.get("GROQ_API_KEY", "")
    modelo = config.get("GROQ_MODELO") or "openai/gpt-oss-120b"

    print("1. LA CLAVE EN .env")
    if not ENV.exists():
        print("   no existe el fichero .env. Copia .env.ejemplo y pega la clave.")
        return 1
    if not clave:
        print("   la línea GROQ_API_KEY está vacía. Pega la clave detrás del =.")
        return 1
    print(f"   {len(clave)} caracteres · {clave[:4]}...{clave[-4:]}")
    if not clave.startswith("gsk_"):
        print("   AVISO: las claves de Groq empiezan por 'gsk_'. ¿Se copió entera?")
    print()

    print("2. ¿LA ACEPTA GROQ?")
    estado, datos = llamar("models", clave)
    if estado != 200:
        print(f"   NO. {estado} · {datos}")
        if estado == 401:
            print("   Esa clave no vale. Puede estar borrada en la consola, o")
            print("   copiada a medias. Mira console.groq.com/keys: la que uses")
            print("   tiene que aparecer ahí en la lista.")
        elif estado == 403:
            print("   403 suele ser Cloudflare, no la clave. Comprueba que se")
            print("   manda un User-Agent propio en la petición.")
        return 1
    vivos = sorted(m["id"] for m in datos["data"])
    print(f"   SÍ · {len(vivos)} modelos disponibles")
    print()

    print("3. ¿EXISTE EL MODELO Y CONTESTA?")
    print(f"   pedido: {modelo}")
    if modelo not in vivos:
        print("   NO ESTÁ en la lista. Groq retira modelos cada pocos meses.")
        print("   Disponibles ahora:")
        for m in vivos:
            print(f"     {m}")
        return 1
    inicio = time.time()
    estado, datos = llamar("chat/completions", clave, {
        "model": modelo,
        "messages": [{"role": "user",
                      "content": "Responde solo con la palabra: listo"}],
        "max_tokens": 600,
        "reasoning_effort": "low",
    })
    if estado != 200:
        print(f"   NO. {estado} · {datos}")
        return 1
    eleccion = datos["choices"][0]
    texto = (eleccion["message"].get("content") or "").strip()
    uso = datos.get("usage", {})
    pensados = uso.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    print(f"   SÍ · {(time.time() - inicio) * 1000:.0f} ms · "
          f"{uso.get('completion_tokens', 0)} tokens ({pensados} de pensar)")
    print(f"   contestó: {texto!r}")
    if not texto and eleccion.get("finish_reason") == "length":
        print("   ...pero vacío: se quedó sin presupuesto razonando. Sube")
        print("   TOPE_RESPUESTA o baja ESFUERZO en 08_conversar.py.")
        return 1
    print()
    print("TODO BIEN. Arranca el panel:  py 06_panel.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
