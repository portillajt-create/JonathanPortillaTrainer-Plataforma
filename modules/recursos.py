"""
Módulo "Guías y Recursos" — biblioteca de consulta para el cliente y el
admin, sin datos por cliente (no recibe cliente_id, a diferencia del resto
de módulos). Se muestra igual para los dos roles porque es contenido fijo,
no algo que varíe según quién esté logueado.

Tres secciones, en desplegables (st.expander), en el orden pedido:
  1. Política de datos y términos y condiciones — el mismo texto que ya se
     muestra al registrarse (ver utils/legal.py), para poder consultarlo
     otra vez sin cerrar sesión.
  2. Videos guía — cómo exportar el historial de Hevy y cómo usar la
     plataforma. Alojados en YouTube como "no listado" (decisión del
     usuario, 2026-09-05): los archivos originales pesan 32-36 MB cada
     uno, y ni el repo de git ni el plan gratuito de Supabase Storage son
     un buen lugar para eso (el repo los cargaría para siempre en su
     historial; Supabase Storage tiene un tope de banda mensual ajustado
     que unos pocos clientes viendo el video ya agotarían). Si la URL de
     un video todavía no está cargada, se avisa en vez de romper.
  3. Glosario de conceptos — términos que la propia plataforma ya usa
     (RPE, 1RM estimado, deload, adherencia, TDEE...) explicados en un
     solo lugar. Es un borrador inicial igual que los generadores de dieta
     y rutina: sirve para arrancar, pero el admin debe revisarlo y
     ajustarlo a como él mismo explica estos conceptos a sus clientes.
"""

from __future__ import annotations

import streamlit as st

from utils.legal import AVISO_TRATAMIENTO_DATOS, TERMINOS_CONDICIONES

#: (título, descripción corta, url de YouTube o None si aún no se cargó).
#: url=None -> se avisa en vez de intentar reproducir un video inexistente.
VIDEOS_GUIA: list[dict[str, str | None]] = [
    {
        "titulo": "Cómo exportar tu historial de Hevy",
        "descripcion": "Paso a paso para descargar el CSV de tus entrenamientos desde la app de Hevy y enviárselo a tu entrenador.",
        "url": None,  # pendiente: "GUIA 1.mp4" del usuario, subir a YouTube como "no listado" y pegar el link acá.
    },
    {
        "titulo": "Cómo usar la plataforma",
        "descripcion": "Recorrido por las secciones de la plataforma: tu perfil, tu dieta, tu rutina, tu progreso y el check-in semanal.",
        "url": None,  # pendiente: "GUIA 2.mp4" del usuario, subir a YouTube como "no listado" y pegar el link acá.
    },
]

#: (término, definición). Borrador inicial — revisar antes de darlo por
#: definitivo (ver nota del módulo). Se explican en los mismos términos que
#: ya usa la plataforma (mismo texto/fórmulas que utils/analisis_progreso.py
#: y modules/rutinas.py) para que lo que el cliente lee acá calce con lo que
#: ve en Entrenamiento y Progreso.
GLOSARIO: list[tuple[str, str]] = [
    (
        "RPE (Percepción del Esfuerzo)",
        "Qué tan difícil sentiste una serie, en una escala de 1 a 10. RPE 8 significa que, al terminar la "
        "serie, sentías que te quedaban 2 repeticiones más en el tanque. En tu rutina se pide como un rango "
        "(ej. \"RPE 8-9\") y no un número exacto, porque en la práctica nadie distingue con precisión un "
        "RPE 8 de un 8.2 — un rango es más fácil de estimar en el momento y sigue siendo útil.",
    ),
    (
        "RIR (Repeticiones en Reserva)",
        "La otra cara del RPE: cuántas repeticiones más podrías haber hecho antes de fallar. RIR 2 y "
        "RPE 8 son, en la práctica, la misma idea vista desde dos lados.",
    ),
    (
        "1RM estimado",
        "Cuánto podrías levantar a una sola repetición, calculado a partir de un peso y unas repeticiones "
        "reales (fórmula de Epley: peso × (1 + repeticiones/30)). Sirve para comparar el esfuerzo entre "
        "sesiones que no usaron el mismo peso ni las mismas repeticiones — \"60 kg × 8\" y \"65 kg × 6\" no "
        "se comparan mirando solo el peso, pero sus 1RM estimados (76.8 kg y 78 kg) sí dicen cuál fue mayor. "
        "Es la misma métrica que ves en la gráfica de progreso por ejercicio.",
    ),
    (
        "Serie de trabajo vs. serie de calentamiento",
        "Las series de calentamiento (peso liviano, antes de la serie pesada) no cuentan como esfuerzo real "
        "y no se tienen en cuenta al calcular tu progreso — por eso, al importar tu historial de Hevy, se "
        "descartan.",
    ),
    (
        "Volumen de entrenamiento",
        "La cantidad total de trabajo hecho: peso × repeticiones, sumado en todas las series de un "
        "ejercicio (o de un músculo, un día, una semana). Subir el volumen con el tiempo es una de las "
        "formas de progresar, junto con subir el peso o las repeticiones.",
    ),
    (
        "Sobrecarga progresiva",
        "La idea central de todo programa de fuerza: para seguir mejorando, el cuerpo necesita una exigencia "
        "que aumenta poco a poco (más peso, más repeticiones o más series) en vez de repetir siempre la "
        "misma carga.",
    ),
    (
        "Deload (semana de descarga)",
        "Una semana con menos intensidad o volumen a propósito, para recuperar mejor cuando el cansancio, "
        "el estrés o el sueño vienen mal en el check-in. No es un retroceso — es parte del plan.",
    ),
    (
        "Adherencia",
        "Qué tanto seguiste el plan (dieta o entrenamiento) esa semana, del 1 al 10. Es lo que reportas "
        "cada check-in, y es más útil que solo mirar resultados: si el resultado no llegó pero la "
        "adherencia fue baja, el problema no es el plan.",
    ),
    (
        "TDEE (gasto energético total diario)",
        "Cuántas calorías quema tu cuerpo en un día normal, contando desde tu metabolismo en reposo hasta "
        "tu actividad física. Es el punto de partida para calcular cuánto comer según tu objetivo (bajar, "
        "mantener o subir de peso).",
    ),
    (
        "Macronutrientes (macros)",
        "Proteína, carbohidratos y grasas — los tres componentes que aportan calorías en la comida. Tu "
        "plan nutricional reparte tu objetivo de calorías entre los tres según tu objetivo y tus "
        "preferencias.",
    ),
]


def _render_videos_guia() -> None:
    for video in VIDEOS_GUIA:
        st.markdown(f"**{video['titulo']}**")
        st.caption(video["descripcion"])
        if video["url"]:
            st.video(video["url"])
        else:
            st.info("🎬 Video en camino — todavía no se ha cargado.")
        st.divider()


def _render_glosario() -> None:
    st.caption(
        "Términos que vas a encontrar en Entrenamiento y en Progreso, explicados en el mismo sentido en "
        "que se usan en la plataforma."
    )
    for termino, definicion in GLOSARIO:
        st.markdown(f"**{termino}**")
        st.caption(definicion)


def render() -> None:
    """Misma vista para admin y cliente — no depende de cliente_id."""
    st.subheader("Guías y Recursos")
    st.caption("Aquí encuentras las políticas de la plataforma, videos guía y el glosario de conceptos.")

    with st.expander("🔒 Política de datos y términos y condiciones"):
        st.markdown("###### Aviso de tratamiento de datos personales")
        st.caption(AVISO_TRATAMIENTO_DATOS)
        st.markdown("###### Términos y condiciones")
        st.caption(TERMINOS_CONDICIONES)

    with st.expander("🎬 Videos guía"):
        _render_videos_guia()

    with st.expander("📖 Glosario de conceptos"):
        _render_glosario()
