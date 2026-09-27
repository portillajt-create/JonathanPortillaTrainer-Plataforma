"""
Autenticación y gestión de roles (Entrenador/Admin vs. Cliente).

Usa Supabase Auth (correo + contraseña) para el login/registro, y la tabla
`public.clientes` (creada por el trigger `handle_new_user` en el SQL del
Paso 1) para saber qué rol tiene cada usuario autenticado.
"""

from __future__ import annotations

import streamlit as st

from utils import sesion_persistente
from utils.session import clear_auth_state
from utils.supabase_client import get_supabase_client


def mensaje_error_auth(exc: Exception, generico: str) -> str:
    """
    Traduce los errores más comunes de Supabase Auth a un mensaje en español
    seguro para pantallas públicas (login/registro/recuperación). Cualquier
    error no reconocido cae al mensaje genérico en vez de mostrar el texto
    crudo de la excepción, que podría revelar detalles internos (rutas,
    nombres de servicio, etc.) a un visitante no autenticado.
    """
    mensaje = str(exc).lower()
    if "not confirmed" in mensaje:
        return "Debes confirmar tu correo antes de iniciar sesión. Revisa tu bandeja de entrada (y spam)."
    if "already registered" in mensaje or "already exists" in mensaje:
        return "Ya existe una cuenta con ese correo. Ve a la pestaña 'Iniciar sesión'."
    if "invalid" in mensaje and ("email" in mensaje or "format" in mensaje):
        return "Ese correo no parece válido. Revísalo e intenta de nuevo."
    if "rate limit" in mensaje or "only request this" in mensaje or "429" in mensaje:
        return "Hiciste varios intentos seguidos. Espera unos minutos y vuelve a intentar."
    if "password" in mensaje and ("short" in mensaje or "at least" in mensaje or "weak" in mensaje):
        return "La contraseña es muy corta o débil. Usa al menos 8 caracteres."
    return generico


def login(email: str, password: str) -> bool:
    """Intenta iniciar sesión. Devuelve True/False y guarda el resultado en session_state."""
    supabase = get_supabase_client()
    st.session_state.pop("auth_error", None)

    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:  # credenciales inválidas, usuario no confirmado, etc.
        st.session_state["auth_error"] = mensaje_error_auth(exc, "Correo o contraseña incorrectos.")
        return False

    if res.user is None or res.session is None:
        st.session_state["auth_error"] = "No se pudo iniciar sesión. Verifica tus credenciales."
        return False

    _abrir_sesion(res.user, res.session)
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
        st.session_state["auth_error"] = mensaje_error_auth(
            exc, "El enlace de recuperación no es válido o ya expiró."
        )
        return False

    if res.user is None or res.session is None:
        st.session_state["auth_error"] = "El enlace de recuperación no es válido o ya expiró."
        return False

    try:
        supabase.auth.update_user({"password": new_password})
    except Exception as exc:
        st.session_state["auth_error"] = mensaje_error_auth(exc, "No se pudo actualizar la contraseña.")
        return False

    _abrir_sesion(res.user, res.session)
    return True


def complete_email_confirmation(token_hash: str) -> bool:
    """
    Confirma el correo del registro a partir del token del enlace.
    Verifica el enlace de confirmación de correo del registro y deja al
    cliente autenticado de una vez. Mismo patrón que complete_password_reset:
    verify_otp con token_hash en vez del flujo de fragmento de URL por
    defecto (#access_token=...), que Streamlit no puede leer del lado
    servidor. Requiere personalizar la plantilla "Confirm signup" en
    Supabase para que enlace a {{ .SiteURL }}/?token_hash={{ .TokenHash }}
    &type=signup en vez de {{ .ConfirmationURL }}.
    """
    supabase = get_supabase_client()
    st.session_state.pop("auth_error", None)

    try:
        res = supabase.auth.verify_otp({"token_hash": token_hash, "type": "signup"})
    except Exception as exc:
        st.session_state["auth_error"] = mensaje_error_auth(
            exc, "El enlace de confirmación no es válido o ya expiró."
        )
        return False

    if res.user is None or res.session is None:
        st.session_state["auth_error"] = "El enlace de confirmación no es válido o ya expiró."
        return False

    _abrir_sesion(res.user, res.session)
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
        sesion_persistente.borrar_sesion()


def _abrir_sesion(user, session, expira: float | None = None) -> None:
    """
    Deja al usuario autenticado en session_state (mismo camino para login,
    recuperación de contraseña, confirmación de correo y sesión restaurada)
    y recuerda la sesión en el navegador (utils/sesion_persistente.py).
    `expira`: vencimiento de la cookie a conservar al restaurar/renovar —
    las horas cuentan desde el login original, no se estiran con el uso.
    """
    _load_perfil(user.id)
    st.session_state["user"] = user
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    st.session_state["cliente_id"] = user.id
    sesion_persistente.guardar_sesion(session.refresh_token, expira)


def restaurar_sesion() -> bool:
    """
    Si no hay login en esta conexión pero el navegador trae la cookie de
    sesión recordada vigente, pide a Supabase una sesión nueva con ese
    refresh token y deja al usuario adentro sin pedirle la contraseña.
    """
    guardada = sesion_persistente.leer_sesion()
    if guardada is None:
        return False
    token, expira = guardada
    try:
        res = get_supabase_client().auth.refresh_session(token)
    except Exception:
        # Token revocado (cerró sesión en otro lado), ya usado o expirado.
        sesion_persistente.borrar_sesion()
        return False
    if res.user is None or res.session is None:
        sesion_persistente.borrar_sesion()
        return False
    _abrir_sesion(res.user, res.session, expira)
    return True


def mantener_sesion() -> None:
    """
    Al inicio de cada corrida con usuario autenticado: renueva el token de
    acceso si está por vencer (dura 1 h) y, como Supabase rota el refresh
    token en cada renovación, actualiza la cookie con el nuevo. Se hace aquí
    y no en segundo plano a propósito — ver utils/supabase_client.py.
    """
    try:
        session = get_supabase_client().auth.get_session()
    except Exception:
        return  # falla de red puntual: se reintenta en la próxima corrida
    if session is None:
        return
    st.session_state["access_token"] = session.access_token
    st.session_state["refresh_token"] = session.refresh_token
    if session.refresh_token != sesion_persistente.token_guardado():
        sesion_persistente.guardar_sesion(session.refresh_token, sesion_persistente.expira_guardado())


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
        # .maybe_single() (no .single()): .single() lanza una excepción si no
        # encuentra la fila, así que el "else" de abajo (pensado justo para el
        # caso borde de latencia del trigger tras el signup) nunca se
        # ejecutaba — el login reventaba con un error en pantalla en vez de
        # degradar como estaba previsto. Mismo método que ya usan
        # get_cliente()/get_onboarding() en utils/queries.py.
        .maybe_single()
        .execute()
    )
    if resp.data:
        st.session_state["rol"] = resp.data.get("rol", "cliente")
        st.session_state["nombre_completo"] = resp.data.get("nombre_completo", "")
    else:
        # Caso borde: el trigger aún no ha corrido (latencia mínima tras el signup).
        st.session_state["rol"] = "cliente"
        st.session_state["nombre_completo"] = ""
