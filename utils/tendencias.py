"""
Comentarios automáticos de tendencia para el reporte PDF de progreso
(ver utils/pdf_export.py:generar_pdf_progreso).

Mismo criterio que utils/analisis_progreso.py: reglas simples y explicables,
sin IA ni nada probabilístico, para que tanto el entrenador como el cliente
puedan entender de dónde sale cada frase. Lógica pura: no importa Streamlit
ni fpdf, así se puede probar sola.

El reporte lo descarga también el propio cliente, así que el tono es
descriptivo y neutral ("subió", "bajó", "estable"): los juicios de valor
("favorable"/"desfavorable") solo se usan donde la dirección buena es
inequívoca (adherencia, sueño, estrés, fatiga, fuerza). Con el peso depende
del objetivo del cliente, así que solo se califica si el objetivo del
onboarding lo deja claro (pérdida de grasa / hipertrofia).
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from utils.analisis_progreso import calcular_e1rm

# Umbrales de "zona alta/baja" en las escalas 1-10 del check-in. Única fuente
# de verdad: modules/checkin.py los importa de acá para sus alertas de deload
# y adherencia, así el comentario del PDF y la alerta del admin nunca usan
# números distintos.
UMBRAL_FATIGA_ALTA = 8
UMBRAL_ESTRES_ALTO = 8
UMBRAL_SUENO_BAJO = 4
UMBRAL_ADHERENCIA_DIETA_BAJA = 5

#: Diferencia mínima (en puntos de la escala 1-10) entre el promedio reciente
#: y el anterior para decir que algo "subió" o "bajó". Por debajo es ruido
#: normal de semana a semana — se reporta como estable.
DELTA_ESCALA_SIGNIFICATIVO = 0.75

#: Cambio de peso por debajo del cual se considera estable (kg).
DELTA_PESO_ESTABLE_KG = 0.3

#: Cambio de 1RM estimado por debajo del cual se considera estable (fracción).
DELTA_1RM_ESTABLE = 0.02

#: Ventana y selección de ejercicios del reporte (sección Fuerza).
DIAS_VENTANA_FUERZA = 180
DIAS_FRECUENCIA_FUERZA = 90
MAX_EJERCICIOS_REPORTE = 4


def _fmt_fecha(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _fmt_num(x: float, decimales: int = 1) -> str:
    return f"{x:.{decimales}f}"


def _fmt_signo(x: float, decimales: int = 1, unidad: str = "") -> str:
    # "–" (U+2013) sí existe en la codificación windows-1252 del PDF.
    signo = "+" if x > 0 else ("–" if x < 0 else "±")
    return f"{signo}{abs(x):.{decimales}f}{unidad}"


def comparar_recientes(valores: list[float]) -> tuple[float, float] | None:
    """
    (promedio anterior, promedio reciente) de una serie cronológica: compara
    las últimas k mediciones contra las k anteriores, con k = hasta 3 (o la
    mitad de la serie si es más corta). Se usa promedio y no "último vs
    penúltimo" para no leer como tendencia una sola semana atípica.
    """
    n = len(valores)
    if n < 2:
        return None
    k = min(3, n // 2)
    return mean(valores[-2 * k : -k]), mean(valores[-k:])


def comentario_escala(
    nombre: str,
    valores: list[float],
    mayor_es_mejor: bool,
    umbral: float | None = None,
    alerta_si_mayor_o_igual: bool = True,
) -> str | None:
    """Comentario de una métrica 1-10 del check-in (adherencia, sueño, estrés, fatiga)."""
    if not valores:
        return None
    ultimo = valores[-1]
    if len(valores) == 1:
        texto = f"{nombre}: {ultimo:.0f}/10 en el único check-in registrado; la tendencia se verá desde el siguiente."
    else:
        anterior, reciente = comparar_recientes(valores)
        delta = reciente - anterior
        if abs(delta) < DELTA_ESCALA_SIGNIFICATIVO:
            tendencia = "se ha mantenido estable en las últimas semanas"
        else:
            sube = delta > 0
            favorable = sube == mayor_es_mejor
            tendencia = (
                f"{'subió' if sube else 'bajó'} en las últimas semanas "
                f"(de {_fmt_num(anterior)} a {_fmt_num(reciente)} en promedio), "
                f"una tendencia {'favorable' if favorable else 'desfavorable'}"
            )
        texto = f"{nombre}: promedio de {_fmt_num(mean(valores))}/10 y {tendencia}."

    if umbral is not None:
        en_zona = ultimo >= umbral if alerta_si_mayor_o_igual else ultimo <= umbral
        if en_zona:
            zona = "alto" if alerta_si_mayor_o_igual else "bajo"
            texto += f" El último check-in marcó {ultimo:.0f}/10, un valor {zona}."
    return texto


def direccion_peso_segun_objetivo(objetivo: str | None) -> int:
    """+1 si subir de peso es lo buscado, -1 si bajar, 0 si no está claro."""
    if objetivo == "Pérdida de grasa":
        return -1
    if objetivo == "Hipertrofia":
        return +1
    return 0


def comentario_peso(puntos: list[tuple[date, float]], objetivo: str | None = None) -> str | None:
    """puntos: (fecha de la semana, peso en kg) en orden cronológico, sin nulos."""
    if not puntos:
        return None
    if len(puntos) == 1:
        return (
            f"Peso corporal: {_fmt_num(puntos[0][1])} kg en el único check-in con peso registrado; "
            "la tendencia se verá a partir del siguiente."
        )

    (f0, p0), (f1, p1) = puntos[0], puntos[-1]
    total = p1 - p0
    semanas = max((f1 - f0).days / 7, 1)
    if abs(total) < DELTA_PESO_ESTABLE_KG:
        texto = (
            f"Peso corporal: prácticamente estable desde el {_fmt_fecha(f0)} "
            f"({_fmt_num(p0)} kg a {_fmt_num(p1)} kg)."
        )
    else:
        texto = (
            f"Peso corporal: pasó de {_fmt_num(p0)} kg a {_fmt_num(p1)} kg desde el {_fmt_fecha(f0)} "
            f"({_fmt_signo(total, unidad=' kg')}, {_fmt_signo(total / p0 * 100, unidad='%')}), "
            f"un ritmo promedio de {_fmt_signo(total / semanas, decimales=2, unidad=' kg')} por semana."
        )
        direccion = direccion_peso_segun_objetivo(objetivo)
        if direccion:
            a_favor = (total > 0) == (direccion > 0)
            texto += (
                f" Va {'en la dirección' if a_favor else 'en dirección contraria a la'} "
                f"de tu objetivo ({objetivo.lower()})."
            )

    # Cambio de rumbo reciente: si las últimas semanas van al revés del total.
    if len(puntos) >= 4:
        reciente = p1 - puntos[-4][1]
        if abs(reciente) >= DELTA_PESO_ESTABLE_KG and abs(total) >= DELTA_PESO_ESTABLE_KG and (reciente > 0) != (total > 0):
            texto += (
                f" Ojo: en los últimos 3 registros la tendencia cambió y "
                f"{'subió' if reciente > 0 else 'bajó'} {_fmt_num(abs(reciente))} kg."
            )
    return texto


def serie_1rm(historial: list[dict], ejercicio: str, desde: date) -> list[tuple[date, float]]:
    """(fecha, 1RM estimado) de un ejercicio desde una fecha, en orden, sin sesiones sin carga."""
    puntos = []
    for fila in historial:
        if fila["ejercicio_nombre"] != ejercicio:
            continue
        fecha = date.fromisoformat(fila["fecha"])
        if fecha < desde:
            continue
        e1rm = calcular_e1rm(fila.get("peso_kg"), fila.get("repeticiones"))
        if e1rm is not None:
            puntos.append((fecha, e1rm))
    return sorted(puntos)


def ejercicios_principales(historial: list[dict], hoy: date) -> list[str]:
    """
    Los ejercicios que el reporte grafica: los más entrenados en los últimos
    DIAS_FRECUENCIA_FUERZA días (por cantidad de sesiones), con al menos 2
    sesiones con carga dentro de la ventana del gráfico — con una sola no
    hay línea que dibujar. Máximo MAX_EJERCICIOS_REPORTE.
    """
    limite_frecuencia = hoy - timedelta(days=DIAS_FRECUENCIA_FUERZA)
    limite_ventana = hoy - timedelta(days=DIAS_VENTANA_FUERZA)
    sesiones: dict[str, int] = {}
    for fila in historial:
        if date.fromisoformat(fila["fecha"]) >= limite_frecuencia:
            sesiones[fila["ejercicio_nombre"]] = sesiones.get(fila["ejercicio_nombre"], 0) + 1

    candidatos = sorted(sesiones, key=lambda e: (-sesiones[e], e))
    elegidos = [e for e in candidatos if len(serie_1rm(historial, e, limite_ventana)) >= 2]
    return elegidos[:MAX_EJERCICIOS_REPORTE]


def inicio_y_final_1rm(puntos: list[tuple[date, float]]) -> tuple[float, float, int] | None:
    """
    (promedio de 1RM de las primeras k sesiones, de las últimas k, k) con
    k = hasta 3. Promedio y no "primera vs última sesión" por el mismo
    motivo que en analisis_progreso.py: una sola sesión liviana (técnica,
    descarga, cambio de máquina) hacía ver como "bajó 28%" un ejercicio que
    en realidad venía estable.
    """
    n = len(puntos)
    if n < 2:
        return None
    k = min(3, n // 2)
    return mean(v for _, v in puntos[:k]), mean(v for _, v in puntos[-k:]), k


def comentario_1rm(ejercicio: str, puntos: list[tuple[date, float]], sin_progreso_reciente: bool) -> str | None:
    if not puntos:
        return None
    if len(puntos) == 1:
        return f"{ejercicio}: una sola sesión con carga en el periodo ({_fmt_num(puntos[0][1], 0)} kg de 1RM estimado)."

    v0, v1, k = inicio_y_final_1rm(puntos)
    mejor_fecha, mejor = max(puntos, key=lambda p: p[1])
    cambio = (v1 - v0) / v0
    base = "la primera y la última sesión" if k == 1 else f"las primeras {k} y las últimas {k} sesiones"
    if abs(cambio) < DELTA_1RM_ESTABLE:
        tendencia = f"estable, alrededor de {_fmt_num(v1, 0)} kg de 1RM estimado (promedio de {base})"
    else:
        tendencia = (
            f"{'progresó' if cambio > 0 else 'bajó'} de {_fmt_num(v0, 0)} a {_fmt_num(v1, 0)} kg de 1RM estimado "
            f"({_fmt_signo(cambio * 100, 0, '%')}, promedio de {base} del periodo)"
        )
    texto = f"{ejercicio}: {tendencia}. Mejor marca: {_fmt_num(mejor, 0)} kg el {_fmt_fecha(mejor_fecha)}."
    if sin_progreso_reciente:
        texto += " En las últimas semanas no muestra progreso (ver 'Ejercicios a tener en cuenta')."
    return texto


def resumen_peso(puntos: list[tuple[date, float]]) -> str | None:
    """Versión corta de comentario_peso() para el recuadro de resumen."""
    if not puntos:
        return None
    if len(puntos) == 1:
        return f"Peso: {_fmt_num(puntos[0][1])} kg (un solo registro por ahora)."
    (f0, p0), (_, p1) = puntos[0], puntos[-1]
    total = p1 - p0
    if abs(total) < DELTA_PESO_ESTABLE_KG:
        return f"Peso: estable desde el {_fmt_fecha(f0)} ({_fmt_num(p1)} kg)."
    return f"Peso: {_fmt_signo(total, unidad=' kg')} desde el {_fmt_fecha(f0)} ({_fmt_num(p0)} a {_fmt_num(p1)} kg)."


def clasificar_1rm(puntos: list[tuple[date, float]]) -> str | None:
    """'progresó' / 'bajó' / 'estable' entre el inicio y el final del periodo, o None."""
    extremos = inicio_y_final_1rm(puntos)
    if extremos is None:
        return None
    v0, v1, _ = extremos
    cambio = (v1 - v0) / v0
    if abs(cambio) < DELTA_1RM_ESTABLE:
        return "estable"
    return "progresó" if cambio > 0 else "bajó"


def resumen_fuerza(clasificaciones: list[str], sin_progreso_reciente: int) -> str | None:
    """
    clasificaciones: clasificar_1rm() de cada ejercicio graficado.
    sin_progreso_reciente: cuántos ejercicios marca detectar_ejercicios_a_revisar().
    """
    validas = [c for c in clasificaciones if c]
    if not validas:
        return None
    partes = []
    for clave, singular, plural in (
        ("progresó", "progresó", "progresaron"), ("estable", "se mantuvo estable", "se mantuvieron estables"),
        ("bajó", "bajó", "bajaron"),
    ):
        n = validas.count(clave)
        if n:
            partes.append(f"{n} {singular if n == 1 else plural}")
    texto = (
        f"Fuerza: de {len(validas)} ejercicio{'s' if len(validas) != 1 else ''} principal"
        f"{'es' if len(validas) != 1 else ''}, {', '.join(partes)} en los últimos 6 meses."
    )
    if sin_progreso_reciente:
        texto += (
            f" {sin_progreso_reciente} ejercicio{'s' if sin_progreso_reciente != 1 else ''} sin progreso "
            "en las últimas semanas."
        )
    return texto


def _direccion_escala(valores: list[float], mayor_es_mejor: bool) -> str | None:
    """'mejoró' / 'empeoró' / 'estable', o None si no hay con qué comparar."""
    cmp = comparar_recientes(valores)
    if cmp is None:
        return None
    delta = cmp[1] - cmp[0]
    if abs(delta) < DELTA_ESCALA_SIGNIFICATIVO:
        return "estable"
    return "mejoró" if (delta > 0) == mayor_es_mejor else "empeoró"


def resumen_bienestar(sueno: list[float], estres: list[float], fatiga: list[float]) -> str | None:
    """Una sola frase para el recuadro de resumen: qué mejoró, qué empeoró, qué se mantuvo."""
    grupos: dict[str, list[str]] = {"mejoró": [], "empeoró": [], "estable": []}
    for nombre, valores, mayor_es_mejor in (
        ("el sueño", sueno, True), ("el estrés", estres, False), ("la fatiga", fatiga, False),
    ):
        d = _direccion_escala(valores, mayor_es_mejor)
        if d:
            grupos[d].append(nombre)
    if not any(grupos.values()):
        return None

    def _lista(xs: list[str]) -> str:
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1]

    partes = []
    if grupos["mejoró"]:
        partes.append(f"{_lista(grupos['mejoró'])} {'mejoró' if len(grupos['mejoró']) == 1 else 'mejoraron'}")
    if grupos["empeoró"]:
        partes.append(f"{_lista(grupos['empeoró'])} {'empeoró' if len(grupos['empeoró']) == 1 else 'empeoraron'}")
    if grupos["estable"]:
        partes.append(
            f"{_lista(grupos['estable'])} "
            f"{'se mantiene estable' if len(grupos['estable']) == 1 else 'se mantienen estables'}"
        )
    frase = "; ".join(partes)
    return f"Bienestar: {frase[0].lower()}{frase[1:]}."
