"""Helpers de formato (fecha/hora y saneado de texto) compartidos entre módulos."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

# Colombia no tiene horario de verano: el offset es -5 todo el año, así que
# no hace falta zoneinfo/tzdata para esto.
_BOGOTA = timezone(timedelta(hours=-5))

# Caracteres con significado en Markdown. st.markdown()/st.write() INTERPRETAN
# markdown, así que el texto que escribe un cliente no es texto plano: puede
# crear enlaces y, peor, imágenes (`![](http://...)`) que el navegador del
# entrenador carga solo al abrir la ficha — una baliza de rastreo sin un solo
# clic. Escapando estos caracteres el texto se muestra literal.
#
# El set incluye "." y "-" a propósito: además de neutralizar listas, rompe el
# auto-enlazado de URLs sueltas (Streamlit convierte "https://x.com" en enlace
# aunque no uses sintaxis de markdown; al escapar el punto, el host queda
# corrupto y el enlace deja de apuntar a ningún lado real).
_MARKDOWN_ESPECIALES = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~])")

# Solo se renderiza como enlace clicable si es realmente un perfil de Hevy.
_URL_HEVY = re.compile(r"^https://(www\.)?hevy\.com/[A-Za-z0-9_\-/.~%?=&+]*$")


def escapar_markdown(texto: Any, vacio: str = "—") -> str:
    """
    Neutraliza el formato Markdown de un texto escrito por el cliente para
    poder mostrarlo con st.markdown()/st.write() sin que se interprete.
    Verificado: el texto clínico normal ("Hipotiroidismo (dx. 2021) - 1-2
    veces/día") se sigue leyendo igual, sin barras invertidas visibles.
    """
    if texto is None or not str(texto).strip():
        return vacio
    return _MARKDOWN_ESPECIALES.sub(lambda m: "\\" + m.group(1), str(texto))


def url_hevy_valida(url: Any) -> str | None:
    """Devuelve la URL solo si apunta de verdad a hevy.com; si no, None."""
    if not url:
        return None
    limpia = str(url).strip()
    return limpia if _URL_HEVY.match(limpia) else None


def hoy_bogota() -> date:
    """
    Fecha de hoy en Colombia. Importante para el check-in semanal: el
    servidor de Streamlit Cloud corre en UTC, así que date.today() cambia de
    día (y por tanto de semana) a las 7:00 p.m. hora Colombia. Con esto, la
    semana pasa de domingo a lunes cuando de verdad es medianoche aquí.
    """
    return datetime.now(_BOGOTA).date()


def fecha_bogota(iso_str: str | None) -> date | None:
    """Convierte un timestamp de Supabase (UTC) a la fecha calendario en Colombia."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_BOGOTA).date()


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
