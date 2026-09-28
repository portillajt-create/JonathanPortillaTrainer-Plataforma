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

Cómo se resuelve: al iniciar sesión se guarda el refresh token de Supabase
en el localStorage del navegador, con vencimiento fijo a las
DURACION_SESION_HORAS del login (no se "estira" con el uso). En una sesión
nueva sin login, el navegador le devuelve ese valor a Python y con él se
pide a Supabase una sesión nueva (utils/auth.py:restaurar_sesion). Al
cerrar sesión se borra.

⚠️ Primera versión (mismo día) — NO repetir: guardaba el token en una
COOKIE y la leía del lado servidor con st.context.cookies. En local
funcionaba, pero en Streamlit Community Cloud el proxy elimina la cabecera
Cookie antes de que la petición llegue a la app: st.context.cookies llega
SIEMPRE vacío (verificado en producción con un diagnóstico que listaba los
nombres de cookies y cabeceras recibidas). Por eso ahora el valor viaja por
la conexión de Streamlit, con un componente v2 (st.components.v2: JS que
corre en la página y le devuelve valores a Python), que no depende de
cabeceras HTTP. Sin dependencias nuevas.

Otros detalles:
  - Supabase ROTA el refresh token cada vez que se usa, y castiga reusar uno
    viejo revocando toda la sesión. Por eso utils/supabase_client.py apaga
    el auto-refresh en segundo plano: el token solo se renueva durante una
    corrida del script (auth.mantener_sesion()), donde también se deja
    pendiente guardarlo.
  - Cada escritura (guardar o borrar) se reenvía al navegador en cada
    corrida hasta que el JS CONFIRMA que la hizo (estado "guardado"): así no
    se pierde si un st.rerun() reemplaza la página antes de que el navegador
    alcance a procesarla (login() y logout() hacen rerun justo después).
  - Seguridad (aceptado por el usuario): quien tenga el navegador
    desbloqueado dentro de esas horas entra sin contraseña, como en
    cualquier app con sesión recordada. A diferencia de una cookie, el
    localStorage no viaja en ninguna petición: solo lo lee el JS de la app.
"""

from __future__ import annotations

import time

import streamlit as st

DURACION_SESION_HORAS = 3

_PENDIENTE = "sesion_guardado_pendiente"  # str a guardar, "" = borrar
_EXPIRA = "sesion_expira"
_TOKEN_GUARDADO = "sesion_token_guardado"
_LECTURA_PROCESADA = "sesion_lectura_procesada"
#: Tras un logout, esta conexión no vuelve a intentar restaurar sesión.
DESCARTADA = "sesion_cookie_descartada"

_JS = """
export default function (component) {
    const { data, setStateValue } = component;
    const CLAVE = "jp_sesion";
    // Limpieza de la primera versión (cookie), que Streamlit Cloud no deja leer.
    document.cookie = CLAVE + "=; Path=/; Max-Age=0";
    if (!data) return;
    try {
        if (typeof data.guardar === "string") {
            if (data.guardar) localStorage.setItem(CLAVE, data.guardar);
            else localStorage.removeItem(CLAVE);
            setStateValue("guardado", data.guardar);
        }
        if (data.leer) setStateValue("leido", localStorage.getItem(CLAVE) || "");
    } catch (e) {
        // Sin localStorage (navegador en modo muy restringido): se comporta
        // como si no hubiera sesión guardada, nunca bloquea el login normal.
        if (data.leer) setStateValue("leido", "");
    }
}
"""

_puente = st.components.v2.component("jp_puente_sesion", js=_JS)


def _nada() -> None:
    pass


def guardar_sesion(refresh_token: str, expira: float | None = None) -> None:
    """Deja pendiente guardar la sesión. Sin `expira`, vence a las DURACION_SESION_HORAS de ahora."""
    expira = expira or time.time() + DURACION_SESION_HORAS * 3600
    st.session_state[_EXPIRA] = expira
    st.session_state[_TOKEN_GUARDADO] = refresh_token
    st.session_state[_PENDIENTE] = f"{refresh_token}|{int(expira)}"
    st.session_state.pop(DESCARTADA, None)


def borrar_sesion() -> None:
    st.session_state[_PENDIENTE] = ""
    st.session_state[DESCARTADA] = True
    st.session_state.pop(_EXPIRA, None)
    st.session_state.pop(_TOKEN_GUARDADO, None)


def expira_guardado() -> float | None:
    return st.session_state.get(_EXPIRA)


def token_guardado() -> str | None:
    return st.session_state.get(_TOKEN_GUARDADO)


def interpretar(valor: str | None) -> tuple[str, float] | None:
    """(refresh_token, vencimiento) del valor guardado, si es válido y no venció."""
    if not valor or "|" not in valor:
        return None
    token, _, expira_txt = valor.rpartition("|")
    try:
        expira = float(expira_txt)
    except ValueError:
        return None
    if not token or expira <= time.time():
        return None
    return token, expira


def sincronizar_navegador(sin_login: bool) -> str | None:
    """
    Monta el puente con el navegador (una vez por corrida, arriba del
    enrutador en app.py): envía la escritura pendiente y, si no hay login en
    esta conexión, pide leer la sesión guardada. Devuelve el valor leído UNA
    sola vez por conexión (luego None); "" si no había nada guardado.
    """
    leer = sin_login and not st.session_state.get(_LECTURA_PROCESADA) and not st.session_state.get(DESCARTADA)
    pendiente = st.session_state.get(_PENDIENTE)
    with st.container(key="jp_puente_sesion_wrap"):
        resultado = _puente(
            key="jp_puente_sesion",
            data={"guardar": pendiente, "leer": leer},
            on_guardado_change=_nada,
            on_leido_change=_nada,
        )
    # El JS confirmó la escritura: deja de reenviarla.
    if pendiente is not None and resultado.get("guardado") == pendiente:
        st.session_state.pop(_PENDIENTE, None)

    leido = resultado.get("leido")
    if leer and leido is not None:
        st.session_state[_LECTURA_PROCESADA] = True
        return leido
    return None
