"""
Módulo de Nutrición e Interactivo de Macros — Paso 3.

  - render_alertas_nutricion: alerta de baja adherencia sostenida a la
    dieta (reusa checkin.render_alertas_adherencia_dieta). Se muestra
    siempre, sin depender de qué cliente esté seleccionado — mismo patrón
    que los vencimientos en Gestión de Clientes y el deload en Entrenamiento.
  - render_admin: Calculadora TDEE (Mifflin-St Jeor) + calculadora
    interactiva de macros (g/kg de proteína, % de grasa) + planificador
    de dieta, con botón "Guardar y Notificar al Cliente" que desactiva el
    plan anterior, guarda el nuevo como activo y dispara una notificación
    in-app (+ correo si hay SMTP configurado).
  - render_cliente: vista de solo lectura del plan nutricional vigente,
    con el desglose de macros en un gráfico de dona.
"""

from __future__ import annotations

import time
from datetime import date

import plotly.graph_objects as go
import streamlit as st

from modules import checkin
from utils import theme
from utils.auth import current_cliente_id
from utils.notificaciones import crear_notificacion
from utils.plan_alimentario import generar_ejemplo_dieta
from utils.queries import get_dieta_activa, get_onboarding, guardar_dieta

TIPOS_DIETA = ["Flexible", "Ciclado de carbohidratos", "Definición", "Volumen", "Mantenimiento"]

FACTORES_ACTIVIDAD = {
    "Sedentario (poco o nulo ejercicio)": 1.2,
    "Ligero (1-3 días/semana)": 1.375,
    "Moderado (3-5 días/semana)": 1.55,
    "Activo (6-7 días/semana)": 1.725,
    "Muy activo (entrenos intensos o 2x/día)": 1.9,
}

NOTA_ADICIONAL_DEFAULT = (
    "Mantente bien hidratado durante el día. El plan de comidas ofrece 1-2 opciones por categoría — "
    "elige la que más se ajuste a tu rutina y a lo que tengas disponible. Prioriza alimentos poco "
    "procesados y respeta los horarios de comida en la medida de lo posible."
)


def render_alertas_nutricion() -> None:
    checkin.render_alertas_adherencia_dieta()


def render_admin(cliente_id: str) -> None:
    st.subheader("Nutrición y Calculadora de Macros")

    dieta_actual = get_dieta_activa(cliente_id)
    if dieta_actual:
        st.caption(
            f"Plan vigente: {dieta_actual.get('calorias_objetivo', 0):.0f} kcal/día · "
            f"{dieta_actual.get('tipo_dieta') or '—'} · "
            f"actualizado el {dieta_actual.get('fecha_actualizacion', '—')[:10]}"
        )
    else:
        st.info("Este cliente todavía no tiene un plan nutricional asignado.")

    onboarding_cliente = get_onboarding(cliente_id) or {}

    st.markdown("##### 1. Calculadora TDEE")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        peso_kg = st.number_input(
            "Peso (kg)", min_value=30.0, max_value=250.0, step=0.5, value=float(onboarding_cliente.get("peso_kg") or 70.0)
        )
    with col2:
        altura_cm = st.number_input(
            "Altura (cm)", min_value=120.0, max_value=230.0, step=1.0, value=float(onboarding_cliente.get("altura_cm") or 170.0)
        )
    with col3:
        edad_actual = _calcular_edad(onboarding_cliente.get("fecha_nacimiento")) or 30
        edad = st.number_input("Edad", min_value=14, max_value=90, step=1, value=edad_actual)
    with col4:
        if dieta_actual and dieta_actual.get("sexo") in ("Hombre", "Mujer"):
            sexo_actual = dieta_actual["sexo"]
        elif onboarding_cliente.get("sexo") in ("Hombre", "Mujer"):
            sexo_actual = onboarding_cliente["sexo"]
        else:
            sexo_actual = "Hombre"
        sexo = st.selectbox("Sexo", ["Hombre", "Mujer"], index=["Hombre", "Mujer"].index(sexo_actual))

    niveles = list(FACTORES_ACTIVIDAD.keys())
    nivel_actual = dieta_actual.get("nivel_actividad") if dieta_actual and dieta_actual.get("nivel_actividad") in niveles else niveles[2]
    nivel_actividad = st.selectbox("Nivel de actividad", niveles, index=niveles.index(nivel_actual))

    tmb = _calcular_tmb(peso_kg, altura_cm, edad, sexo)
    tdee = tmb * FACTORES_ACTIVIDAD[nivel_actividad]

    col_tmb, col_tdee = st.columns(2)
    col_tmb.metric("TMB (metabolismo basal)", f"{tmb:.0f} kcal/día")
    col_tdee.metric("TDEE (gasto total estimado)", f"{tdee:.0f} kcal/día")

    st.markdown("##### 2. Objetivo calórico")
    ajuste_actual = int(dieta_actual["ajuste_pct"]) if dieta_actual and dieta_actual.get("ajuste_pct") is not None else 0
    ajuste_pct = st.slider(
        "Ajuste sobre el TDEE (%)", min_value=-30, max_value=30, value=ajuste_actual, step=5,
        help="Negativo = déficit (perder grasa) · 0 = mantenimiento · Positivo = superávit (ganar masa)",
    )
    calorias_objetivo = tdee * (1 + ajuste_pct / 100)
    st.metric("Calorías objetivo", f"{calorias_objetivo:.0f} kcal/día")

    st.markdown("##### 3. Calculadora interactiva de macros")
    proteina_actual = float(dieta_actual["proteina_g_kg"]) if dieta_actual and dieta_actual.get("proteina_g_kg") is not None else 2.0
    grasa_actual = int(dieta_actual["grasa_pct"]) if dieta_actual and dieta_actual.get("grasa_pct") is not None else 25
    col5, col6 = st.columns(2)
    with col5:
        proteina_g_kg = st.slider("Proteína (g por kg de peso corporal)", 1.2, 3.0, proteina_actual, 0.1)
    with col6:
        grasa_pct = st.slider("Grasas (% de las calorías objetivo)", 15, 40, grasa_actual, 5)

    proteinas_g = peso_kg * proteina_g_kg
    proteina_kcal = proteinas_g * 4
    grasas_kcal = calorias_objetivo * (grasa_pct / 100)
    grasas_g = grasas_kcal / 9
    carb_kcal = max(calorias_objetivo - proteina_kcal - grasas_kcal, 0)
    carbohidratos_g = carb_kcal / 4

    col7, col8, col9 = st.columns(3)
    col7.metric("Proteína", f"{proteinas_g:.0f} g")
    col8.metric("Carbohidratos", f"{carbohidratos_g:.0f} g")
    col9.metric("Grasas", f"{grasas_g:.0f} g")

    st.plotly_chart(_grafico_macros(proteina_kcal, carb_kcal, grasas_kcal), use_container_width=True)

    st.markdown("##### 4. Planificador de dieta")
    tipo_actual = dieta_actual.get("tipo_dieta") if dieta_actual and dieta_actual.get("tipo_dieta") in TIPOS_DIETA else TIPOS_DIETA[0]
    tipo_dieta = st.selectbox("Tipo de dieta", TIPOS_DIETA, index=TIPOS_DIETA.index(tipo_actual))

    alergias = onboarding_cliente.get("alergias_alimentarias")
    if alergias:
        st.warning(f"⚠️ Este cliente reportó alergias/intolerancias: **{alergias}**. Revisa el ejemplo antes de guardarlo.")

    plan_key = f"dieta_plan_comidas_{cliente_id}"
    if plan_key not in st.session_state:
        st.session_state[plan_key] = (dieta_actual.get("plan_comidas") if dieta_actual else None) or ""

    if st.button("🍽️ Generar ejemplo de dieta con estos macros"):
        st.session_state[plan_key] = generar_ejemplo_dieta(proteinas_g, carbohidratos_g, grasas_g)
        st.rerun()

    plan_comidas = st.text_area(
        "Plan de comidas (editable — genera un ejemplo arriba o escribe el tuyo). "
        "Admite formato: **negrita** para títulos y '- ' para viñetas.",
        key=plan_key,
        height=260,
    )
    if st.session_state[plan_key]:
        with st.expander("👁️ Vista previa (así lo verá el cliente)"):
            st.markdown(st.session_state[plan_key])

    notas_key = f"dieta_notas_adicionales_{cliente_id}"
    if notas_key not in st.session_state:
        st.session_state[notas_key] = (dieta_actual.get("notas") if dieta_actual else None) or NOTA_ADICIONAL_DEFAULT
    notas = st.text_area(
        "Notas adicionales para el cliente (indicaciones generales, timing de comidas, suplementación, etc.)",
        key=notas_key,
        height=120,
    )

    if st.button("💾 Guardar y notificar al cliente", use_container_width=True, type="primary"):
        guardar_dieta(
            cliente_id,
            actualizado_por=current_cliente_id(),
            tdee=round(tdee, 1),
            calorias_objetivo=round(calorias_objetivo, 1),
            proteinas_g=round(proteinas_g, 1),
            carbohidratos_g=round(carbohidratos_g, 1),
            grasas_g=round(grasas_g, 1),
            tipo_dieta=tipo_dieta,
            plan_comidas=plan_comidas,
            notas=notas,
            sexo=sexo,
            nivel_actividad=nivel_actividad,
            ajuste_pct=ajuste_pct,
            proteina_g_kg=round(proteina_g_kg, 2),
            grasa_pct=grasa_pct,
        )
        crear_notificacion(
            cliente_id,
            tipo="dieta_actualizada",
            titulo="Tu plan nutricional fue actualizado",
            mensaje=(
                f"Tu entrenador actualizó tu plan nutricional: {calorias_objetivo:.0f} kcal/día "
                f"({proteinas_g:.0f}g proteína, {carbohidratos_g:.0f}g carbohidratos, {grasas_g:.0f}g grasas). "
                "Revísalo en la sección 'Mi Dieta'."
            ),
            creado_por=current_cliente_id(),
        )
        del st.session_state[plan_key]
        del st.session_state[notas_key]
        st.session_state[f"dieta_guardada_{cliente_id}"] = True
        st.rerun()

    if st.session_state.pop(f"dieta_guardada_{cliente_id}", False):
        st.success("✅ Plan nutricional actualizado y asesorado notificado.")
        time.sleep(5)
        st.rerun()


def render_cliente(cliente_id: str) -> None:
    st.subheader("Mi Plan Nutricional")

    dieta = get_dieta_activa(cliente_id)
    if not dieta:
        st.info("Tu entrenador todavía no te ha asignado un plan nutricional.")
        return

    st.caption(f"Última actualización: {(dieta.get('fecha_actualizacion') or '—')[:10]}")

    col1, col2 = st.columns(2)
    col1.metric("Calorías objetivo", f"{dieta.get('calorias_objetivo', 0):.0f} kcal/día")
    col2.metric("Tipo de dieta", dieta.get("tipo_dieta") or "—")

    proteinas_g = dieta.get("proteinas_g") or 0
    carbohidratos_g = dieta.get("carbohidratos_g") or 0
    grasas_g = dieta.get("grasas_g") or 0

    col3, col4, col5 = st.columns(3)
    col3.metric("Proteína", f"{proteinas_g:.0f} g")
    col4.metric("Carbohidratos", f"{carbohidratos_g:.0f} g")
    col5.metric("Grasas", f"{grasas_g:.0f} g")

    st.plotly_chart(
        _grafico_macros(proteinas_g * 4, carbohidratos_g * 4, grasas_g * 9),
        use_container_width=True,
    )

    if dieta.get("plan_comidas"):
        st.markdown("##### 🍽️ Plan de comidas")
        with st.container(border=True):
            st.markdown(dieta["plan_comidas"])

    if dieta.get("notas"):
        st.markdown("##### 📝 Notas adicionales de tu entrenador")
        st.write(dieta["notas"])


def _calcular_tmb(peso_kg: float, altura_cm: float, edad: int, sexo: str) -> float:
    """Tasa Metabólica Basal por la fórmula de Mifflin-St Jeor."""
    base = 10 * peso_kg + 6.25 * altura_cm - 5 * edad
    return base + 5 if sexo == "Hombre" else base - 161


def _calcular_edad(fecha_nacimiento: str | None) -> int | None:
    if not fecha_nacimiento:
        return None
    nacimiento = date.fromisoformat(fecha_nacimiento)
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _grafico_macros(proteina_kcal: float, carb_kcal: float, grasas_kcal: float) -> go.Figure:
    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Proteína", "Carbohidratos", "Grasas"],
                values=[max(proteina_kcal, 0), max(carb_kcal, 0), max(grasas_kcal, 0)],
                hole=0.55,
                marker=dict(colors=["#4C9AFF", "#36B37E", "#FFAB00"], line=dict(color="#000000", width=2)),
                textinfo="label+percent",
                textfont=dict(color="#FFFFFF", size=14),
                hovertemplate="%{label}: %{value:.0f} kcal (%{percent})<extra></extra>",
            )
        ]
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10), height=280)
    return theme.estilizar_grafico(fig)
