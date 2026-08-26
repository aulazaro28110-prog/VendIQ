# -*- coding: utf-8 -*-
"""LOS DOS CANALES NUEVOS, GENERADOS DEL CATÁLOGO REAL.

Un desguace no vende solo por WhatsApp. Por Gmail entra otro tipo de cliente y
por Wallapop, otro muy distinto — y lo que se le puede decir a cada uno cambia
de FORMA pero no de FONDO: el precio sigue necesitando saber de qué coche es la
pieza, venga la pregunta por donde venga.

Estos corpus se generan, no se escriben a mano, por la misma razón que el banco
de conversaciones: si las piezas, los coches y las referencias salen del
catálogo de verdad, no puede colarse un caso que pida un motor que no existe y
que el sistema «resuelva» por accidente.

    python scripts/generar_canales.py

    datos/canales/correos.jsonl    50 correos, uno por cliente
    datos/canales/wallapop.jsonl   20 conversaciones largas

GMAIL
-----
Un solo correo, y viene COMPLETO: coche, matrícula o bastidor, pieza y a menudo
la referencia OEM. Quien escribe un correo se lo ha pensado. Eso permite lo que
no permite un «hola» de WhatsApp: contestar una vez y con todo dentro — qué hay,
cuánto vale, cuánto tarda, qué garantía lleva y cómo se paga.

WALLAPOP
--------
Lo contrario. Gente que pregunta por piezas que no llevamos, que regatea cinco
veces, que quiere que se la mandes antes de pagar, que te enseña la captura de
una transferencia que no existe. Conversaciones largas y a propósito incómodas:
lo que se mide aquí no es si acierta, es si AGUANTA sin ceder y sin perder los
modales.
"""
import csv
import json
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INVENTARIO = BASE / "datos" / "inventario_sintetico.csv"
SALIDA = BASE / "datos" / "canales"

LETRAS = "BCDFGHJKLMNPRSTVWXYZ"
ALFABETO_VIN = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def matricula(rnd):
    letras = "".join(rnd.choices(LETRAS, k=3))
    return str(rnd.randint(1000, 9999)) + " " + letras


def bastidor(rnd):
    return "".join(rnd.choices(ALFABETO_VIN, k=17))


def sin_acentos(t):
    for a, b in zip("áéíóúñÁÉÍÓÚÑ", "aeiounAEIOUN"):
        t = t.replace(a, b)
    return t


def cargar_catalogo():
    with open(INVENTARIO, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


# ---------------------------------------------------------------------------
# GMAIL · 50 correos
# ---------------------------------------------------------------------------
TALLERES = [
    ("Javier Ruiz", "Talleres Motor Sur", "Getafe"),
    ("Marta Peña", "Auto Recambios Henares", "Alcalá de Henares"),
    ("Luis Company", "Taller Company e Hijos", "Madrid"),
    ("Andrés Vidal", "Electromecánica Vidal", "Torrejón"),
    ("Nuria Sanz", "Talleres Sanz", "Azuqueca"),
    ("Óscar Ibáñez", "Chapa y Pintura Ibáñez", "Meco"),
    ("Rocío Bravo", "Auto Bravo", "Coslada"),
    ("Fernando Gil", "Mecánica Gil", "Alovera"),
]
PARTICULARES = [
    "Carlos Menéndez", "Ana Belén Torres", "Sergio Pardo", "Lucía Ferrer",
    "Miguel Ángel Rojas", "Patricia Nieto", "Iván Salgado", "Elena Cuesta",
    "Raúl Domínguez", "Sonia Márquez", "Alberto Quintana", "Beatriz Lorente",
]

ASUNTOS = [
    "Consulta disponibilidad {pieza}",
    "{pieza} para {marca} {modelo}",
    "Presupuesto {pieza}",
    "Solicitud de recambio - {pieza}",
    "¿Tenéis {pieza} de {marca} {modelo}?",
    "Petición de pieza y precio",
]

# Cada plantilla da TODO lo necesario para contestar de una vez: el coche, el
# identificador y la pieza. Es lo que distingue este canal del WhatsApp, donde
# el primer mensaje casi nunca trae la matrícula.
# La URL de la ficha viaja en el correo cuando la pieza existe. No es adorno: es
# el identificador MÁS fuerte que puede dar un cliente. Quien escribe un correo
# ha estado antes en la web mirando la pieza y pega el enlace — y ese enlace
# lleva dentro el número de stock, que identifica la ficha sin ambigüedad
# ninguna. Con él no hay que adivinar cuál de los cuatro alternadores es.
#
# Los ocho que piden algo que no llevamos NO llevan enlace, claro: no hay página
# a la que enlazar. Eso también es una señal.
CUERPOS_TALLER = [
    "Buenos días:\n\n"
    "Les escribo desde {empresa} ({ciudad}). Necesitamos una {pieza} para un "
    "{marca} {modelo} {motor} del año {anio}.\n"
    "Matrícula del vehículo: {matricula}.{enlace}\n\n"
    "¿Nos pueden confirmar disponibilidad, precio, plazo de entrega y garantía? "
    "Trabajamos con factura.\n\n"
    "Un saludo,\n{nombre}\n{empresa}",

    "Hola, buenos días.\n\n"
    "Buscamos {pieza} para el siguiente vehículo:\n"
    "  Marca y modelo: {marca} {modelo}\n"
    "  Motor: {motor}\n"
    "  Año: {anio}\n"
    "  Bastidor: {vin}{enlace}\n\n"
    "Si la tenéis, indicadnos precio con IVA, plazo y si lleva garantía. "
    "Necesitaríamos saber también si hacéis envío al taller.\n\n"
    "Gracias.\n{nombre} · {empresa}",

    "Buenas tardes:\n\n"
    "Referencia OEM {oem}, correspondiente a {pieza} de {marca} {modelo} "
    "{motor} ({anio}). Matrícula {matricula}.{enlace}\n\n"
    "Confírmenme por favor si disponen de ella, el importe y el plazo. "
    "Precisamos factura a nombre de {empresa}.\n\n"
    "Atentamente,\n{nombre}",
]
CUERPOS_PARTICULAR = [
    "Hola buenas,\n\n"
    "Necesito una {pieza} para mi {marca} {modelo} {motor} del {anio}, "
    "matrícula {matricula}.{enlace}\n"
    "¿Cuánto me costaría y cuánto tardaría en llegar? ¿Tiene alguna garantía?\n\n"
    "Gracias de antemano.\n{nombre}",

    "Buenos días,\n\n"
    "Escribo porque estoy buscando {pieza} para un {marca} {modelo} del año "
    "{anio} (motor {motor}). La matrícula es {matricula} y la referencia que me "
    "han dado en el taller es {oem}.{enlace}\n\n"
    "¿Me podéis decir precio y si la mandáis a domicilio? Estoy en Madrid.\n\n"
    "Un saludo,\n{nombre}",

    "Hola,\n\n"
    "Mi coche es un {marca} {modelo} {motor} de {anio}, matrícula {matricula}. "
    "Se me ha roto {pieza} y me gustaría saber si tenéis una de segunda mano.{enlace}\n"
    "Necesito saber el precio, la garantía y cómo se paga.\n\n"
    "Muchas gracias,\n{nombre}",
]

# Ocho de los cincuenta piden algo que NO está en catálogo. Sin ellos el corpus
# solo mide el camino fácil, y el correo difícil de escribir no es el que dice
# «sí, la tengo»: es el que tiene que decir que no y aun así servir para algo.
#
# LOS OCHO SON REPUESTOS USADOS, no consumibles. La primera versión de esta
# lista pedía pastillas, aceite, filtros y neumáticos, y estaba mal planteada:
# un desguace no vende eso ni lo va a vender nunca, así que medir cómo dice que
# no a un bote de 5W30 no mide nada del negocio. El «no» que este desguace da
# de verdad es otro — «esa pieza sí la desguazamos, pero ahora mismo no la
# tengo» — y ese es el que hay que saber escribir.
#
# Las ocho son peticiones que a Desguaces Madrid Norte le entran cualquier día;
# simplemente no están entre los 37 tipos del catálogo actual. Dos van con
# segunda intención:
#
#   «bomba de inyección»  — "bomba" SÍ es vocabulario del catálogo (bomba de
#                           agua, bomba de dirección). Mide que no le encasquete
#                           una bomba cualquiera a quien pide otra.
#   «palanca de cambios»  — "cambios" SÍ lo es (caja de cambios), y va detrás de
#                           un "de". Mide la regla del núcleo.
NO_LLEVAMOS = [
    ("salpicadero completo", "SEAT", "Ibiza", "1.6 TDI", "2015"),
    ("asiento delantero derecho", "Renault", "Mégane", "1.5 dCi", "2014"),
    ("culata", "Ford", "Focus", "1.0 EcoBoost", "2018"),
    ("depósito de combustible", "Opel", "Corsa", "1.2", "2016"),
    ("luna trasera", "Peugeot", "308", "1.6 HDi", "2013"),
    ("árbol de transmisión", "Citroën", "C4", "1.6 HDi", "2012"),
    ("bomba de inyección", "Volkswagen", "Golf", "2.0 TDI", "2017"),
    ("palanca de cambios", "Toyota", "Auris", "1.8 HSD", "2015"),
]


def generar_correos(catalogo, rnd, cuantos=50):
    correos = []
    for i in range(cuantos):
        profesional = i % 3 != 2                  # dos de cada tres, talleres
        if profesional:
            nombre, empresa, ciudad = rnd.choice(TALLERES)
        else:
            nombre, empresa, ciudad = rnd.choice(PARTICULARES), "", "Madrid"

        if i < len(NO_LLEVAMOS):
            pieza, marca, modelo, motor, anio = NO_LLEVAMOS[i]
            oem, en_catalogo, id_pieza, url = "", False, "", ""
        else:
            fila = rnd.choice(catalogo)
            pieza, marca, modelo = fila["pieza"], fila["marca"], fila["modelo"]
            motor, anio = fila["motor"], fila["anio"]
            oem, en_catalogo, id_pieza = fila["referencia_oem"], True, fila["id"]
            url = fila["url"]

        datos = {
            "pieza": pieza.lower(), "marca": marca, "modelo": modelo,
            "motor": motor, "anio": anio, "oem": oem,
            "matricula": matricula(rnd), "vin": bastidor(rnd),
            "nombre": nombre, "empresa": empresa or "un particular",
            "ciudad": ciudad,
            "enlace": ("\nLa he visto en vuestra web: " + url) if url else "",
        }
        plantillas = CUERPOS_TALLER if profesional else CUERPOS_PARTICULAR
        cuerpo = rnd.choice(plantillas).format(**datos)
        asunto = rnd.choice(ASUNTOS).format(**datos)

        buzon = sin_acentos(nombre).lower().replace(" ", ".")
        dominio = (sin_acentos(empresa).lower().split()[0] + ".es"
                   if profesional else "gmail.com")

        correos.append({
            "n": i + 1,
            "canal": "email",
            "de": buzon + "@" + dominio,
            "quien": nombre,
            "empresa": empresa,
            "asunto": asunto,
            "cuerpo": cuerpo,
            # Lo que el corpus AFIRMA del caso, para que la prueba compruebe la
            # respuesta sin volver a adivinar de qué iba el correo.
            "espera": {
                "en_catalogo": en_catalogo,
                "id_pieza": id_pieza,
                "pieza": pieza,
                "url": url,
                "coche": marca + " " + modelo + " " + motor + " " + anio,
                "identificado": True,     # todos traen matrícula, bastidor o ambos
                "profesional": profesional,
            },
        })
    return correos


# ---------------------------------------------------------------------------
# WALLAPOP · 20 conversaciones largas
# ---------------------------------------------------------------------------
# Cada guion es una MANERA de ponerlo difícil, no un cliente concreto. Las
# piezas y los coches se rellenan del catálogo, así que el mismo guion con otra
# semilla es otra conversación distinta y sigue siendo coherente.
#
# {pieza} y {coche} son de catálogo. {nohay} es algo que este desguace NO lleva:
# hace falta para medir lo que más cuesta, que es decir que no y no perder al
# cliente por el camino.
GUIONES = [
    ("regatea sin parar", [
        "hola sigue disponible?", "{pieza} para {coche}", "cuanto es lo menos",
        "va, dejalo en la mitad", "en otro sitio me lo dejan mas barato",
        "hombre por 20 euros menos me lo llevo hoy",
        "que si, que te lo pago ahora mismo si me lo dejas",
        "y si me llevo dos?", "ultima oferta", "bueno pues nada",
        "espera espera, y si pago en efectivo?",
    ]),
    ("quiere que se lo mandes sin pagar", [
        "buenas, tienes {pieza}?", "es para un {coche}", "{matricula}",
        "vale me interesa", "mandamelo y te pago al recibirlo",
        "es que no me fio de pagar por adelantado",
        "hombre yo tengo 40 valoraciones positivas",
        "venga va, te hago bizum de la mitad y el resto al recibirlo",
        "pues vaya servicio", "bueno dime como se paga",
    ]),
    ("captura falsa", [
        "hola, {pieza} de {coche}", "{matricula}", "vale lo quiero",
        "ya te he hecho la transferencia", "te paso captura",
        "mira, pone hecho y todo", "sera cosa de tu banco",
        "que te digo que esta pagado", "me lo mandas ya o que",
        "pues denuncio", "a ver, dime que te falta",
    ]),
    ("pide algo que no llevamos", [
        "hola tienes {nohay}?", "para un {coche}", "seguro? mira bien",
        "pero si sois un desguace", "y algo parecido?",
        "en la foto del anuncio parecia que si",
        "vaya perdida de tiempo", "y {pieza} tienes?", "{matricula}",
        "ah vale, eso si me sirve", "cuanto?",
    ]),
    ("prisa y presión", [
        "necesito {pieza} YA", "es para hoy", "para un {coche}, {matricula}",
        "no puedo esperar", "no hay forma de que salga hoy?",
        "pago lo que sea", "y si voy yo a recogerlo?",
        "a que hora cerrais", "vale voy para alla", "confirmame que esta ahi",
    ]),
    ("maleducado", [
        "oye", "tienes {pieza} o no", "responde",
        "vaya tela como funciona esto", "para un {coche}", "{matricula}",
        "y por que tan caro", "esto es un robo", "es un desguace no un concesionario",
        "a ver, cuanto es lo minimo", "vale vale, lo pillo",
    ]),
    ("pregunta lo mismo de cinco maneras", [
        "hola tienes {pieza}?", "es para {coche}", "{matricula}",
        "esta bien de estado?", "pero funciona?", "esta probada?",
        "seguro que va bien?", "no me la vas a colar no?",
        "y si no funciona que", "y cuanto tiempo tengo para devolverla",
        "vale, me la quedo",
    ]),
    ("se va y vuelve", [
        "hola, {pieza}?", "{coche}, {matricula}", "vale luego te digo",
        "hola?", "sigue disponible?", "perdona es que se me paso",
        "cuanto era?", "vale dejame que lo mire",
        "oye ya lo he mirado, lo quiero", "como quedamos",
    ]),
    ("quiere quedar en persona", [
        "hola tienes {pieza}", "para {coche}", "{matricula}",
        "prefiero verla antes", "quedamos y te lo pago en mano",
        "donde estais", "eso esta muy lejos", "no puedes acercarte tu?",
        "y mandarlo cuanto seria", "vale pues mandamelo",
    ]),
    ("duda del precio", [
        "hola cuanto por {pieza}", "{coche}", "{matricula}",
        "en el anuncio ponia otro precio", "eso es con iva o sin iva",
        "o sea que son mas caros de lo que pone",
        "eso es publicidad enganosa", "a ver explicamelo otra vez",
        "vale, entonces cuanto pago en total", "y el envio aparte?",
    ]),
    ("cambia de pieza a mitad", [
        "hola necesito {pieza}", "para un {coche}", "{matricula}",
        "cuanto vale", "uf, y {nohay}?", "ah vale",
        "pues entonces vuelvo a lo de antes", "el primero cuanto era",
        "vale me lo quedo", "me lo mandas al pueblo?",
    ]),
    ("no da la matricula", [
        "hola tienes {pieza}", "es para un coche", "un {coche}",
        "no me se la matricula", "no la tengo a mano",
        "pero si te digo el modelo no vale?", "que mania con la matricula",
        "a ver espera", "{matricula}", "ya esta, cuanto es",
    ]),
    ("quiere factura sin serlo", [
        "hola {pieza} para {coche}", "{matricula}", "me interesa",
        "hazme factura sin iva", "es que es para la empresa de un amigo",
        "venga hombre que mas te da", "todo el mundo lo hace",
        "pues entonces con iva", "cuanto queda en total", "vale",
    ]),
    ("compara con otro desguace", [
        "hola, {pieza} de {coche}", "{matricula}",
        "en otro me la dejan a mitad", "y mas nueva",
        "por que sois mas caros", "que garantia dais vosotros",
        "y ellos dan mas?", "a ver convenceme",
        "vale, me quedo con la vuestra", "como se paga",
    ]),
    ("mensaje sucio y a trozos", [
        "ola", "kiero pieza", "pa un coxe", "{coche}",
        "{pieza}", "espera q miro la matricula", "{matricula}",
        "kuanto", "uff", "vale mandamela",
    ]),
    ("insiste con lo que no hay", [
        "buenas, {nohay}", "para {coche}", "no teneis nada?",
        "pero podeis pedirlo?", "y de otra marca?",
        "en serio que no?", "vaya", "y de segunda mano tampoco?",
        "pues nada", "oye y {pieza} si tienes?",
    ]),
    ("amenaza con la valoración", [
        "hola {pieza} {coche}", "{matricula}", "cuanto",
        "muy caro", "si no me lo bajas te pongo una estrella",
        "que lo digo en serio", "ya he puesto malas valoraciones a otros",
        "venga, un descuentito", "bueno vale", "como pago",
    ]),
    ("pide envío al extranjero", [
        "hola tienes {pieza}", "{coche}, {matricula}",
        "lo mandas a francia?", "y a portugal?",
        "cuanto seria el porte", "eso quien lo paga",
        "y tarda mucho?", "y si hay problemas en aduana",
        "vale, y a canarias?", "bueno dejalo, lo mando yo desde madrid",
    ]),
    ("posventa que se tuerce", [
        "hola {pieza} para {coche}", "{matricula}", "me lo quedo",
        "al taller de siempre", "ya ha salido?", "me ha llegado",
        "no es la que pedi", "esto es de otro modelo",
        "y ahora que hago", "quiero que me devolvais el dinero",
    ]),
    ("pone a prueba la paciencia", [
        "hola", "hola?", "no contestas?", "bueno", "tienes {pieza}",
        "de {coche}", "vale", "y?", "{matricula}",
        "sigues ahi?", "cuanto vale", "ah vale", "gracias", "adios",
    ]),
]


def generar_wallapop(catalogo, rnd, cuantos=20):
    conversaciones = []
    nada = [n[0] for n in NO_LLEVAMOS]
    for i in range(cuantos):
        titulo, guion = GUIONES[i % len(GUIONES)]
        fila = rnd.choice(catalogo)
        datos = {
            "pieza": fila["pieza"].lower(),
            "coche": fila["marca"] + " " + fila["modelo"] + " " + fila["motor"],
            "matricula": matricula(rnd),
            "nohay": rnd.choice(nada),
        }
        mensajes = [m.format(**datos) for m in guion]
        conversaciones.append({
            "n": i + 1,
            "canal": "wallapop",
            "guion": titulo,
            "pieza": fila["pieza"],
            "id_pieza": fila["id"],
            "coche": datos["coche"],
            "matricula": datos["matricula"],
            "mensajes": mensajes,
        })
    return conversaciones


def escribir(fichero, filas):
    fichero.parent.mkdir(parents=True, exist_ok=True)
    with open(fichero, "w", encoding="utf-8", newline="\n") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fichero


def main():
    rnd = random.Random(11)
    catalogo = cargar_catalogo()

    correos = generar_correos(catalogo, rnd)
    wallapop = generar_wallapop(catalogo, rnd)

    escribir(SALIDA / "correos.jsonl", correos)
    escribir(SALIDA / "wallapop.jsonl", wallapop)

    sin_stock = sum(1 for c in correos if not c["espera"]["en_catalogo"])
    turnos = sum(len(c["mensajes"]) for c in wallapop)
    print("datos/canales/correos.jsonl   " + str(len(correos)) + " correos "
          "(" + str(sin_stock) + " piden algo que no llevamos)")
    print("datos/canales/wallapop.jsonl  " + str(len(wallapop)) + " conversaciones, "
          + str(turnos) + " mensajes "
          "(" + str(round(turnos / len(wallapop), 1)) + " de media)")


if __name__ == "__main__":
    main()
