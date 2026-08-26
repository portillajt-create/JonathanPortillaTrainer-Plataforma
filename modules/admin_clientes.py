"""
Módulo de Gestión de Clientes y Suscripciones (EXCLUSIVO ADMIN) — Paso 2.

Vista en tarjetas de todos los clientes, con:
  - Métricas rápidas (total, activos, por vencer, vencidos/inactivos).
  - Alertas de vencimiento de suscripción, con botón para notificar al
    cliente (se integró aquí en el rediseño visual; antes vivía en un
    "Centro de Alertas" aparte).
  - Buscador y filtro por estado.
  - Control de estado (Activo/Inactivo), tipo de plan, fecha de último pago
    y fecha de vencimiento por cliente, con alertas visuales de días
    restantes (se calculan en la vista SQL "vista_suscripciones").

Si un cliente queda "Inactivo" (o su suscripción vence), el bloqueo de
acceso correspondiente se aplica en app.py al entrar a la app como cliente.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from utils.auth import current_cliente_id
from utils.notificaciones import crear_notificacion
from utils.queries import admin_eliminar_cliente, list_clientes_con_suscripcion, upsert_suscripcion

PLANES = ["Mensual", "Trimestral", "Semestral", "Personalizado"]


def render() -> None:
    st.subheader("Gestión de Clientes y Suscripciones")

    clientes = list_clientes_con_suscripcion()
    if not clientes:
        st.info("Todavía no hay clientes registrados. Comparte el enlace de la app para que se registren.")
        return

    _render_metricas(clientes)
    st.divider()
    _render_alertas_vencimiento(clientes)
    st.divider()

    col_buscar, col_filtro = st.columns([2, 1])
    with col_buscar:
        filtro_texto = st.text_input("🔎 Buscar por nombre o correo")
    with col_filtro:
        filtro_estado = st.selectbox(
            "Filtrar por estado",
            ["Todos", "Activo", "Por vencer", "Vencido / Inactivo", "Sin suscripción"],
        )

    clientes_filtrados = [c for c in clientes if _coincide_filtro(c, filtro_texto, filtro_estado)]

    if not clientes_filtrados:
        st.warning("Ningún cliente coincide con el filtro seleccionado.")
        return

    for cliente in clientes_filtrados:
        badge = _badge_estado(cliente)
        dias = cliente.get("dias_restantes")
        dias_txt = f" · {dias} días restantes" if dias is not None else ""
        titulo = f"{badge} — {cliente['nombre_completo'] or cliente['email']}{dias_txt}"
        with st.expander(titulo):
            _render_form_suscripcion(cliente)


def _render_metricas(clientes: list[dict]) -> None:
    total = len(clientes)
    activos = sum(1 for c in clientes if c["estado"] == "Activo" and not c["vencida"])
    por_vencer = sum(1 for c in clientes if c["por_vencer"])
    vencidos = sum(1 for c in clientes if c["vencida"] or c["estado"] == "Inactivo")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total clientes", total)
    col2.metric("Activos", activos)
    col3.metric("Por vencer (≤5 días)", por_vencer)
    col4.metric("Vencidos / inactivos", vencidos)


def _render_alertas_vencimiento(clientes: list[dict]) -> None:
    alertas = [c for c in clientes if c["vencida"] or c["por_vencer"]]
    if not alertas:
        st.success("🔔 Ningún cliente tiene la suscripción vencida o por vencer.")
        return

    st.markdown("##### 🔔 Vencimientos de suscripción")
    for cliente in alertas:
        dias = cliente.get("dias_restantes")
        nombre = cliente["nombre_completo"] or cliente["email"]
        col1, col2 = st.columns([4, 1])
        with col1:
            if cliente["vencida"]:
                st.error(f"🔴 **{nombre}** — suscripción vencida ({dias if dias is not None else '—'} días).")
            else:
                st.warning(f"🟡 **{nombre}** — vence en {dias} día(s).")
        with col2:
            if st.button("🔔 Recordar", key=f"recordar_venc_{cliente['cliente_id']}", use_container_width=True):
                crear_notificacion(
                    cliente["cliente_id"],
                    tipo="alerta_vencimiento",
                    titulo="Tu suscripción está por vencer",
                    mensaje=(
                        "Tu plan de asesoría vence pronto. Contacta a tu entrenador para renovarlo y no "
                        "perder acceso a tu dieta, rutina y seguimiento."
                    ),
                    creado_por=current_cliente_id(),
                )
                st.success(f"Notificación enviada a {nombre}.")


def _badge_estado(cliente: dict) -> str:
    if cliente["estado"] == "Sin suscripción":
        return "⚪ Sin suscripción"
    if cliente["estado"] == "Inactivo":
        return "🔴 Inactivo"
    if cliente["vencida"]:
        return "🔴 Vencida"
    if cliente["por_vencer"]:
        return "🟡 Por vencer"
    return "🟢 Activo"


def _coincide_filtro(cliente: dict, filtro_texto: str, filtro_estado: str) -> bool:
    if filtro_texto:
        texto = filtro_texto.lower()
        if texto not in (cliente["nombre_completo"] or "").lower() and texto not in (cliente["email"] or "").lower():
            return False

    badge = _badge_estado(cliente)
    mapa_filtro = {
        "Activo": "🟢",
        "Por vencer": "🟡",
        "Vencido / Inactivo": "🔴",
        "Sin suscripción": "⚪",
    }
    if filtro_estado != "Todos" and not badge.startswith(mapa_filtro[filtro_estado]):
        return False
    return True


def _render_form_suscripcion(cliente: dict) -> None:
    cliente_id = cliente["cliente_id"]
    st.caption(cliente["email"])

    plan_actual = cliente["tipo_plan"] if cliente["tipo_plan"] in PLANES else PLANES[0]
    estado_actual = "Inactivo" if cliente["estado"] == "Inactivo" else "Activo"
    fecha_pago_actual = date.fromisoformat(cliente["fecha_ultimo_pago"]) if cliente["fecha_ultimo_pago"] else date.today()
    fecha_venc_actual = (
        date.fromisoformat(cliente["fecha_vencimiento"]) if cliente["fecha_vencimiento"] else date.today() + timedelta(days=30)
    )

    with st.form(f"suscripcion_form_{cliente_id}"):
        col1, col2 = st.columns(2)
        with col1:
            tipo_plan = st.selectbox("Tipo de plan", PLANES, index=PLANES.index(plan_actual), key=f"plan_{cliente_id}")
            estado = st.selectbox(
                "Estado",
                ["Activo", "Inactivo"],
                index=["Activo", "Inactivo"].index(estado_actual),
                key=f"estado_{cliente_id}",
                help="Si queda 'Inactivo', el cliente verá un aviso de plan caducado al iniciar sesión.",
            )
        with col2:
            fecha_pago = st.date_input("Fecha del último pago", value=fecha_pago_actual, key=f"pago_{cliente_id}")
            fecha_vencimiento = st.date_input("Fecha de vencimiento", value=fecha_venc_actual, key=f"venc_{cliente_id}")

        guardar = st.form_submit_button("💾 Guardar suscripción", use_container_width=True)

    if guardar:
        upsert_suscripcion(
            cliente_id,
            tipo_plan=tipo_plan,
            estado=estado,
            fecha_ultimo_pago=fecha_pago.isoformat(),
            fecha_vencimiento=fecha_vencimiento.isoformat(),
        )
        st.success("Suscripción actualizada.")
        st.rerun()

    st.divider()
    if st.button("🗑️ Eliminar cliente", key=f"eliminar_{cliente_id}"):
        _confirmar_eliminar_cliente(cliente_id, cliente["nombre_completo"] or cliente["email"])


@st.dialog("Eliminar cliente")
def _confirmar_eliminar_cliente(cliente_id: str, nombre: str) -> None:
    st.warning(
        f"⚠️ Vas a eliminar por completo la cuenta de **{nombre}**: su perfil, dieta, rutina, "
        "check-ins y notificaciones desaparecen para siempre. Esta acción no se puede deshacer."
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()
    with col2:
        if st.button("Sí, eliminar definitivamente", use_container_width=True):
            admin_eliminar_cliente(cliente_id)
            st.success(f"{nombre} fue eliminado.")
            st.rerun()
