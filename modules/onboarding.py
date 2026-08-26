"""
Módulo de Onboarding (Anamnesis Inicial) y Ficha del Atleta — Paso 2.

  - render_formulario_cliente: formulario que el cliente llena/edita
    (datos personales, historial médico, experiencia, disponibilidad,
    hábitos y enlace a su perfil público de Hevy).
  - render_ficha_admin: vista de solo lectura para el entrenador, en
    tarjetas organizadas por sección, con alertas visuales destacadas si
    el cliente reportó patologías o lesiones.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from utils.pdf_export import generar_pdf_onboarding
from utils.queries import get_cliente, get_onboarding, update_cliente_hevy_url, upsert_onboarding

NIVELES_EXPERIENCIA = ["Principiante", "Intermedio", "Avanzado"]
OBJETIVOS = ["Fuerza", "Hipertrofia", "Pérdida de grasa", "Recomposición", "Salud general"]


def render_formulario_cliente(cliente_id: str) -> None:
    st.subheader("Mi Perfil / Formulario de Onboarding")

    if not cliente_id:
        st.warning("No se encontró tu identificador de cliente.")
        return

    datos = get_onboarding(cliente_id) or {}

    if datos:
        st.caption("Ya completaste este formulario. Puedes editarlo cuando quieras.")
    else:
        st.info(
            "Completa este formulario una sola vez para que tu entrenador conozca tu punto de "
            "partida. Podrás actualizarlo más adelante si algo cambia."
        )

    with st.form("onboarding_form"):
        st.markdown("##### Datos personales")
        col1, col2, col3 = st.columns(3)
        with col1:
            fecha_nacimiento_actual = date.fromisoformat(datos["fecha_nacimiento"]) if datos.get("fecha_nacimiento") else date(2000, 1, 1)
            fecha_nacimiento = st.date_input(
                "Fecha de nacimiento", value=fecha_nacimiento_actual, min_value=date(1940, 1, 1), max_value=date.today()
            )
            ocupacion = st.text_input("Ocupación", value=datos.get("ocupacion") or "")
        with col2:
            altura_cm = st.number_input("Altura (cm)", min_value=100.0, max_value=230.0, step=1.0, value=float(datos.get("altura_cm") or 170))
            peso_kg = st.number_input("Peso (kg)", min_value=30.0, max_value=250.0, step=0.5, value=float(datos.get("peso_kg") or 70))
        with col3:
            ciudad_pais = st.text_input("Ciudad / País", value=datos.get("ciudad_pais") or "")

        st.markdown("##### Historial médico")
        patologias = st.text_area("Patologías (si no tienes ninguna, deja el campo en blanco)", value=datos.get("patologias") or "")
        lesiones = st.text_area("Lesiones actuales o pasadas relevantes", value=datos.get("lesiones") or "")
        medicamentos = st.text_area("Medicamentos que tomas regularmente", value=datos.get("medicamentos") or "")

        st.markdown("##### Entrenamiento")
        col4, col5 = st.columns(2)
        with col4:
            nivel_actual = datos.get("nivel_experiencia") if datos.get("nivel_experiencia") in NIVELES_EXPERIENCIA else NIVELES_EXPERIENCIA[0]
            nivel_experiencia = st.selectbox("Nivel de experiencia", NIVELES_EXPERIENCIA, index=NIVELES_EXPERIENCIA.index(nivel_actual))
            disponibilidad_dias = st.slider("Días disponibles por semana", 0, 7, value=datos.get("disponibilidad_dias") or 3)
        with col5:
            objetivo_actual = datos.get("objetivo_principal") if datos.get("objetivo_principal") in OBJETIVOS else OBJETIVOS[0]
            objetivo_principal = st.selectbox("Objetivo principal", OBJETIVOS, index=OBJETIVOS.index(objetivo_actual))
            equipamiento = st.text_input(
                "Equipamiento disponible", value=datos.get("equipamiento") or "", placeholder="Ej: Gimnasio completo, mancuernas en casa"
            )

        st.markdown("##### Hábitos")
        col6, col7, col8 = st.columns(3)
        with col6:
            horas_sueno_promedio = st.number_input(
                "Horas de sueño promedio", min_value=0.0, max_value=14.0, step=0.5, value=float(datos.get("horas_sueno_promedio") or 7)
            )
        with col7:
            nivel_estres_habitual = st.slider("Nivel de estrés habitual (1-10)", 1, 10, value=datos.get("nivel_estres_habitual") or 5)
        with col8:
            comidas_dia = st.number_input("Comidas al día", min_value=1, max_value=10, step=1, value=datos.get("comidas_dia") or 4)

        alergias_alimentarias = st.text_input("Alergias o intolerancias alimentarias", value=datos.get("alergias_alimentarias") or "")

        st.markdown("##### Hevy (opcional)")
        hevy_perfil_url = st.text_input(
            "Enlace a tu perfil público de Hevy",
            value=datos.get("hevy_perfil_url") or "",
            placeholder="https://hevy.com/user/tu_usuario",
        )

        submitted = st.form_submit_button("💾 Guardar mi información", use_container_width=True, type="primary")

    if submitted:
        upsert_onboarding(
            cliente_id,
            fecha_nacimiento=fecha_nacimiento.isoformat(),
            altura_cm=altura_cm,
            peso_kg=peso_kg,
            ocupacion=ocupacion,
            ciudad_pais=ciudad_pais,
            patologias=patologias,
            lesiones=lesiones,
            medicamentos=medicamentos,
            nivel_experiencia=nivel_experiencia,
            disponibilidad_dias=disponibilidad_dias,
            equipamiento=equipamiento,
            horas_sueno_promedio=horas_sueno_promedio,
            nivel_estres_habitual=nivel_estres_habitual,
            comidas_dia=comidas_dia,
            alergias_alimentarias=alergias_alimentarias,
            objetivo_principal=objetivo_principal,
            hevy_perfil_url=hevy_perfil_url or None,
        )
        if hevy_perfil_url:
            update_cliente_hevy_url(cliente_id, hevy_perfil_url)
        st.success("¡Información guardada correctamente!")
        st.rerun()


def render_ficha_admin(cliente_id: str) -> None:
    st.subheader("Ficha del Atleta")

    if not cliente_id:
        st.info("Selecciona un cliente en el menú lateral para ver su ficha.")
        return

    cliente = get_cliente(cliente_id)
    if not cliente:
        st.error("No se encontró el cliente seleccionado.")
        return

    st.markdown(f"### {cliente.get('nombre_completo') or cliente.get('email')}")
    st.caption(cliente.get("email"))

    datos = get_onboarding(cliente_id)
    if not datos:
        st.warning("Este cliente todavía no completó su formulario de onboarding.")
        return

    if (datos.get("patologias") or "").strip() or (datos.get("lesiones") or "").strip():
        st.error(
            "⚠️ **Atención**: este cliente reportó patologías y/o lesiones. "
            "Revisa el detalle abajo antes de asignar cargas o ejercicios de riesgo."
        )

    edad = _calcular_edad(datos.get("fecha_nacimiento"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Edad", f"{edad} años" if edad is not None else "—")
    col2.metric("Peso", f"{datos['peso_kg']:.0f} kg" if datos.get("peso_kg") is not None else "—")
    col3.metric("Altura", f"{datos['altura_cm']:.0f} cm" if datos.get("altura_cm") is not None else "—")

    col4, col5, col6 = st.columns(3)
    col4.metric("Nivel", datos.get("nivel_experiencia") or "—")
    col5.metric("Objetivo", datos.get("objetivo_principal") or "—")
    dias_disp = datos.get("disponibilidad_dias")
    col6.metric("Disponibilidad de entrenamiento", f"{dias_disp} días/semana" if dias_disp is not None else "—")

    with st.container(border=True):
        st.markdown("##### Historial médico")
        _campo_alerta("Patologías", datos.get("patologias"))
        _campo_alerta("Lesiones", datos.get("lesiones"))
        st.write(f"• **Medicamentos:** {datos.get('medicamentos') or '—'}")

    with st.container(border=True):
        st.markdown("##### Datos personales")
        col7, col8 = st.columns(2)
        col7.write(f"• **Fecha de nacimiento:** {datos.get('fecha_nacimiento') or '—'}")
        col7.write(f"• **Ocupación:** {datos.get('ocupacion') or '—'}")
        col8.write(f"• **Ciudad/País:** {datos.get('ciudad_pais') or '—'}")

    with st.container(border=True):
        st.markdown("##### Hábitos")
        col9, col10, col11 = st.columns(3)
        col9.write(f"• **Sueño promedio:** {datos.get('horas_sueno_promedio') or '—'} h")
        col10.write(f"• **Estrés habitual:** {datos.get('nivel_estres_habitual') or '—'}/10")
        col11.write(f"• **Comidas/día:** {datos.get('comidas_dia') or '—'}")
        st.write(f"• **Alergias alimentarias:** {datos.get('alergias_alimentarias') or '—'}")
        st.write(f"• **Equipamiento disponible:** {datos.get('equipamiento') or '—'}")

    if datos.get("hevy_perfil_url"):
        st.markdown(f"• **Perfil Hevy:** [{datos['hevy_perfil_url']}]({datos['hevy_perfil_url']})")

    st.divider()
    st.download_button(
        "📄 Descargar resumen en PDF",
        data=generar_pdf_onboarding(cliente, datos),
        file_name=f"onboarding_{(cliente.get('nombre_completo') or cliente.get('email') or 'cliente').replace(' ', '_')}.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary",
    )


def _calcular_edad(fecha_nacimiento: str | None) -> int | None:
    if not fecha_nacimiento:
        return None
    nacimiento = date.fromisoformat(fecha_nacimiento)
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _campo_alerta(etiqueta: str, valor: str | None) -> None:
    if valor and valor.strip():
        st.markdown(f":red[• **{etiqueta}:** {valor}]")
    else:
        st.write(f"• **{etiqueta}:** Ninguna reportada")
