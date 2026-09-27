"""
Sesión que sobrevive a una reconexión: "recordar" el login en el navegador
por DURACION_SESION_HORAS (pedido del usuario, 2026-09-27: los clientes se
quejaban de que la sesión "se cierra muy pronto").

Por qué se cerraba: el login de la app vive solo en st.session_state, que
Streamlit guarda en la memoria de la CONEXIÓN (websocket) de esa pestaña.
En el celular, al cambiar de app o bloquear la pantalla, el sistema corta
esa conexión; al volver, la página se recarga como una sesión nueva de
Streamlit, sin session_state, y se veía el login otra vez — no tenía nada
que ver con que el token de Supabase hubiera vencido.

Cómo se resuelve:
  1. Al iniciar sesión se guarda en una cookie del navegador el refresh
     token de Supabase, con vencimiento fijo a las DURACION_SESION_HORAS
     del login (no se "estira" con el uso).
  2. En una sesión nueva sin login, si esa cookie sigue vigente, se usa
     para pedirle a Supabase una sesión nueva (utils/auth.py:restaurar_sesion).
  3. Al cerrar sesión se borra.

Detalles importantes:
  - La cookie se ESCRIBE con JavaScript (st.components.v1.html sobre
    window.parent, el mismo mecanismo que ya usa theme.py) y se LEE del lado
    servidor con st.context.cookies, que son las cookies con las que el
    navegador abrió la conexión. Sin dependencias nuevas.
  - Supabase ROTA el refresh token cada vez que se usa, y castiga reusar uno
    viejo revocando toda la sesión. Por eso utils/supabase_client.py apaga
    el auto-refresh en segundo plano: el token solo se renueva durante una
    corrida del script (mantener_sesion()), que es donde también se puede
    actualizar la cookie. Si se renovara en un hilo aparte, la cookie
    quedaría con un token ya usado y la siguiente reconexión fallaría.
  - La escritura se deja "pendiente" en session_state y se emite recién en
    emitir_cookie_pendiente(), llamada en una corrida que llega a dibujar la
    página: login() y logout() hacen st.rerun() justo después, y un iframe
    dibujado antes del rerun podía no alcanzar a ejecutarse.
  - Seguridad (aceptado por el usuario): quien tenga el navegador
    desbloqueado dentro de esas horas entra sin contraseña, como en
    cualquier app con sesión recordada. La cookie es SameSite=Strict y
    Secure (en https); no puede ser HttpOnly porque la escribe JavaScript.
"""

from __future__ import annotations

import json
import time
from urllib.parse import unquote

import streamlit as st
import streamlit.components.v1 as components

COOKIE_SESION = "jp_sesion"
DURACION_SESION_HORAS = 3

_PENDIENTE = "sesion_cookie_pendiente"
_EXPIRA = "sesion_expira"
_TOKEN_GUARDADO = "sesion_token_guardado"
#: Tras un logout, la cookie vieja sigue apareciendo en st.context.cookies
#: durante toda esta conexión (son las cookies de cuando se abrió): esta
#: marca evita "re-loguear" al usuario con ella en la misma pestaña.
DESCARTADA = "sesion_cookie_descartada"


def guardar_sesion(refresh_token: str, expira: float | None = None) -> None:
    """Deja pendiente escribir la cookie. Sin `expira`, vence a las DURACION_SESION_HORAS de ahora."""
    expira = expira or time.time() + DURACION_SESION_HORAS * 3600
    st.session_state[_EXPIRA] = expira
    st.session_state[_TOKEN_GUARDADO] = refresh_token
    st.session_state[_PENDIENTE] = (f"{refresh_token}|{int(expira)}", max(int(expira - time.time()), 0))
    st.session_state.pop(DESCARTADA, None)


def borrar_sesion() -> None:
    st.session_state[_PENDIENTE] = ("", 0)
    st.session_state[DESCARTADA] = True
    st.session_state.pop(_EXPIRA, None)
    st.session_state.pop(_TOKEN_GUARDADO, None)


def leer_sesion() -> tuple[str, float] | None:
    """(refresh_token, vencimiento) de la cookie, si existe, no venció y no se descartó."""
    if st.session_state.get(DESCARTADA):
        return None
    try:
        crudo = st.context.cookies.get(COOKIE_SESION)
    except Exception:
        return None
    # La escribe encodeURIComponent() ("|" llega como "%7C").
    crudo = unquote(crudo or "")
    if "|" not in crudo:
        return None
    token, _, expira_txt = crudo.rpartition("|")
    try:
        expira = float(expira_txt)
    except ValueError:
        return None
    if not token or expira <= time.time():
        return None
    return token, expira


def expira_guardado() -> float | None:
    return st.session_state.get(_EXPIRA)


def token_guardado() -> str | None:
    return st.session_state.get(_TOKEN_GUARDADO)


def emitir_cookie_pendiente() -> None:
    """Escribe (o borra) la cookie si hay algo pendiente. Llamar en cada corrida que dibuja la página."""
    pendiente = st.session_state.pop(_PENDIENTE, None)
    if pendiente is None:
        return
    valor, max_age = pendiente
    components.html(
        f"""
<script>
(function () {{
    var seguro = window.parent.location.protocol === "https:" ? "; Secure" : "";
    window.parent.document.cookie = {json.dumps(COOKIE_SESION)} + "=" + encodeURIComponent({json.dumps(valor)})
        + "; Path=/; Max-Age=" + {int(max_age)} + "; SameSite=Strict" + seguro;
}})();
</script>
""",
        height=0,
    )
