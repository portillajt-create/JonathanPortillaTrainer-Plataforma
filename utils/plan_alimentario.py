"""
Generador de un plan de comidas de EJEMPLO a partir de los macros objetivo
(proteína/carbohidratos/grasas en gramos) calculados en el módulo de
Nutrición. No es un optimizador nutricional real: reparte los macros en 4
comidas típicas y, para cada una, ofrece 2 combinaciones completas de
alimentos (Opción 1 / Opción 2) para que el cliente pueda elegir según lo
que tenga disponible. Se genera
en Markdown para que se vea claro tanto al editarlo (admin) como al leerlo
(cliente). Es un punto de partida rápido pensado para editarse antes de
guardarlo (alergias, preferencias, etc.).
"""

from __future__ import annotations

# Macros por 100 g (aproximados, fuente: tablas nutricionales genéricas).
# El nombre de cada alimento indica el estado en que se debe pesar: "cocido/a"
# significa peso YA COCINADO (como se sirve en el plato); "crudo/a" o "en
# polvo" significa que se pesa ANTES de cocinar (o tal cual, sin cocción).
ALIMENTOS_PROTEINA = {
    "Pechuga de pollo cocida": {"kcal": 165, "prot": 31, "carb": 0, "grasa": 3.6},
    "Carne de res magra cocida": {"kcal": 164, "prot": 26, "carb": 0, "grasa": 7},
    "Claras de huevo crudas": {"kcal": 52, "prot": 11, "carb": 0.7, "grasa": 0.2},
    "Atún en agua (escurrido)": {"kcal": 116, "prot": 26, "carb": 0, "grasa": 1},
    "Proteína en polvo (whey)": {"kcal": 380, "prot": 80, "carb": 8, "grasa": 5},
}

ALIMENTOS_CARBOHIDRATO = {
    "Avena cruda": {"kcal": 389, "prot": 17, "carb": 66, "grasa": 7},
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
    (
        "Desayuno", 0.25,
        ["Claras de huevo crudas", "Atún en agua (escurrido)"],
        ["Avena cruda", "Pan integral"],
        ["Almendras", "Mantequilla de maní"],
    ),
    (
        "Almuerzo", 0.35,
        ["Pechuga de pollo cocida", "Carne de res magra cocida"],
        ["Arroz blanco cocido", "Papa cocida"],
        ["Aceite de oliva", "Aguacate"],
    ),
    (
        "Cena", 0.30,
        ["Pechuga de pollo cocida", "Atún en agua (escurrido)"],
        ["Papa cocida", "Arroz blanco cocido"],
        ["Aguacate", "Almendras"],
    ),
    (
        "Snack", 0.10,
        ["Proteína en polvo (whey)", "Claras de huevo crudas"],
        ["Banana", "Avena cruda"],
        ["Mantequilla de maní", "Almendras"],
    ),
]


def _redondear(gramos: float) -> int:
    return int(round(gramos / 5.0)) * 5


def _det3(m: list[list[float]]) -> float:
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def _resolver_combo(objetivo: tuple[float, float, float], alimentos: list[dict]) -> list[float]:
    """
    Calcula los gramos de 3 alimentos (uno "de proteína", uno "de carbohidrato",
    uno "de grasa") que, comidos JUNTOS, suman exactamente el objetivo de
    proteína/carbohidrato/grasa del bloque — resolviendo el sistema 3x3
    completo en vez de calcular cada alimento mirando solo su macro asignada.

    Esto importa porque ningún alimento real es 100% puro: la avena también
    tiene proteína, las almendras también tienen carbohidratos y proteína,
    etc. Ignorar eso (como se hacía antes) hacía que el total real de comer
    las 3 porciones juntas quedara muy por encima de los macros calculados.
    """
    filas = ["prot", "carb", "grasa"]
    matriz = [[alimentos[col][fila] / 100 for col in range(3)] for fila in filas]

    gramos = None
    det = _det3(matriz)
    if abs(det) > 1e-9:
        gramos = []
        for col in range(3):
            matriz_col = [fila[:] for fila in matriz]
            for fila in range(3):
                matriz_col[fila][col] = objetivo[fila]
            gramos.append(_det3(matriz_col) / det)
        if all(g >= -1e-6 for g in gramos):
            return [max(0.0, g) for g in gramos]

    # El sistema 3x3 pidió una cantidad negativa de algún alimento (ej: el
    # salmón ya aporta de sobra la grasa objetivo por sí solo, y "restar"
    # aguacate no es una opción real). En ese caso se fija en 0 justo el
    # alimento que salió negativo (el más negativo primero) y se resuelven
    # exactamente las otras dos macros con los 2 alimentos restantes; la
    # macro del alimento descartado queda como venga (mejor eso que una
    # cantidad negativa sin sentido).
    orden_k = sorted(range(3), key=lambda i: gramos[i]) if gramos else list(range(3))
    return _resolver_2x2_con_uno_en_cero(objetivo, matriz, orden_k)


def _resolver_2x2_con_uno_en_cero(
    objetivo: tuple[float, float, float], matriz: list[list[float]], orden_k: list[int]
) -> list[float]:
    for k in orden_k:
        activas = [i for i in range(3) if i != k]
        a2 = [[matriz[f][c] for c in activas] for f in activas]
        b2 = [objetivo[f] for f in activas]
        det2 = a2[0][0] * a2[1][1] - a2[0][1] * a2[1][0]
        if abs(det2) < 1e-9:
            continue
        x0 = (b2[0] * a2[1][1] - a2[0][1] * b2[1]) / det2
        x1 = (a2[0][0] * b2[1] - b2[0] * a2[1][0]) / det2
        if x0 >= -1e-6 and x1 >= -1e-6:
            resultado = [0.0, 0.0, 0.0]
            resultado[activas[0]] = max(0.0, x0)
            resultado[activas[1]] = max(0.0, x1)
            return resultado

    # Última salida (combinación de alimentos poco realista): cada uno
    # calculado mirando solo su propia macro, sin ajustar por cruces.
    return [
        (objetivo[i] / matriz[i][i] if matriz[i][i] > 0 else 0.0)
        for i in range(3)
    ]


def _texto_combo(gramos: list[float], nombres: list[str]) -> str:
    return " + ".join(f"{_redondear(g)} g de {nombre.lower()}" for g, nombre in zip(gramos, nombres))


def generar_ejemplo_dieta(proteinas_g: float, carbohidratos_g: float, grasas_g: float) -> str:
    """
    Devuelve un plan de comidas de ejemplo en Markdown: 2 combinaciones
    completas por comida (una con la primera opción de cada categoría, otra
    con la segunda), cada una calculada para sumar los macros exactos de
    ese bloque al comerse junta.
    """
    bloques = []
    for nombre_comida, pct, prot_opciones, carb_opciones, grasa_opciones in PLANTILLA_COMIDAS:
        objetivo = (proteinas_g * pct, carbohidratos_g * pct, grasas_g * pct)

        opciones_texto = []
        for i in range(2):
            nombres = [prot_opciones[i], carb_opciones[i], grasa_opciones[i]]
            alimentos = [ALIMENTOS_PROTEINA[nombres[0]], ALIMENTOS_CARBOHIDRATO[nombres[1]], ALIMENTOS_GRASA[nombres[2]]]
            gramos = _resolver_combo(objetivo, alimentos)
            opciones_texto.append(_texto_combo(gramos, nombres))

        bloques.append(
            f"**{nombre_comida}**\n"
            f"- Opción 1: {opciones_texto[0]}\n"
            f"- Opción 2: {opciones_texto[1]}\n"
            f"- Vegetales libres a elección (brócoli, espinaca, lechuga, tomate)"
        )

    encabezado = (
        f"*Plan personalizado según tus macros: ≈{_redondear(proteinas_g)}g proteína / "
        f"{_redondear(carbohidratos_g)}g carbohidratos / {_redondear(grasas_g)}g grasas al día. "
        "Cada opción está pensada para comerse completa (no mezcles alimentos de la Opción 1 con "
        "los de la Opción 2 en la misma comida).*\n\n"
    )
    return encabezado + "\n\n".join(bloques)
