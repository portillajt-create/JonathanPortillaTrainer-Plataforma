"""Helpers para inicializar y limpiar las claves de session_state que usa la app."""

import streamlit as st

# Claves de sesión relacionadas con el usuario autenticado.
AUTH_KEYS = [
    "user",
    "access_token",
    "refresh_token",
    "cliente_id",
    "rol",
    "nombre_completo",
    "auth_error",
]


def init_session_state() -> None:
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("rol", None)


def clear_auth_state() -> None:
    for key in AUTH_KEYS:
        st.session_state.pop(key, None)
