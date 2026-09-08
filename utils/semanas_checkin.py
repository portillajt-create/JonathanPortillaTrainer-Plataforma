"""
Modelo de semanas del check-in — lógica pura, sin Streamlit (mismo
criterio que hevy_import.py, analisis_progreso.py, plan_alimentario.py,
plan_entrenamiento.py: se puede probar directo desde Python, y además
esto permite que el cron de recordatorios (scripts/recordatorios_diarios.py,
que corre fuera de la app, sin Streamlit) calcule EXACTAMENTE la misma
"semana a reportar" que ve el cliente en su formulario — una sola fuente
de verdad, no dos copias que puedan divergir.

Extraído de modules/checkin.py el 2026-09-09 (antes vivía ahí, duplicado
en espíritu con lo que necesitaba el cron).

"semana_fecha" identifica la semana que el check-in REPORTA (su lunes), no
la semana en que se llenó el formulario. Es la diferencia clave: un cliente
que entra el lunes no puede calificar una semana que apenas empieza — lo que
reporta es cómo le fue la semana que acaba de cerrar.

Cada semana queda abierta para reportarse durante los 7 días siguientes:
  - Lunes a domingo de la semana W+1 -> se reporta la semana W ("semana pasada")
  - Desde el jueves de W+1 -> también se habilita reportar W+1 en curso, para
    quien ya sabe cómo le fue y prefiere no esperar al lunes.
Al llegar el lunes siguiente la ventana se cierra sola y esa semana ya no
se puede reportar.
"""

from __future__ import annotations

from datetime import date, timedelta

from utils.formato import hoy_bogota

# Arranque del seguimiento: los clientes registrados antes de esta fecha eran
# cuentas de prueba que todavía no habían empezado su plan, así que no se les
# reclama ningún check-in anterior. La primera semana reportable es la del
# 31/08/2026, y el primer recordatorio posible cae el lunes 07/09/2026.
SEMANA_INICIO_CHECKINS = date(2026, 8, 31)

# Día de la semana (lunes=0) desde el que se habilita reportar la semana en curso.
DIA_APERTURA_SEMANA_EN_CURSO = 3  # jueves

MESES_ABREV = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def lunes_semana_en_curso() -> date:
    return lunes_de(hoy_bogota())


def semana_a_reportar() -> date | None:
    """
    Lunes de la semana cerrada que el cliente debería reportar ahora mismo
    (la inmediatamente anterior). None si todavía no entra en el periodo de
    seguimiento — es lo que evita reclamar semanas previas al arranque.
    """
    lunes = lunes_semana_en_curso() - timedelta(days=7)
    return lunes if lunes >= SEMANA_INICIO_CHECKINS else None


def semana_en_curso_reportable() -> date | None:
    """Lunes de la semana en curso, solo si ya es jueves o después."""
    lunes = lunes_semana_en_curso()
    if lunes < SEMANA_INICIO_CHECKINS:
        return None
    if hoy_bogota().weekday() < DIA_APERTURA_SEMANA_EN_CURSO:
        return None
    return lunes


def rango_semana(lunes: date) -> str:
    """date(2026, 8, 31) -> '31 ago – 6 sep'"""
    domingo = lunes + timedelta(days=6)
    return f"{lunes.day} {MESES_ABREV[lunes.month - 1]} – {domingo.day} {MESES_ABREV[domingo.month - 1]}"
