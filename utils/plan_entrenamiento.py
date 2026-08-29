"""
Generador de una rutina de EJEMPLO a partir del nombre y la descripción que
escribe el admin (ej. "Full body 3 días" / "quiero entrenar en casa con
mancuernas, push pull legs"). No usa IA: interpreta el texto por palabras
clave (idioma, ubicación, número de días, tipo de split) y arma la rutina
combinando plantillas de días con una base de ejercicios por músculo.

Por ser un sistema de palabras clave (no de comprensión de lenguaje real),
SIEMPRE hay que revisar lo detectado: la función devuelve también qué
entendió, para mostrárselo al admin antes de que confíe en el resultado.
Es un punto de partida rápido pensado para editarse, igual que el
generador de dietas (ver utils/plan_alimentario.py).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# Mismas cadenas que DIAS/MUSCULOS en modules/rutinas.py — se duplican en vez
# de importarlas para no crear un import circular (rutinas.py importa de
# aquí, no al revés).
DIAS_APP = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5", "Día 6", "Día 7"]

# =============================================================================
# 1. DETECCIÓN DE PARÁMETROS EN EL TEXTO (nombre + descripción)
# =============================================================================

# Palabras EXCLUSIVAS de cada idioma (a propósito NO incluye términos como
# "full body"/"push pull legs": son jerga de gimnasio que se usa igual en
# español, así que no sirven para distinguir el idioma del texto).
_PALABRAS_ES = {
    "días", "dia", "días", "con", "sin", "quiero", "casa", "gimnasio", "entrenar",
    "rutina", "pierna", "piernas", "espalda", "pecho", "brazo", "brazos", "hombro",
    "hombros", "semana", "ejercicios", "ejercicio", "libres", "libre", "cuerpo",
    "completo", "tengo", "disponible", "peso", "corporal", "mancuernas", "mancuerna",
}
_PALABRAS_EN = {
    "days", "day", "with", "without", "want", "home", "gym", "train", "training",
    "routine", "leg", "legs", "back", "chest", "arm", "arms", "shoulder", "shoulders",
    "week", "exercises", "exercise", "free", "weight", "weights", "body", "available",
    "only", "have", "dumbbells", "dumbbell", "bodyweight",
}

_CASA_RX = re.compile(r"\b(casa|hogar|home|apartamento|departamento)\b", re.IGNORECASE)
_GYM_RX = re.compile(r"\b(gimnasio|gym|m[aá]quinas?|machines?)\b", re.IGNORECASE)

_NUM_PALABRA = {
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
}
# Acepta cualquier número de 1-2 cifras (no solo 2-7): si alguien escribe "10
# días" se detecta igual y se recorta a 7 más abajo, en vez de ignorarse en
# silencio y caer al valor por defecto del split.
_DIAS_RX = re.compile(r"\b(\d{1,2})\s*(?:d[ií]as?|days?)\b", re.IGNORECASE)

# Orden importa poco (se buscan todas), pero se listan de más a menos
# específico para que quede claro en el código.
_SPLIT_PATRONES: list[tuple[str, re.Pattern]] = [
    ("ppl", re.compile(
        r"push[\s/-]*pull[\s/-]*legs?|\bppl\b|empuje.*(jal[oó]n|tir[oó]n).*pierna", re.IGNORECASE
    )),
    ("upper_lower", re.compile(
        r"upper[\s/-]*lower|torso[\s/-]*pierna|tren superior.*tren inferior", re.IGNORECASE
    )),
    ("arnold", re.compile(r"\barnold\b", re.IGNORECASE)),
    ("weider", re.compile(
        r"\bweider\b|bro[\s-]*split|un m[uú]sculo por d[ií]a|un solo grupo muscular", re.IGNORECASE
    )),
    ("full_body", re.compile(r"full[\s-]*body|cuerpo completo", re.IGNORECASE)),
]

# Duración por defecto de cada split cuando el texto no dice el número de días.
_DIAS_DEFECTO = {"full_body": 3, "upper_lower": 4, "ppl": 3, "weider": 5, "arnold": 3}


def detectar_idioma(texto: str) -> str:
    """'es' o 'en', según qué set de palabras exclusivas aparece más veces."""
    palabras = set(re.findall(r"[a-záéíóúñ]+", texto.lower()))
    puntos_es = len(palabras & _PALABRAS_ES)
    puntos_en = len(palabras & _PALABRAS_EN)
    return "en" if puntos_en > puntos_es else "es"


def detectar_ubicacion(texto: str) -> str:
    """'casa' o 'gimnasio' (default gimnasio si no hay pistas claras)."""
    hay_casa = bool(_CASA_RX.search(texto))
    hay_gym = bool(_GYM_RX.search(texto))
    if hay_casa and not hay_gym:
        return "casa"
    return "gimnasio"


def detectar_dias(texto: str) -> int | None:
    m = _DIAS_RX.search(texto)
    if m:
        return int(m.group(1))
    texto_l = texto.lower()
    for palabra, n in _NUM_PALABRA.items():
        if re.search(rf"\b{palabra}\b\s*(?:d[ií]as?|days?)", texto_l):
            return n
    return None


def detectar_splits(texto: str) -> list[str]:
    """
    Hasta 2 tipos de split detectados, en el ORDEN en que aparecen en el texto
    (no en el orden de _SPLIT_PATRONES) para que el resumen que ve el admin
    coincida con cómo escribió la descripción. ['full_body'] si no se
    reconoce nada.
    """
    coincidencias = []
    for clave, patron in _SPLIT_PATRONES:
        m = patron.search(texto)
        if m:
            coincidencias.append((m.start(), clave))
    coincidencias.sort(key=lambda c: c[0])
    encontrados = [clave for _, clave in coincidencias]
    return encontrados[:2] if encontrados else ["full_body"]


# =============================================================================
# 2. BASE DE EJERCICIOS POR MÚSCULO Y EQUIPO
#    (nombre_es, nombre_en, "compuesto" | "aislamiento")
# =============================================================================

EJERCICIOS: dict[tuple[str, str], list[tuple[str, str, str]]] = {
    ("Pectoral", "gimnasio"): [
        ("Press de banca con barra", "Barbell bench press", "compuesto"),
        ("Press inclinado con mancuernas", "Incline dumbbell press", "compuesto"),
        ("Press de pecho en máquina", "Chest press machine", "compuesto"),
        ("Fondos en paralelas", "Dips", "compuesto"),
        ("Aperturas en polea", "Cable flyes", "aislamiento"),
        ("Aperturas con mancuernas", "Dumbbell flyes", "aislamiento"),
    ],
    ("Pectoral", "casa"): [
        ("Flexiones de pecho", "Push-ups", "compuesto"),
        ("Press de pecho con mancuernas en el piso", "Dumbbell floor press", "compuesto"),
        ("Flexiones con manos elevadas", "Incline push-ups", "compuesto"),
        ("Flexiones con pies elevados", "Decline push-ups", "compuesto"),
        ("Aperturas con mancuernas en el piso", "Dumbbell floor flyes", "aislamiento"),
    ],
    ("Espalda", "gimnasio"): [
        ("Dominadas", "Pull-ups", "compuesto"),
        ("Remo con barra", "Barbell row", "compuesto"),
        ("Jalón al pecho en polea", "Lat pulldown", "compuesto"),
        ("Remo en máquina", "Seated cable row", "compuesto"),
        ("Remo con mancuerna a una mano", "One-arm dumbbell row", "compuesto"),
        ("Pullover en polea", "Cable pullover", "aislamiento"),
    ],
    ("Espalda", "casa"): [
        ("Remo con mancuerna a una mano", "One-arm dumbbell row", "compuesto"),
        ("Remo renegado", "Renegade row", "compuesto"),
        ("Remo con banda elástica", "Band row", "compuesto"),
        ("Pullover con mancuerna", "Dumbbell pullover", "aislamiento"),
        ("Superman", "Superman", "aislamiento"),
    ],
    ("Cuádriceps", "gimnasio"): [
        ("Sentadilla con barra", "Barbell squat", "compuesto"),
        ("Prensa de piernas", "Leg press", "compuesto"),
        ("Zancadas con mancuernas", "Dumbbell lunges", "compuesto"),
        ("Sentadilla búlgara", "Bulgarian split squat", "compuesto"),
        ("Extensión de cuádriceps en máquina", "Leg extension", "aislamiento"),
    ],
    ("Cuádriceps", "casa"): [
        ("Sentadilla con mancuernas (goblet)", "Goblet squat", "compuesto"),
        ("Zancadas", "Bodyweight lunges", "compuesto"),
        ("Sentadilla búlgara con mancuernas", "Bulgarian split squat", "compuesto"),
        ("Sentadilla salto", "Jump squat", "aislamiento"),
        ("Sentadilla sumo con mancuerna", "Dumbbell sumo squat", "compuesto"),
    ],
    ("Isquios", "gimnasio"): [
        ("Peso muerto rumano con barra", "Barbell RDL", "compuesto"),
        ("Curl femoral en máquina", "Leg curl machine", "aislamiento"),
        ("Peso muerto rumano con mancuernas", "Dumbbell RDL", "compuesto"),
        ("Hip thrust con barra", "Barbell hip thrust", "compuesto"),
    ],
    ("Isquios", "casa"): [
        ("Peso muerto rumano con mancuernas", "Dumbbell RDL", "compuesto"),
        ("Peso muerto a una pierna", "Single-leg deadlift", "compuesto"),
        ("Puente de glúteo a una pierna", "Single-leg glute bridge", "aislamiento"),
        ("Curl femoral nórdico", "Nordic curl", "aislamiento"),
    ],
    ("Glúteo", "gimnasio"): [
        ("Hip thrust con barra", "Barbell hip thrust", "compuesto"),
        ("Sentadilla sumo con mancuerna", "Dumbbell sumo squat", "compuesto"),
        ("Patada de glúteo en polea", "Cable kickback", "aislamiento"),
        ("Abducción de cadera en máquina", "Hip abduction machine", "aislamiento"),
    ],
    ("Glúteo", "casa"): [
        ("Puente de glúteo", "Glute bridge", "aislamiento"),
        ("Zancada búlgara", "Bulgarian split squat", "compuesto"),
        ("Sentadilla sumo con mancuerna", "Dumbbell sumo squat", "compuesto"),
        ("Patada de glúteo", "Donkey kicks", "aislamiento"),
    ],
    ("Hombros", "gimnasio"): [
        ("Press militar con barra", "Barbell overhead press", "compuesto"),
        ("Press Arnold con mancuernas", "Arnold press", "compuesto"),
        ("Elevaciones laterales con mancuernas", "Lateral raises", "aislamiento"),
        ("Elevaciones frontales", "Front raises", "aislamiento"),
        ("Pájaros (deltoide posterior)", "Rear delt fly", "aislamiento"),
    ],
    ("Hombros", "casa"): [
        ("Press militar con mancuernas", "Dumbbell overhead press", "compuesto"),
        ("Flexiones pike", "Pike push-ups", "compuesto"),
        ("Elevaciones laterales con mancuernas", "Lateral raises", "aislamiento"),
        ("Elevaciones frontales con mancuernas", "Front raises", "aislamiento"),
        ("Pájaros con mancuernas", "Rear delt fly", "aislamiento"),
    ],
    ("Bíceps", "gimnasio"): [
        ("Curl con barra", "Barbell curl", "aislamiento"),
        ("Curl martillo con mancuernas", "Hammer curl", "aislamiento"),
        ("Curl en polea baja", "Cable curl", "aislamiento"),
        ("Curl concentrado", "Concentration curl", "aislamiento"),
    ],
    ("Bíceps", "casa"): [
        ("Curl con mancuernas", "Dumbbell curl", "aislamiento"),
        ("Curl martillo con mancuernas", "Hammer curl", "aislamiento"),
        ("Curl concentrado", "Concentration curl", "aislamiento"),
        ("Curl con banda elástica", "Band curl", "aislamiento"),
    ],
    ("Tríceps", "gimnasio"): [
        ("Extensión de tríceps en polea", "Triceps pushdown", "aislamiento"),
        ("Press francés con barra", "Skull crushers", "aislamiento"),
        ("Fondos en banco", "Bench dips", "compuesto"),
        ("Extensión de tríceps sobre la cabeza con mancuerna", "Overhead triceps extension", "aislamiento"),
    ],
    ("Tríceps", "casa"): [
        ("Fondos en silla", "Chair dips", "compuesto"),
        ("Flexiones cerradas", "Close-grip push-ups", "compuesto"),
        ("Extensión de tríceps con mancuerna", "Overhead triceps extension", "aislamiento"),
        ("Patada de tríceps", "Triceps kickback", "aislamiento"),
    ],
    ("Trapecio", "gimnasio"): [
        ("Encogimientos con barra", "Barbell shrugs", "aislamiento"),
        ("Encogimientos con mancuernas", "Dumbbell shrugs", "aislamiento"),
    ],
    ("Trapecio", "casa"): [
        ("Encogimientos con mancuernas", "Dumbbell shrugs", "aislamiento"),
    ],
    ("Pantorrillas", "gimnasio"): [
        ("Elevación de talones de pie", "Standing calf raise", "aislamiento"),
        ("Elevación de talones sentado", "Seated calf raise", "aislamiento"),
    ],
    ("Pantorrillas", "casa"): [
        ("Elevación de talones de pie", "Standing calf raise", "aislamiento"),
        ("Elevación de talones a una pierna", "Single-leg calf raise", "aislamiento"),
    ],
    ("Antebrazos", "gimnasio"): [
        ("Curl de muñeca con barra", "Barbell wrist curl", "aislamiento"),
        ("Farmer walk", "Farmer's carry", "compuesto"),
    ],
    ("Antebrazos", "casa"): [
        ("Curl de muñeca con mancuerna", "Dumbbell wrist curl", "aislamiento"),
    ],
    ("Abdomen", "gimnasio"): [
        ("Rueda abdominal", "Ab wheel rollout", "compuesto"),
        ("Plancha", "Plank", "aislamiento"),
        ("Elevación de piernas colgado", "Hanging leg raises", "aislamiento"),
        ("Crunch en polea", "Cable crunch", "aislamiento"),
    ],
    ("Abdomen", "casa"): [
        ("Plancha", "Plank", "aislamiento"),
        ("Crunch", "Crunch", "aislamiento"),
        ("Elevación de piernas", "Leg raises", "aislamiento"),
        ("Plancha lateral", "Side plank", "aislamiento"),
    ],
}


# =============================================================================
# 3. PLANTILLAS DE DÍA (arquetipo -> [(músculo, cantidad de ejercicios), ...])
#    y PLANTILLAS DE SPLIT (split -> secuencia de arquetipos, se repite/rota
#    para cubrir la cantidad de días que corresponda).
# =============================================================================

ARQUETIPOS: dict[str, list[tuple[str, int]]] = {
    "full_body": [
        ("Pectoral", 1), ("Espalda", 1), ("Cuádriceps", 1), ("Isquios", 1), ("Hombros", 1), ("Abdomen", 1),
    ],
    "upper": [("Pectoral", 2), ("Espalda", 2), ("Hombros", 1), ("Bíceps", 1), ("Tríceps", 1)],
    "lower": [("Cuádriceps", 2), ("Isquios", 1), ("Glúteo", 1), ("Pantorrillas", 1), ("Abdomen", 1)],
    "push": [("Pectoral", 2), ("Hombros", 2), ("Tríceps", 2)],
    "pull": [("Espalda", 3), ("Trapecio", 1), ("Bíceps", 2)],
    "legs": [("Cuádriceps", 2), ("Isquios", 2), ("Glúteo", 1), ("Pantorrillas", 1)],
    "pecho_triceps": [("Pectoral", 3), ("Tríceps", 2)],
    "espalda_biceps": [("Espalda", 3), ("Bíceps", 2)],
    "pierna_weider": [("Cuádriceps", 2), ("Isquios", 2), ("Glúteo", 1), ("Pantorrillas", 1)],
    "hombro_abdomen": [("Hombros", 3), ("Abdomen", 2)],
    "brazo": [("Bíceps", 2), ("Tríceps", 2), ("Antebrazos", 1)],
    "pecho_espalda_arnold": [("Pectoral", 2), ("Espalda", 2)],
    "hombro_brazo_arnold": [("Hombros", 2), ("Bíceps", 1), ("Tríceps", 1)],
}

_PLANTILLA_SPLIT: dict[str, list[str]] = {
    "full_body": ["full_body"],
    "upper_lower": ["upper", "lower"],
    "ppl": ["push", "pull", "legs"],
    "weider": ["pecho_triceps", "espalda_biceps", "pierna_weider", "hombro_abdomen", "brazo"],
    "arnold": ["pecho_espalda_arnold", "hombro_brazo_arnold", "legs"],
}

NOMBRE_SPLIT_LEGIBLE = {
    "full_body": "Full Body",
    "upper_lower": "Upper / Lower",
    "ppl": "Push / Pull / Legs",
    "weider": "Weider (un grupo muscular por día)",
    "arnold": "Arnold Split",
}


def _dias_para_split(split: str, n: int) -> list[str]:
    base = _PLANTILLA_SPLIT[split]
    return [base[i % len(base)] for i in range(n)]


def _asignar_arquetipos(splits: list[str], n_dias: int) -> list[str]:
    if len(splits) == 1:
        return _dias_para_split(splits[0], n_dias)
    # Combinación de 2 splits: reparte los días entre ambos (el primero se
    # lleva el día extra si n_dias es impar), cada uno rotando su propia
    # secuencia dentro de los días que le tocaron.
    n_a = math.ceil(n_dias / 2)
    n_b = n_dias - n_a
    return _dias_para_split(splits[0], n_a) + _dias_para_split(splits[1], n_b)


# =============================================================================
# 4. GENERACIÓN
# =============================================================================


@dataclass
class ResultadoGeneracion:
    bloques: list[dict]
    dias_detectados: int
    splits_detectados: list[str]
    ubicacion_detectada: str
    idioma_detectado: str
    resumen: str = field(default="")


def _elegir_ejercicios(musculo: str, equipo: str, cantidad: int, offset: int) -> list[tuple[str, str, str]]:
    pool = EJERCICIOS.get((musculo, equipo)) or EJERCICIOS.get((musculo, "gimnasio")) or []
    if not pool:
        return []
    return [pool[(offset + i) % len(pool)] for i in range(cantidad)]


def generar_ejemplo_rutina(nombre_rutina: str, descripcion: str) -> ResultadoGeneracion:
    """
    Arma una rutina de ejemplo (lista de bloques, mismo formato que usa
    modules/rutinas.py) interpretando nombre_rutina + descripcion por
    palabras clave: idioma, ubicación (casa/gimnasio), número de días y
    tipo(s) de split.
    """
    texto = f"{nombre_rutina} {descripcion}".strip()

    idioma = detectar_idioma(texto)
    equipo = detectar_ubicacion(texto)
    splits = detectar_splits(texto)
    n_dias = detectar_dias(texto) or _DIAS_DEFECTO.get(splits[0], 3)
    n_dias = max(2, min(7, n_dias))

    arquetipos_por_dia = _asignar_arquetipos(splits, n_dias)

    contador_musculo: dict[str, int] = {}
    bloques: list[dict] = []
    for idx, arquetipo in enumerate(arquetipos_por_dia):
        for musculo, cantidad in ARQUETIPOS[arquetipo]:
            offset = contador_musculo.get(musculo, 0)
            elegidos = _elegir_ejercicios(musculo, equipo, cantidad, offset)
            contador_musculo[musculo] = offset + cantidad

            for nombre_es, nombre_en, tipo in elegidos:
                nombre = nombre_en if idioma == "en" else nombre_es
                if tipo == "compuesto":
                    series, repeticiones, descanso_min = 4, "6-10", 2.0
                else:
                    series, repeticiones, descanso_min = 3, "10-15", 1.0
                bloques.append(
                    {
                        "dia": DIAS_APP[idx],
                        "ejercicio": nombre,
                        "musculo": musculo,
                        "series": series,
                        "repeticiones": repeticiones,
                        "rpe_rir": "RIR 2",
                        "descanso_min": descanso_min,
                        "notas": "",
                    }
                )

    nombres_split = " + ".join(NOMBRE_SPLIT_LEGIBLE.get(s, s) for s in splits)
    resumen = (
        f"{n_dias} días · {nombres_split} · "
        f"{'en casa' if equipo == 'casa' else 'en gimnasio'} · "
        f"{'inglés' if idioma == 'en' else 'español'}"
    )

    return ResultadoGeneracion(
        bloques=bloques,
        dias_detectados=n_dias,
        splits_detectados=splits,
        ubicacion_detectada=equipo,
        idioma_detectado=idioma,
        resumen=resumen,
    )
