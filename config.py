"""
Configuración central del proyecto.

Soporta dos formas de definir las credenciales de Supabase, para que el
mismo código funcione igual en local y en producción:

1. Local: variables en un archivo .env (ver .env.example)
2. Streamlit Community Cloud: variables en .streamlit/secrets.toml

Nunca subas .env ni secrets.toml a un repositorio público (ver .gitignore).
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_config(key: str, default: str | None = None) -> str | None:
    """Busca primero en st.secrets (Streamlit Cloud) y luego en variables de entorno (.env)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets lanza excepción si no existe secrets.toml en absoluto; lo ignoramos.
        pass
    return os.getenv(key, default)


APP_NAME = "Jonathan Portilla Trainer"

SUPABASE_URL = _get_config("SUPABASE_URL")
SUPABASE_ANON_KEY = _get_config("SUPABASE_ANON_KEY")

# ---------------------------------------------------------------------------
# SMTP (opcional, desde el Paso 3): envío de correo para el centro de
# notificaciones. Si no se configura, la app sigue funcionando normalmente
# y simplemente omite el envío de correo (la notificación in-app se crea
# siempre, independientemente de esto).
# ---------------------------------------------------------------------------
SMTP_HOST = _get_config("SMTP_HOST")
SMTP_PORT = _get_config("SMTP_PORT", "587")
SMTP_USER = _get_config("SMTP_USER")
SMTP_PASSWORD = _get_config("SMTP_PASSWORD")
SMTP_FROM = _get_config("SMTP_FROM") or SMTP_USER
