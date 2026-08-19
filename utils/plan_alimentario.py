"""
Generador de un plan de comidas de EJEMPLO a partir de los macros objetivo
(proteína/carbohidratos/grasas en gramos) calculados en el módulo de
Nutrición. No es un optimizador nutricional real: reparte los macros en 4
comidas típicas y, para cada una, ofrece 2 alimentos alternativos por
categoría (ej. "200 g de pechuga de pollo o 210 g de carne de res magra")
para que el cliente pueda elegir según lo que tenga disponible. Se genera
en Markdown para que se vea claro tanto al editarlo (admin) como al leerlo
(cliente). Es un punto de partida rápido pensado para editarse antes de
guardarlo (alergias, preferencias, etc.).
"""

from __future__ import annotations

# Macros por 100 g de parte comestible (aproximados, fuente: tablas nutricionales genéricas).
ALIMENTOS_PROTEINA = {
    "Pechuga de pollo": {"kcal": 165, "prot": 31, "carb": 0, "grasa": 3.6},
    "Carne de res magra": {"kcal": 137, "prot": 21, "carb": 0, "grasa": 5},
    "Claras de huevo": {"kcal": 52, "prot": 11, "carb": 0.7, "grasa": 0.2},
    "Atún en agua": {"kcal": 116, "prot": 26, "carb": 0, "grasa": 1},
    "Salmón": {"kcal": 208, "prot": 20, "carb": 0, "grasa": 13},
    "Proteína en polvo (whey)": {"kcal": 380, "prot": 80, "carb": 8, "grasa": 5},
}

ALIMENTOS_CARBOHIDRATO = {
    "Avena": {"kcal": 389, "prot": 17, "carb": 66, "grasa": 7},
    "Arroz blanco cocido": {"kcal": 130, "prot": 2.7, "carb": 28, "grasa": 0.3},
    "Papa cocida": {"kcal": 87, "prot": 2, "carb": 20, "grasa": 0.1},
    "Pan integral": {"kcal": 247, "prot": 13, "carb": 41, "grasa": 3.4},
    "Banana": {"kcal": 89, "prot": 1.1, "carb": 23, "grasa": 0.3},
}

ALIMENTOS_GRASA = {
    "Aceite de oliva": {"kcal": 884, "prot": 0, "carb": 0, "grasa": 100},
    "Aguacate": {"kcal": 160, "prot": 2, "carb": 9, "grasa": 15},
    "Almendras": {"kcal": 579, "prot": 21, "carb": 22, "grasa": 50},
    "Mantequilla de maní": {"kcal": 588, "prot": 25, "carb": 20, "grasa": 50},
}

# (nombre de la comida, % del día, opciones de proteína, de carbohidrato, de grasa)
# Cada categoría trae 2 alternativas para que el cliente elija según lo que tenga.
PLANTILLA_COMIDAS = [
    ("Desayuno", 0.25, ["Claras de huevo", "Atún en agua"], ["Avena", "Pan integral"], ["Almendras", "Mantequilla de maní"]),
    ("Almuerzo", 0.35, ["Pechuga de pollo", "Carne de res magra"], ["Arroz blanco cocido", "Papa cocida"], ["Aceite de oliva", "Aguacate"]),
    ("Cena", 0.30, ["Salmón", "Pechuga de pollo"], ["Papa cocida", "Arroz blanco cocido"], ["Aguacate", "Almendras"]),
    ("Snack", 0.10, ["Proteína en polvo (whey)", "Claras de huevo"], ["Banana", "Avena"], ["Mantequilla de maní", "Almendras"]),
]


def _gramos_para_macro(alimento: dict, macro: str, objetivo_g: float) -> float:
    por_100g = alimento[macro]
    if por_100g <= 0 or objetivo_g <= 0:
        return 0.0
    return (objetivo_g / por_100g) * 100


def _redondear(gramos: float) -> int:
    return int(round(gramos / 5.0)) * 5


def _opciones_texto(alimentos: dict, nombres: list[str], macro: str, objetivo_g: float) -> str:
    partes = []
    for nombre in nombres:
        gramos = _gramos_para_macro(alimentos[nombre], macro, objetivo_g)
        partes.append(f"{_redondear(gramos)} g de {nombre.lower()}")
    return " **o** ".join(partes)


def generar_ejemplo_dieta(proteinas_g: float, carbohidratos_g: float, grasas_g: float) -> str:
    """Devuelve un plan de comidas de ejemplo en Markdown, con alternativas por comida."""
    bloques = []
    for nombre_comida, pct, prot_opciones, carb_opciones, grasa_opciones in PLANTILLA_COMIDAS:
        prot_txt = _opciones_texto(ALIMENTOS_PROTEINA, prot_opciones, "prot", proteinas_g * pct)
        carb_txt = _opciones_texto(ALIMENTOS_CARBOHIDRATO, carb_opciones, "carb", carbohidratos_g * pct)
        grasa_txt = _opciones_texto(ALIMENTOS_GRASA, grasa_opciones, "grasa", grasas_g * pct)

        bloques.append(
            f"**{nombre_comida}**\n"
            f"- Proteína: {prot_txt}\n"
            f"- Carbohidrato: {carb_txt}\n"
            f"- Grasa: {grasa_txt}\n"
            f"- Vegetales libres a elección (brócoli, espinaca, lechuga, tomate)"
        )

    encabezado = (
        f"*Plan personalizado según tus macros: ≈{_redondear(proteinas_g)}g proteína / "
        f"{_redondear(carbohidratos_g)}g carbohidratos / {_redondear(grasas_g)}g grasas al día.*\n\n"
    )
    return encabezado + "\n\n".join(bloques)
