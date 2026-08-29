# -*- coding: utf-8 -*-
"""
tests/test_prompt.py
====================
EL PROMPT DE docs/Prompt_Agente_Conversacional.md, COMPROBADO.

    py tests/test_prompt.py

Ese documento son 41 secciones de como tiene que comunicarse el bot. Un
documento asi no sirve de nada si nadie comprueba que se cumple: cada seccion
que se pueda medir se convierte aqui en una conversacion concreta, y se mira lo
que sale.

La primera pasada dio 5 de 12. Lo que fallaba no era menor: "precio" a secas se
contestaba con "sin prisa, lo dejo apuntado por si acaso", un sintoma ("cuando
freno hace un ruido metalico") acababa en la politica de garantia, y el bot
decia "lo aparto a tu nombre" sin apartar nada en ningun sitio.

No estan las 41 porque no todas se pueden medir asi -- "personalidad", "venta
consultiva" o "no manipules al cliente" no se comprueban con una expresion
regular. Las que estan, se comprueban de verdad.
"""
import sys, re, importlib.util, pathlib

sys.argv = ['x']
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


def cargar(f, alias):
    spec = importlib.util.spec_from_file_location(alias, BASE / f)
    m = importlib.util.module_from_spec(spec); sys.modules[alias] = m
    spec.loader.exec_module(m); return m


panel = cargar('06_panel.py', 'panel')
S = panel.Sistema()
S.config_llm = dict(S.config_llm, GROQ_API_KEY="")   # el redactor propio

n = [0]
resultados = []


def probar(seccion, titulo, guion, espera, comprueba):
    """espera: lo que deberia hacer. comprueba: fn(ultimo_mensaje, conv) -> bool"""
    n[0] += 1
    sid = f"aud{n[0]}"
    for i, m in enumerate(guion):
        d = S.chatear(sid, m, perfil="nuevo", reiniciar=(i == 0))
    conv = S.chats[sid]
    ok = comprueba(d["bot"]["mensaje"], conv)
    print(f"{'CUMPLE  ' if ok else 'NO CUMPLE'} §{seccion:<3} {titulo}")
    if not ok:
        print(f"           cliente: {guion[-1]}")
        for l in d["bot"]["lineas"]:
            print(f"           VENDIQ : {l}")
        print(f"           esperado: {espera}")
    resultados.append(ok)
    return ok


print("=" * 90)
print("EL PROMPT DE COMUNICACION, SECCION A SECCION")
print("=" * 90)

probar("3", "no repregunta un dato ya dado",
       ["necesito un alternador para un audi a4", "4521 KBD", "cuanto vale"],
       "no vuelve a pedir la matricula",
       lambda m, c: not re.search(r"p[aá]same la matr|necesito la matr", m, re.I))

probar("4", "detecta una contradiccion y pregunta cual vale",
       ["necesito un alternador para un audi a4", "4521 KBD",
        "perdona, no es un a4, es un a3"],
       "avisa del cambio o rehace la busqueda con el A3",
       lambda m, c: "a3" in m.lower() or "antes" in m.lower())

probar("6", "distingue confirmado de probable",
       ["tienes un alternador para un audi a4", "4521 KBD", "seguro que encaja?"],
       "no afirma compatibilidad con certeza",
       lambda m, c: not re.search(r"seguro que (encaja|vale)|te vale seguro", m, re.I))

probar("18", "el cliente corrige un dato",
       ["necesito un alternador para un seat leon 2.0 tdi", "4521 KBD",
        "no, es gasolina, no diesel"],
       "reconoce la correccion y rehace",
       lambda m, c: re.search(r"gasolina|entonces|cambia", m, re.I) is not None)

# DIAGNOSTICAR = False (07_redactor.py). Esta comprobacion pedia que el bot
# contestara "pastillas" o "discos" a un ruido al frenar, y eso es exactamente lo
# que la decision de negocio marco como el error a corregir: son consumibles de
# mecanica rapida y este desguace no los vende ni los va a vender. El test se
# habia quedado anclado al rol viejo y suspendia al codigo por hacer lo correcto.
# Lo que se mide ahora es la decision de verdad: quien decide que hay que cambiar
# en un coche es el taller, que lo tiene en un elevador, no un asistente leyendo
# "hace un ruido raro". El bot lo dice y reconduce al dato que si puede usar.
probar("20", "describe un sintoma, no sabe la pieza",
       ["cuando freno hace un ruido metalico"],
       "no diagnostica: lo manda al taller y pide la pieza",
       lambda m, c: (re.search(r"taller|qu[eé] pieza|matr[ií]cula", m, re.I)
                     and not re.search(r"pastilla|disco", m, re.I)))

import json as _json
probar("23", "lo que dice que hace, lo hace",
       ["necesito un alternador para un audi a4", "4521 KBD", "me lo quedo"],
       "si dice que lo aparta, tiene que quedar escrito en salida/reservas.json",
       lambda m, c: (not re.search(r"aparto a tu nombre", m, re.I)) or any(
           r.get("matricula") == c.matricula and r.get("pieza")
           for r in _json.loads(
               (BASE / "salida" / "reservas.json").read_text(encoding="utf-8"))))

probar("24", "da el enlace del producto si se lo piden",
       ["necesito un alternador para un audi a4", "4521 KBD", "pasame el link"],
       "da la url de la ficha, que esta en el catalogo",
       lambda m, c: "http" in m.lower())

probar("29", "varios mensajes seguidos, una sola intencion",
       ["necesito un alternador", "es para un audi a4", "4521 KBD"],
       "no contesta tres veces lo mismo",
       lambda m, c: bool(c.ultima_pieza))

probar("30", "resume el contexto en conversacion larga",
       ["necesito un alternador para un audi a4", "4521 KBD", "y de garantia?",
        "y el envio?", "y el iva?", "a ver, que teniamos"],
       "recapitula coche + pieza + precio",
       lambda m, c: sum(x in m.lower() for x in ("a4", "alternador", "195")) >= 2)

probar("33", "listo para comprar: facilita el paso",
       ["necesito un alternador para un audi a4", "4521 KBD", "la quiero"],
       "no sigue preguntando, facilita la compra",
       lambda m, c: c.estado in ("cerrada", "posventa"))

probar("35", "una sola pregunta por mensaje",
       ["hola", "necesito un alternador"],
       "como mucho un signo de interrogacion de cierre",
       lambda m, c: m.count("?") <= 1)

probar("19", "cliente impaciente: responde directo",
       ["necesito un alternador para un audi a4", "4521 KBD", "precio"],
       "da el precio sin rodeos",
       lambda m, c: "195" in m)

print()
print("=" * 90)

fallan = [x for x in resultados if not x]
print(f"{len(resultados) - len(fallan)}/{len(resultados)} secciones cumplidas")
print("=" * 90)
sys.exit(1 if fallan else 0)
