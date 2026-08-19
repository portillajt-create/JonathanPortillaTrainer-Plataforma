"""
Cliente de Supabase.

⚠️ Detalle de arquitectura importante:
Streamlit ejecuta UNA sola app compartida por todos los usuarios que la
visitan (entrenador y cada cliente). Si cacheáramos el cliente de Supabase
con `st.cache_resource` (como sugieren muchos tutoriales), estaríamos
compartiendo UNA sola sesión de autenticación entre TODOS los navegadores
conectados al mismo tiempo: el usuario B heredaría el token del usuario A.

Por eso aquí el cliente se crea una vez POR SESIÓN de Streamlit y se guarda
en `st.session_state`, que sí es privado por navegador/pestaña. Esto
garantiza que el token de sesión de cada persona (admin o cliente) quede
aislado y que las políticas RLS se apliquen con la identidad correcta.
"""

import streamlit as st
from supabase import Client, create_client

from config import SUPABASE_ANON_KEY, SUPABASE_URL

_CLIENT_KEY = "supabase_client"


def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        st.error(
            "Faltan las variables SUPABASE_URL / SUPABASE_ANON_KEY. "
            "Configúralas en tu archivo .env (local) o en .streamlit/secrets.toml (producción)."
        )
        st.stop()

    if _CLIENT_KEY not in st.session_state:
        st.session_state[_CLIENT_KEY] = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

    return st.session_state[_CLIENT_KEY]
