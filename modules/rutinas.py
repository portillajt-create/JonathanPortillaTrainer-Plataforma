"""
Módulo de Entrenamiento (Rutinas) — Paso 4.

  - render_alertas_entrenamiento: alertas de la página "Entrenamiento"
    (deload, reusando checkin.render_alertas_deload; y la nota de
    "estancamiento en cargas" pendiente). Se muestra siempre, sin
    depender de qué cliente esté seleccionado — mismo patrón que los
    vencimientos en Gestión de Clientes.
  - render_admin: constructor flexible de bloques de entrenamiento
    (día, ejercicio, músculo priorizado, series, repeticiones, RPE/RIR,
    descanso, notas técnicas) para el cliente seleccionado. Los bloques
    se guardan como JSON en "rutinas.bloques" — no hay un número fijo de
    ejercicios, el admin agrega/quita los que necesite. Cada día vive en
    un st.expander colapsable. Botón "Guardar y Notificar al Cliente"
    desactiva la rutina anterior, guarda la nueva como activa y dispara
    la notificación.
  - _render_resumen_volumen: gráfico de barras con las series totales
    por músculo de toda la rutina; se usa tanto en render_admin (en vivo
    mientras se edita) como en render_cliente.
  - render_cliente: vista de solo lectura de la rutina vigente, agrupada
    por día en expanders (el primer día abierto, el resto colapsado).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from modules import checkin
from utils import theme
from utils.auth import current_cliente_id
from utils.formato import formatear_fecha_hora
from utils.notificaciones import crear_notificacion
from utils.plan_entrenamiento import generar_ejemplo_rutina
from utils.queries import get_rutina_activa, guardar_rutina

DIAS = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5", "Día 6", "Día 7"]


def _texto_cantidad_ejercicios(cantidad: int) -> str:
    """" (N ejercicios)" para mostrar junto al título de cada día — vacío
    si el día todavía no tiene ejercicios (no tiene sentido decir "(0
    ejercicios)")."""
    if cantidad <= 0:
        return ""
    return f" ({cantidad} ejercicio{'s' if cantidad != 1 else ''})"

MUSCULOS = [
    "Pectoral", "Espalda", "Cuádriceps", "Isquios", "Hombros", "Glúteo", "Bíceps",
    "Tríceps", "Trapecio", "Aductores", "Abductores", "Pantorrillas", "Antebrazos", "Abdomen",
]

# (color de st.badge, color hex para el gráfico) — agrupados por función
# muscular (empuje en rojo/naranja, tirón en azul, piernas en verde) para
# que la paleta se sienta coherente en vez de arbitraria.
MUSCULO_COLOR: dict[str, tuple[str, str]] = {
    "Pectoral": ("red", "#FF6B6B"),
    "Hombros": ("orange", "#FFA94D"),
    "Tríceps": ("orange", "#FFA94D"),
    "Espalda": ("blue", "#4C9AFF"),
    "Bíceps": ("blue", "#4C9AFF"),
    "Trapecio": ("blue", "#4C9AFF"),
    "Cuádriceps": ("green", "#36B37E"),
    "Isquios": ("green", "#36B37E"),
    "Glúteo": ("green", "#36B37E"),
    "Aductores": ("green", "#36B37E"),
    "Abductores": ("green", "#36B37E"),
    "Pantorrillas": ("gray", "#ADB5BD"),
    "Antebrazos": ("gray", "#ADB5BD"),
    "Abdomen": ("violet", "#9775FA"),
}

BLOQUE_DEFAULT = {
    "dia": DIAS[0], "ejercicio": "", "musculo": MUSCULOS[0], "series": 3,
    "repeticiones": "8-12", "rpe_rir": "RIR 2", "descanso_min": 1.5, "notas": "",
}


def _mover_bloque(bloques: list[dict[str, Any]], bid: str, dia: str, direccion: int) -> None:
    """
    Sube (-1) o baja (+1) un ejercicio dentro de su mismo día, cambiando su
    posición en la lista real (no solo la vista agrupada por día) para que
    el orden se conserve al guardar.
    """
    indices_dia = [i for i, b in enumerate(bloques) if (b.get("dia") if b.get("dia") in DIAS else DIAS[0]) == dia]
    pos = indices_dia.index(next(i for i in indices_dia if bloques[i]["_id"] == bid))
    nueva_pos = pos + direccion
    if 0 <= nueva_pos < len(indices_dia):
        i, j = indices_dia[pos], indices_dia[nueva_pos]
        bloques[i], bloques[j] = bloques[j], bloques[i]


def render_alertas_entrenamiento() -> None:
    checkin.render_alertas_deload()
    st.info(
        "⏳ Alerta de estancamiento en cargas (3+ semanas sin progresar peso levantado): pendiente. "
        "Requiere un historial de cargas por ejercicio (historial_entrenamientos) que hoy no existe — "
        "depende de la integración con Hevy, pausada en el Paso 5 porque su API pública exige "
        "autenticación incluso para perfiles públicos."
    )


def render_admin(cliente_id: str) -> None:
    st.subheader("Rutina del cliente")

    rutina_actual = get_rutina_activa(cliente_id)
    if rutina_actual:
        st.caption(
            f"Rutina vigente: {rutina_actual.get('nombre_rutina')} · "
            f"{len(rutina_actual.get('bloques') or [])} ejercicios · "
            f"asignada el {formatear_fecha_hora(rutina_actual.get('fecha_asignacion'))}"
        )
    else:
        st.info("Este cliente todavía no tiene una rutina asignada.")

    bloques_key = f"rutina_bloques_{cliente_id}"
    if bloques_key not in st.session_state:
        bloques_iniciales = (rutina_actual.get("bloques") if rutina_actual else None) or []
        st.session_state[bloques_key] = [{**bloque, "_id": str(uuid.uuid4())} for bloque in bloques_iniciales]

    nombre_rutina = st.text_input(
        "Nombre de la rutina",
        value=(rutina_actual.get("nombre_rutina") if rutina_actual else None) or "Rutina de fuerza",
    )
    descripcion = st.text_area(
        "Descripción / objetivo de este bloque de entrenamiento",
        value=(rutina_actual.get("descripcion") if rutina_actual else None) or "",
        placeholder=(
            "Ej: Full body 3 días, ejercicios libres o con mancuerna en casa. "
            "Detecto automáticamente: idioma, días, si es en casa o gimnasio, y el tipo de "
            "split (Full Body, Upper/Lower, Push/Pull/Legs, Weider, Arnold, o una combinación "
            "de dos)."
        ),
    )

    if st.button("🤖 Generar ejemplo de rutina con esta descripción"):
        if not descripcion.strip():
            st.warning("Escribe algo en la descripción primero (ej. días, split, si es en casa o gimnasio).")
        else:
            resultado = generar_ejemplo_rutina(nombre_rutina, descripcion)
            st.session_state[bloques_key] = [
                {**bloque, "_id": str(uuid.uuid4())} for bloque in resultado.bloques
            ]
            for dia in DIAS:
                st.session_state.pop(f"rutina_etiqueta_{cliente_id}_{dia}", None)
            st.session_state[f"rutina_generada_resumen_{cliente_id}"] = resultado.resumen
            st.rerun()

    resumen_generado = st.session_state.pop(f"rutina_generada_resumen_{cliente_id}", None)
    if resumen_generado:
        st.info(
            f"🔎 Detecté: **{resumen_generado}**. Es una interpretación por palabras clave, no "
            "inteligencia artificial — revisa los ejercicios abajo y ajusta lo que haga falta "
            "antes de guardar."
        )

    st.markdown("##### Ejercicios")
    bloques: list[dict[str, Any]] = st.session_state[bloques_key]

    if not bloques:
        st.caption("Todavía no hay ejercicios. Abre un día abajo y agrega el primero.")

    por_dia: dict[str, list[dict[str, Any]]] = {dia: [] for dia in DIAS}
    for bloque in bloques:
        dia_bloque = bloque.get("dia") if bloque.get("dia") in DIAS else DIAS[0]
        por_dia[dia_bloque].append(bloque)

    # Todos los días se muestran siempre (colapsados si están vacíos) para
    # poder agregar el primer ejercicio de un día directamente ahí, y para
    # que "Agregar ejercicio" quede dentro de cada día en vez de mandar
    # siempre al Día 1.
    for dia in DIAS:
        etiqueta_key = f"rutina_etiqueta_{cliente_id}_{dia}"
        if etiqueta_key not in st.session_state:
            st.session_state[etiqueta_key] = next((b.get("dia_etiqueta") for b in por_dia[dia] if b.get("dia_etiqueta")), "")

        etiqueta_actual = st.session_state.get(etiqueta_key, "")
        sufijo_cantidad = _texto_cantidad_ejercicios(len(por_dia[dia]))
        titulo_expander = f"{dia}: {etiqueta_actual}{sufijo_cantidad}" if etiqueta_actual else f"{dia}{sufijo_cantidad}"
        with st.expander(titulo_expander, expanded=bool(por_dia[dia])):
            st.text_input("Nombre del día (opcional)", key=etiqueta_key, placeholder="Ej. Pecho y bíceps")

            total_dia = len(por_dia[dia])
            for i, bloque in enumerate(por_dia[dia]):
                bid = bloque["_id"]
                if i > 0:
                    st.divider()

                col1, col2, col_up, col_down, col3 = st.columns([1, 3, 0.5, 0.5, 1])
                with col1:
                    dia_actual = bloque.get("dia") if bloque.get("dia") in DIAS else DIAS[0]
                    bloque["dia"] = st.selectbox("Día", DIAS, index=DIAS.index(dia_actual), key=f"dia_{bid}")
                with col2:
                    bloque["ejercicio"] = st.text_input("Ejercicio", value=bloque.get("ejercicio", ""), key=f"ejercicio_{bid}")
                with col_up:
                    st.write("")
                    with st.container(key=f"arrow-up-{bid}"):
                        if st.button("↑", key=f"subir_{bid}", disabled=(i == 0), use_container_width=True, help="Subir"):
                            _mover_bloque(st.session_state[bloques_key], bid, dia, -1)
                            st.rerun()
                with col_down:
                    st.write("")
                    with st.container(key=f"arrow-down-{bid}"):
                        if st.button(
                            "↓", key=f"bajar_{bid}", disabled=(i == total_dia - 1), use_container_width=True, help="Bajar"
                        ):
                            _mover_bloque(st.session_state[bloques_key], bid, dia, 1)
                            st.rerun()
                with col3:
                    st.write("")
                    if st.button("🗑️ Quitar", key=f"quitar_{bid}", use_container_width=True):
                        st.session_state[bloques_key] = [b for b in bloques if b["_id"] != bid]
                        st.rerun()

                col4, col5, col6, col7, col8 = st.columns(5)
                with col4:
                    musculo_actual = bloque.get("musculo") if bloque.get("musculo") in MUSCULOS else MUSCULOS[0]
                    bloque["musculo"] = st.selectbox(
                        "Músculo", MUSCULOS, index=MUSCULOS.index(musculo_actual), key=f"musculo_{bid}"
                    )
                with col5:
                    bloque["series"] = st.number_input(
                        "Series", min_value=1, max_value=15, step=1, value=int(bloque.get("series") or 3), key=f"series_{bid}"
                    )
                with col6:
                    bloque["repeticiones"] = st.text_input(
                        "Repeticiones", value=bloque.get("repeticiones") or "8-12", key=f"reps_{bid}"
                    )
                with col7:
                    bloque["rpe_rir"] = st.text_input("RPE / RIR", value=bloque.get("rpe_rir") or "RIR 2", key=f"rpe_{bid}")
                with col8:
                    bloque["descanso_min"] = st.number_input(
                        "Descanso (min)", min_value=0.0, max_value=10.0, step=0.5,
                        value=float(bloque.get("descanso_min") or 1.5), key=f"descanso_{bid}"
                    )

                bloque["notas"] = st.text_input("Notas técnicas", value=bloque.get("notas") or "", key=f"notas_{bid}")

            if por_dia[dia]:
                st.divider()
            if st.button(f"➕ Agregar ejercicio a {dia}", key=f"agregar_{cliente_id}_{dia}"):
                st.session_state[bloques_key].append({**BLOQUE_DEFAULT, "dia": dia, "_id": str(uuid.uuid4())})
                st.rerun()

    _render_resumen_volumen(bloques)

    st.divider()

    if st.button("💾 Guardar y notificar al cliente", type="primary", use_container_width=True):
        bloques_limpios = []
        for bloque in st.session_state[bloques_key]:
            if not (bloque.get("ejercicio") or "").strip():
                continue
            etiqueta = st.session_state.get(f"rutina_etiqueta_{cliente_id}_{bloque['dia']}", "")
            limpio = {k: v for k, v in bloque.items() if k != "_id"}
            limpio["dia_etiqueta"] = etiqueta
            bloques_limpios.append(limpio)

        if not bloques_limpios:
            st.error("Agrega al menos un ejercicio con nombre antes de guardar.")
        else:
            guardar_rutina(
                cliente_id,
                creado_por=current_cliente_id(),
                nombre_rutina=nombre_rutina,
                descripcion=descripcion,
                bloques=bloques_limpios,
            )
            crear_notificacion(
                cliente_id,
                tipo="rutina_actualizada",
                titulo="Tienes una rutina nueva o actualizada",
                mensaje=(
                    f"Tu entrenador actualizó tu rutina '{nombre_rutina}' ({len(bloques_limpios)} ejercicios). "
                    "Revísala en la sección 'Mi Rutina'."
                ),
                creado_por=current_cliente_id(),
            )
            for dia in DIAS:
                st.session_state.pop(f"rutina_etiqueta_{cliente_id}_{dia}", None)
            del st.session_state[bloques_key]
            st.session_state[f"rutina_guardada_{cliente_id}"] = True
            st.rerun()

    if st.session_state.pop(f"rutina_guardada_{cliente_id}", False):
        st.success("✅ Rutina actualizada y asesorado notificado.")
        time.sleep(5)
        st.rerun()


def _render_resumen_volumen(bloques: list[dict[str, Any]]) -> None:
    """Gráfico de barras con las series totales por músculo en toda la rutina."""
    conteo = {musculo: 0 for musculo in MUSCULOS}
    for bloque in bloques:
        if not (bloque.get("ejercicio") or "").strip():
            continue
        musculo = bloque.get("musculo") if bloque.get("musculo") in MUSCULOS else None
        if musculo:
            conteo[musculo] += int(bloque.get("series") or 0)

    filas = sorted(((m, s) for m, s in conteo.items() if s > 0), key=lambda f: f[1])
    if not filas:
        return

    musculos_orden = [f[0] for f in filas]
    series_orden = [f[1] for f in filas]
    colores = [MUSCULO_COLOR.get(m, ("gray", "#ADB5BD"))[1] for m in musculos_orden]

    st.markdown("##### Volumen total por músculo (series de toda la rutina)")
    fig = go.Figure(
        go.Bar(
            x=series_orden,
            y=musculos_orden,
            orientation="h",
            marker=dict(color=colores),
            text=series_orden,
            textposition="outside",
            hovertemplate="%{y}: %{x} series<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=30), height=max(220, 36 * len(filas)))
    fig.update_xaxes(showgrid=False, zeroline=False)
    st.plotly_chart(theme.estilizar_grafico(fig), use_container_width=True)


def render_cliente(cliente_id: str) -> None:
    st.subheader("Mi Rutina")

    rutina = get_rutina_activa(cliente_id)
    if not rutina:
        st.info("Tu entrenador todavía no te ha asignado una rutina.")
        return

    st.caption(f"Asignada el {formatear_fecha_hora(rutina.get('fecha_asignacion'))}")
    st.markdown(f"### {rutina.get('nombre_rutina')}")
    if rutina.get("descripcion"):
        st.write(rutina["descripcion"])

    bloques = rutina.get("bloques") or []
    if not bloques:
        st.info("Esta rutina todavía no tiene ejercicios cargados.")
        return

    por_dia: dict[str, list[dict[str, Any]]] = {}
    for bloque in bloques:
        por_dia.setdefault(bloque.get("dia") or "Sin día asignado", []).append(bloque)

    dias_ordenados = sorted(por_dia, key=lambda d: DIAS.index(d) if d in DIAS else len(DIAS))
    for idx, dia in enumerate(dias_ordenados):
        etiqueta = next((b.get("dia_etiqueta") for b in por_dia[dia] if b.get("dia_etiqueta")), "")
        sufijo_cantidad = _texto_cantidad_ejercicios(len(por_dia[dia]))
        titulo_dia = f"{dia}: {etiqueta}{sufijo_cantidad}" if etiqueta else f"{dia}{sufijo_cantidad}"
        with st.expander(titulo_dia, expanded=(idx == 0)):
            for i, ejercicio in enumerate(por_dia[dia]):
                if i > 0:
                    st.divider()
                st.markdown(f"#### {ejercicio.get('ejercicio') or 'Ejercicio sin nombre'}")
                musculo = ejercicio.get("musculo")
                if musculo in MUSCULOS:
                    color, _ = MUSCULO_COLOR.get(musculo, ("gray", "#ADB5BD"))
                    st.badge(musculo, color=color)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Series", ejercicio.get("series") if ejercicio.get("series") is not None else "—")
                col2.metric("Reps", ejercicio.get("repeticiones") or "—")
                col3.metric("RPE/RIR", ejercicio.get("rpe_rir") or "—")
                col4.metric("Descanso", f"{_formatear_minutos(ejercicio.get('descanso_min'))} min")
                if ejercicio.get("notas"):
                    st.caption(f"📝 {ejercicio['notas']}")

    st.divider()
    _render_resumen_volumen(bloques)


def _formatear_minutos(minutos: float | None) -> str:
    valor = minutos or 0
    return str(int(valor)) if float(valor).is_integer() else f"{valor:g}"
