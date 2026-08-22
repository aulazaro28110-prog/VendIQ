"""
08_conversar.py
===============
EL BUCLE DE CONVERSACIÓN. Fase 1 de docs/VendIQ_Spec_Conversacion.md.

En cada turno el asistente elige UNA de tres acciones:

    RESPONDER  — contesta; si es una condición (pago, IVA, garantía, envío),
                 cita la política de la que sale.
    PREGUNTAR  — hay ambigüedad real: lanza 2-4 botones sacados de las piezas
                 candidatas de verdad, nunca inventados.
    ESCALAR    — no tiene la pieza o no está seguro: lo dice, avisa a una
                 persona y guarda la pregunta en el registro de no resueltas.

QUIÉN DECIDE QUÉ (esto es lo importante)
----------------------------------------
La acción la decide el CÓDIGO, no el modelo. El LLM solo redacta dentro de la
acción ya elegida, y solo con los datos que se le pasan.

Podría dejarse elegir al modelo y escribiría mensajes más naturales. No se hace
por una razón concreta: si el modelo decide, los guardarraíles solo se pueden
comprobar por estadística — "de 100 pruebas no dio ningún precio malo". Como
están, se comprueban por construcción: **al modelo no se le pasa el precio si la
búsqueda no lo ha autorizado**, así que no puede decirlo aunque quiera. Es la
misma propiedad que ya tenía 07_redactor.py y no se pierde al meter el LLM.

SIN CLAVE DE API SIGUE FUNCIONANDO
----------------------------------
Si no hay GROQ_API_KEY, redacta 07_redactor.py y todo lo demás es idéntico: las
mismas acciones, los mismos botones, el mismo registro. El LLM mejora cómo suena,
no lo que se puede decir.
"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
ENV = BASE / ".env"

MODELO_POR_DEFECTO = "openai/gpt-oss-120b"  # llama-3.3-70b lo apagó Groq el 16/08/26
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
TIEMPO_MAXIMO = 12          # segundos; si tarda más, se responde sin LLM

# Cómo se presenta VendIQ ante la API. Ver el comentario de la petición: no es
# cortesía, es que sin esto Cloudflare devuelve 403.
AGENTE = "VendIQ/1.0 (+https://github.com/)"

# Presupuesto de la respuesta. Parece mucho para un mensaje de dos líneas, y lo
# es: la mayor parte no se gasta en el mensaje. Los modelos que razonan cuentan
# los tokens de pensar contra este mismo tope, y con 220 —el número que venía de
# llama-3.3-70b, que no razona— se gastaban 218 pensando y devolvían el mensaje
# vacío. Las diez primeras conversaciones reales salieron todas del redactor
# determinista sin que nada fallara aparentemente.
TOPE_RESPUESTA = 600

# Y sobre todo: que piense poco. Aquí no hay nada que razonar — la acción ya está
# decidida, los datos vienen dados y el modelo solo pone la forma. Medido sobre
# cinco preguntas: 45 tokens de pensar en vez de 228, y 528 ms en vez de 1290.
ESFUERZO = "low"

# Máximo de preguntas de aclaración por conversación (regla del diseño). A la
# tercera ya no estás aclarando, estás interrogando.
TOPE_ACLARACIONES = 2

# Turnos que se le pasan al modelo tal cual. Lo anterior no se tira: se resume.
VENTANA_TURNOS = 6


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

def leer_env() -> dict:
    """Lee .env sin dependencias. El fichero NO se sube a git (.gitignore)."""
    valores = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip('"').strip("'")
    # Una variable de entorno de verdad manda sobre el fichero.
    for clave in ("GROQ_API_KEY", "GROQ_MODELO"):
        if os.environ.get(clave):
            valores[clave] = os.environ[clave]
    return valores


def hay_llm() -> bool:
    return bool(leer_env().get("GROQ_API_KEY"))


# ---------------------------------------------------------------------------
# PREGUNTAS CON BOTONES  (idea 6 de la especificación)
# ---------------------------------------------------------------------------
# Los botones salen SIEMPRE de las fichas que la búsqueda ha devuelto. Nunca se
# inventa una opción: si el botón dice "Faro delantero izquierdo" es porque esa
# pieza existe en el catálogo con ese nombre exacto.
#
# Y solo se pregunta cuando hace falta de verdad. Un bot que pregunta en cada
# turno cansa más que uno que se equivoca: la regla es preguntar cuando hay dos
# o más candidatas que se distinguen en UN dato, y ese dato es el que falta.

CAMPOS_DESAMBIGUAR = [
    ("pieza",  "¿Cuál de estas necesitas?"),
    ("modelo", "¿Qué modelo es exactamente?"),
    ("motor",  "¿Qué motor monta?"),
    ("anio",   "¿De qué año es?"),
]


def opciones_desambiguacion(busqueda, maximo=4):
    """Devuelve {'pregunta': str, 'campo': str, 'opciones': [...]} o None.

    Se usa cuando el precio se ha retenido porque el cliente no ha nombrado la
    pieza entera: en vez de dejarlo en "dime cuál", se le dan las que hay.
    """
    piezas = [r for r in (busqueda.get("resultados") or [])
              if r.get("tipo") == "inventario" and r.get("meta")]
    if len(piezas) < 2:
        return None

    for campo, pregunta in CAMPOS_DESAMBIGUAR:
        vistos, opciones = set(), []
        for r in piezas:
            valor = (r["meta"].get(campo) or "").strip()
            if not valor or valor in vistos:
                continue
            vistos.add(valor)
            opciones.append({
                "texto": valor,
                # Lo que se manda al bot al pulsar: el mensaje que habría escrito
                # el cliente. Así el botón no es una vía paralela con reglas
                # propias — entra por la misma puerta que el texto libre.
                "envia": valor,
                "id_pieza": r["meta"].get("id", ""),
            })
        if 2 <= len(opciones) <= maximo:
            return {"pregunta": pregunta, "campo": campo, "opciones": opciones}
    return None


# ---------------------------------------------------------------------------
# LA ACCIÓN DEL TURNO
# ---------------------------------------------------------------------------

def elegir_accion(busqueda, respuesta, opciones, aclaraciones=0):
    """RESPONDER / PREGUNTAR / ESCALAR, y por qué.

    Se decide sobre lo que ya han dicho la búsqueda y el redactor. No hay ninguna
    señal nueva: esto es el nombre de lo que el sistema ya estaba haciendo, que
    es justo lo que pedía la especificación.
    """
    reglas = " · ".join(r["regla"] for r in respuesta.get("reglas", []))

    if respuesta.get("escala"):
        return "ESCALAR", "lo ve una persona: " + (
            "es una decisión de negocio" if "condición de la empresa" in reglas
            or "escalado a persona" in reglas else "el bot no está seguro")

    # Solo se pregunta si el precio se ha quedado retenido por falta de datos Y
    # existen opciones reales que lo desbloquean. Preguntar por preguntar, no.
    if opciones and "precio retenido" in reglas:
        # ...y como mucho dos veces. Si dos intentos no han bastado para decidir,
        # adivinar sale más caro que molestar a una persona.
        if aclaraciones >= TOPE_ACLARACIONES:
            return "ESCALAR", (f"ya se ha preguntado {aclaraciones} veces y sigue "
                               f"sin poder decidir: lo ve una persona en vez de "
                               f"seguir preguntando")
        return "PREGUNTAR", (f"hay {len(opciones['opciones'])} piezas que encajan "
                             f"con lo que ha dicho: se pregunta cuál en vez de "
                             f"adivinar")

    if "política de la empresa" in reglas:
        return "RESPONDER", "contesta citando la política de la empresa"
    return "RESPONDER", "contesta con las fichas del catálogo"


# ---------------------------------------------------------------------------
# EL LLM  (solo redacta; los hechos vienen dados)
# ---------------------------------------------------------------------------

ROL = """Eres el asistente de Desguaces Madrid Norte, desguace de Alcobendas (Madrid).
Escribes por WhatsApp a profesionales del motor y talleres.

CÓMO ESCRIBES (esto no se negocia):
- Tuteas SIEMPRE, también a clientes nuevos.
- De 1 a 3 líneas cortas. Sin firma, sin emojis, sin asunto.
- Cercano y comercial, de profesional a profesional. Al grano, sin explicar lo obvio.
- La empresa habla en plural ("lo hemos desmontado") y tú en singular ("te lo consigo").
- Terminas moviendo la venta: una pregunta, nunca un punto final.

LO QUE NO PUEDES HACER NUNCA:
- No digas ningún precio que no esté en los DATOS de abajo. Si ahí no hay precio,
  no hay precio: di que lo confirmas.
- No inventes piezas, plazos, referencias ni condiciones que no estén en los DATOS.
- No asegures que una pieza encaja: eso lo confirma una persona con la matrícula.
- No aceptes enviar nada sin pago confirmado, ni des por válido un justificante.

Te doy la ACCIÓN ya decidida y los DATOS. Escribe SOLO el mensaje al cliente."""


# Matrícula española (moderna y antigua) y bastidor. Es la misma detección que
# hace 07_redactor.py; aquí se usa para lo contrario: para quitarla.
_MATRICULA = re.compile(
    r"\b\d{4}\s?[BCDFGHJKLMNPRSTVWXYZ]{3}\b"
    r"|\b[A-Z]{1,2}[\s-]?\d{4}[\s-]?[A-Z]{2}\b"
    r"|\b[A-HJ-NPR-Z0-9]{17}\b", re.I)


def sin_matricula(texto):
    """El mismo texto con la matrícula o el VIN sustituidos por una marca.

    MINIMIZACIÓN. El modelo no necesita el dato para escribir el mensaje: le basta
    con saber que el cliente ya lo dio, que es justo lo que dice la marca. El dato
    entero se queda en esta máquina, en la memoria de la conversación, y solo sale
    si el redactor determinista ha decidido decirlo — y eso solo pasa cuando el
    cliente pide que se lo repitan.

    Sin esto, la matrícula viajaba a Groq (EE. UU.) tres veces por petición: en el
    resumen, en los turnos literales del historial y en el mensaje del cliente.
    """
    return _MATRICULA.sub("[MATRÍCULA YA DADA]", texto or "")


def resumir(memoria, omitidos):
    """Comprime en datos lo que ya no cabe en la ventana de turnos.

    NO lo escribe el modelo. Se monta con lo que la conversación lleva guardado,
    porque un resumen generado puede inventarse una matrícula que nadie dijo, y
    éste no puede: cada línea o está en memoria o no aparece. Sale gratis, es
    reproducible y no alucina.
    """
    if not memoria:
        return None
    campos = [
        ("cliente", memoria.get("nombre") or None),
        # La matrícula NO viaja: solo el hecho de que la dio. Ver sin_matricula().
        ("matrícula", "sí, ya la dio — no se la vuelvas a pedir"
         if memoria.get("matricula") else None),
        ("coche del que se habla", memoria.get("vehiculo")),
        ("pieza que busca", memoria.get("pieza")),
        ("último precio dicho", memoria.get("precio")),
        # EN QUÉ PUNTO VA LA VENTA. Sin esto el modelo trata igual a alguien que
        # acaba de escribir y a alguien que ya ha comprado.
        ("punto de la conversación", memoria.get("estado")),
    ]
    lineas = [f"  {etiqueta}: {valor}" for etiqueta, valor in campos if valor]

    # LAS OTRAS PIEZAS. Un taller pide tres cosas del mismo coche en el mismo
    # hilo; con solo la última, las dos primeras se pierden y hay que
    # repetírselas al cliente.
    otras = [p for p in (memoria.get("otras_piezas") or []) if p]
    if otras:
        lineas.append(f"  también se habló de: {', '.join(otras)}")

    # LO QUE SE LE PROMETIÓ. Es lo que hace que un «¿ya lo tienes?» tres días
    # después tenga respuesta.
    for pendiente in (memoria.get("promesas") or []):
        lineas.append(f"  QUEDA PENDIENTE: {pendiente}")

    # LAS CONDICIONES YA EXPLICADAS. Repetir el párrafo de envío tres veces es lo
    # que delata a un bot, y el modelo no se acuerda de habérselo dicho.
    temas = [t for t in (memoria.get("temas") or []) if t]
    if temas:
        lineas.append(f"  ya se le explicó: {', '.join(t.lower() for t in temas)}"
                      f" — NO se lo repitas")

    if memoria.get("garantia_dicha"):
        lineas.append("  la garantía ya se le explicó: no la repitas")
    if memoria.get("escalado"):
        lineas.append("  ya está en manos de una persona")
    if not lineas:
        return None
    return (f"LO YA HABLADO ({omitidos} mensajes anteriores, resumidos):\n"
            + "\n".join(lineas))


def _mensajes(consulta, respuesta, accion, opciones, historial, memoria=None):
    """Monta lo que ve el modelo. Lo que no esté aquí, para él no existe."""
    datos = [f"ACCIÓN: {accion}"]

    piezas = [r for r in (consulta.get("resultados") or [])
              if r.get("tipo") == "inventario"]
    if piezas:
        meta = piezas[0].get("meta") or {}
        precio = piezas[0].get("precio_cliente") or {}
        ficha = [f"pieza: {meta.get('pieza')}",
                 f"vehículo: {meta.get('marca')} {meta.get('modelo')} "
                 f"{meta.get('motor')} ({meta.get('anio')})",
                 f"estado: {meta.get('estado')}",
                 f"disponibilidad: {meta.get('disponibilidad')}",
                 f"garantía: {meta.get('garantia')}"]
        # AQUÍ ESTÁ EL GUARDARRAÍL: el importe entra en el contexto del modelo
        # SOLO si la búsqueda lo ha autorizado. Si no, el modelo no lo tiene y
        # no puede decirlo — no es que se le pida que no lo diga.
        if precio.get("publicable"):
            ficha.append(f"precio: {precio['importe']} (autorizado a decirlo)")
        elif precio.get("estado") == "sin_matricula":
            # No es lo mismo «no puedo darte el precio» que «necesito la matrícula
            # para saber cuál es el tuyo». Si al modelo se le dice solo lo primero,
            # escribe que lo confirmará y no pide el dato — y la conversación se
            # queda parada esperando a nadie.
            n = piezas[0].get("variantes") or 1
            ficha.append(f"precio: NO SE DA todavía. De esta pieza para ese coche "
                         f"hay {n} referencias según motor y año, así que aún no se "
                         f"sabe cuál es la suya. NO ofrezcas esta ficha concreta ni "
                         f"su precio: PIDE LA MATRÍCULA, que es el primer paso.")
        else:
            ficha.append("precio: NO DISPONIBLE para el cliente. Di que lo confirmas.")
        datos.append("FICHA ENCONTRADA:\n  " + "\n  ".join(ficha))
    elif (memoria or {}).get("pieza"):
        # SEGUIMIENTO. La búsqueda de este turno no devuelve ficha porque el
        # cliente ya no nombra la pieza: dice «¿cuánto vale?» o «¿lleva
        # garantía?». Pero la conversación sí la tiene, y decirle al modelo «no
        # tenemos esa pieza» aquí es peor que no decirle nada.
        #
        # Salió de la primera conversación larga contra Groq. Turno 3: «tenemos
        # el alternador, 200,77 € + IVA, ¿lo aparto?». Turno 4, «¿cuánto vale?»:
        # «no disponemos de ese alternador». Se contradecía a sí mismo un turno
        # después, y con toda la razón: eso era lo que le habíamos escrito.
        #
        # El importe que va aquí es uno que YA se dijo — `ultimo_precio` solo se
        # rellena cuando la búsqueda autorizó publicarlo. Repetirlo cuando el
        # cliente vuelve a preguntar no es publicar un precio nuevo, y es lo
        # mismo que ya hacía el redactor determinista.
        seguimiento = [f"pieza: {memoria['pieza']}"]
        if memoria.get("vehiculo"):
            seguimiento.append(f"vehículo: {memoria['vehiculo']}")
        if memoria.get("precio"):
            seguimiento.append(f"precio: {memoria['precio']} (ya se le dijo)")
        else:
            seguimiento.append("precio: aún no se le ha dado. Di que lo confirmas.")
        datos.append("NO HAY FICHA NUEVA, pero la conversación ya iba de esta "
                     "pieza. NO digas que no la tenemos:\n  "
                     + "\n  ".join(seguimiento))
    else:
        datos.append("FICHA ENCONTRADA: ninguna. No tenemos esa pieza.")

    politicas = [r for r in (consulta.get("resultados") or [])
                 if r.get("tipo") == "politica"]
    if politicas:
        datos.append("POLÍTICA DE LA EMPRESA (cítala, no la cambies):\n  "
                     + politicas[0]["texto"][:600])

    if opciones:
        lista = " / ".join(o["texto"] for o in opciones["opciones"])
        datos.append(f"PREGUNTA A HACER: {opciones['pregunta']}\n"
                     f"  Opciones REALES del catálogo: {lista}\n"
                     f"  Nómbralas tal cual. No añadas ninguna que no esté.")

    # Lo que el redactor determinista ya decidió: sirve de referencia de tono y
    # de red de seguridad. El modelo reescribe, no reinventa.
    datos.append("BORRADOR (mismo contenido, mejóralo de forma):\n  "
                 + respuesta["mensaje"])

    mensajes = [{"role": "system", "content": ROL}]
    # Si la conversación se ha hecho larga, lo que se sale de la ventana entra
    # resumido en vez de desaparecer. Es la diferencia entre recortar y recordar.
    omitidos = max(0, len(historial) - VENTANA_TURNOS)
    if omitidos:
        resumen = resumir(memoria, omitidos)
        if resumen:
            mensajes.append({"role": "system", "content": resumen})
    # Los turnos anteriores van enmascarados: lo que el modelo necesita del
    # historial es el hilo de la conversación, no los datos del coche.
    for turno in historial[-VENTANA_TURNOS:]:
        mensajes.append({"role": "user", "content": sin_matricula(turno["cliente"])})
        mensajes.append({"role": "assistant", "content": sin_matricula(turno["bot"])})
    # El mensaje de este turno también. El BORRADOR no se toca: si el redactor ha
    # decidido decir la matrícula —porque el cliente ha pedido que se la repitan—
    # entonces sí hace falta, y es el único caso en que sale de aquí.
    mensajes.append({"role": "user",
                     "content": f"MENSAJE DEL CLIENTE: "
                                f"{sin_matricula(consulta.get('pregunta', ''))}\n\n"
                                + "\n\n".join(datos)})
    return mensajes


def redactar_con_llm(consulta, respuesta, accion, opciones, historial, config,
                     memoria=None):
    """Devuelve las líneas escritas por el modelo, o None si no se puede.

    Cualquier fallo (sin clave, sin red, cuota agotada, respuesta rara) devuelve
    None y el sistema sigue con el redactor determinista. Un desguace no se puede
    quedar sin contestar porque una API esté caída.
    """
    clave = config.get("GROQ_API_KEY")
    if not clave:
        return None, "sin clave de API: redacta el redactor determinista"

    modelo = config.get("GROQ_MODELO") or MODELO_POR_DEFECTO
    peticion_json = {
        "model": modelo,
        "messages": _mensajes(consulta, respuesta, accion, opciones, historial,
                              memoria),
        "temperature": 0.4,     # algo de variedad, pero no delirios
        "max_tokens": TOPE_RESPUESTA,
    }
    # Solo los modelos que razonan entienden este parámetro; a los demás les
    # sobra, y mandárselo puede costar un 400. Se pregunta por el nombre porque
    # es lo único que se sabe del modelo antes de llamarlo.
    if "gpt-oss" in modelo or "qwen3" in modelo:
        peticion_json["reasoning_effort"] = ESFUERZO
    cuerpo = json.dumps(peticion_json).encode("utf-8")

    peticion = urllib.request.Request(
        URL_GROQ, data=cuerpo,
        headers={"Authorization": f"Bearer {clave}",
                 "Content-Type": "application/json",
                 # Sin esto, 403. Groq está detrás de Cloudflare y Cloudflare
                 # rechaza el User-Agent por defecto de Python
                 # («Python-urllib/3.x») con su error 1010. Medido en la primera
                 # llamada de verdad: sin cabecera 403, con cabecera 200. No lo
                 # cazó ninguna prueba porque todas sustituyen urlopen y nunca
                 # llega a salir un paquete a la red.
                 "User-Agent": AGENTE})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_MAXIMO) as r:
            datos = json.loads(r.read().decode("utf-8"))
        eleccion = datos["choices"][0]
        texto = (eleccion["message"].get("content") or "").strip()
        motivo = eleccion.get("finish_reason")
    except urllib.error.HTTPError as e:
        return None, f"la API respondió {e.code}: sigue el redactor determinista"
    except Exception as e:
        return None, f"{type(e).__name__}: sigue el redactor determinista"

    lineas = [l.strip() for l in texto.splitlines() if l.strip()][:3]
    if not lineas:
        # Se distingue el vacío del quedarse sin presupuesto porque no son el
        # mismo problema y no se arreglan igual. «Vacío» a secas escondió durante
        # diez conversaciones que el modelo se estaba gastando el tope entero
        # pensando: el panel decía que el LLM no había contestado, cuando lo que
        # pasaba es que no le habíamos dejado sitio para hacerlo.
        if motivo == "length":
            return None, (f"{modelo} agotó los {TOPE_RESPUESTA} tokens antes de "
                          f"escribir nada: sube TOPE_RESPUESTA o baja ESFUERZO")
        return None, "el modelo devolvió un mensaje vacío"
    return lineas, f"redactado por {config.get('GROQ_MODELO') or MODELO_POR_DEFECTO}"
