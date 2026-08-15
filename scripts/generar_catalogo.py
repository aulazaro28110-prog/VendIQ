"""
scripts/generar_catalogo.py
===========================
Genera el catálogo sintético de VendIQ: 1.000 piezas, todas con precio.

Esto NO es parte del pipeline: se ejecuta una vez para crear los datos de prueba.
Los datos son sintéticos por regla del proyecto (privacidad), pero los PRECIOS
tienen que ser creíbles, porque de ellos dependen las ofertas y los descuentos.

CÓMO SE CALCULA UN PRECIO
-------------------------
    precio = base(pieza) · factor(marca) · factor(antigüedad) · ruido

  - base(pieza): rango de mercado del recambio usado en España. Anclado a lo que
    publican los desguaces online (ver RANGOS): retrovisores desde ~30 €, faros
    desde ~20 €, alternadores 35-73 €, cajas de cambio 109-182 € en utilitario.
    Los extremos del catálogo van de un paso de rueda de 20 € a un motor completo
    de gama alta, que puede pasar de 4.000 €.
  - factor(marca): un faro de Mercedes no vale lo que uno de Seat. Tres segmentos.
  - factor(antigüedad): un recambio de 2021 vale más que el mismo de 2005.
  - ruido: ±12 %, porque dos piezas iguales nunca salen al mismo precio (estado,
    kilómetros, cuánto lleva parada).

El precio final se recorta al rango de su tipo de pieza, para que ninguna
combinación rara produzca un disparate.

Uso:  python scripts/generar_catalogo.py [--n 1000]
"""

import argparse
import csv
import random
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SALIDA = BASE / "datos" / "inventario_sintetico.csv"

# (mínimo, máximo) en euros para un utilitario de gama media y edad media.
# El clamp final usa estos mismos límites ampliados por los factores.
RANGOS = {
    "Motor completo":                 (650, 4000),
    "Caja de cambios":                (170, 1150),
    "Turbo":                          (150,  620),
    "Catalizador":                    (110,  480),
    "Centralita motor":               (100,  420),
    "Cremallera de dirección":         (90,  340),
    "Compresor aire acondicionado":    (85,  290),
    "Portón trasero":                 (110,  380),
    "Puerta delantera derecha":       (100,  360),
    "Puerta delantera izquierda":     (100,  360),
    "Puerta trasera izquierda":        (90,  330),
    "Airbag volante":                  (70,  280),
    "Cuadro de instrumentos":          (70,  270),
    "Parachoques delantero":           (65,  260),
    "Parachoques trasero":             (65,  260),
    "Capó":                            (75,  260),
    "Módulo electrónico":              (55,  220),
    "Intercooler":                     (60,  210),
    "Faro delantero derecho":          (45,  240),
    "Faro delantero izquierdo":        (45,  240),
    "Alternador":                      (35,  190),
    "Aleta delantera izquierda":       (50,  185),
    "Colector de admisión":            (45,  170),
    "Radiador":                        (40,  165),
    "Bomba de dirección":              (45,  160),
    "Retrovisor derecho":              (30,  165),
    "Retrovisor izquierdo":            (30,  165),
    "Motor de arranque":               (35,  150),
    "Cárter":                          (30,  120),
    "Elevalunas delantero izquierdo":  (30,  105),
    "Piloto trasero derecho":          (25,   95),
    "Piloto trasero izquierdo":        (25,   95),
    "Bomba de agua":                   (25,   90),
    "Amortiguador delantero":          (25,   85),
    "Cinturón de seguridad":           (25,   80),
    "Cerradura puerta delantera":      (22,   70),
    "Paso de rueda trasero izquierdo": (20,   62),
}

# Segmento de marca: lo mismo cuesta más en premium.
FACTOR_MARCA = {
    "MERCEDES-BENZ": 1.45, "BMW": 1.40, "AUDI": 1.35, "VOLKSWAGEN": 1.12,
    "TOYOTA": 1.08, "SKODA": 1.02, "SEAT": 0.95, "PEUGEOT": 0.95,
    "RENAULT": 0.93, "CITROEN": 0.93, "OPEL": 0.94, "FORD": 0.96,
    "NISSAN": 1.00, "HYUNDAI": 0.97, "KIA": 0.97,
}

# Modelos y motorizaciones por marca (calcados a la estructura de la web real).
CATALOGO = {
    "AUDI":          {"A3": ["1.6 TDI", "2.0 TDI", "1.4 TFSI"],
                      "A4": ["2.0 TDI", "3.0 TDI", "2.0 TFSI"],
                      "Q3": ["2.0 TDI", "1.4 TFSI"]},
    "BMW":           {"Serie 1": ["118d", "116d", "120i"],
                      "Serie 3": ["320d", "318d", "330i"],
                      "X1":      ["18d", "20d"]},
    "MERCEDES-BENZ": {"Clase A": ["180 CDI", "200 CDI"],
                      "Clase E Coupé": ["220 CDI", "250 CDI"],
                      "CLA": ["200 CDI", "180 CDI"]},
    "SEAT":          {"Ibiza": ["1.9 TDI", "1.2 TSI", "1.6 TDI"],
                      "Ateca": ["1.5 TSI", "2.0 TDI"],
                      "León": ["1.6 TDI", "2.0 TDI"]},
    "SKODA":         {"Octavia": ["2.0 TDI", "1.6 TDI"],
                      "Fabia": ["1.4 TDI", "1.2 TSI"]},
    "VOLKSWAGEN":    {"Golf": ["1.6 TDI", "2.0 TDI", "1.4 TSI"],
                      "Passat": ["2.0 TDI", "1.6 TDI"],
                      "Polo": ["1.2 TSI", "1.4 TDI"]},
    "RENAULT":       {"Clio": ["1.5 dCi", "1.2 16v"],
                      "Megane": ["1.5 dCi", "1.6 dCi"],
                      "Captur": ["1.5 dCi", "0.9 TCe"]},
    "PEUGEOT":       {"208": ["1.4 HDi", "1.6 HDi"],
                      "308": ["1.6 HDi", "2.0 HDi"],
                      "3008": ["1.6 HDi", "2.0 HDi"]},
    "CITROEN":       {"C4": ["1.6 HDi", "1.6 VTi"],
                      "C3": ["1.4 HDi", "1.2 PureTech"]},
    "OPEL":          {"Corsa": ["1.3 CDTI", "1.2 16v"],
                      "Astra": ["1.7 CDTI", "1.6 CDTI"]},
    "FORD":          {"Focus": ["1.6 TDCi", "2.0 TDCi"],
                      "Fiesta": ["1.5 TDCi", "1.0 EcoBoost"],
                      "Fusion": ["1.4 TDCi"]},
    "NISSAN":        {"Qashqai": ["1.5 dCi", "1.6 dCi"],
                      "Juke": ["1.5 dCi", "1.2 DIG-T"]},
    "TOYOTA":        {"Camry": ["2.5 Hybrid"],
                      "Proace City": ["1.5 D-4D"],
                      "Corolla": ["1.8 Hybrid", "1.4 D-4D"]},
    "HYUNDAI":       {"i30": ["1.6 CRDi", "1.4 CRDi"],
                      "Tucson": ["1.7 CRDi", "2.0 CRDi"]},
    "KIA":           {"Ceed": ["1.6 CRDi", "1.4 CRDi"],
                      "Sportage": ["1.7 CRDi", "2.0 CRDi"]},
}

# Tamaño del coche. Un motor de Polo no vale lo que uno de Clase E, pero un
# retrovisor de Polo sí se parece bastante al de un Clase E. Por eso el segmento
# no se aplica igual a todas las piezas: ver SENSIBILIDAD.
SEGMENTO = {
    "pequeno": 0.70, "medio": 1.00, "grande": 1.30,
}
MODELO_SEGMENTO = {
    "Polo": "pequeno", "Fabia": "pequeno", "Ibiza": "pequeno", "Clio": "pequeno",
    "208": "pequeno", "C3": "pequeno", "Corsa": "pequeno", "Fiesta": "pequeno",
    "Fusion": "pequeno", "Juke": "pequeno", "Captur": "pequeno",
    "Golf": "medio", "Octavia": "medio", "León": "medio", "Astra": "medio",
    "Focus": "medio", "Megane": "medio", "308": "medio", "C4": "medio",
    "Qashqai": "medio", "i30": "medio", "Ceed": "medio", "A3": "medio",
    "Serie 1": "medio", "Clase A": "medio", "CLA": "medio", "Corolla": "medio",
    "Ateca": "medio", "Proace City": "medio",
    "Passat": "grande", "A4": "grande", "Serie 3": "grande", "Q3": "grande",
    "X1": "grande", "Clase E Coupé": "grande", "Camry": "grande",
    "3008": "grande", "Tucson": "grande", "Sportage": "grande",
}
# Cuánto le afecta el tamaño del coche al precio de cada pieza (0 = nada, 1 = todo).
SENSIBILIDAD = {
    "Motor completo": 1.00, "Caja de cambios": 0.95, "Turbo": 0.80,
    "Catalizador": 0.75, "Centralita motor": 0.60, "Cremallera de dirección": 0.55,
    "Portón trasero": 0.55, "Compresor aire acondicionado": 0.50,
    "Puerta delantera derecha": 0.50, "Puerta delantera izquierda": 0.50,
    "Puerta trasera izquierda": 0.50, "Capó": 0.50, "Parachoques delantero": 0.45,
    "Parachoques trasero": 0.45, "Radiador": 0.40, "Intercooler": 0.40,
    "Colector de admisión": 0.40, "Cárter": 0.35, "Airbag volante": 0.35,
    "Cuadro de instrumentos": 0.35, "Aleta delantera izquierda": 0.35,
}
SENSIBILIDAD_POR_DEFECTO = 0.22          # piezas pequeñas: el tamaño casi no influye

ESTADOS = (["Comprobada, funcionando"] * 6 + ["Desmontada de vehículo"] * 3
           + ["Sin comprobar"])
DISPONIBILIDAD = ["En stock"] * 6 + ["Bajo pedido 24-48h"] * 4
LETRAS = "ABCDEFGHJKLMNPQRSTVWXYZ"


def factor_antiguedad(anio: int) -> float:
    """Un recambio de 2021 se paga más que el mismo de 2005."""
    return 0.72 + (anio - 2005) * 0.028      # 2005 -> 0.72 · 2021 -> 1.17


def factor_segmento(pieza: str, modelo: str) -> float:
    """Cuánto encarece (o abarata) el tamaño del coche esta pieza en concreto."""
    tamano = SEGMENTO[MODELO_SEGMENTO.get(modelo, "medio")]
    peso = SENSIBILIDAD.get(pieza, SENSIBILIDAD_POR_DEFECTO)
    return 1 + (tamano - 1) * peso


def formato_euros(valor: float) -> str:
    """1250.5 -> '1.250,50 € + IVA' (formato español, como en la web)."""
    return f"{valor:,.2f} € + IVA".replace(",", "X").replace(".", ",").replace("X", ".")


def generar(n: int, semilla: int = 2026) -> list:
    random.seed(semilla)
    piezas = sorted(RANGOS)
    marcas = sorted(CATALOGO)

    filas, vistas = [], set()
    id_actual = 69100
    intentos = 0
    while len(filas) < n and intentos < n * 60:
        intentos += 1
        marca = random.choice(marcas)
        modelo = random.choice(sorted(CATALOGO[marca]))
        motor = random.choice(CATALOGO[marca][modelo])
        pieza = random.choice(piezas)
        anio = random.randint(2005, 2021)

        clave = (pieza, marca, modelo, motor, anio)
        if clave in vistas:
            continue
        vistas.add(clave)

        minimo, maximo = RANGOS[pieza]
        base = random.uniform(minimo, maximo)
        precio = (base
                  * FACTOR_MARCA.get(marca, 1.0)
                  * factor_segmento(pieza, modelo)
                  * factor_antiguedad(anio)
                  * random.uniform(0.88, 1.12))
        # Recorte: ningún factor puede sacar la pieza de su franja razonable.
        precio = max(minimo * 0.85, min(precio, maximo * 1.45))
        precio = round(precio, 2)

        id_actual += random.randint(1, 3)      # los ids del almacén no son correlativos exactos
        filas.append({
            "id": str(id_actual),
            "referencia_oem": (f"{random.randint(1000, 9999)}{random.choice(LETRAS)}"
                               f"{random.choice(LETRAS)}{random.randint(10, 99)}"
                               f"{random.choice('ABCDEF')}"),
            "pieza": pieza, "marca": marca, "modelo": modelo, "motor": motor,
            "anio": str(anio),
            "estado": random.choice(ESTADOS),
            "garantia": "1 año",
            "disponibilidad": random.choice(DISPONIBILIDAD),
            "precio": formato_euros(precio),
            "url": f"https://desguacesmadridnorte.com/{id_actual}-pieza.html",
            "_valor": precio,
        })
    return filas


def main():
    ap = argparse.ArgumentParser(description="Genera el catálogo sintético de VendIQ")
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--semilla", type=int, default=2026)
    args = ap.parse_args()

    filas = generar(args.n, args.semilla)
    if len(filas) < args.n:
        raise SystemExit(f"Solo se pudieron generar {len(filas)} combinaciones únicas.")

    columnas = ["id", "referencia_oem", "pieza", "marca", "modelo", "motor", "anio",
                "estado", "garantia", "disponibilidad", "precio", "url"]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)

    valores = sorted(f["_valor"] for f in filas)
    print(f"OK. {len(filas)} piezas escritas en {SALIDA.relative_to(BASE)}")
    print(f"   marcas: {len({f['marca'] for f in filas})}  ·  "
          f"tipos de pieza: {len({f['pieza'] for f in filas})}")
    print(f"   precio  min {valores[0]:.2f} €  ·  mediana {valores[len(valores)//2]:.2f} €"
          f"  ·  max {valores[-1]:.2f} €")
    print(f"   valor total del stock: {sum(valores):,.0f} €".replace(",", "."))

    caros = sorted(filas, key=lambda f: -f["_valor"])[:3]
    baratos = sorted(filas, key=lambda f: f["_valor"])[:3]
    print("\n   más caras:")
    for f in caros:
        print(f"     {f['precio']:>18}  {f['pieza']} · {f['marca']} {f['modelo']} {f['anio']}")
    print("   más baratas:")
    for f in baratos:
        print(f"     {f['precio']:>18}  {f['pieza']} · {f['marca']} {f['modelo']} {f['anio']}")


if __name__ == "__main__":
    main()
