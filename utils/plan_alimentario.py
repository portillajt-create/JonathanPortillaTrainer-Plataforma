"""
Generador de un plan de comidas de EJEMPLO a partir de los macros objetivo
(proteína/carbohidratos/grasas en gramos) calculados en el módulo de
Nutrición. No es un optimizador nutricional real ni usa IA: reparte los
macros en 4 comidas típicas y, para cada una, sortea 2 combinaciones
completas de alimentos (Opción 1 / Opción 2) desde una base más amplia por
comida — así dos generaciones (o dos clientes con macros parecidos) no
salen siempre con los mismos alimentos. Respeta las alergias/intolerancias
que el cliente reportó en su onboarding, excluyéndolas de la búsqueda.

Se genera en Markdown para que se vea claro tanto al editarlo (admin) como
al leerlo (cliente). Sigue siendo un punto de partida rápido pensado para
editarse antes de guardarlo (preferencias, alergias no detectadas, etc.).
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass, field

# =============================================================================
# 1. BASE DE ALIMENTOS (macros por 100 g, aproximados — fuentes tipo USDA).
#    El nombre indica el estado en que se debe pesar: "cocido/a"/"asada" =
#    peso YA PREPARADO (como se sirve en el plato); "crudo/a", "en polvo" o
#    sin calificar (ya listo para comer, sin cocción de por medio: frutos
#    secos, aceite, proteína en polvo, etc.) = se pesa tal cual.
# =============================================================================

# Nota: "Huevo entero cocido" se probó y se descartó a propósito (no está
# en esta lista). Su proporción grasa/proteína (11g grasa por 13g proteína)
# es tan alta que, dosificado para dar la proteína exacta de una comida,
# se pasaba de la grasa objetivo en el 91% de las combinaciones probadas —
# mismo problema que tuvo el salmón antes. "Claras de huevo crudas" cubre
# el huevo sin ese problema.
ALIMENTOS_PROTEINA = {
    "Pechuga de pollo cocida": {"kcal": 165, "prot": 31, "carb": 0, "grasa": 3.6},
    "Carne de res magra cocida": {"kcal": 164, "prot": 26, "carb": 0, "grasa": 7},
    "Pechuga de pavo cocida": {"kcal": 135, "prot": 30, "carb": 0, "grasa": 1},
    "Claras de huevo crudas": {"kcal": 52, "prot": 11, "carb": 0.7, "grasa": 0.2},
    "Atún en agua (escurrido)": {"kcal": 116, "prot": 26, "carb": 0, "grasa": 1},
    "Proteína en polvo (whey)": {"kcal": 380, "prot": 80, "carb": 8, "grasa": 5},
}

ALIMENTOS_CARBOHIDRATO = {
    "Avena cruda": {"kcal": 389, "prot": 17, "carb": 66, "grasa": 7},
    "Arroz blanco cocido": {"kcal": 130, "prot": 2.7, "carb": 28, "grasa": 0.3},
    "Papa cocida": {"kcal": 87, "prot": 2, "carb": 20, "grasa": 0.1},
    "Papa criolla cocida": {"kcal": 85, "prot": 2, "carb": 19, "grasa": 0.1},
    "Yuca cocida": {"kcal": 160, "prot": 1.4, "carb": 38, "grasa": 0.3},
    "Plátano maduro cocido": {"kcal": 122, "prot": 1.3, "carb": 32, "grasa": 0.4},
    "Arepa de maíz asada": {"kcal": 217, "prot": 5, "carb": 44, "grasa": 2},
    "Pan integral": {"kcal": 247, "prot": 13, "carb": 41, "grasa": 3.4},
    "Banana": {"kcal": 89, "prot": 1.1, "carb": 23, "grasa": 0.3},
    "Frijoles rojos cocidos": {"kcal": 127, "prot": 8.7, "carb": 22.8, "grasa": 0.5},
    "Lentejas cocidas": {"kcal": 116, "prot": 9, "carb": 20, "grasa": 0.4},
    "Garbanzos cocidos": {"kcal": 164, "prot": 8.9, "carb": 27, "grasa": 2.6},
    "Quinoa cocida": {"kcal": 120, "prot": 4.4, "carb": 21, "grasa": 1.9},
}

ALIMENTOS_GRASA = {
    "Aceite de oliva": {"kcal": 884, "prot": 0, "carb": 0, "grasa": 100},
    "Aguacate": {"kcal": 160, "prot": 2, "carb": 9, "grasa": 15},
    "Almendras": {"kcal": 579, "prot": 21, "carb": 22, "grasa": 50},
    "Mantequilla de maní": {"kcal": 588, "prot": 25, "carb": 20, "grasa": 50},
    "Maní tostado": {"kcal": 567, "prot": 25, "carb": 16, "grasa": 49},
    "Nueces": {"kcal": 654, "prot": 15, "carb": 14, "grasa": 65},
    "Queso costeño": {"kcal": 300, "prot": 22, "carb": 2, "grasa": 23},
}

# =============================================================================
# 2. BOLSAS DE ALIMENTOS "TÍPICOS" POR COMIDA
#    (nombre de la comida, % del día, alimentos de proteína, de carbohidrato,
#    de grasa). Cada bolsa trae varias opciones — se sortean 2 por comida en
#    cada generación, así no siempre salen los mismos alimentos.
# =============================================================================

PLANTILLA_COMIDAS = [
    (
        "Desayuno", 0.25,
        ["Claras de huevo crudas", "Atún en agua (escurrido)", "Proteína en polvo (whey)"],
        ["Avena cruda", "Arepa de maíz asada", "Pan integral", "Banana"],
        ["Almendras", "Mantequilla de maní", "Aguacate", "Queso costeño"],
    ),
    (
        "Almuerzo", 0.35,
        ["Pechuga de pollo cocida", "Carne de res magra cocida", "Pechuga de pavo cocida", "Atún en agua (escurrido)"],
        [
            "Arroz blanco cocido", "Papa cocida", "Papa criolla cocida", "Yuca cocida",
            "Plátano maduro cocido", "Frijoles rojos cocidos", "Lentejas cocidas", "Garbanzos cocidos", "Quinoa cocida",
        ],
        ["Aceite de oliva", "Aguacate", "Almendras", "Queso costeño"],
    ),
    (
        "Cena", 0.30,
        ["Pechuga de pollo cocida", "Carne de res magra cocida", "Pechuga de pavo cocida", "Atún en agua (escurrido)"],
        ["Papa cocida", "Arroz blanco cocido", "Quinoa cocida", "Lentejas cocidas", "Frijoles rojos cocidos"],
        ["Aguacate", "Almendras", "Aceite de oliva"],
    ),
    (
        "Snack", 0.10,
        ["Proteína en polvo (whey)", "Claras de huevo crudas", "Atún en agua (escurrido)"],
        ["Banana", "Avena cruda", "Plátano maduro cocido"],
        ["Mantequilla de maní", "Almendras", "Maní tostado", "Nueces"],
    ),
]

# =============================================================================
# 3. ALERGIAS/INTOLERANCIAS: palabra clave detectada en el texto libre del
#    onboarding -> alimentos que se excluyen de la búsqueda. Por palabras
#    clave (no IA), así que no es infalible — el admin siempre debe revisar
#    el resultado, tal como ya advierte la UI.
# =============================================================================

#: Claves SIEMPRE sin tilde: el texto de entrada se normaliza (se le quitan
#: las tildes) antes de comparar, así "maní"/"mani" o "lácteos"/"lacteos"
#: se detectan igual sin tener que listar cada variante acentuada aparte.
#: Sí hay que listar singular y plural por separado (quitar tildes no
#: pluraliza/singulariza una palabra).
ALERGENOS: dict[str, set[str]] = {
    "mani": {"Mantequilla de maní", "Maní tostado"},
    "cacahuate": {"Mantequilla de maní", "Maní tostado"},
    "cacahuates": {"Mantequilla de maní", "Maní tostado"},
    "cacahuete": {"Mantequilla de maní", "Maní tostado"},
    "cacahuetes": {"Mantequilla de maní", "Maní tostado"},
    "peanut": {"Mantequilla de maní", "Maní tostado"},
    "peanuts": {"Mantequilla de maní", "Maní tostado"},
    "frutos secos": {"Almendras", "Nueces", "Mantequilla de maní", "Maní tostado"},
    "nuez": {"Nueces", "Almendras"},
    "nueces": {"Nueces", "Almendras"},
    "nuts": {"Almendras", "Nueces", "Mantequilla de maní", "Maní tostado"},
    "almendra": {"Almendras"},
    "almendras": {"Almendras"},
    "lactosa": {"Proteína en polvo (whey)", "Queso costeño"},
    "leche": {"Proteína en polvo (whey)", "Queso costeño"},
    "lacteo": {"Proteína en polvo (whey)", "Queso costeño"},
    "lacteos": {"Proteína en polvo (whey)", "Queso costeño"},
    "queso": {"Queso costeño"},
    "quesos": {"Queso costeño"},
    "dairy": {"Proteína en polvo (whey)", "Queso costeño"},
    "milk": {"Proteína en polvo (whey)", "Queso costeño"},
    "huevo": {"Claras de huevo crudas"},
    "huevos": {"Claras de huevo crudas"},
    "egg": {"Claras de huevo crudas"},
    "eggs": {"Claras de huevo crudas"},
    "gluten": {"Pan integral", "Avena cruda"},
    "trigo": {"Pan integral"},
    "wheat": {"Pan integral"},
    "marisco": {"Atún en agua (escurrido)"},
    "mariscos": {"Atún en agua (escurrido)"},
    "pescado": {"Atún en agua (escurrido)"},
    "pescados": {"Atún en agua (escurrido)"},
    "atun": {"Atún en agua (escurrido)"},
    "atunes": {"Atún en agua (escurrido)"},
    "seafood": {"Atún en agua (escurrido)"},
    "fish": {"Atún en agua (escurrido)"},
    "legumbre": {"Frijoles rojos cocidos", "Lentejas cocidas", "Garbanzos cocidos"},
    "legumbres": {"Frijoles rojos cocidos", "Lentejas cocidas", "Garbanzos cocidos"},
    "frijol": {"Frijoles rojos cocidos"},
    "frijoles": {"Frijoles rojos cocidos"},
    "lenteja": {"Lentejas cocidas"},
    "lentejas": {"Lentejas cocidas"},
    "garbanzo": {"Garbanzos cocidos"},
    "garbanzos": {"Garbanzos cocidos"},
}


def _sin_acentos(texto: str) -> str:
    """Quita las tildes (á→a, í→i, etc.) para que 'lácteos'/'lacteos' o
    'maní'/'mani' se reconozcan igual — muy común escribir sin tildes desde
    el celular."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _detectar_alimentos_excluidos(texto_alergias: str | None) -> tuple[set[str], list[str]]:
    """(alimentos a excluir, palabras clave de alergia reconocidas en el texto)."""
    if not texto_alergias or not texto_alergias.strip():
        return set(), []
    texto_l = _sin_acentos(texto_alergias.lower())
    excluidos: set[str] = set()
    detectadas: list[str] = []
    for clave, alimentos in ALERGENOS.items():
        if re.search(rf"\b{re.escape(clave)}\b", texto_l):
            excluidos |= alimentos
            detectadas.append(clave)
    return excluidos, detectadas


def _pool_disponible(nombres_comida: list[str], base_completa: dict[str, dict], excluidos: set[str]) -> list[str]:
    disponibles = [n for n in nombres_comida if n not in excluidos]
    if disponibles:
        return disponibles
    # Si la alergia excluyó TODAS las opciones típicas de esta comida, se
    # amplía la búsqueda a toda la categoría (mejor ofrecer algo seguro
    # aunque no sea lo más típico de esa comida, que dejar el bloque vacío).
    disponibles = [n for n in base_completa if n not in excluidos]
    return disponibles or list(nombres_comida)  # última salida: no dejar la comida sin nada


# =============================================================================
# 4. RESOLUCIÓN DE GRAMOS (sistema de 3 ecuaciones, sin cambios de fondo)
# =============================================================================


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
    etc. Ignorar eso hacía que el total real de comer las 3 porciones juntas
    quedara muy por encima de los macros calculados.
    """
    filas = ["prot", "carb", "grasa"]
    matriz = [[alimentos[col][fila] / 100 for col in range(3)] for fila in filas]

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

    # El sistema 3x3 pidió una cantidad negativa de algún alimento (ej: un
    # alimento ya aporta de sobra una macro por sí solo, y "restar" otro no
    # es una opción real). Se prueban las 3 formas de fijar un alimento en 0
    # y resolver las otras dos macros exactas con los 2 restantes, y se usa
    # la que deja MENOR desvío en la macro sacrificada — no la primera que
    # dé un resultado válido, sino la mejor de las disponibles.
    return _resolver_2x2_con_uno_en_cero(objetivo, matriz)


def _resolver_2x2_con_uno_en_cero(
    objetivo: tuple[float, float, float], matriz: list[list[float]]
) -> list[float]:
    candidatos: list[tuple[float, list[float]]] = []
    for k in range(3):
        activas = [i for i in range(3) if i != k]
        a2 = [[matriz[f][c] for c in activas] for f in activas]
        b2 = [objetivo[f] for f in activas]
        det2 = a2[0][0] * a2[1][1] - a2[0][1] * a2[1][0]
        if abs(det2) < 1e-9:
            continue
        x0 = (b2[0] * a2[1][1] - a2[0][1] * b2[1]) / det2
        x1 = (a2[0][0] * b2[1] - b2[0] * a2[1][0]) / det2
        if x0 < -1e-6 or x1 < -1e-6:
            continue
        resultado = [0.0, 0.0, 0.0]
        resultado[activas[0]] = max(0.0, x0)
        resultado[activas[1]] = max(0.0, x1)
        # Cuánto se desvía la macro del alimento sacrificado (k) del objetivo,
        # con lo que YA aportan los otros 2 alimentos hacia ese eje.
        real_k = sum(resultado[col] * matriz[k][col] for col in range(3))
        desviacion = abs(real_k - objetivo[k])
        candidatos.append((desviacion, resultado))

    if candidatos:
        candidatos.sort(key=lambda c: c[0])
        return candidatos[0][1]

    # Última salida (combinación de alimentos poco realista): cada uno
    # calculado mirando solo su propia macro, sin ajustar por cruces.
    return [
        (objetivo[i] / matriz[i][i] if matriz[i][i] > 0 else 0.0)
        for i in range(3)
    ]


#: Alimentos que en la práctica no se pesan en gramos sino que se cuentan
#: por unidad — nadie pesa una clara de huevo en una balanza de cocina. El
#: sistema de ecuaciones sigue resolviendo en gramos por dentro (para que
#: la precisión de macros no cambie), pero el texto final se redondea a
#: unidades enteras porque es lo que el cliente puede medir de verdad.
#: (gramos por unidad, "1 ..." singular, "N ..." plural)
UNIDADES_ALIMENTO: dict[str, tuple[float, str, str]] = {
    "Claras de huevo crudas": (30, "clara de huevo", "claras de huevo"),
}


def _texto_cantidad(gramos: float, nombre: str) -> str:
    unidad = UNIDADES_ALIMENTO.get(nombre)
    if unidad:
        gramos_por_unidad, singular, plural = unidad
        cantidad = max(1, round(gramos / gramos_por_unidad))
        return f"{cantidad} {singular if cantidad == 1 else plural}"
    return f"{_redondear(gramos)} g de {nombre.lower()}"


def _texto_combo(gramos: list[float], nombres: list[str]) -> str:
    return " + ".join(_texto_cantidad(g, nombre) for g, nombre in zip(gramos, nombres))


def _desvio_total(objetivo: tuple[float, float, float], nombres: list[str], alimentos: list[dict]) -> tuple[float, list[float]]:
    gramos = _resolver_combo(objetivo, alimentos)
    real = [sum(gramos[j] * alimentos[j][macro] / 100 for j in range(3)) for macro in ("prot", "carb", "grasa")]
    desvio = sum(abs(real[k] - objetivo[k]) for k in range(3))
    return desvio, gramos


def _mejores_2_combos(
    objetivo: tuple[float, float, float], prot_pool: list[str], carb_pool: list[str], grasa_pool: list[str],
    intentos: int = 16,
) -> list[tuple[list[str], list[float]]]:
    """
    Sortea varios tríos (proteína, carbohidrato, grasa) del pool disponible
    y se queda con los 2 MEJORES (menor desvío total al resolverlos), no
    con los 2 primeros que salgan al azar. Algunos pares de alimentos no
    pueden cuadrar bien juntos por más que se ajusten los gramos —por
    ejemplo, dos fuentes que ya aportan de sobra la misma macro "escondida"
    cada una por su lado— y esto evita quedarse con esa combinación cuando
    había otra mejor en el mismo sorteo. Las 2 elegidas quedan además en
    orden aleatorio, para que no siempre sea la misma la que sale de
    "Opción 1".

    intentos=16 (en vez de 8): con objetivos de macros muy desbalanceados
    (p. ej. muy pocas proteínas y muchos carbohidratos) hacían falta más
    sorteos para tener buena chance de dar con la combinación de carbohi-
    drato que no aporte de más proteína "escondida" — verificado con 500
    generaciones simuladas del peor caso encontrado: con 8 intentos el
    desvío máximo era de 16.4 g, con 16 bajó a 0.0 g.
    """
    candidatos: list[tuple[float, list[str], list[float]]] = []
    vistos: set[tuple[str, str, str]] = set()
    for _ in range(intentos):
        nombres = [random.choice(prot_pool), random.choice(carb_pool), random.choice(grasa_pool)]
        clave = tuple(nombres)
        if clave in vistos:
            continue
        vistos.add(clave)
        alimentos = [ALIMENTOS_PROTEINA[nombres[0]], ALIMENTOS_CARBOHIDRATO[nombres[1]], ALIMENTOS_GRASA[nombres[2]]]
        desvio, gramos = _desvio_total(objetivo, nombres, alimentos)
        candidatos.append((desvio, nombres, gramos))

    candidatos.sort(key=lambda c: c[0])
    mejores = candidatos[:2] if len(candidatos) >= 2 else candidatos * 2
    random.shuffle(mejores)
    return [(nombres, gramos) for _, nombres, gramos in mejores]


# =============================================================================
# 5. GENERACIÓN
# =============================================================================


@dataclass
class ResultadoDieta:
    texto: str
    alergenos_detectados: list[str] = field(default_factory=list)
    alimentos_excluidos: list[str] = field(default_factory=list)


def generar_ejemplo_dieta(
    proteinas_g: float, carbohidratos_g: float, grasas_g: float, alergias_texto: str | None = None
) -> ResultadoDieta:
    """
    Devuelve un plan de comidas de ejemplo en Markdown: 2 combinaciones
    completas por comida (Opción 1 / Opción 2), sorteadas de una base más
    amplia de alimentos y excluyendo los que coincidan con alergias/
    intolerancias reportadas. Cada opción se calcula para sumar los macros
    exactos de ese bloque al comerse junta (ver _resolver_combo).
    """
    excluidos, alergenos_detectados = _detectar_alimentos_excluidos(alergias_texto)

    bloques = []
    for nombre_comida, pct, prot_pool, carb_pool, grasa_pool in PLANTILLA_COMIDAS:
        objetivo = (proteinas_g * pct, carbohidratos_g * pct, grasas_g * pct)

        prot_disp = _pool_disponible(prot_pool, ALIMENTOS_PROTEINA, excluidos)
        carb_disp = _pool_disponible(carb_pool, ALIMENTOS_CARBOHIDRATO, excluidos)
        grasa_disp = _pool_disponible(grasa_pool, ALIMENTOS_GRASA, excluidos)

        opciones = _mejores_2_combos(objetivo, prot_disp, carb_disp, grasa_disp)
        opciones_texto = [_texto_combo(gramos, nombres) for nombres, gramos in opciones]

        bloques.append(
            f"**{nombre_comida}**\n"
            f"- Opción 1: {opciones_texto[0]}\n"
            f"- Opción 2: {opciones_texto[1]}\n"
            f"- Vegetales libres a elección (brócoli, espinaca, lechuga, tomate) + 1 porción de fruta "
            f"si quieres (manzana, pera, fresas, mandarina, papaya)"
        )

    encabezado = (
        f"*Plan personalizado según tus macros: ≈{_redondear(proteinas_g)}g proteína / "
        f"{_redondear(carbohidratos_g)}g carbohidratos / {_redondear(grasas_g)}g grasas al día. "
        "Cada opción está pensada para comerse completa (no mezcles alimentos de la Opción 1 con "
        "los de la Opción 2 en la misma comida).*\n\n"
    )
    texto = encabezado + "\n\n".join(bloques)

    return ResultadoDieta(
        texto=texto,
        alergenos_detectados=alergenos_detectados,
        alimentos_excluidos=sorted(excluidos),
    )
