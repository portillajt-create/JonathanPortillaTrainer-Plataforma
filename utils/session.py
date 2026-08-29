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
    # "supabase_client" no se borraba antes: logout() llama a
    # supabase.auth.sign_out() pero si esa llamada falla (red, token ya
    # vencido) el error se traga en silencio y el objeto cliente queda en
    # memoria del servidor con un token que puede seguir siendo válido,
    # aunque la pantalla ya muestre el login. Borrando la clave, la próxima
    # get_supabase_client() crea un cliente nuevo y sin sesión, sin depender
    # de que sign_out() haya funcionado.
    "supabase_client",
]

# Prefijos de claves dinámicas (una por cliente, o por cliente+día) que
# guardan datos que el ADMIN estaba editando en pantalla: plan de comidas,
# notas y bloques de una rutina. No son credenciales, pero cerrar sesión
# debería soltarlas igual — si no, ese texto sin guardar queda en memoria
# del servidor después del logout.
_PREFIJOS_ESTADO_ADMIN = (
    "dieta_plan_comidas_",
    "dieta_notas_adicionales_",
    "rutina_bloques_",
    "rutina_etiqueta_",
)


def init_session_state() -> None:
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("rol", None)


def clear_auth_state() -> None:
    for key in AUTH_KEYS:
        st.session_state.pop(key, None)

    st.session_state.pop("selector_cliente_admin", None)
    for key in [k for k in st.session_state if k.startswith(_PREFIJOS_ESTADO_ADMIN)]:
        del st.session_state[key]
