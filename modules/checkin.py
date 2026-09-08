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
from utils.formato import escapar_markdown, fecha_bogota, hoy_bogota
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
# Modelo de semanas del check-in: lógica pura, sin Streamlit — vive en
# utils/semanas_checkin.py para que scripts/recordatorios_diarios.py (el
# cron, que corre fuera de la app) calcule EXACTAMENTE la misma "semana a
# reportar" que ve el cliente acá, sin duplicar la lógica en dos lugares
# que puedan divergir. Se importa con un alias corto porque se usa mucho
# en este módulo.
from utils.semanas_checkin import rango_semana as _rango_semana
from utils.semanas_checkin import semana_a_reportar, semana_en_curso_reportable
from utils.semanas_checkin import lunes_semana_en_curso as _lunes_semana_en_curso

UMBRAL_FATIGA_ALTA = 8
UMBRAL_ESTRES_ALTO = 8
UMBRAL_SUENO_BAJO = 4
UMBRAL_ADHERENCIA_DIETA_BAJA = 5


# ---------------------------------------------------------------------------
# Check-in semanal (cliente)
# ---------------------------------------------------------------------------
def render_checkin_cliente(cliente_id: str) -> None:
    st.subheader("Check-in Semanal")

    if not cliente_id:
        st.warning("No se encontró tu identificador de cliente.")
        return

    semanas: list[tuple[date, str]] = []
    pendiente = semana_a_reportar()
    if pendiente:
        semanas.append((pendiente, "Semana pasada"))
    en_curso = semana_en_curso_reportable()
    if en_curso:
        semanas.append((en_curso, "Semana en curso"))

    if not semanas:
        proximo_lunes = _lunes_semana_en_curso() + timedelta(days=7)
        st.info(
            "Todavía no hay ninguna semana por reportar. El check-in se llena sobre una semana "
            f"ya terminada: el primero se habilita el lunes {_rango_semana(proximo_lunes).split(' –')[0]}, "
            "o desde el jueves si quieres adelantar el de la semana en curso."
        )
        return

    st.caption(
        "El check-in se reporta sobre una semana **ya terminada**, para que puedas calificar cómo "
        "te fue de verdad. Puntúa cada aspecto de 1 (muy bajo) a 10 (muy alto)."
    )

    if len(semanas) == 1:
        lunes, etiqueta = semanas[0]
        _render_form_semana(cliente_id, lunes, etiqueta)
        return

    tabs = st.tabs([f"{etiqueta} ({_rango_semana(lunes)})" for lunes, etiqueta in semanas])
    for tab, (lunes, etiqueta) in zip(tabs, semanas):
        with tab:
            _render_form_semana(cliente_id, lunes, etiqueta)


def _render_form_semana(cliente_id: str, lunes: date, etiqueta: str) -> None:
    """Formulario de check-in de UNA semana concreta (identificada por su lunes)."""
    guardado = get_checkin_semana(cliente_id, lunes) or {}
    rango = _rango_semana(lunes)

    # Los avisos de "te falta" / "en curso" van ARRIBA porque son una
    # instrucción: dicen qué hacer antes de tocar el formulario. El de "ya
    # reportaste" va ABAJO, después del botón (ver más abajo), porque no es
    # una instrucción sino una confirmación: es lo que el cliente necesita
    # ver justo donde acaba de hacer clic al guardar.
    if not guardado:
        if etiqueta == "Semana pasada":
            st.warning(f"⏳ Te falta reportar la semana del {rango}. Tienes hasta el domingo para hacerlo.")
        else:
            st.info(f"Semana del {rango}, todavía en curso. Puedes adelantarla si ya sabes cómo te fue.")

    sufijo = lunes.isoformat()
    with st.form(f"checkin_form_{sufijo}"):
        col1, col2 = st.columns(2)
        with col1:
            adherencia_dieta = st.slider(
                "Adherencia a la dieta", 1, 10, value=guardado.get("adherencia_dieta") or 7, key=f"ad_{sufijo}"
            )
            calidad_sueno = st.slider(
                "Calidad del sueño", 1, 10, value=guardado.get("calidad_sueno") or 7, key=f"cs_{sufijo}"
            )
            fatiga = st.slider(
                "Fatiga (10 = muy fatigado)", 1, 10, value=guardado.get("fatiga") or 4, key=f"fa_{sufijo}"
            )
        with col2:
            adherencia_entrenamiento = st.slider(
                "Adherencia al entrenamiento", 1, 10,
                value=guardado.get("adherencia_entrenamiento") or 7, key=f"ae_{sufijo}",
            )
            nivel_estres = st.slider(
                "Nivel de estrés (10 = muy estresado)", 1, 10,
                value=guardado.get("nivel_estres") or 4, key=f"ne_{sufijo}",
            )
            peso_corporal_kg = st.number_input(
                "Peso corporal (kg)", min_value=30.0, max_value=250.0, step=0.1,
                value=float(guardado.get("peso_corporal_kg") or 70.0), key=f"pc_{sufijo}",
            )

        st.markdown("##### Notas de la semana (opcional)")
        st.caption("Cuéntale a tu entrenador cualquier cosa que los números no digan")
        notas = st.text_area(
            "Notas de la semana",
            value=guardado.get("notas") or "",
            placeholder=(
                "¿Cómo te sentiste esta semana? Energía, ánimo, algún dolor o molestia, "
                "cambios en tu rutina diaria o en tu alimentación...\n"
                "Cualquier otra cosa que quieras contarle a tu entrenador."
            ),
            label_visibility="collapsed",
            key=f"no_{sufijo}",
        )

        submitted = st.form_submit_button("💾 Guardar check-in", use_container_width=True, type="primary")

    if guardado:
        st.success(f"✅ Ya reportaste la semana del {rango}. Puedes actualizarla si algo cambió.")

    if submitted:
        upsert_checkin(
            cliente_id,
            semana_fecha=lunes.isoformat(),
            adherencia_dieta=adherencia_dieta,
            adherencia_entrenamiento=adherencia_entrenamiento,
            calidad_sueno=calidad_sueno,
            nivel_estres=nivel_estres,
            fatiga=fatiga,
            peso_corporal_kg=peso_corporal_kg,
            notas=notas,
        )
        st.success(f"Check-in de la semana del {rango} guardado. ¡Gracias por la actualización!")
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
    Avisa si la semana anterior (ya cerrada) sigue sin reportarse. Se evalúa
    al entrar a "Mis Notificaciones" en vez de con un cron, porque la app no
    tiene proceso en segundo plano.

    A diferencia de la versión anterior, el aviso SÍ se repite mientras el
    check-in siga pendiente — que es lo útil, porque el cliente todavía está
    a tiempo de llenarlo. El límite es de un aviso por día: sin ese tope,
    cada visita a esta pantalla dispararía otro correo.
    """
    semana = semana_a_reportar()
    if semana is None:
        return  # aún no arranca el periodo de seguimiento (ver SEMANA_INICIO_CHECKINS)

    cliente = get_cliente(cliente_id)
    fecha_creacion = fecha_bogota(cliente.get("created_at") if cliente else None)
    if fecha_creacion and fecha_creacion > semana:
        return  # el cliente todavía no existía en esa semana

    if get_checkin_semana(cliente_id, semana):
        return  # ya la reportó: no se avisa nada

    hoy = hoy_bogota()
    ya_avisado_hoy = any(
        n["tipo"] == "checkin_faltante" and fecha_bogota(n.get("created_at")) == hoy
        for n in list_notificaciones(cliente_id)
    )
    if ya_avisado_hoy:
        return

    # crear_notificacion_sistema (no crear_notificacion): esta alerta la dispara
    # la sesión del propio CLIENTE, y la policy de INSERT de "notificaciones"
    # exige ser admin. Ver sql/001_schema_roles_rls.sql.
    crear_notificacion_sistema(
        cliente_id,
        tipo="checkin_faltante",
        titulo="Check-in semanal pendiente",
        mensaje=(
            f"Todavía no reportaste tu check-in de la semana del {_rango_semana(semana)}. "
            "Tienes hasta el domingo para completarlo en 'Check-in Semanal' y que tu "
            "entrenador pueda dar seguimiento a tu progreso."
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
