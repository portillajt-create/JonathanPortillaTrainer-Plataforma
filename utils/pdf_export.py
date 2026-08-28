"""
Generación de PDFs descargables para el entrenador.

Usa fpdf2 (puro Python, sin dependencias de sistema como Cairo/Pango) para
que la generación funcione igual en local y en Streamlit Community Cloud.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fpdf import FPDF

_AZUL = (59, 130, 246)
_GRIS = (110, 110, 110)
_ROJO = (200, 30, 30)
_ANCHO_CONTENIDO = 190


def _safe(texto: Any) -> str:
    """
    Las fuentes core de fpdf2 (Helvetica) solo soportan latin-1, donde caben
    tildes y "ñ" sin problema. Por si llega algo fuera de ese rango (emoji,
    etc.) lo reemplazamos en vez de romper la generación del PDF.
    """
    if texto in (None, ""):
        return "-"
    return str(texto).encode("latin-1", "replace").decode("latin-1")


class _PDFOnboarding(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*_AZUL)
        self.cell(0, 10, "Ficha de Onboarding", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_GRIS)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")


def _seccion(pdf: _PDFOnboarding, titulo: str) -> None:
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_AZUL)
    pdf.cell(0, 8, _safe(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_AZUL)
    pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + _ANCHO_CONTENIDO, pdf.get_y())
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _campo(pdf: _PDFOnboarding, etiqueta: str, valor: Any, alerta: bool = False) -> None:
    pdf.set_font("Helvetica", "B", 10)
    if alerta:
        pdf.set_text_color(*_ROJO)
    pdf.cell(52, 6, _safe(f"{etiqueta}:"))
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _safe(valor), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)


def _calcular_edad(fecha_nacimiento: str | None) -> int | None:
    if not fecha_nacimiento:
        return None
    nacimiento = date.fromisoformat(fecha_nacimiento)
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def generar_pdf_onboarding(cliente: dict[str, Any], datos: dict[str, Any]) -> bytes:
    """Arma el PDF de resumen de onboarding de un cliente para descargar desde la Ficha del Atleta."""
    pdf = _PDFOnboarding()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    nombre = cliente.get("nombre_completo") or cliente.get("email") or "Cliente"
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, _safe(nombre), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRIS)
    pdf.cell(0, 6, _safe(cliente.get("email")), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"Generado el {date.today().isoformat()}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    hay_patologias = bool((datos.get("patologias") or "").strip())
    hay_lesiones = bool((datos.get("lesiones") or "").strip())
    if hay_patologias or hay_lesiones:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*_ROJO)
        pdf.multi_cell(
            _ANCHO_CONTENIDO,
            6,
            _safe(
                "ATENCIÓN: este cliente reportó patologías y/o lesiones. Revisar antes de "
                "asignar cargas o ejercicios de riesgo."
            ),
        )
        pdf.set_text_color(0, 0, 0)

    edad = _calcular_edad(datos.get("fecha_nacimiento"))

    _seccion(pdf, "Datos personales")
    _campo(pdf, "Fecha de nacimiento", datos.get("fecha_nacimiento"))
    _campo(pdf, "Edad", f"{edad} años" if edad is not None else None)
    _campo(pdf, "Sexo", datos.get("sexo"))
    _campo(pdf, "Ocupación", datos.get("ocupacion"))
    _campo(pdf, "Ciudad / País", datos.get("ciudad_pais"))
    _campo(pdf, "Altura", f"{datos['altura_cm']:.0f} cm" if datos.get("altura_cm") is not None else None)
    _campo(pdf, "Peso", f"{datos['peso_kg']:.0f} kg" if datos.get("peso_kg") is not None else None)

    _seccion(pdf, "Historial médico")
    _campo(pdf, "Patologías", datos.get("patologias"), alerta=hay_patologias)
    _campo(pdf, "Lesiones", datos.get("lesiones"), alerta=hay_lesiones)
    _campo(pdf, "Medicamentos", datos.get("medicamentos"))

    _seccion(pdf, "Entrenamiento")
    _campo(pdf, "Nivel de experiencia", datos.get("nivel_experiencia"))
    _campo(pdf, "Objetivo principal", datos.get("objetivo_principal"))
    dias = datos.get("disponibilidad_dias")
    _campo(pdf, "Días disponibles/semana", dias if dias is not None else None)
    _campo(pdf, "Equipamiento disponible", datos.get("equipamiento"))

    _seccion(pdf, "Hábitos")
    sueno = datos.get("horas_sueno_promedio")
    _campo(pdf, "Sueño promedio", f"{sueno} h" if sueno is not None else None)
    estres = datos.get("nivel_estres_habitual")
    _campo(pdf, "Estrés habitual", f"{estres}/10" if estres is not None else None)
    comidas = datos.get("comidas_dia")
    _campo(pdf, "Comidas al día", comidas if comidas is not None else None)
    _campo(pdf, "Alergias alimentarias", datos.get("alergias_alimentarias"))

    if datos.get("hevy_perfil_url"):
        _seccion(pdf, "Hevy")
        _campo(pdf, "Perfil público", datos.get("hevy_perfil_url"))

    if (datos.get("notas_adicionales") or "").strip():
        _seccion(pdf, "Notas adicionales del asesorado")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _safe(datos["notas_adicionales"]), new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
