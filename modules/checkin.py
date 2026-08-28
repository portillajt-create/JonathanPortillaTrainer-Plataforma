"""
Módulo de Seguimiento Semanal (Check-in) y Centro de Notificaciones —
Paso 6 (reorganizado tras el feedback de diseño: ya no hay un "Centro de
Alertas" aparte; cada alerta vive en la página donde el admin ya la
necesita: vencimientos en Gestión de Clientes [admin_clientes.py] y
deload en Entrenamiento [rutinas.py, usando render_alertas_deload de
aquí]).

  - render_checkin_cliente: formulario semanal (1-10: adherencia a dieta/
    entreno, calidad de sueño, estrés, fatiga + peso corporal). Un solo
    check-in por semana calendario: se guarda con upsert sobre el lunes
    de esa semana, así que reenviar el formulario la misma semana
    actualiza el dato en vez de duplicarlo.
  - render_alertas_deload: semanas de descarga sugeridas (2 check-ins
    consecutivos con fatiga/estrés altos o sueño bajo), con botón para
    notificar al cliente. Se embebe en la página "Entrenamiento" del admin.
  - render_alertas_adherencia_dieta: baja adherencia sostenida a la dieta
    (2 check-ins consecutivos con "adherencia a la dieta" baja), con botón
    para notificar. Se embebe en "Nutrición y Macros" [nutricion.py, vía
    render_alertas_nutricion].
  - render_notificaciones_cliente: centro de notificaciones in-app del
    cliente, con marcado de leídas. También dispara (de forma perezosa,
    al entrar) la notificación de check-in semanal faltante si la semana
    pasada terminó sin registro.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from utils.auth import current_cliente_id
from utils.formato import escapar_markdown
from utils.notificaciones import crear_notificacion, crear_notificacion_sistema
from utils.queries import (
    descartar_alerta,
    get_checkin_semana,
    get_cliente,
    list_alertas_descartadas,
    list_checkins,
    list_clientes_con_suscripcion,
    list_notificaciones,
    marcar_notificacion_leida,
    marcar_todas_notificaciones_leidas,
    upsert_checkin,
)

UMBRAL_FATIGA_ALTA = 8
UMBRAL_ESTRES_ALTO = 8
UMBRAL_SUENO_BAJO = 4
UMBRAL_ADHERENCIA_DIETA_BAJA = 5


def _inicio_semana_actual() -> date:
    hoy = date.today()
    return hoy - timedelta(days=hoy.weekday())


# ---------------------------------------------------------------------------
# Check-in semanal (cliente)
# ---------------------------------------------------------------------------
def render_checkin_cliente(cliente_id: str) -> None:
    st.subheader("Check-in Semanal")

    if not cliente_id:
        st.warning("No se encontró tu identificador de cliente.")
        return

    semana_actual = _inicio_semana_actual()
    checkin_actual = get_checkin_semana(cliente_id, semana_actual) or {}

    if checkin_actual:
        st.caption(f"Ya registraste tu check-in de esta semana (desde el {semana_actual.isoformat()}). Puedes actualizarlo.")
    else:
        st.info(
            f"Check-in de la semana que inicia el {semana_actual.isoformat()}. "
            "Puntúa cada aspecto de 1 (muy bajo) a 10 (muy alto)."
        )

    with st.form("checkin_form"):
        col1, col2 = st.columns(2)
        with col1:
            adherencia_dieta = st.slider("Adherencia a la dieta", 1, 10, value=checkin_actual.get("adherencia_dieta") or 7)
            calidad_sueno = st.slider("Calidad del sueño", 1, 10, value=checkin_actual.get("calidad_sueno") or 7)
            fatiga = st.slider("Fatiga (10 = muy fatigado)", 1, 10, value=checkin_actual.get("fatiga") or 4)
        with col2:
            adherencia_entrenamiento = st.slider(
                "Adherencia al entrenamiento", 1, 10, value=checkin_actual.get("adherencia_entrenamiento") or 7
            )
            nivel_estres = st.slider("Nivel de estrés (10 = muy estresado)", 1, 10, value=checkin_actual.get("nivel_estres") or 4)
            peso_corporal_kg = st.number_input(
                "Peso corporal (kg)", min_value=30.0, max_value=250.0, step=0.1,
                value=float(checkin_actual.get("peso_corporal_kg") or 70.0),
            )

        notas = st.text_area("Notas de la semana (opcional)", value=checkin_actual.get("notas") or "")

        submitted = st.form_submit_button("💾 Guardar check-in", use_container_width=True, type="primary")

    if submitted:
        upsert_checkin(
            cliente_id,
            semana_fecha=semana_actual.isoformat(),
            adherencia_dieta=adherencia_dieta,
            adherencia_entrenamiento=adherencia_entrenamiento,
            calidad_sueno=calidad_sueno,
            nivel_estres=nivel_estres,
            fatiga=fatiga,
            peso_corporal_kg=peso_corporal_kg,
            notas=notas,
        )
        st.success("Check-in guardado. ¡Gracias por la actualización!")
        st.rerun()


# ---------------------------------------------------------------------------
# Alerta de deload — se embebe en la página "Entrenamiento" del admin
# ---------------------------------------------------------------------------
def render_alertas_deload() -> None:
    alertas = []
    for cliente in list_clientes_con_suscripcion():
        checkins = list_checkins(cliente["cliente_id"])
        if len(checkins) < 2:
            continue
        ultimas_dos = checkins[-2:]
        fechas = [date.fromisoformat(ci["semana_fecha"]) for ci in ultimas_dos]
        son_consecutivas = (fechas[1] - fechas[0]).days == 7
        if son_consecutivas and all(_semana_critica(ci) for ci in ultimas_dos):
            alertas.append(cliente)

    if not alertas:
        st.success("✅ Ningún cliente muestra señales de necesitar una semana de descarga.")
        return

    for cliente in alertas:
        nombre = escapar_markdown(cliente["nombre_completo"] or cliente["email"])
        col1, col2 = st.columns([4, 1])
        with col1:
            st.warning(
                f"🟠 **{nombre}** — fatiga/estrés altos o sueño bajo en las últimas 2 semanas consecutivas. "
                "Considera sugerir una semana de descarga."
            )
        with col2:
            if st.button("🔔 Sugerir", key=f"recordar_deload_{cliente['cliente_id']}", use_container_width=True):
                crear_notificacion(
                    cliente["cliente_id"],
                    tipo="alerta_deload",
                    titulo="Tu entrenador sugiere una semana de descarga",
                    mensaje=(
                        "Según tus últimos check-ins, tu entrenador recomienda bajar la intensidad esta "
                        "semana (semana de descarga) para recuperar mejor."
                    ),
                    creado_por=current_cliente_id(),
                )
                st.success(f"Notificación enviada a {nombre}.")


def _semana_critica(checkin: dict[str, Any]) -> bool:
    fatiga = checkin.get("fatiga") or 0
    estres = checkin.get("nivel_estres") or 0
    sueno = checkin.get("calidad_sueno")
    sueno_bajo = sueno is not None and sueno <= UMBRAL_SUENO_BAJO
    return fatiga >= UMBRAL_FATIGA_ALTA or estres >= UMBRAL_ESTRES_ALTO or sueno_bajo


# ---------------------------------------------------------------------------
# Alerta de adherencia a la dieta — se embebe en la página "Nutrición y Macros"
# ---------------------------------------------------------------------------
def render_alertas_adherencia_dieta() -> None:
    descartadas = list_alertas_descartadas("alerta_adherencia_dieta")

    alertas = []
    for cliente in list_clientes_con_suscripcion():
        checkins = list_checkins(cliente["cliente_id"])
        if len(checkins) < 2:
            continue
        ultimas_dos = checkins[-2:]
        fechas = [date.fromisoformat(ci["semana_fecha"]) for ci in ultimas_dos]
        son_consecutivas = (fechas[1] - fechas[0]).days == 7
        adherencia_baja = all((ci.get("adherencia_dieta") or 10) <= UMBRAL_ADHERENCIA_DIETA_BAJA for ci in ultimas_dos)
        semana_referencia = fechas[1].isoformat()
        if son_consecutivas and adherencia_baja and (cliente["cliente_id"], semana_referencia) not in descartadas:
            alertas.append({**cliente, "semana_referencia": semana_referencia})

    if not alertas:
        st.success("✅ Ningún cliente muestra baja adherencia sostenida a su dieta actual.")
        return

    for cliente in alertas:
        nombre = escapar_markdown(cliente["nombre_completo"] or cliente["email"])
        col1, col2 = st.columns([4, 1])
        with col1:
            st.warning(
                f"🍽️ **{nombre}** — adherencia baja a la dieta en las últimas 2 semanas consecutivas. "
                "Considera ajustar su plan alimenticio."
            )
        with col2:
            if st.button("🗑️ Eliminar alerta", key=f"descartar_dieta_{cliente['cliente_id']}", use_container_width=True):
                descartar_alerta(
                    cliente["cliente_id"], "alerta_adherencia_dieta", cliente["semana_referencia"], current_cliente_id()
                )
                st.rerun()


def _generar_notificacion_checkin_faltante(cliente_id: str) -> None:
    """
    Si la semana pasada (lunes a domingo, ya cerrada) terminó sin check-in,
    crea la notificación una sola vez por semana faltante. Se llama al
    entrar a "Mis Notificaciones" en vez de con un cron, porque la app no
    tiene un proceso en segundo plano — se evalúa de forma perezosa en
    cada visita, con guardas para no duplicar ni avisar antes de tiempo.
    """
    semana_actual = _inicio_semana_actual()
    semana_pasada = semana_actual - timedelta(days=7)

    cliente = get_cliente(cliente_id)
    fecha_creacion_str = (cliente.get("created_at") if cliente else None) or ""
    if fecha_creacion_str and date.fromisoformat(fecha_creacion_str[:10]) > semana_pasada:
        return  # el cliente todavía no existía en esa semana

    if get_checkin_semana(cliente_id, semana_pasada):
        return  # sí lo llenó

    ya_avisado = any(
        n["tipo"] == "checkin_faltante" and (n.get("created_at") or "") >= semana_actual.isoformat()
        for n in list_notificaciones(cliente_id)
    )
    if ya_avisado:
        return

    # crear_notificacion_sistema (no crear_notificacion): esta alerta la dispara
    # la sesión del propio CLIENTE, y la policy de INSERT de "notificaciones"
    # exige ser admin. Sin esa vía el registro se rechazaba siempre y, como el
    # correo sale antes del insert, el cliente recibía el mismo correo en cada
    # visita a esta pantalla.
    crear_notificacion_sistema(
        cliente_id,
        tipo="checkin_faltante",
        titulo="Check-in semanal pendiente",
        mensaje=(
            f"No registraste tu check-in de la semana del {semana_pasada.isoformat()} al "
            f"{(semana_pasada + timedelta(days=6)).isoformat()}. Complétalo en 'Check-in Semanal' "
            "para que tu entrenador pueda dar seguimiento a tu progreso."
        ),
    )


# ---------------------------------------------------------------------------
# Centro de notificaciones (cliente)
# ---------------------------------------------------------------------------
def render_notificaciones_cliente(cliente_id: str) -> None:
    st.subheader("Mis Notificaciones")

    if not cliente_id:
        st.warning("No se encontró tu identificador de cliente.")
        return

    _generar_notificacion_checkin_faltante(cliente_id)
    notificaciones = list_notificaciones(cliente_id)
    if not notificaciones:
        st.info("No tienes notificaciones todavía.")
        return

    no_leidas = sum(1 for n in notificaciones if not n["leida"])
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"{no_leidas} sin leer de {len(notificaciones)} en total.")
    with col2:
        if no_leidas and st.button("Marcar todas como leídas", use_container_width=True):
            marcar_todas_notificaciones_leidas(cliente_id)
            st.rerun()

    for n in notificaciones:
        icono = _icono_tipo(n["tipo"])
        etiqueta = f"{icono} {n['titulo']}" if n["leida"] else f"{icono} **{n['titulo']}** 🔵 nuevo"
        with st.expander(etiqueta):
            st.write(n["mensaje"])
            st.caption((n.get("created_at") or "")[:16].replace("T", " "))
            if not n["leida"]:
                if st.button("Marcar como leída", key=f"leida_{n['id']}"):
                    marcar_notificacion_leida(n["id"])
                    st.rerun()


def _icono_tipo(tipo: str) -> str:
    return {
        "dieta_actualizada": "🥗",
        "rutina_actualizada": "🏋️",
        "alerta_vencimiento": "⏰",
        "alerta_deload": "😮‍💨",
        "alerta_estancamiento": "📉",
        "alerta_adherencia_dieta": "🍽️",
        "checkin_faltante": "📅",
        "general": "🔔",
    }.get(tipo, "🔔")
