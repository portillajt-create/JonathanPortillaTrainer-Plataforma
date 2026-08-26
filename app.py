"""
Jonathan Portilla Trainer — Dashboard de Asesorías de Entrenamiento y Nutrición.

Punto de entrada de la app. Responsabilidades de este archivo:
  1. Pantalla de login / registro de clientes.
  2. Cargar el rol del usuario autenticado (admin vs. cliente).
  3. Enrutar hacia el "shell" de navegación correspondiente.
  4. (Desde el Paso 2) Selector real de cliente para las páginas de admin,
     y bloqueo de acceso si la suscripción del cliente está inactiva/vencida.

Los módulos de negocio (clientes, onboarding, nutrición, rutinas, Hevy,
check-in) viven en modules/ y se van implementando en los Pasos 2 a 6;
los que aún no se han construido quedan conectados como stubs para que la
navegación funcione desde ya.
"""

import streamlit as st
from streamlit_option_menu import option_menu

from modules import admin_clientes, checkin, hevy_integration, nutricion, onboarding, rutinas
from utils import theme
from utils.auth import (
    complete_password_reset,
    current_role,
    is_authenticated,
    login,
    logout,
    request_password_reset,
    signup_cliente,
)
from utils.branding import FAVICON, ICON, LOGIN_HERO, LOGO_FULL, NOMBRE
from utils.notificaciones import notificar_admin_nuevo_cliente
from utils.queries import get_onboarding, get_suscripcion_vista, list_clientes
from utils.session import init_session_state

st.set_page_config(page_title="Jonathan Portilla Trainer", page_icon=str(FAVICON), layout="wide")
st.logo(str(LOGO_FULL), icon_image=str(ICON))
theme.inject()

init_session_state()


# ---------------------------------------------------------------------------
# Pantalla de autenticación
# ---------------------------------------------------------------------------
def render_auth_screen() -> None:
    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        st.image(str(LOGIN_HERO), use_container_width=True)
    st.caption("<p style='text-align:center'>Plataforma de asesorías de entrenamiento y nutrición</p>", unsafe_allow_html=True)

    tab_login, tab_signup = st.tabs(["Iniciar sesión", "Crear cuenta (clientes)"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Correo electrónico")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar sesión", use_container_width=True, type="primary")

        if submitted:
            if login(email, password):
                st.rerun()
            else:
                st.error(st.session_state.get("auth_error") or "Correo o contraseña incorrectos.")

        with st.expander("¿Olvidaste tu contraseña?"):
            with st.form("forgot_password_form"):
                email_recuperar = st.text_input("Correo electrónico", key="forgot_password_email")
                enviar_recuperacion = st.form_submit_button("Enviar enlace de recuperación", use_container_width=True)

            if enviar_recuperacion:
                if not email_recuperar:
                    st.warning("Escribe tu correo electrónico.")
                else:
                    try:
                        request_password_reset(email_recuperar)
                        st.success(
                            "📧 Si ese correo está registrado, te enviamos un enlace para "
                            "restablecer tu contraseña. Revisa tu bandeja de entrada (y spam)."
                        )
                    except Exception as exc:
                        st.error(f"No se pudo enviar el correo: {exc}")

    with tab_signup:
        st.caption("Regístrate aquí si tu entrenador te compartió el enlace de esta plataforma.")
        with st.form("signup_form"):
            nombre = st.text_input("Nombre completo")
            email_signup = st.text_input("Correo electrónico", key="signup_email")
            password_signup = st.text_input("Contraseña", type="password", key="signup_password")
            submitted_signup = st.form_submit_button("Crear cuenta", use_container_width=True, type="primary")

        if submitted_signup:
            if not nombre.strip() or not email_signup.strip():
                st.warning("Completa tu nombre y correo electrónico.")
            elif len(password_signup) < 8:
                st.warning("La contraseña debe tener al menos 8 caracteres.")
            else:
                try:
                    signup_cliente(email_signup, password_signup, nombre)
                    notificar_admin_nuevo_cliente(nombre, email_signup)
                    st.success(
                        "✅ ¡Cuenta creada con éxito! Ve a la pestaña **'Iniciar sesión'** de arriba "
                        "y entra con el correo y la contraseña que acabas de registrar."
                    )
                except Exception as exc:
                    st.error(f"No se pudo crear la cuenta: {exc}")


# ---------------------------------------------------------------------------
# Pantalla de restablecer contraseña (llega desde el enlace del correo de
# recuperación). El enlace apunta a la app con ?token_hash=...&type=recovery
# en vez de sesión iniciada, así que esta pantalla se muestra por encima de
# cualquier otra cosa, sin importar si hay o no una sesión activa.
# ---------------------------------------------------------------------------
def render_reset_password_screen(token_hash: str) -> None:
    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        st.image(str(LOGIN_HERO), use_container_width=True)
    st.subheader("Restablecer contraseña")
    st.caption("Escribe tu nueva contraseña para continuar.")

    with st.form("reset_password_form"):
        nueva = st.text_input("Nueva contraseña", type="password")
        confirmar = st.text_input("Confirmar nueva contraseña", type="password")
        submitted = st.form_submit_button("Guardar nueva contraseña", use_container_width=True, type="primary")

    if submitted:
        if not nueva or len(nueva) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
        elif nueva != confirmar:
            st.error("Las contraseñas no coinciden.")
        elif complete_password_reset(token_hash, nueva):
            st.query_params.clear()
            st.success("✅ Contraseña actualizada. Entrando...")
            st.rerun()
        else:
            st.error(st.session_state.get("auth_error") or "El enlace no es válido o ya expiró. Solicita uno nuevo.")


# ---------------------------------------------------------------------------
# Encabezado (icono) y pie de página (nombre) — se repiten en cada sección
# ---------------------------------------------------------------------------
def _render_titulo(pagina: str) -> None:
    st.image(str(ICON), width=64)
    st.title(pagina)


def _render_pie_pagina() -> None:
    st.divider()
    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        st.image(str(NOMBRE), width=280)


# ---------------------------------------------------------------------------
# Selector de cliente reutilizable en las páginas de admin
# ---------------------------------------------------------------------------
def _selector_cliente(key: str) -> str | None:
    clientes = list_clientes()
    if not clientes:
        st.info("Todavía no hay clientes registrados.")
        return None

    opciones = {f"{c['nombre_completo'] or c['email']} — {c['email']}": c["id"] for c in clientes}
    with st.container(border=True):
        st.markdown("###### 👤 Cliente seleccionado")
        seleccion = st.selectbox("Cliente", list(opciones.keys()), key=key, label_visibility="collapsed")
    return opciones[seleccion]


# ---------------------------------------------------------------------------
# Shell de navegación — Entrenador / Admin
# ---------------------------------------------------------------------------
ADMIN_PAGINAS = ["Gestión de Clientes", "Ficha del Atleta", "Nutrición y Macros", "Entrenamiento", "Progreso"]
ADMIN_ICONOS = ["people-fill", "clipboard2-pulse", "egg-fried", "lightning-charge-fill", "graph-up-arrow"]


def render_admin_shell() -> None:
    nombre = st.session_state.get("nombre_completo") or "Entrenador"

    with st.sidebar:
        theme.render_perfil_sidebar(nombre, "Administrador")
        pagina = option_menu(
            menu_title=None,
            options=ADMIN_PAGINAS,
            icons=ADMIN_ICONOS,
            default_index=0,
            styles=theme.MENU_STYLES,
            key="admin_nav",
        )
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()

    _render_titulo(pagina)

    if pagina == "Gestión de Clientes":
        admin_clientes.render()
    elif pagina == "Ficha del Atleta":
        cliente_id = _selector_cliente(key="selector_ficha")
        if cliente_id:
            onboarding.render_ficha_admin(cliente_id)
    elif pagina == "Nutrición y Macros":
        nutricion.render_alertas_nutricion()
        st.divider()
        cliente_id = _selector_cliente(key="selector_nutricion")
        if cliente_id:
            nutricion.render_admin(cliente_id)
    elif pagina == "Entrenamiento":
        rutinas.render_alertas_entrenamiento()
        st.divider()
        cliente_id = _selector_cliente(key="selector_rutinas")
        if cliente_id:
            rutinas.render_admin(cliente_id)
    elif pagina == "Progreso":
        cliente_id = _selector_cliente(key="selector_progreso")
        if cliente_id:
            hevy_integration.render_progreso(cliente_id)

    _render_pie_pagina()


# ---------------------------------------------------------------------------
# Shell de navegación — Cliente
# ---------------------------------------------------------------------------
CLIENTE_PAGINAS = ["Mis Notificaciones", "Mi Perfil", "Mi Dieta", "Mi Entrenamiento", "Mi Progreso", "Check-in Semanal"]
CLIENTE_ICONOS = ["bell-fill", "person-badge", "egg-fried", "lightning-charge-fill", "graph-up-arrow", "calendar2-check"]


def render_cliente_shell() -> None:
    nombre = st.session_state.get("nombre_completo") or "Cliente"
    cliente_id = st.session_state.get("cliente_id")

    suscripcion = get_suscripcion_vista(cliente_id) if cliente_id else None
    if suscripcion and (suscripcion.get("estado") == "Inactivo" or suscripcion.get("vencida")):
        with st.sidebar:
            theme.render_perfil_sidebar(nombre, "Cliente")
            if st.button("Cerrar sesión", use_container_width=True):
                logout()
                st.rerun()
        _render_titulo("Plan no activo")
        st.error(
            "🚫 Tu plan de asesoría no está activo actualmente.\n\n"
            "Contacta a tu entrenador para renovar tu suscripción y recuperar el acceso "
            "completo al panel (dieta, rutina, progreso y check-ins)."
        )
        _render_pie_pagina()
        return

    with st.sidebar:
        theme.render_perfil_sidebar(nombre, "Cliente")
        onboarding_completo = bool(get_onboarding(cliente_id)) if cliente_id else True
        indice_inicial = CLIENTE_PAGINAS.index("Mis Notificaciones" if onboarding_completo else "Mi Perfil")
        pagina = option_menu(
            menu_title=None,
            options=CLIENTE_PAGINAS,
            icons=CLIENTE_ICONOS,
            default_index=indice_inicial,
            styles=theme.MENU_STYLES,
            key="cliente_nav",
        )
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
            st.rerun()

    _render_titulo(pagina)

    if pagina == "Mi Perfil":
        onboarding.render_formulario_cliente(cliente_id)
    elif pagina == "Mi Dieta":
        nutricion.render_cliente(cliente_id)
    elif pagina == "Mi Entrenamiento":
        rutinas.render_cliente(cliente_id)
    elif pagina == "Mi Progreso":
        hevy_integration.render_progreso(cliente_id)
    elif pagina == "Check-in Semanal":
        checkin.render_checkin_cliente(cliente_id)
    elif pagina == "Mis Notificaciones":
        checkin.render_notificaciones_cliente(cliente_id)

    _render_pie_pagina()


# ---------------------------------------------------------------------------
# Enrutador principal
# ---------------------------------------------------------------------------
_reset_token_hash = st.query_params.get("token_hash")
if _reset_token_hash and st.query_params.get("type") == "recovery":
    render_reset_password_screen(_reset_token_hash)
elif not is_authenticated():
    render_auth_screen()
elif current_role() == "admin":
    render_admin_shell()
else:
    render_cliente_shell()
