"""Helpers de formato de fecha/hora compartidos entre módulos."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Colombia no tiene horario de verano: el offset es -5 todo el año, así que
# no hace falta zoneinfo/tzdata para esto.
_BOGOTA = timezone(timedelta(hours=-5))


def formatear_fecha_hora(iso_str: str | None) -> str:
    """'2026-08-26T14:32:07+00:00' (UTC, como lo guarda Supabase) -> '26/08/2026 09:32' (hora de Bogotá)."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BOGOTA).strftime("%d/%m/%Y %H:%M")
