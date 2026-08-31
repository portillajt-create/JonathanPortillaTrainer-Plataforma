"""
Análisis del historial de entrenamiento real (importado de Hevy — ver
utils/hevy_import.py) para detectar ejercicios que el admin debería
revisar: sin progreso real en fuerza en las últimas sesiones, o que el
cliente dejó de entrenar hace unas semanas.

No usa IA ni nada probabilístico — son reglas simples y explicables sobre
las sesiones más recientes de cada ejercicio, a propósito, para que el
admin pueda confiar en el motivo exacto que se le muestra.
"""

from __future__ import annotations

from datetime import date

#: Cuántas de las sesiones MÁS RECIENTES de un ejercicio se miran para
#: juzgar si hubo progreso real. Se compara el promedio de la mitad más
#: vieja contra la mitad más nueva de esta ventana (no la última sesión
#: contra el mejor reciente) — comparar una sola sesión contra el mejor
#: dato reciente marcaba como "estancado" cosas que son variación normal
#: de entrenamiento (un día flojo, una sesión de técnica con menos peso,
#: etc.), no un plateau real.
VENTANA_SESIONES = 6

#: Mínimo de sesiones para intentar juzgar progreso (se parte por la
#: mitad); con menos que esto no hay tendencia confiable que comparar.
MIN_SESIONES_PROGRESO = 4

#: Con menos sesiones que esto no hay información suficiente ni para decir
#: "sin entrenar" — 1-2 sesiones no son un patrón, y evita llenar la lista
#: con ejercicios que el cliente probó una sola vez.
MIN_SESIONES = 3

#: Rango de semanas "sin entrenar" que vale la pena avisar. El mínimo evita
#: ruido por una pausa normal de una semana; el MÁXIMO es igual de
#: importante — con años de historial, un ejercicio que se dejó de hacer
#: hace 2+ años casi seguro fue un cambio de rutina a propósito, no algo
#: que el admin "se le esté pasando". Sin el máximo, la lista terminaba
#: dominada por ejercicios abandonados hace años en vez de vacíos
#: recientes de la rutina actual.
SEMANAS_SIN_ENTRENAR_MIN = 3
SEMANAS_SIN_ENTRENAR_MAX = 10

#: Margen para no contar como "progreso" una diferencia que es solo ruido
#: de redondeo del 1RM estimado (1% del mejor 1RM reciente).
TOLERANCIA_PROGRESO = 0.01


def calcular_e1rm(peso_kg: float | None, repeticiones: int | float | None) -> float | None:
    """
    1RM estimado (fórmula de Epley): cuánto podría levantar el cliente a
    una repetición, a partir de un peso y unas repeticiones reales. Es la
    forma estándar de comparar el esfuerzo entre sesiones que no usaron
    el mismo peso ni las mismas repeticiones — "60 kg x 8" y "65 kg x 6"
    no se pueden comparar mirando solo el peso, pero sus 1RM estimados
    (76.8 kg y 78 kg) sí dicen cuál esfuerzo fue mayor.
    """
    if peso_kg is None or repeticiones is None or repeticiones <= 0:
        return None
    return peso_kg * (1 + repeticiones / 30)


def detectar_ejercicios_a_revisar(historial: list[dict], hoy: date) -> list[dict]:
    """
    historial: filas de historial_entrenamientos (fecha ISO, ejercicio_nombre,
    peso_kg, repeticiones, ...) de UN cliente, en cualquier orden.

    Devuelve una fila por ejercicio marcado (ordenadas por más urgente
    primero), con: Ejercicio, Motivo (texto legible), Última sesión,
    Semanas desde la última, Sesiones totales.
    """
    por_ejercicio: dict[str, list[dict]] = {}
    for fila in historial:
        por_ejercicio.setdefault(fila["ejercicio_nombre"], []).append(fila)

    resultado = []
    for ejercicio, filas in por_ejercicio.items():
        if len(filas) < MIN_SESIONES:
            continue

        filas_ordenadas = sorted(filas, key=lambda f: f["fecha"])
        ultima_fecha = date.fromisoformat(filas_ordenadas[-1]["fecha"])
        semanas_desde_ultima = (hoy - ultima_fecha).days // 7

        # Ya no es parte de la rutina actual -- no tiene sentido revisarlo
        # (ni por "sin entrenar" ni por si dejó de progresar, esas sesiones
        # ya son historia vieja).
        if semanas_desde_ultima > SEMANAS_SIN_ENTRENAR_MAX:
            continue

        motivos = []
        if semanas_desde_ultima >= SEMANAS_SIN_ENTRENAR_MIN:
            motivos.append(f"sin entrenar hace {semanas_desde_ultima} semanas")

        recientes = filas_ordenadas[-VENTANA_SESIONES:]
        e1rms = [calcular_e1rm(f.get("peso_kg"), f.get("repeticiones")) for f in recientes]
        if len(recientes) >= MIN_SESIONES_PROGRESO and all(v is not None for v in e1rms):
            mitad = len(e1rms) // 2
            promedio_viejo = sum(e1rms[:mitad]) / mitad
            promedio_nuevo = sum(e1rms[mitad:]) / (len(e1rms) - mitad)
            if promedio_nuevo <= promedio_viejo * (1 + TOLERANCIA_PROGRESO):
                motivos.append(
                    f"sin progreso en fuerza en las últimas {len(recientes)} sesiones "
                    f"(1RM estimado promedio: {promedio_viejo:.0f} kg -> {promedio_nuevo:.0f} kg)"
                )

        if not motivos:
            continue

        resultado.append(
            {
                "Ejercicio": ejercicio,
                "Motivo": " · ".join(motivos),
                "Última sesión": ultima_fecha.isoformat(),
                "Semanas desde la última": semanas_desde_ultima,
                "Sesiones totales": len(filas),
            }
        )

    resultado.sort(key=lambda r: -r["Semanas desde la última"])
    return resultado
