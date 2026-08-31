"""
Importador del CSV que Hevy permite exportar manualmente desde su propia
app (Perfil -> Configuración -> Exportar datos). No depende de scraping ni
de su API — ver modules/hevy_integration.py para el porqué de eso.

Formato esperado (columnas reales de la exportación de Hevy):
    title, start_time, end_time, description, exercise_title,
    superset_id, exercise_notes, set_index, set_type, weight_kg, reps,
    distance_km, duration_seconds, rpe

Cada fila del CSV es UNA serie. "historial_entrenamientos" guarda una
fila por (cliente, fecha, ejercicio) — no por serie — así que acá se
agrupan todas las series de un mismo ejercicio hechas el mismo día:

  - series: cuántas series de TRABAJO hizo ese día (se excluyen las de
    calentamiento, set_type="warmup" — no reflejan la carga real).
  - peso_kg / repeticiones: los de la serie con MÁS peso ese día (la
    serie "top" es la métrica estándar para trackear sobrecarga
    progresiva). Si ninguna serie de ese ejercicio ese día tiene peso
    registrado (ejercicios a peso corporal, ej. dominadas sin lastre),
    se usa la serie de más repeticiones en su lugar.
  - volumen_total: suma de peso×repeticiones de todas las series de
    trabajo. None si ninguna serie tiene peso Y repeticiones a la vez
    (ej. plancha, que se mide en duración — Hevy no manda esa columna
    al esquema actual, así que ese ejercicio queda sin volumen/peso,
    pero igual se cuenta cuántas series se hicieron).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

_MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_COLUMNAS_REQUERIDAS = {"start_time", "exercise_title", "set_type", "weight_kg", "reps"}


def _parsear_fecha(start_time: str) -> date | None:
    """'30 ago 2026, 12:51' -> date(2026, 8, 30). None si el texto no calza el formato esperado."""
    if not start_time:
        return None
    try:
        parte_fecha = start_time.split(",")[0].strip()  # "30 ago 2026"
        dia_s, mes_s, anio_s = parte_fecha.split(" ")
        mes = _MESES_ES.get(mes_s.lower().rstrip("."))
        if mes is None:
            return None
        return date(int(anio_s), mes, int(dia_s))
    except (ValueError, IndexError):
        return None


def _numero(valor: str | None) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


@dataclass
class ResultadoImportacionHevy:
    filas: list[dict]  # listas para upsert en historial_entrenamientos (sin cliente_id todavía)
    ejercicios_detectados: list[str] = field(default_factory=list)
    dias_detectados: int = 0
    filas_omitidas: int = 0  # series del CSV que no se pudieron leer (fecha inválida, sin nombre de ejercicio)
    rango_fechas: tuple[date, date] | None = None


def parsear_csv_hevy(contenido: str) -> ResultadoImportacionHevy:
    """Lee el CSV completo (como texto) y devuelve las filas ya agrupadas y listas
    para guardar. Lanza ValueError si el archivo no tiene las columnas de Hevy."""
    lector = csv.DictReader(io.StringIO(contenido))
    columnas = set(lector.fieldnames or [])
    if not _COLUMNAS_REQUERIDAS.issubset(columnas):
        faltantes = _COLUMNAS_REQUERIDAS - columnas
        raise ValueError(
            "El archivo no tiene el formato de exportación de Hevy — "
            f"faltan estas columnas: {', '.join(sorted(faltantes))}"
        )

    # (fecha, ejercicio) -> lista de (peso_kg|None, reps|None), una por serie de trabajo
    grupos: dict[tuple[date, str], list[tuple[float | None, float | None]]] = defaultdict(list)
    filas_omitidas = 0

    for fila in lector:
        if (fila.get("set_type") or "").strip().lower() == "warmup":
            continue
        fecha = _parsear_fecha(fila.get("start_time") or "")
        ejercicio = (fila.get("exercise_title") or "").strip()
        if fecha is None or not ejercicio:
            filas_omitidas += 1
            continue
        grupos[(fecha, ejercicio)].append((_numero(fila.get("weight_kg")), _numero(fila.get("reps"))))

    filas_resultado = []
    fechas: list[date] = []
    for (fecha, ejercicio), series in grupos.items():
        fechas.append(fecha)

        con_peso = [(p, r) for p, r in series if p is not None]
        if con_peso:
            peso_top, reps_top = max(con_peso, key=lambda pr: (pr[0], pr[1] or 0))
        else:
            con_reps = [(p, r) for p, r in series if r is not None]
            peso_top, reps_top = (None, max(r for _, r in con_reps)) if con_reps else (None, None)

        volumen = sum(p * r for p, r in series if p is not None and r is not None)

        filas_resultado.append(
            {
                "fecha": fecha.isoformat(),
                "ejercicio_nombre": ejercicio,
                "peso_kg": peso_top,
                "series": len(series),
                "repeticiones": int(reps_top) if reps_top is not None else None,
                "volumen_total": volumen if volumen > 0 else None,
                "fuente": "hevy_csv_import",
            }
        )

    return ResultadoImportacionHevy(
        filas=filas_resultado,
        ejercicios_detectados=sorted({f["ejercicio_nombre"] for f in filas_resultado}),
        dias_detectados=len({f["fecha"] for f in filas_resultado}),
        filas_omitidas=filas_omitidas,
        rango_fechas=(min(fechas), max(fechas)) if fechas else None,
    )
