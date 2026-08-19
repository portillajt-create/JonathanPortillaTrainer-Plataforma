"""
Autenticación y gestión de roles (Entrenador/Admin vs. Cliente).

Usa Supabase Auth (correo + contraseña) para el login/registro, y la tabla
`public.clientes` (creada por el trigger `handle_new_user` en el SQL del
Paso 1) para saber qué rol tiene cada usuario autenticado.
"""

from __future__ import annotations

import streamlit as st

from utils.session import clear_auth_state
from utils.supabase_client import get_supabase_client


def login(email: str, password: str) -> bool:
    """Intenta iniciar sesión. Devuelve True/False y guarda el resultado en session_state."""
    supabase = get_supabase_client()
    st.session_state.pop("auth_error", None)

    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # credenciales inválidas, usuario no confirmado, etc.
        st.session_state["auth_error"] = str(exc)
        return False

    if res.user is None or res.session is None:
        st.session_state["auth_error"] = "No se pudo iniciar sesión. Verifica tus credenciales."
        return False

    _load_perfil(res.user.id)
    st.session_state["user"] = res.user
    st.session_state["access_token"] = res.session.access_token
    st.session_state["refresh_token"] = res.session.refresh_token
    st.session_state["cliente_id"] = res.user.id
    return True


def request_password_reset(email: str) -> None:
    """Dispara el correo de recuperación de contraseña de Supabase Auth."""
    supabase = get_supabase_client()
    supabase.auth.reset_password_for_email(email)


def complete_password_reset(token_hash: str, new_password: str) -> bool:
    """
    Verifica el token del enlace de recuperación y define la nueva
    contraseña. `verify_otp` ya deja al usuario autenticado (mismo patrón
    que un login normal), así que reusamos esa sesión en vez de pedirle
    que inicie sesión de nuevo con la contraseña que acaba de definir.
    """
    supabase = get_supabase_client()
    st.session_state.pop("auth_error", None)

    try:
        res = supabase.auth.verify_otp({"token_hash": token_hash, "type": "recovery"})
    except Exception as exc:
        st.session_state["auth_error"] = str(exc)
        return False

    if res.user is None or res.session is None:
        st.session_state["auth_error"] = "El enlace de recuperación no es válido o ya expiró."
        return False

    try:
        supabase.auth.update_user({"password": new_password})
    except Exception as exc:
        st.session_state["auth_error"] = str(exc)
        return False

    _load_perfil(res.user.id)
    st.session_state["user"] = res.user
    st.session_state["access_token"] = res.session.access_token
    st.session_state["refresh_token"] = res.session.refresh_token
    st.session_state["cliente_id"] = res.user.id
    return True


def signup_cliente(email: str, password: str, nombre_completo: str):
    """
    Autorregistro de un nuevo cliente. El trigger `handle_new_user` del SQL
    crea automáticamente su fila en `clientes` con rol = 'cliente'.

    Nota: según la configuración de tu proyecto Supabase, es posible que el
    usuario deba confirmar su correo antes de poder iniciar sesión.
    """
    supabase = get_supabase_client()
    return supabase.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {"data": {"nombre_completo": nombre_completo}},
        }
    )


def logout() -> None:
    supabase = get_supabase_client()
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    finally:
        clear_auth_state()


def is_authenticated() -> bool:
    return st.session_state.get("user") is not None


def current_role() -> str:
    return st.session_state.get("rol") or "cliente"


def current_cliente_id() -> str | None:
    return st.session_state.get("cliente_id")


def _load_perfil(user_id: str) -> None:
    """Carga rol y nombre desde public.clientes hacia session_state."""
    supabase = get_supabase_client()
    resp = (
        supabase.table("clientes")
        .select("rol, nombre_completo")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if resp.data:
        st.session_state["rol"] = resp.data.get("rol", "cliente")
        st.session_state["nombre_completo"] = resp.data.get("nombre_completo", "")
    else:
        # Caso borde: el trigger aún no ha corrido (latencia mínima tras el signup).
        st.session_state["rol"] = "cliente"
        st.session_state["nombre_completo"] = ""
