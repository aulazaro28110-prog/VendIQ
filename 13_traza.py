# -*- coding: utf-8 -*-
"""
13_traza.py
===========
La traza del «por qué»: por qué el bot contestó lo que contestó, paso a paso.

NO decide nada. Ensambla en un objeto lo que YA han decidido la búsqueda
(`consultar`), el redactor (`redactar`) y la elección de acción (`elegir_accion`),
más el estado de la conversación antes y después del turno. Cada dato sale del
sitio donde se tomó la decisión —la rama de contexto la etiqueta la propia rama de
`chatear()`, la acción y su porqué los da `elegir_accion()`, las reglas las da el
redactor—; aquí solo se ordena y se pone en palabras. Así el «por qué» no puede
desalinearse de lo que el bot hizo: se construye con los mismos datos.

El `resumen` es una frase DETERMINISTA construida por plantilla (acción × fuente),
nunca escrita por el LLM. Nombra las tres cosas que pide la especificación: qué
hizo el bot, el dato del cliente que lo provocó y la fuente (ficha, política, FAQ,
regla o persona).

Se añade a la respuesta de `/api/chat` sin quitar ni renombrar nada (solo suma la
clave `traza`). El panel la enseña al hacer clic en una burbuja; el banco de
guiones comprueba (C7) que coincide con lo que de verdad hizo el bot.
"""

# El bloque de contexto no se pinta cuando no se completó nada con la memoria,
# pero el paso SÍ viaja siempre con su `rama` ("ninguna" incluida): así el test de
# coherencia (C7) siempre tiene una rama que contrastar con `busqueda.contexto`.
RAMAS = ("ninguna", "correccion_coche", "coche_de_memoria", "pieza_de_memoria",
         "pieza_referida", "matricula_desbloquea")

# El dato del cliente que disparó el turno, por intención. Frases cortas y en
# segunda persona, para el resumen. Si la intención no está aquí, el resumen cae a
# nombrar la pieza/el texto, que siempre existe.
_DATO = {
    "plazo": "preguntaste cuánto tarda",
    "envio": "preguntaste por el envío",
    "garantia": "preguntaste por la garantía",
    "devolucion": "preguntaste si se puede devolver",
    "pago": "preguntaste cómo se paga",
    "precio otra vez": "volviste a preguntar el precio",
    "kilometros": "preguntaste los kilómetros",
    "estado": "preguntaste por el estado de la pieza",
    "compatibilidad": "preguntaste si encaja",
    "regateo": "intentaste negociar el precio",
    "pide sin pagar": "pediste pagar al recibir",
    "justificante": "pediste algo sobre la factura",
    "queja": "pusiste una queja",
    "saludo": "saludaste",
    "agradecimiento": "diste las gracias",
    "despedida": "te despediste",
    "cierre": "dijiste que sí",
    "aparca": "dijiste que lo dejabas de momento",
    "prisa": "dijiste que corría prisa",
    "recapitula": "pediste un resumen",
    "recuerda mi dato": "preguntaste por un dato que ya habías dado",
    "enlace": "pediste un enlace o la dirección",
    "seguimiento": "seguiste con la misma pieza",
}

# Reglas del redactor que significan «aún no puedo buscar: identifícame el coche».
# Cuando alguna sale, el bot ha PEDIDO datos, no citado una política —aunque entre
# los candidatos de la búsqueda asome una FAQ—. Nombres exactos de 07_redactor.py.
_PIDE_DATOS = {
    "faltan datos para buscar",
    "identificar antes de decir que sí o que no",
    "un dato por mensaje",
    "la matrícula va primero",
}


def _titulo(resultado):
    """Un título corto y legible de un resultado de búsqueda."""
    if not resultado:
        return None
    meta = resultado.get("meta") or {}
    if resultado.get("tipo") == "inventario":
        partes = [meta.get("pieza"), meta.get("marca"), meta.get("modelo")]
        titulo = " ".join(str(p) for p in partes if p)
        return titulo or (resultado.get("texto") or "")[:50]
    # Política o FAQ: el título suele ser lo primero del texto, en mayúsculas.
    texto = (resultado.get("texto") or "").strip()
    cabeza = texto.split(".")[0].split("\n")[0].strip()
    return (cabeza or texto)[:50]


def _mejor(busqueda):
    """La ficha/política que ganó, o el mejor descartado si no ganó ninguna."""
    res = busqueda.get("resultados") or []
    if res:
        return res[0]
    desc = busqueda.get("descartados") or []
    return desc[0] if desc else None


def _umbral_de(resultado, umbrales):
    if not resultado:
        return umbrales.get("inventario", 0.50)
    return umbrales.get(resultado.get("tipo"), umbrales.get("inventario", 0.50))


def _dato_cliente(entrada, mejor_titulo):
    """La frase del dato del cliente que provocó el turno."""
    if entrada.get("matricula_en_mensaje"):
        return f"diste la matrícula ({entrada['matricula_en_mensaje']})"
    intn = entrada.get("intencion")
    if intn in _DATO:
        return _DATO[intn]
    if entrada.get("habla_de_pieza") and mejor_titulo:
        return f"preguntaste por {mejor_titulo.lower()}"
    if entrada.get("coche_en_mensaje"):
        return f"nombraste el {entrada['coche_en_mensaje']}"
    return "lo preguntaste"


def _resumen(accion, busqueda, respuesta, entrada, mejor, mejor_titulo,
             score, umbral, publicable, precio):
    """Una frase cierta que nombra: qué hizo, el dato del cliente y la fuente.

    El caso RESPONDER mira primero las REGLAS del redactor (son un paso de la
    traza), no solo el mejor resultado de la búsqueda: así «te ha pedido la
    matrícula» no se confunde con «ha citado una política» por que entre los
    candidatos asome una FAQ suelta. No re-deduce nada: elige entre plantillas
    ciertas según lo que el redactor ya decidió.
    """
    decision = busqueda.get("decision")
    dato = _dato_cliente(entrada, mejor_titulo)
    reglas = {r.get("regla") for r in respuesta.get("reglas", [])}
    de_persona = "respuesta escrita por una persona" in reglas
    # Lo ACEPTADO (lo que de verdad se ofreció), no el mejor candidato a secas: con
    # la decisión ESCALA/NO DISPONIBLE no hay nada aceptado y el «mejor» es un
    # descartado bajo umbral que NO se citó.
    aceptados = busqueda.get("resultados") or []
    tipo_acc = aceptados[0].get("tipo") if aceptados else None
    titulo_acc = _titulo(aceptados[0]) if aceptados else mejor_titulo
    confianza = (f" ({score:.2f} >= {umbral:.2f})"
                 if score is not None and score >= (umbral or 0) else "")

    if accion == "ESCALAR":
        return f"Lo ha pasado a una persona porque {dato}: lo ve Álvaro."

    if accion == "PREGUNTAR":
        opts = (respuesta.get("opciones") or {}).get("opciones") or []
        return (f"Te ha preguntado cuál de las {len(opts)} piezas que encajan "
                f"porque {dato} y falta un dato para elegir sin adivinar.")

    # RESPONDER
    if de_persona:
        return (f"Te ha contestado con una respuesta escrita por una persona "
                f"porque {dato}: se dice tal cual, sin pasarla por el modelo.")
    if "cierre de venta" in reglas:
        return (f"Te ha cerrado la venta y te la aparta a tu nombre porque {dato}; "
                f"antes de salir confirma que encaja con tu coche.")
    if precio:
        return (f"Te ha dado el precio ({precio}) de {titulo_acc} porque {dato} "
                f"y esa ficha del catálogo supera el umbral de confianza{confianza}.")
    if reglas & _PIDE_DATOS:
        return (f"Te ha pedido la matrícula para identificar la pieza porque {dato}: "
                f"sin saber el coche no puede confirmar cuál monta.")
    if decision == "NO DISPONIBLE" or "no se ofrece una parecida" in reglas:
        falla = (f" (el mejor candidato se queda en {score:.2f}, por debajo de "
                 f"{umbral:.2f})" if score is not None else "")
        busca = ("; se ofrece a buscártela con la matrícula"
                 if "no se ofrece una parecida" in reglas else "")
        return (f"Te ha dicho que esa pieza no la tiene{falla}{busca}, porque {dato}.")
    if tipo_acc == "inventario":
        return (f"Te ha confirmado {titulo_acc} pero ha retenido el precio "
                f"porque {dato} y aún no está identificado el coche "
                f"(falta la matrícula).")
    if tipo_acc == "politica":
        return (f"Te ha contestado con la política «{titulo_acc}» porque {dato}; "
                f"la política lo cubre{confianza}.")
    if "memoria de conversación" in reglas:
        return (f"Te ha respondido con lo que ya habíais hablado, sin repetir la "
                f"ficha, porque {dato}.")
    return f"Te ha contestado porque {dato}."


def construir(*, mensaje, entrada, contexto, busqueda, respuesta,
              accion, porque_accion, coche_identificado,
              memoria_antes, memoria_despues, umbrales, umbral_precio,
              auditorias=None, texto_modelo=None):
    """Monta la traza de un turno. Argumentos, todos ya decididos en su sitio:

    - `entrada`: {habla_de_pieza, coche_en_mensaje, matricula_en_mensaje, intencion}
    - `contexto`: {rama, texto_buscado, por_que} tal como la etiquetó la rama de
      `chatear()` que completó (o no) con la memoria.
    - `busqueda`: lo que devolvió `consultar()` (decision, resultados, ms…).
    - `respuesta`: lo que devolvió `redactar()` + lo que añadió `chatear()`.
    - `accion`/`porque_accion`: lo que devolvió `elegir_accion()`.
    - `memoria_antes`/`memoria_despues`: el estado de la conversación.
    - `auditorias`/`texto_modelo`: solo cuando ha redactado el LLM (si no, vacío).
    """
    resultados = busqueda.get("resultados") or []
    mejor = _mejor(busqueda)
    mejor_titulo = _titulo(mejor)
    score = mejor.get("puntuacion") if mejor else None
    umbral = _umbral_de(mejor, umbrales)

    fichas = [r for r in resultados if r.get("tipo") == "inventario"]
    mejor_ficha = fichas[0] if fichas else None
    pc = (mejor_ficha.get("precio_cliente") or {}) if mejor_ficha else {}
    publicable = bool(pc.get("publicable"))
    precio_dado = respuesta.get("precio_dado")

    # ---- 1. ENTRADA: qué ha leído del mensaje ------------------------------
    pasos = [{
        "paso": "entrada", "estado": "info", "titulo": "Qué ha leído",
        "datos": {
            "habla_de_pieza": bool(entrada.get("habla_de_pieza")),
            "coche_en_mensaje": entrada.get("coche_en_mensaje") or None,
            "matricula_en_mensaje": entrada.get("matricula_en_mensaje") or None,
            "intencion": entrada.get("intencion"),
        },
    }]

    # ---- 2. CONTEXTO: qué ha completado con la memoria ---------------------
    # Viaja siempre (también "ninguna"); el panel no lo pinta cuando es "ninguna".
    pasos.append({
        "paso": "contexto", "estado": "info",
        "titulo": "Qué ha completado con la memoria",
        "rama": contexto.get("rama", "ninguna"),
        "texto_buscado": contexto.get("texto_buscado") or mensaje,
        "por_que": contexto.get("por_que") or "",
    })

    # ---- 3. BÚSQUEDA: qué ha encontrado ------------------------------------
    decision = busqueda.get("decision")
    estado_busq = {"RESPONDE": "ok", "NO DISPONIBLE": "aviso",
                   "ESCALA": "bloqueo"}.get(decision, "info")
    pasos.append({
        "paso": "busqueda", "estado": estado_busq, "titulo": "Qué ha encontrado",
        "decision": decision,
        "mejor": ({"tipo": mejor.get("tipo"), "titulo": mejor_titulo,
                   "puntuacion": score, "umbral": umbral} if mejor else None),
        "candidatos": len(resultados) + len(busqueda.get("descartados") or []),
        "ms": busqueda.get("ms"),
    })

    # ---- 4. PRECIO ---------------------------------------------------------
    if not mejor_ficha:
        estado_precio, motivo = "no_aplica", "no hay ficha de inventario que ofrecer"
    elif publicable:
        estado_precio = "ok"
        motivo = pc.get("motivo") or "la ficha está identificada y autorizada"
    else:
        estado_precio = "bloqueo"
        motivo = pc.get("motivo") or "sin identificar el coche no se publica el precio"
    pasos.append({
        "paso": "precio", "estado": estado_precio, "titulo": "Precio",
        "publicable": publicable if mejor_ficha else None,
        "motivo": motivo, "umbral_precio": umbral_precio,
        "coche_identificado": bool(coche_identificado),
    })

    # ---- 5. REGLAS DEL REDACTOR --------------------------------------------
    pasos.append({
        "paso": "reglas", "estado": "info", "titulo": "Reglas del redactor",
        "reglas": list(respuesta.get("reglas") or []),
    })

    # ---- 6. ACCIÓN ---------------------------------------------------------
    pasos.append({
        "paso": "accion", "estado": ("aviso" if accion == "ESCALAR" else "ok"),
        "titulo": "Decisión", "accion": accion, "por_que": porque_accion,
    })

    # ---- 7. REDACCIÓN: quién lo ha escrito ---------------------------------
    nota = respuesta.get("redactor") or ""
    if "una persona" in nota:
        redactor = "persona"
    elif respuesta.get("llm_descartado"):
        redactor = "determinista"      # el modelo escribió, pero se descartó
    elif respuesta.get("borrador"):
        redactor = "modelo"
    else:
        redactor = "determinista"
    paso_red = {
        "paso": "redaccion",
        "estado": ("aviso" if respuesta.get("llm_descartado") else "ok"),
        "titulo": "Quién lo ha escrito", "redactor": redactor,
        "auditorias": list(auditorias or []),
        "nota": nota,
        "texto_enviado": respuesta.get("mensaje"),
    }
    if texto_modelo:
        paso_red["texto_modelo"] = texto_modelo
    pasos.append(paso_red)

    # ---- 8. MEMORIA: qué recuerda ahora ------------------------------------
    cambios = [k for k in memoria_despues
               if memoria_antes.get(k) != memoria_despues.get(k)]
    pasos.append({
        "paso": "memoria", "estado": "info", "titulo": "Qué recuerda ahora",
        "antes": memoria_antes, "despues": memoria_despues, "cambios": cambios,
    })

    resumen = _resumen(accion, busqueda, respuesta, entrada, mejor, mejor_titulo,
                       score, umbral, publicable, precio_dado)
    return {"resumen": resumen, "pasos": pasos}


# Nombres de los pasos, para que el test de coherencia y el panel los busquen sin
# depender del orden.
def paso(traza, nombre):
    for p in (traza or {}).get("pasos", []):
        if p.get("paso") == nombre:
            return p
    return None
