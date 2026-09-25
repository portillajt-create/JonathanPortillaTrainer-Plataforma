"""
PDFs descargables: ficha de onboarding (Ficha del Atleta) y reporte de
progreso (Progreso). Los dos, SOLO desde la vista del admin — el cliente no
tiene botón de descarga en ninguna página (decisión del usuario, 2026-09-25);
el entrenador decide si le comparte el reporte.

El aspecto visual (fondo negro, logo, degradado cian-azul, tarjetas,
gráficas) vive en utils/pdf_base.py; los comentarios de tendencia, en
utils/tendencias.py. Este módulo solo decide QUÉ va en cada reporte.

Ninguna función de acá consulta la base de datos ni usa Streamlit: reciben
los datos ya cargados por la página. Eso permite pasarlas a
st.download_button como callable (se generan recién al hacer clic, en otro
hilo — donde no hay sesión de Streamlit ni de Supabase disponibles).
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import mean
from typing import Any

from utils import tendencias as t
from utils.analisis_progreso import detectar_ejercicios_a_revisar
from utils.formato import es_respuesta_vacia_o_negativa
from utils.pdf_base import CIAN, GRIS, ROJO, PDFMarca


def _calcular_edad(fecha_nacimiento: str | None, hoy: date) -> int | None:
    if not fecha_nacimiento:
        return None
    nacimiento = date.fromisoformat(fecha_nacimiento)
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def _nombre(cliente: dict[str, Any]) -> str:
    return (cliente.get("nombre_completo") or cliente.get("email") or "Cliente").strip()


# ---------------------------------------------------------------------------
# Ficha de onboarding
# ---------------------------------------------------------------------------
def generar_pdf_onboarding(cliente: dict[str, Any], datos: dict[str, Any], hoy: date) -> bytes:
    """Resumen del formulario de onboarding de un cliente, para la Ficha del Atleta."""
    pdf = PDFMarca("Ficha de Onboarding")
    pdf.add_page()

    edad = _calcular_edad(datos.get("fecha_nacimiento"), hoy)
    pdf.portada(
        "Ficha del atleta",
        "Ficha de Onboarding",
        _nombre(cliente),
        [cliente.get("email"), datos.get("ciudad_pais")],
    )

    hay_patologias = not es_respuesta_vacia_o_negativa(datos.get("patologias"))
    hay_lesiones = not es_respuesta_vacia_o_negativa(datos.get("lesiones"))
    if hay_patologias or hay_lesiones:
        pdf.aviso(
            "Atención: este cliente reportó patologías y/o lesiones. Revisar antes de asignar "
            "cargas o ejercicios de riesgo."
        )

    dias = datos.get("disponibilidad_dias")
    pdf.kpis(
        [
            ("Edad", f"{edad} años" if edad is not None else "—", None, GRIS),
            ("Altura", f"{datos['altura_cm']:.0f} cm" if datos.get("altura_cm") is not None else "—", None, GRIS),
            ("Peso", f"{datos['peso_kg']:.0f} kg" if datos.get("peso_kg") is not None else "—", None, GRIS),
            ("Nivel", datos.get("nivel_experiencia") or "—", None, GRIS),
            ("Objetivo", datos.get("objetivo_principal") or "—", None, GRIS),
            ("Disponibilidad", f"{dias} días/semana" if dias is not None else "—", None, GRIS),
        ]
    )

    pdf.seccion("Historial médico")
    pdf.grilla_campos(
        [
            ("*Patologías", datos.get("patologias") if hay_patologias else "Ninguna reportada", hay_patologias),
            ("*Lesiones", datos.get("lesiones") if hay_lesiones else "Ninguna reportada", hay_lesiones),
            ("*Medicamentos", datos.get("medicamentos"), False),
        ]
    )

    pdf.seccion("Datos personales")
    pdf.grilla_campos(
        [
            ("Fecha de nacimiento", _fecha_legible(datos.get("fecha_nacimiento")), False),
            ("Sexo", datos.get("sexo"), False),
            ("Ocupación", datos.get("ocupacion"), False),
            ("Ciudad / País", datos.get("ciudad_pais"), False),
        ]
    )

    sueno = datos.get("horas_sueno_promedio")
    estres = datos.get("nivel_estres_habitual")
    comidas = datos.get("comidas_dia")
    pdf.seccion("Hábitos y entrenamiento")
    pdf.grilla_campos(
        [
            ("Sueño promedio", f"{sueno} h" if sueno is not None else None, False),
            ("Estrés habitual", f"{estres}/10" if estres is not None else None, False),
            ("Comidas al día", comidas, False),
            ("Días disponibles por semana", dias, False),
            ("*Equipamiento disponible", datos.get("equipamiento"), False),
            ("*Alergias alimentarias", datos.get("alergias_alimentarias"), False),
        ]
    )

    if datos.get("hevy_perfil_url"):
        pdf.seccion("Hevy")
        pdf.grilla_campos([("*Perfil público", datos.get("hevy_perfil_url"), False)])

    if (datos.get("notas_adicionales") or "").strip():
        pdf.seccion("Notas adicionales del asesorado")
        pdf.grilla_campos([("*Notas", datos["notas_adicionales"], False)])

    return bytes(pdf.output())


def _fecha_legible(iso: str | None) -> str | None:
    return date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else None


# ---------------------------------------------------------------------------
# Reporte de progreso
# ---------------------------------------------------------------------------
def _serie(checkins: list[dict], campo: str) -> list[tuple[date, float]]:
    return [
        (date.fromisoformat(c["semana_fecha"]), float(c[campo]))
        for c in checkins
        if c.get(campo) is not None
    ]


def _delta_kpi(
    checkins: list[dict], campo: str, mayor_es_mejor: bool | None, unidad: str = "", decimales: int = 0,
) -> tuple[str | None, tuple[int, int, int]]:
    """Texto "±x vs semana anterior" y su color (cian favorable, rojo desfavorable, gris neutral)."""
    valores = [c[campo] for c in checkins if c.get(campo) is not None]
    if len(valores) < 2:
        return None, GRIS
    delta = valores[-1] - valores[-2]
    if abs(delta) < 10 ** -(decimales + 1):
        return "igual que el check-in anterior", GRIS
    signo = "+" if delta > 0 else "–"
    texto = f"{signo}{abs(delta):.{decimales}f}{unidad} vs check-in anterior"
    if mayor_es_mejor is None:
        return texto, GRIS
    return texto, (CIAN if (delta > 0) == mayor_es_mejor else ROJO)


def _valor_kpi(checkin: dict, campo: str, formato: str) -> str:
    v = checkin.get(campo)
    return formato.format(v) if v is not None else "—"


def generar_pdf_progreso(
    cliente: dict[str, Any],
    checkins: list[dict],
    historial: list[dict],
    objetivo: str | None,
    hoy: date,
) -> bytes:
    """
    Reporte de progreso: el mismo contenido de la página Progreso (check-ins,
    peso, adherencia, bienestar, fuerza por ejercicio) más comentarios
    automáticos de tendencia. checkins en orden cronológico (list_checkins),
    historial = list_historial_entrenamientos.
    """
    pdf = PDFMarca("Reporte de Progreso")
    pdf.add_page()

    checkins = sorted(checkins, key=lambda c: c["semana_fecha"])
    detalles = [cliente.get("email")]
    if objetivo:
        detalles.append(f"Objetivo: {objetivo.lower()}")
    if checkins:
        f0 = date.fromisoformat(checkins[0]["semana_fecha"])
        f1 = date.fromisoformat(checkins[-1]["semana_fecha"])
        detalles.append(
            f"{len(checkins)} check-in{'s' if len(checkins) != 1 else ''} "
            + (f"del {f0.strftime('%d/%m/%Y')} al {f1.strftime('%d/%m/%Y')}" if f0 != f1 else f"(semana del {f0.strftime('%d/%m/%Y')})")
        )
    pdf.portada("Reporte de progreso", "Reporte de Progreso", _nombre(cliente), detalles)

    peso = _serie(checkins, "peso_corporal_kg")
    ad_dieta = _serie(checkins, "adherencia_dieta")
    ad_entreno = _serie(checkins, "adherencia_entrenamiento")
    sueno = _serie(checkins, "calidad_sueno")
    estres = _serie(checkins, "nivel_estres")
    fatiga = _serie(checkins, "fatiga")

    # --- Fuerza (se calcula antes porque también alimenta el resumen) ---
    a_revisar = detectar_ejercicios_a_revisar(historial, hoy) if historial else []
    nombres_a_revisar = {r["Ejercicio"] for r in a_revisar}
    desde_fuerza = hoy - timedelta(days=t.DIAS_VENTANA_FUERZA)
    ejercicios = t.ejercicios_principales(historial, hoy) if historial else []
    series_fuerza = {e: t.serie_1rm(historial, e, desde_fuerza) for e in ejercicios}

    # --- Resumen ---
    valores = lambda s: [v for _, v in s]  # noqa: E731
    resumen = []
    if checkins:
        resumen.append(t.resumen_peso(peso))
        if ad_dieta or ad_entreno:
            partes = []
            if ad_dieta:
                partes.append(f"dieta {mean(valores(ad_dieta)):.1f}/10")
            if ad_entreno:
                partes.append(f"entrenamiento {mean(valores(ad_entreno)):.1f}/10")
            resumen.append(f"Adherencia promedio: {' · '.join(partes)}.")
        resumen.append(t.resumen_bienestar(valores(sueno), valores(estres), valores(fatiga)))
    if ejercicios:
        resumen.append(
            t.resumen_fuerza([t.clasificar_1rm(series_fuerza[e]) for e in ejercicios], len(a_revisar))
        )
    resumen = [r for r in resumen if r]

    if not checkins and not historial:
        pdf.seccion("Todavía no hay datos de progreso")
        pdf.escribir(
            "Este reporte se llena con los check-ins semanales y el historial de entrenamiento de Hevy. "
            "Aparecerán aquí en cuanto haya al menos un check-in registrado.",
            pdf.epw, color=GRIS,
        )
        return bytes(pdf.output())

    if resumen:
        pdf.seccion("Resumen")
        pdf.vinetas(resumen)

    # --- Último check-in ---
    if checkins:
        ultimo = checkins[-1]
        semana = date.fromisoformat(ultimo["semana_fecha"]).strftime("%d/%m/%Y")
        pdf.seccion(
            "Último check-in",
            f"Semana del {semana}" + (", comparada con el check-in anterior." if len(checkins) > 1 else "."),
        )
        direccion_peso = t.direccion_peso_segun_objetivo(objetivo)
        pdf.kpis(
            [
                ("Peso corporal", _valor_kpi(ultimo, "peso_corporal_kg", "{:.1f} kg"),
                 *_delta_kpi(checkins, "peso_corporal_kg", (direccion_peso > 0) if direccion_peso else None, " kg", 1)),
                ("Adherencia dieta", _valor_kpi(ultimo, "adherencia_dieta", "{}/10"),
                 *_delta_kpi(checkins, "adherencia_dieta", True)),
                ("Adherencia entreno", _valor_kpi(ultimo, "adherencia_entrenamiento", "{}/10"),
                 *_delta_kpi(checkins, "adherencia_entrenamiento", True)),
                ("Calidad de sueño", _valor_kpi(ultimo, "calidad_sueno", "{}/10"),
                 *_delta_kpi(checkins, "calidad_sueno", True)),
                ("Nivel de estrés", _valor_kpi(ultimo, "nivel_estres", "{}/10"),
                 *_delta_kpi(checkins, "nivel_estres", False)),
                ("Fatiga", _valor_kpi(ultimo, "fatiga", "{}/10"),
                 *_delta_kpi(checkins, "fatiga", False)),
            ]
        )
        notas = (ultimo.get("notas") or "").strip()
        if notas:
            pdf.grilla_campos([("*Notas del cliente sobre esa semana", notas, False)])

        comentarios_adherencia = [
            t.comentario_escala("Adherencia a la dieta", valores(ad_dieta), True, t.UMBRAL_ADHERENCIA_DIETA_BAJA, False),
            t.comentario_escala("Adherencia al entrenamiento", valores(ad_entreno), True),
        ]
        comentario_peso = [t.comentario_peso(peso, objetivo)]
        primer_grafico = (
            pdf.alto_grafico(pdf.epw, comentario_peso, 46) if peso
            else pdf.alto_grafico(pdf.epw, comentarios_adherencia, 46)
        )
        pdf.seccion(
            "Check-ins semanales", "Evolución semana a semana y lectura automática de la tendencia.",
            reservar=primer_grafico,
        )
        if peso:
            pdf.grafico_lineas("Peso corporal (kg)", [("Peso", peso)], comentario_peso, area=True)
        pdf.grafico_lineas(
            "Adherencia",
            [("Dieta", ad_dieta), ("Entrenamiento", ad_entreno)],
            comentarios_adherencia,
            escala_1_10=True,
        )
        pdf.grafico_lineas(
            "Bienestar",
            [("Sueño", sueno), ("Estrés", estres), ("Fatiga", fatiga)],
            [
                t.comentario_escala("Calidad de sueño", valores(sueno), True, t.UMBRAL_SUENO_BAJO, False),
                t.comentario_escala("Nivel de estrés", valores(estres), False, t.UMBRAL_ESTRES_ALTO, True),
                t.comentario_escala("Fatiga", valores(fatiga), False, t.UMBRAL_FATIGA_ALTA, True),
            ],
            escala_1_10=True,
        )

    # --- Fuerza ---
    sep = 4
    ancho = (pdf.epw - sep) / 2
    alto_plot = 34
    comentarios_fuerza = {
        e: [t.comentario_1rm(e, series_fuerza[e], e in nombres_a_revisar)] for e in ejercicios
    }
    pdf.seccion(
        "Fuerza",
        "1RM estimado (fórmula de Epley) de los ejercicios más entrenados en los últimos 3 meses, "
        "graficado sobre los últimos 6 meses.",
        # Si la sección abre directo con las gráficas (sin tabla de
        # ejercicios a revisar), reservar la primera fila completa.
        reservar=(
            max(pdf.alto_grafico(ancho, comentarios_fuerza[e], alto_plot) for e in ejercicios[:2])
            if ejercicios and not a_revisar else 22
        ),
    )
    if not historial:
        pdf.escribir(
            "Todavía no se ha cargado el historial de entrenamiento de Hevy de este cliente.",
            pdf.epw, size=9.5, color=GRIS,
        )
        pdf.ln(3)
    else:
        if a_revisar:
            pdf.set_x(pdf.l_margin)
            pdf.escribir("Ejercicios a tener en cuenta", pdf.epw, size=10, estilo="B")
            pdf.escribir(
                "Se siguen entrenando pero sin progreso real de fuerza en las últimas sesiones, del más al menos marcado.",
                pdf.epw, size=8.5, alto_linea=4.5, color=GRIS,
            )
            pdf.ln(2)
            pdf.tabla(
                ["Ejercicio", "Motivo", "Última sesión"],
                [
                    [r["Ejercicio"], r["Motivo"], date.fromisoformat(r["Última sesión"]).strftime("%d/%m/%Y")]
                    for r in a_revisar
                ],
                [3, 6, 1.6],
            )
        if not ejercicios:
            pdf.escribir(
                "No hay ejercicios con suficientes sesiones con carga en los últimos meses para graficar.",
                pdf.epw, size=9.5, color=GRIS,
            )
        # Dos gráficas por fila, de la misma altura.
        for i in range(0, len(ejercicios), 2):
            par = ejercicios[i : i + 2]
            comentarios = {e: comentarios_fuerza[e] for e in par}
            alto = max(pdf.alto_grafico(ancho, comentarios[e], alto_plot) for e in par)
            pdf.asegurar_espacio(alto + 4)
            y = pdf.get_y()
            for j, e in enumerate(par):
                pdf.set_y(y)
                pdf.grafico_lineas(
                    e, [("1RM estimado", series_fuerza[e])], comentarios[e], unidad="",
                    alto_plot=alto_plot, area=True, ancho=ancho, x=pdf.l_margin + j * (ancho + sep), alto_min=alto,
                )
            pdf.set_y(y + alto + 5)

    pdf.ln(2)
    pdf.escribir(
        "Los comentarios de este reporte se generan con reglas fijas sobre tus datos (promedios de las "
        "últimas semanas frente a las anteriores), no son un diagnóstico. Cualquier duda, háblala con tu entrenador.",
        pdf.epw, size=7.5, alto_linea=4, color=GRIS,
    )
    return bytes(pdf.output())
