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

import calendar
from datetime import date, timedelta

import streamlit as st

from utils.auth import current_cliente_id
from utils.formato import escapar_markdown
from utils.notificaciones import crear_notificacion
from utils.queries import admin_eliminar_cliente, list_clientes_con_suscripcion, upsert_suscripcion

PLANES = ["Mensual", "Trimestral", "Semestral", "Personalizado"]
DURACION_MESES = {"Mensual": 1, "Trimestral": 3, "Semestral": 6}


def _sumar_meses(fecha: date, meses: int) -> date:
    """
    Suma meses conservando el día del mes (ej: 26 ago + 1 mes = 26 sep).
    Si el mes destino es más corto que ese día (ej: 31 ene + 1 mes), lo
    ajusta al último día de ese mes en vez de reventar.
    """
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    ultimo_dia_mes = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha.day, ultimo_dia_mes))


def _calcular_vencimiento(tipo_plan: str, fecha_pago: date) -> date:
    if tipo_plan in DURACION_MESES:
        return _sumar_meses(fecha_pago, DURACION_MESES[tipo_plan])
    return fecha_pago + timedelta(days=30)


def _actualizar_vencimiento(plan_key: str, pago_key: str, venc_key: str) -> None:
    tipo_plan = st.session_state.get(plan_key)
    fecha_pago = st.session_state.get(pago_key)
    if tipo_plan and fecha_pago:
        st.session_state[venc_key] = _calcular_vencimiento(tipo_plan, fecha_pago)


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

    with st.container(key="lista_clientes"):
        for cliente in clientes_filtrados:
            badge = _badge_estado(cliente)
            dias = cliente.get("dias_restantes")
            dias_txt = f" · {dias} días restantes" if dias is not None else ""
            correo_txt = "" if cliente.get("correo_confirmado") else " · ⏳ Correo sin confirmar"
            # .strip(): un nombre con espacio al final (ej. "Dayana caceres ") rompe el
            # markdown de negrita — "**texto **" con espacio antes del cierre no se
            # interpreta como negrita y sale literal con los asteriscos.
            # escapar_markdown: el nombre lo escribe el propio cliente en el
            # registro (antes incluso de confirmar su correo) y aquí se renderiza
            # como markdown; sin escapar podría inyectar enlaces en esta lista.
            nombre = escapar_markdown((cliente["nombre_completo"] or cliente["email"]).strip())
            titulo = f"**{nombre}** — {badge}{dias_txt}{correo_txt}"
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
        nombre = escapar_markdown(cliente["nombre_completo"] or cliente["email"])
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
        date.fromisoformat(cliente["fecha_vencimiento"])
        if cliente["fecha_vencimiento"]
        else _calcular_vencimiento(plan_actual, fecha_pago_actual)
    )

    plan_key, pago_key, venc_key = f"plan_{cliente_id}", f"pago_{cliente_id}", f"venc_{cliente_id}"

    # Sin st.form: así el cambio de "Tipo de plan" o "Fecha del último pago"
    # puede recalcular la fecha de vencimiento en vivo (los widgets dentro de
    # un st.form no disparan on_change hasta que se envía el formulario).
    col1, col2 = st.columns(2)
    with col1:
        tipo_plan = st.selectbox(
            "Tipo de plan",
            PLANES,
            index=PLANES.index(plan_actual),
            key=plan_key,
            on_change=_actualizar_vencimiento,
            args=(plan_key, pago_key, venc_key),
        )
        estado = st.selectbox(
            "Estado",
            ["Activo", "Inactivo"],
            index=["Activo", "Inactivo"].index(estado_actual),
            key=f"estado_{cliente_id}",
            help="Si queda 'Inactivo', el cliente verá un aviso de plan caducado al iniciar sesión.",
        )
    with col2:
        fecha_pago = st.date_input(
            "Fecha del último pago",
            value=fecha_pago_actual,
            key=pago_key,
            on_change=_actualizar_vencimiento,
            args=(plan_key, pago_key, venc_key),
        )
        fecha_vencimiento = st.date_input(
            "Fecha de vencimiento",
            value=fecha_venc_actual,
            key=venc_key,
            help="Se recalcula sola según el plan y la fecha de pago; puedes ajustarla manualmente si lo necesitas.",
        )

    guardar = st.button(
        "💾 Guardar suscripción", key=f"guardar_susc_{cliente_id}", use_container_width=True, type="primary"
    )

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
        _confirmar_eliminar_cliente(cliente_id, escapar_markdown(cliente["nombre_completo"] or cliente["email"]))


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
