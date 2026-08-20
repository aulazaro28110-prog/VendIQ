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
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
ENV = BASE / ".env"

MODELO_POR_DEFECTO = "llama-3.3-70b-versatile"
URL_GROQ = "https://api.groq.com/openai/v1/chat/completions"
TIEMPO_MAXIMO = 12          # segundos; si tarda más, se responde sin LLM

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
        ("matrícula que dio", memoria.get("matricula")),
        ("coche del que se habla", memoria.get("vehiculo")),
        ("pieza que busca", memoria.get("pieza")),
        ("último precio dicho", memoria.get("precio")),
    ]
    lineas = [f"  {etiqueta}: {valor}" for etiqueta, valor in campos if valor]
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
        else:
            ficha.append("precio: NO DISPONIBLE para el cliente. Di que lo confirmas.")
        datos.append("FICHA ENCONTRADA:\n  " + "\n  ".join(ficha))
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
    for turno in historial[-VENTANA_TURNOS:]:
        mensajes.append({"role": "user", "content": turno["cliente"]})
        mensajes.append({"role": "assistant", "content": turno["bot"]})
    mensajes.append({"role": "user",
                     "content": f"MENSAJE DEL CLIENTE: {consulta.get('pregunta', '')}\n\n"
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

    cuerpo = json.dumps({
        "model": config.get("GROQ_MODELO") or MODELO_POR_DEFECTO,
        "messages": _mensajes(consulta, respuesta, accion, opciones, historial,
                              memoria),
        "temperature": 0.4,     # algo de variedad, pero no delirios
        "max_tokens": 220,
    }).encode("utf-8")

    peticion = urllib.request.Request(
        URL_GROQ, data=cuerpo,
        headers={"Authorization": f"Bearer {clave}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_MAXIMO) as r:
            datos = json.loads(r.read().decode("utf-8"))
        texto = datos["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        return None, f"la API respondió {e.code}: sigue el redactor determinista"
    except Exception as e:
        return None, f"{type(e).__name__}: sigue el redactor determinista"

    lineas = [l.strip() for l in texto.splitlines() if l.strip()][:3]
    if not lineas:
        return None, "el modelo devolvió un mensaje vacío"
    return lineas, f"redactado por {config.get('GROQ_MODELO') or MODELO_POR_DEFECTO}"
