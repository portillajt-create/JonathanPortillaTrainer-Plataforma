"""
Módulo de Análisis y Gráficas de Progreso — Paso 5 (rediseñado).

La integración automática con el perfil público de Hevy se DESCARTÓ a
propósito — no es una limitación temporal, es la decisión adoptada. Al
investigar el perfil público real (hevy.com/user/USERNAME) se confirmó
que:

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

La solución adoptada es que el admin IMPORTE el historial real del
cliente desde el archivo CSV que Hevy sí permite exportar manualmente
(Perfil -> Configuración -> Exportar datos, dentro de su propia app) —
ver utils/hevy_import.py para el parseo. Es un paso manual (el cliente le
pasa el archivo al admin y este lo sube), no una sincronización
automática, pero usa datos 100% reales del cliente sin sortear ningún
control de acceso.

El enlace de perfil de Hevy que el cliente ya guarda en su onboarding
(ver modules/onboarding.py) queda intacto como referencia, aunque hoy no
se use para nada automático.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import theme
from utils.analisis_progreso import calcular_e1rm, detectar_ejercicios_a_revisar
from utils.formato import hoy_bogota
from utils.hevy_import import parsear_csv_hevy
from utils.queries import guardar_historial_entrenamientos, list_checkins, list_historial_entrenamientos

#: Periodo -> días hacia atrás desde hoy (None = sin filtro, todo el historial).
_PERIODOS_DIAS: dict[str, int | None] = {
    "1 mes": 30, "3 meses": 90, "6 meses": 180, "1 año": 365, "Todo": None,
}


def render_admin(cliente_id: str) -> None:
    st.subheader("Progreso y Métricas")
    _render_importar_hevy(cliente_id)
    _render_checkins(cliente_id)
    _render_historial_ejercicio(cliente_id)


def render_cliente(cliente_id: str) -> None:
    st.subheader("Progreso y Métricas")
    _render_checkins(cliente_id)
    _render_historial_ejercicio(cliente_id)


def _render_importar_hevy(cliente_id: str) -> None:
    total_importado = st.session_state.pop(f"hevy_importado_{cliente_id}", None)
    if total_importado is not None:
        st.success(f"✅ Se guardaron {total_importado} registros en el historial de entrenamiento del cliente.")

    with st.expander("📥 Importar historial de entrenamiento desde Hevy (CSV)"):
        st.caption(
            "El cliente puede exportar su historial completo desde la app de Hevy "
            "(Perfil → Configuración → Exportar datos) y descargar un archivo CSV. "
            "Súbelo acá para cargar su historial real de entrenamientos — no reemplaza "
            "nada, solo agrega/actualiza lo que traiga el archivo."
        )
        archivo = st.file_uploader("Archivo CSV de Hevy", type=["csv"], key=f"hevy_csv_{cliente_id}")
        if archivo is None:
            return

        try:
            contenido = archivo.getvalue().decode("utf-8")
            resultado = parsear_csv_hevy(contenido)
        except ValueError as e:
            st.error(f"❌ {e}")
            return
        except UnicodeDecodeError:
            st.error("❌ No se pudo leer el archivo — confirma que sea el CSV exportado directamente de Hevy.")
            return

        if not resultado.filas:
            st.warning("El archivo no tiene series de trabajo para importar (¿está vacío?).")
            return

        desde, hasta = resultado.rango_fechas
        st.success(
            f"Se detectaron **{len(resultado.filas)} registros** (día + ejercicio) de "
            f"**{len(resultado.ejercicios_detectados)} ejercicios distintos**, entre "
            f"{desde.strftime('%d/%m/%Y')} y {hasta.strftime('%d/%m/%Y')}."
        )
        if resultado.filas_omitidas:
            st.caption(f"⚠️ {resultado.filas_omitidas} series del archivo no se pudieron leer y se omitieron.")

        st.dataframe(resultado.filas[:10], use_container_width=True)
        st.caption("Vista previa: primeros 10 de los registros que se guardarían.")

        if st.button("✅ Importar este historial", key=f"confirmar_hevy_{cliente_id}", type="primary"):
            total = guardar_historial_entrenamientos(cliente_id, resultado.filas)
            st.session_state[f"hevy_importado_{cliente_id}"] = total
            st.rerun()


def _render_checkins(cliente_id: str) -> None:
    checkins = list_checkins(cliente_id)
    if not checkins:
        st.info(
            "Todavía no hay check-ins semanales registrados para este cliente. "
            "Las gráficas de progreso aparecerán aquí en cuanto haya al menos un check-in."
        )
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


def _render_ejercicios_a_revisar(historial: list[dict]) -> None:
    """Tabla de ejercicios que el admin debería revisar: se están
    entrenando actualmente pero no muestran progreso real de fuerza en
    sus últimas sesiones — ver utils/analisis_progreso.py para las
    reglas exactas."""
    revisar = detectar_ejercicios_a_revisar(historial, hoy_bogota())
    if not revisar:
        return

    st.markdown("##### Ejercicios a tener en cuenta")
    st.caption(
        f"{len(revisar)} ejercicio{'s' if len(revisar) != 1 else ''} que el cliente sigue entrenando "
        "pero sin progreso real de fuerza en sus últimas sesiones, del más al menos marcado."
    )
    st.dataframe(
        revisar, use_container_width=True, hide_index=True,
        column_config={
            "Ejercicio": st.column_config.TextColumn(width="medium"),
            "Motivo": st.column_config.TextColumn(width="large"),
            "Última sesión": st.column_config.TextColumn(width="small"),
        },
    )


def _render_historial_ejercicio(cliente_id: str) -> None:
    """Progreso por ejercicio a partir del historial real importado — ver
    _render_importar_hevy. Si el cliente todavía no tiene historial
    importado, esta sección no muestra nada (no hay ejercicios entre los
    cuales elegir)."""
    historial = list_historial_entrenamientos(cliente_id)
    if not historial:
        st.caption("⏳ Todavía no se ha cargado el historial de entrenamiento de Hevy de este cliente.")
        return

    _render_ejercicios_a_revisar(historial)

    df = pd.DataFrame(historial)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["e1rm"] = [calcular_e1rm(p, r) for p, r in zip(df["peso_kg"], df["repeticiones"])]

    st.markdown("##### Progreso por ejercicio")
    ejercicios = sorted(df["ejercicio_nombre"].unique())
    ejercicio_elegido = st.selectbox("Ejercicio", ejercicios, key=f"hevy_ejercicio_{cliente_id}")

    periodo_elegido = st.segmented_control(
        "Periodo", list(_PERIODOS_DIAS.keys()), default="6 meses",
        required=True, key=f"hevy_periodo_{cliente_id}",
    )
    dias = _PERIODOS_DIAS[periodo_elegido]

    df_ejercicio = df[df["ejercicio_nombre"] == ejercicio_elegido].sort_values("fecha")
    if dias is not None:
        desde = pd.Timestamp(hoy_bogota()) - pd.Timedelta(days=dias)
        df_ejercicio = df_ejercicio[df_ejercicio["fecha"] >= desde]

    if df_ejercicio.empty:
        st.caption("Este ejercicio no tiene sesiones registradas en el periodo elegido.")
        return

    if df_ejercicio["e1rm"].notna().any():
        fig = px.line(
            df_ejercicio, x="fecha", y="e1rm", markers=True,
            labels={"fecha": "Fecha", "e1rm": "1RM estimado (kg)"},
            custom_data=["peso_kg", "repeticiones"],
        )
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=320)
        fig.update_traces(
            line_color="#FFFFFF", marker=dict(color="#FFFFFF", size=6),
            hovertemplate="%{x|%d/%m/%Y}<br>1RM estimado: %{y:.0f} kg<br>Serie top: %{customdata[0]:g} kg x %{customdata[1]:g}<extra></extra>",
        )
        st.plotly_chart(theme.estilizar_grafico(fig), use_container_width=True)
        st.caption(
            "El **1RM estimado** (fórmula de Epley) combina el peso y las repeticiones de la serie "
            "más pesada de cada día en un solo número comparable entre sesiones, aunque no hayan usado "
            "el mismo peso ni las mismas repeticiones — pasa el mouse sobre un punto para ver los datos reales."
        )
    else:
        st.caption("Este ejercicio no tiene peso/repeticiones registrados en el periodo elegido (a peso corporal o medido por duración).")


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

