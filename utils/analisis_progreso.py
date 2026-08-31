"""
Análisis del historial de entrenamiento real (importado de Hevy — ver
utils/hevy_import.py) para detectar ejercicios que el admin debería
revisar: se están entrenando actualmente, pero no muestran progreso real
de fuerza en las últimas sesiones.

No usa IA ni nada probabilístico — son reglas simples y explicables sobre
las sesiones más recientes de cada ejercicio, a propósito, para que el
admin pueda confiar en el motivo exacto que se le muestra.
"""

from __future__ import annotations

from datetime import date

#: Si la última vez que se entrenó un ejercicio fue hace más de esto, se
#: considera que ya no es parte de lo que el cliente está haciendo AHORA
#: (cambió de rutina, lo dejó, etc.) y no tiene sentido revisarlo — solo
#: interesan los ejercicios que sigue entrenando.
SEMANAS_ACTIVO_MAX = 2

#: Cuántas de las sesiones MÁS RECIENTES de un ejercicio se miran para
#: juzgar si hubo progreso real. Se compara el promedio de la mitad más
#: vieja contra la mitad más nueva de esta ventana (no la última sesión
#: contra el mejor reciente) — comparar una sola sesión contra el mejor
#: dato reciente marcaba como "estancado" cosas que son variación normal
#: de entrenamiento (un día flojo, una sesión de técnica con menos peso,
#: etc.), no un plateau real.
VENTANA_SESIONES = 6

#: Mínimo de sesiones (dentro de la ventana activa) para intentar juzgar
#: progreso — con menos que esto no hay tendencia confiable que comparar.
MIN_SESIONES_PROGRESO = 4

#: Margen para no contar como "progreso" una diferencia que es solo ruido
#: de redondeo del 1RM estimado (1%).
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

    Solo considera ejercicios que el cliente sigue entrenando actualmente
    (ver SEMANAS_ACTIVO_MAX) y que no muestran progreso real de fuerza en
    sus sesiones recientes. Devuelve una fila por ejercicio marcado,
    ordenadas por la caída de 1RM más grande primero.
    """
    por_ejercicio: dict[str, list[dict]] = {}
    for fila in historial:
        por_ejercicio.setdefault(fila["ejercicio_nombre"], []).append(fila)

    resultado = []
    for ejercicio, filas in por_ejercicio.items():
        filas_ordenadas = sorted(filas, key=lambda f: f["fecha"])
        ultima_fecha = date.fromisoformat(filas_ordenadas[-1]["fecha"])
        semanas_desde_ultima = (hoy - ultima_fecha).days // 7

        # No es algo que el cliente esté haciendo ahora -- no interesa.
        if semanas_desde_ultima > SEMANAS_ACTIVO_MAX:
            continue

        recientes = filas_ordenadas[-VENTANA_SESIONES:]
        if len(recientes) < MIN_SESIONES_PROGRESO:
            continue

        e1rms = [calcular_e1rm(f.get("peso_kg"), f.get("repeticiones")) for f in recientes]
        if not all(v is not None for v in e1rms):
            continue

        mitad = len(e1rms) // 2
        promedio_viejo = sum(e1rms[:mitad]) / mitad
        promedio_nuevo = sum(e1rms[mitad:]) / (len(e1rms) - mitad)
        if promedio_nuevo > promedio_viejo * (1 + TOLERANCIA_PROGRESO):
            continue  # sí hubo progreso -- no se marca

        resultado.append(
            {
                "Ejercicio": ejercicio,
                "Motivo": (
                    f"sin progreso en fuerza en las últimas {len(recientes)} sesiones "
                    f"(1RM estimado promedio: {promedio_viejo:.0f} kg -> {promedio_nuevo:.0f} kg)"
                ),
                "Última sesión": ultima_fecha.isoformat(),
                "Semanas desde la última": semanas_desde_ultima,
                "Sesiones totales": len(filas),
                "_caida_pct": (promedio_viejo - promedio_nuevo) / promedio_viejo,
            }
        )

    resultado.sort(key=lambda r: -r["_caida_pct"])
    for fila in resultado:
        del fila["_caida_pct"]
    return resultado
