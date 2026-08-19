"""
Módulo de Análisis y Gráficas de Progreso — Paso 5 (rediseñado).

La integración automática con el perfil público de Hevy queda PENDIENTE a
propósito. Al investigar el perfil público real (hevy.com/user/USERNAME)
se confirmó que:

  1. No es HTML estático: los datos se renderizan vía JavaScript, así que
     requests + BeautifulSoup (el enfoque original) no funciona.
  2. El JavaScript de la página obtiene los datos de una API
     (api.hevyapp.com/user_workouts_paged) que responde 401 Unauthorized
     sin credenciales — incluso para perfiles "públicos". Extraer o
     incrustar en el código la clave que la desbloquea equivaldría a
     rodear un control de acceso explícito de Hevy, así que no se
     construyó eso aquí.
  3. Incluso con un navegador headless (que sí respetaría ese control de
     acceso, renderizando la página tal como la ve cualquier visitante),
     lo único visible sin sesión iniciada es el ÚLTIMO entrenamiento
     (fecha, duración, volumen y ejercicios con series) — sin peso ni
     repeticiones por serie, insuficiente para graficar sobrecarga
     progresiva histórica.

El enlace de perfil de Hevy que el cliente ya guarda en su onboarding
(ver modules/onboarding.py) queda intacto para cuando se habilite una vía
oficial (p. ej. la API de Hevy con la cuenta Pro del propio entrenador).

Mientras tanto, este módulo muestra el progreso real y verificable que sí
tenemos: peso corporal y tendencias de adherencia/bienestar a partir de
los check-ins semanales (Paso 6).
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import theme
from utils.queries import list_checkins


def render_progreso(cliente_id: str) -> None:
    st.subheader("Progreso y Métricas")

    checkins = list_checkins(cliente_id)
    if not checkins:
        st.info(
            "Todavía no hay check-ins semanales registrados para este cliente. "
            "Las gráficas de progreso aparecerán aquí en cuanto haya al menos un check-in."
        )
        _nota_hevy()
        return

    df = pd.DataFrame(checkins)
    df["semana_fecha"] = pd.to_datetime(df["semana_fecha"])
    df = df.sort_values("semana_fecha")
    ultimo = df.iloc[-1]

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Peso corporal actual",
        f"{ultimo['peso_corporal_kg']:.1f} kg" if pd.notna(ultimo["peso_corporal_kg"]) else "—",
    )
    col2.metric(
        "Adherencia dieta (última)",
        f"{int(ultimo['adherencia_dieta'])}/10" if pd.notna(ultimo["adherencia_dieta"]) else "—",
    )
    col3.metric(
        "Adherencia entreno (última)",
        f"{int(ultimo['adherencia_entrenamiento'])}/10" if pd.notna(ultimo["adherencia_entrenamiento"]) else "—",
    )

    if df["peso_corporal_kg"].notna().any():
        st.markdown("##### Peso corporal")
        fig_peso = px.line(
            df, x="semana_fecha", y="peso_corporal_kg", markers=True,
            labels={"semana_fecha": "Semana", "peso_corporal_kg": "Peso (kg)"},
        )
        fig_peso.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
        fig_peso.update_traces(line_color="#FFFFFF", marker=dict(color="#FFFFFF", size=7))
        st.plotly_chart(theme.estilizar_grafico(fig_peso), use_container_width=True)

    st.markdown("##### Adherencia")
    _grafico_lineas(
        df,
        columnas={"adherencia_dieta": "Adherencia a la dieta", "adherencia_entrenamiento": "Adherencia al entrenamiento"},
    )

    st.markdown("##### Bienestar (sueño, estrés, fatiga)")
    _grafico_lineas(
        df,
        columnas={"calidad_sueno": "Calidad de sueño", "nivel_estres": "Nivel de estrés", "fatiga": "Fatiga"},
    )

    _nota_hevy()


def _grafico_lineas(df: pd.DataFrame, columnas: dict[str, str]) -> None:
    df_largo = df.melt(
        id_vars="semana_fecha", value_vars=list(columnas.keys()), var_name="métrica", value_name="valor"
    ).dropna(subset=["valor"])
    if df_largo.empty:
        return

    df_largo["métrica"] = df_largo["métrica"].map(columnas)
    fig = px.line(
        df_largo, x="semana_fecha", y="valor", color="métrica", markers=True,
        labels={"semana_fecha": "Semana", "valor": "Puntaje (1-10)"},
    )
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300, yaxis_range=[0, 10])
    st.plotly_chart(theme.estilizar_grafico(fig), use_container_width=True)


def _nota_hevy() -> None:
    st.caption(
        "ℹ️ La sincronización automática con Hevy está pendiente: su página pública no expone el "
        "historial completo sin autenticación. El enlace de perfil que el cliente ya guardó en su "
        "onboarding queda listo para cuando se habilite una vía oficial."
    )
