"""
Identidad visual compartida de los PDFs descargables (onboarding y progreso):
fondo negro, logo en blanco, degradado cian-azul (#5EEAD4 → #3B82F6, el
mismo de los títulos y botones principales de la app — ver utils/theme.py)
y tarjetas oscuras redondeadas como las de la interfaz.

Todo se dibuja con fpdf2 (puro Python, sin Cairo/Pango/Chrome), incluidas
las gráficas: se trazan directo con líneas y círculos del PDF en vez de
exportar las de Plotly a imagen. Así:
  - no hace falta ninguna dependencia nueva (exportar Plotly exige kaleido +
    un Chrome instalado, que Streamlit Community Cloud no garantiza);
  - las gráficas quedan vectoriales (nítidas a cualquier zoom) y con la
    paleta de marca, no con la de Plotly.

Fuente: Helvetica (core de fpdf2) con core_fonts_encoding="windows-1252",
que a diferencia del latin-1 por defecto sí trae comillas tipográficas,
guion largo (–), viñeta (•) y puntos suspensivos. Lo que no cabe ahí (emoji
que pueda escribir un cliente, flechas) se descarta en _safe() en vez de
romper la generación.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

from fpdf import FPDF
from fpdf.pattern import LinearGradient

from utils.formato import hoy_bogota

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO_COMPLETO = _ASSETS / "logo_full.png"
LOGO_ICONO = _ASSETS / "icon.png"

NEGRO = (0, 0, 0)
TARJETA = (17, 17, 20)
TARJETA_ALERTA = (48, 14, 18)
BORDE = (38, 38, 43)
BORDE_ALERTA = (127, 29, 29)
GRILLA = (42, 42, 48)
TEXTO = (242, 242, 242)
GRIS = (156, 163, 175)
GRIS_OSCURO = (107, 114, 128)
CIAN = (94, 234, 212)
AZUL = (59, 130, 246)
VIOLETA = (167, 139, 250)
ROJO = (248, 113, 113)
DEGRADADO = ["#5EEAD4", "#3B82F6"]

#: Colores de las series de las gráficas, en orden (paleta de marca).
COLORES_SERIES = [CIAN, AZUL, VIOLETA]


def _safe(texto: Any) -> str:
    if texto in (None, ""):
        return "—"
    original = str(texto)
    limpio = original.encode("cp1252", "ignore").decode("cp1252")
    if limpio != original:
        # Al quitar un emoji puede quedar "en hotel ." — se pega la puntuación.
        limpio = re.sub(r"[ \t]+([.,;:!?)])", r"\1", limpio)
    return limpio.strip() or "—"


def _ticks_bonitos(vmin: float, vmax: float, n: int = 4) -> tuple[float, float, list[float]]:
    """Rango y marcas "redondas" (1, 2, 2.5, 5 × 10^k) para un eje con datos entre vmin y vmax."""
    if vmin == vmax:
        vmin, vmax = vmin - 1, vmax + 1
    margen = (vmax - vmin) * 0.12
    vmin, vmax = vmin - margen, vmax + margen
    crudo = (vmax - vmin) / n
    mag = 10 ** math.floor(math.log10(crudo))
    paso = mag
    for m in (1, 2, 2.5, 5, 10):
        paso = m * mag
        if (vmax - vmin) / paso <= n:
            break
    lo = math.floor(vmin / paso) * paso
    hi = math.ceil(vmax / paso) * paso
    marcas = [lo + i * paso for i in range(int(round((hi - lo) / paso)) + 1)]
    return lo, hi, marcas


class PDFMarca(FPDF):
    """FPDF con el fondo, encabezado y pie de marca, más los bloques visuales reutilizables."""

    def __init__(self, titulo_documento: str) -> None:
        super().__init__(format="A4")
        self.core_fonts_encoding = "windows-1252"
        self.titulo_documento = titulo_documento
        self.set_margins(14, 14, 14)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_title(titulo_documento)
        self.set_author("Jonathan Portilla Trainer")
        self.set_creator("Jonathan Portilla Trainer")

    # ------------------------------------------------------------------
    # Página
    # ------------------------------------------------------------------
    def header(self) -> None:
        # Fondo negro en TODAS las páginas, incluidas las que agrega el salto
        # automático a mitad de un texto largo.
        self.set_fill_color(*NEGRO)
        self.rect(0, 0, self.w, self.h, style="F")
        if self.page_no() == 1:
            return  # la portada la dibuja portada()
        self.image(str(LOGO_ICONO), x=self.l_margin, y=8, h=5)
        self.set_xy(self.l_margin, 8)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _safe(self.titulo_documento), align="R")
        self.barra_degradado(self.l_margin, 15.5, self.epw, 0.35)
        self.set_y(21)

    def footer(self) -> None:
        self.barra_degradado(self.l_margin, self.h - 13, self.epw, 0.35)
        self.set_xy(self.l_margin, self.h - 11.5)
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(*GRIS_OSCURO)
        self.cell(self.epw / 2, 5, "Jonathan Portilla Trainer")
        self.cell(self.epw / 2, 5, f"Página {self.page_no()} de {{nb}}", align="R")

    def asegurar_espacio(self, alto: float) -> None:
        if self.get_y() + alto > self.page_break_trigger:
            self.add_page()

    # ------------------------------------------------------------------
    # Primitivas de marca
    # ------------------------------------------------------------------
    # Los dos métodos de degradado van dentro de local_context() (q ... Q del
    # PDF) a propósito: al salir de use_pattern(), fpdf2 re-emite el color de
    # RELLENO usando el valor del color de LÍNEA, pero sin actualizar su
    # registro interno del relleno. Sin el q/Q, la siguiente tarjeta que
    # pidiera su color de fondo (igual al que fpdf2 cree que ya está puesto)
    # salía pintada con el color del borde, más clara de lo debido.
    def barra_degradado(self, x: float, y: float, w: float, h: float, radio: float = 0) -> None:
        with self.local_context():
            with self.use_pattern(LinearGradient(x, 0, x + w, 0, DEGRADADO)):
                self.rect(x, y, w, h, style="F", round_corners=radio > 0, corner_radius=radio)

    def texto_degradado(self, texto: str, size: float, alto: float, align: str = "L") -> None:
        """Texto con el mismo degradado de los títulos de la app (h1 de theme.py)."""
        self.set_font("Helvetica", "B", size)
        ancho = self.get_string_width(_safe(texto))
        x0 = self.get_x() if align == "L" else self.l_margin + self.epw - ancho
        with self.local_context():
            # cell() fuerza su propio color de texto cuando es distinto del de
            # relleno, y eso taparía el degradado: se igualan antes.
            self.set_text_color(0, 0, 0)
            self.set_fill_color(0, 0, 0)
            # extend_*: la última letra puede asomar un poco más allá del ancho
            # medido (la "g" de "Onboarding" quedaba cortada sin esto).
            degradado = LinearGradient(x0, 0, x0 + ancho, 0, DEGRADADO, extend_before=True, extend_after=True)
            with self.use_pattern(degradado):
                self.cell(0, alto, _safe(texto), align=align)
        self.ln(alto)

    def tarjeta(self, x: float, y: float, w: float, h: float, alerta: bool = False) -> None:
        self.set_fill_color(*(TARJETA_ALERTA if alerta else TARJETA))
        self.set_draw_color(*(BORDE_ALERTA if alerta else BORDE))
        self.set_line_width(0.25)
        self.rect(x, y, w, h, style="DF", round_corners=True, corner_radius=3)

    def alto_texto(self, texto: str, w: float, size: float, alto_linea: float, estilo: str = "") -> float:
        self.set_font("Helvetica", estilo, size)
        return self.multi_cell(w, alto_linea, _safe(texto), dry_run=True, output="HEIGHT")

    def escribir(
        self, texto: str, w: float, size: float = 9.5, alto_linea: float = 5,
        color: tuple[int, int, int] = TEXTO, estilo: str = "", align: str = "L",
    ) -> None:
        self.set_font("Helvetica", estilo, size)
        self.set_text_color(*color)
        self.multi_cell(w, alto_linea, _safe(texto), align=align, new_x="LEFT", new_y="NEXT")

    # ------------------------------------------------------------------
    # Bloques
    # ------------------------------------------------------------------
    def portada(self, etiqueta: str, titulo: str, nombre: str, detalles: Sequence[str]) -> None:
        """Encabezado de la primera página: logo, título en degradado, cliente y datos."""
        self.image(str(LOGO_COMPLETO), x=self.l_margin, y=13, w=50)
        self.set_xy(self.l_margin, 15)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*CIAN)
        self.set_char_spacing(1.2)
        self.cell(0, 5, _safe(etiqueta.upper()), align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_char_spacing(0)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*GRIS)
        self.cell(0, 5, f"Generado el {hoy_bogota().strftime('%d/%m/%Y')}", align="R", new_x="LMARGIN", new_y="NEXT")

        self.set_y(43)
        self.texto_degradado(titulo, 25, 12)
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(*TEXTO)
        self.cell(0, 8, _safe(nombre), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*GRIS)
        self.cell(0, 5, _safe("   •   ".join(d for d in detalles if d)), new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.barra_degradado(self.l_margin, self.get_y(), self.epw, 1.1, radio=0.55)
        self.ln(7)

    def seccion(self, titulo: str, subtitulo: str | None = None, reservar: float = 22) -> None:
        """
        `reservar`: espacio que debe quedar libre en la página para el título
        MÁS el primer bloque que introduce — si no cabe, salta de página
        antes, así el título nunca queda huérfano al pie separado de su
        contenido. Por defecto 22 mm; las secciones que abren con una
        gráfica alta le pasan el alto real de esa gráfica.
        """
        self.asegurar_espacio(reservar + (18 if subtitulo else 12))
        y = self.get_y()
        self.barra_degradado(self.l_margin, y + 0.8, 1.4, 6, radio=0.7)
        self.set_xy(self.l_margin + 4, y)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*TEXTO)
        self.cell(0, 7.5, _safe(titulo), new_x="LMARGIN", new_y="NEXT")
        if subtitulo:
            self.set_x(self.l_margin + 4)
            self.escribir(subtitulo, self.epw - 4, size=8.5, alto_linea=4.5, color=GRIS)
            self.set_x(self.l_margin)
        self.ln(2.5)

    def aviso(self, texto: str) -> None:
        """Recuadro rojo (patologías/lesiones reportadas)."""
        pad = 4
        w_texto = self.epw - 2 * pad - 6
        alto = self.alto_texto(texto, w_texto, 9.5, 5, "B") + 2 * pad
        self.asegurar_espacio(alto + 4)
        x, y = self.l_margin, self.get_y()
        self.tarjeta(x, y, self.epw, alto, alerta=True)
        self.set_fill_color(*ROJO)
        self.circle(x + pad + 1.6, y + pad + 2.5, 1.3, style="F")
        self.set_xy(x + pad + 6, y + pad)
        self.escribir(texto, w_texto, size=9.5, color=(254, 202, 202), estilo="B")
        self.set_y(y + alto + 5)

    def grilla_campos(self, campos: Sequence[tuple[str, Any, bool]], columnas: int = 2) -> None:
        """
        Tarjeta con pares etiqueta/valor en `columnas` columnas. Cada campo es
        (etiqueta, valor, alerta). Un campo con etiqueta que empieza con "*"
        ocupa el ancho completo (textos largos: equipamiento, patologías...).
        """
        pad, sep = 5, 6
        # Cada fila: (campos, ocupa_ancho_completo)
        filas: list[tuple[list[tuple[str, Any, bool]], bool]] = []
        actual: list[tuple[str, Any, bool]] = []
        for etiqueta, valor, alerta in campos:
            if etiqueta.startswith("*"):
                if actual:
                    filas.append((actual, False))
                    actual = []
                filas.append(([(etiqueta[1:], valor, alerta)], True))
            else:
                actual.append((etiqueta, valor, alerta))
                if len(actual) == columnas:
                    filas.append((actual, False))
                    actual = []
        if actual:
            filas.append((actual, False))

        ancho_util = self.epw - 2 * pad
        col_w = (ancho_util - sep * (columnas - 1)) / columnas

        def _alto_fila(fila: list[tuple[str, Any, bool]], completo: bool) -> float:
            w = ancho_util if completo else col_w
            return max(4.2 + self.alto_texto(_safe(v), w, 10, 5) for _, v, _ in fila) + 3.5

        altos = [_alto_fila(f, c) for f, c in filas]
        alto_total = sum(altos) + 2 * pad - 3.5

        if alto_total > self.page_break_trigger - self.t_margin - 10:
            # Más alto que una página entera (notas muy largas): sin tarjeta,
            # dejando que el texto corra y salte de página solo.
            for fila, _ in filas:
                for etiqueta, valor, alerta in fila:
                    self._campo(self.l_margin, self.epw, etiqueta, valor, alerta)
                    self.ln(2)
            return

        self.asegurar_espacio(alto_total + 4)
        x0, y0 = self.l_margin, self.get_y()
        self.tarjeta(x0, y0, self.epw, alto_total)
        y = y0 + pad
        for (fila, completo), alto in zip(filas, altos):
            for i, (etiqueta, valor, alerta) in enumerate(fila):
                w = ancho_util if completo else col_w
                x = x0 + pad + i * (col_w + sep)
                self.set_xy(x, y)
                self._campo(x, w, etiqueta, valor, alerta)
            y += alto
        self.set_y(y0 + alto_total + 5)

    def _campo(self, x: float, w: float, etiqueta: str, valor: Any, alerta: bool) -> None:
        self.set_x(x)
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*(ROJO if alerta else GRIS))
        self.set_char_spacing(0.6)
        self.cell(w, 4.2, _safe(etiqueta.upper()), new_x="LEFT", new_y="NEXT")
        self.set_char_spacing(0)
        self.set_x(x)
        self.escribir(valor, w, size=10, color=(254, 202, 202) if alerta else TEXTO)

    def vinetas(self, items: Sequence[str]) -> None:
        """Lista con viñetas en degradado dentro de una tarjeta (recuadro de resumen)."""
        items = [i for i in items if i]
        if not items:
            return
        pad = 5
        w_texto = self.epw - 2 * pad - 5
        altos = [self.alto_texto(i, w_texto, 9.5, 5) for i in items]
        alto = sum(altos) + 2.5 * (len(items) - 1) + 2 * pad
        self.asegurar_espacio(alto + 4)
        x0, y0 = self.l_margin, self.get_y()
        self.tarjeta(x0, y0, self.epw, alto)
        y = y0 + pad
        for item, a in zip(items, altos):
            self.barra_degradado(x0 + pad, y + 1.6, 1.8, 1.8, radio=0.9)
            self.set_xy(x0 + pad + 5, y)
            self.escribir(item, w_texto, size=9.5)
            y += a + 2.5
        self.set_y(y0 + alto + 5)

    def kpis(self, items: Sequence[tuple[str, str, str | None, tuple[int, int, int]]], por_fila: int = 3) -> None:
        """Tarjetas de métrica: (etiqueta, valor, detalle opcional, color del detalle)."""
        sep, alto = 4, 21
        w = (self.epw - sep * (por_fila - 1)) / por_fila
        for inicio in range(0, len(items), por_fila):
            self.asegurar_espacio(alto + 4)
            y = self.get_y()
            for i, (etiqueta, valor, detalle, color) in enumerate(items[inicio : inicio + por_fila]):
                x = self.l_margin + i * (w + sep)
                self.tarjeta(x, y, w, alto)
                self.set_xy(x + 4, y + 3.5)
                self.set_font("Helvetica", "B", 6.8)
                self.set_char_spacing(0.5)
                self.set_text_color(*GRIS)
                self.cell(w - 8, 4, _safe(etiqueta.upper()))
                self.set_char_spacing(0)
                self.set_xy(x + 4, y + 8.5)
                self.set_font("Helvetica", "B", 15)
                self.set_text_color(*TEXTO)
                self.cell(w - 8, 7, _safe(valor))
                if detalle:
                    self.set_xy(x + 4, y + 15.3)
                    self.set_font("Helvetica", "", 7.2)
                    self.set_text_color(*color)
                    self.cell(w - 8, 4, _safe(detalle))
            self.set_y(y + alto + sep)
        self.ln(1)

    def tabla(self, encabezados: Sequence[str], filas: Sequence[Sequence[Any]], anchos: Sequence[float]) -> None:
        """Tabla oscura simple (ancho total = epw; `anchos` son proporciones)."""
        total = sum(anchos)
        anchos_mm = [self.epw * a / total for a in anchos]
        pad = 2.5
        self.asegurar_espacio(18)
        x0 = self.l_margin

        y = self.get_y()
        self.set_fill_color(*BORDE)
        self.rect(x0, y, self.epw, 7, style="F", round_corners=("TOP_LEFT", "TOP_RIGHT"), corner_radius=2.5)
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*GRIS)
        x = x0
        for enc, w in zip(encabezados, anchos_mm):
            self.set_xy(x + pad, y + 1.5)
            self.cell(w - 2 * pad, 4, _safe(enc.upper()))
            x += w
        y += 7

        for n, fila in enumerate(filas):
            alto = max(self.alto_texto(_safe(v), w - 2 * pad, 8.5, 4.3) for v, w in zip(fila, anchos_mm)) + 3
            if y + alto > self.page_break_trigger:
                self.add_page()
                y = self.get_y()
            self.set_fill_color(*(TARJETA if n % 2 == 0 else (12, 12, 14)))
            self.rect(x0, y, self.epw, alto, style="F")
            x = x0
            for i, (valor, w) in enumerate(zip(fila, anchos_mm)):
                self.set_xy(x + pad, y + 1.5)
                self.escribir(valor, w - 2 * pad, size=8.5, alto_linea=4.3, estilo="B" if i == 0 else "")
                x += w
            y += alto
        self.set_y(y + 5)

    # ------------------------------------------------------------------
    # Gráficas
    # ------------------------------------------------------------------
    def grafico_lineas(
        self,
        titulo: str,
        series: Sequence[tuple[str, Sequence[tuple[date, float]]]],
        comentarios: Sequence[str] = (),
        escala_1_10: bool = False,
        unidad: str = "",
        alto_plot: float = 46,
        area: bool = False,
        ancho: float | None = None,
        x: float | None = None,
        alto_min: float = 0,
    ) -> float:
        """
        Tarjeta con título, leyenda, gráfico de líneas por fecha y debajo los
        comentarios de tendencia. `series` = [(nombre, [(fecha, valor), ...])].

        Con `x` dado se dibuja en esa columna y en el Y actual, sin mover el
        cursor ni revisar el salto de página (lo hace quien arma la fila —
        ver alto_grafico()); `alto_min` estira la tarjeta para que dos
        gráficas lado a lado queden de la misma altura. Devuelve el alto.
        """
        ancho = ancho or self.epw
        x0 = self.l_margin if x is None else x
        pad = 5
        series = [(n, sorted(p)) for n, p in series if p]
        comentarios = [c for c in comentarios if c]
        w_texto = ancho - 2 * pad
        alto = max(self.alto_grafico(ancho, comentarios, alto_plot), alto_min)

        if x is None:
            self.asegurar_espacio(alto + 4)
        y0 = self.get_y()
        self.tarjeta(x0, y0, ancho, alto)

        self.set_xy(x0 + pad, y0 + pad - 0.5)
        self.set_font("Helvetica", "B", 10.5)
        self.set_text_color(*TEXTO)
        self.cell(ancho / 2, 6, _safe(titulo))

        # Leyenda (solo si hay más de una serie), alineada a la derecha.
        if len(series) > 1:
            self.set_font("Helvetica", "", 7.2)
            items = [(n, COLORES_SERIES[i % len(COLORES_SERIES)]) for i, (n, _) in enumerate(series)]
            xl = x0 + ancho - pad
            for nombre, color in reversed(items):
                wn = self.get_string_width(_safe(nombre))
                xl -= wn
                self.set_text_color(*GRIS)
                self.set_xy(xl, y0 + pad)
                self.cell(wn, 5, _safe(nombre))
                self.set_fill_color(*color)
                self.circle(xl - 2.2, y0 + pad + 2.5, 1.1, style="F")
                xl -= 6.5

        if series:
            self._plot(x0 + pad, y0 + pad + 8, ancho - 2 * pad, alto_plot, series, escala_1_10, unidad, area)
        else:
            self.set_xy(x0 + pad, y0 + pad + 8 + alto_plot / 2 - 3)
            self.escribir("Sin datos suficientes para graficar.", w_texto, size=9, color=GRIS, align="C")

        y = y0 + pad + 7 + alto_plot + 3
        for c in comentarios:
            self.set_xy(x0 + pad, y)
            self.escribir(c, w_texto, size=8.5, alto_linea=4.5, color=(209, 213, 219))
            y += self.alto_texto(c, w_texto, 8.5, 4.5) + 1.5

        if x is None:
            self.set_y(y0 + alto + 5)
        return alto

    def alto_grafico(self, ancho: float, comentarios: Sequence[str], alto_plot: float) -> float:
        """Alto que ocupará grafico_lineas() con esos comentarios, sin dibujar nada."""
        pad = 5
        comentarios = [c for c in comentarios if c]
        alto_coment = sum(self.alto_texto(c, ancho - 2 * pad, 8.5, 4.5) + 1.5 for c in comentarios)
        return pad + 7 + alto_plot + 3 + alto_coment + pad - (1.5 if comentarios else 3)

    def _plot(
        self, x: float, y: float, w: float, h: float,
        series: Sequence[tuple[str, Sequence[tuple[date, float]]]],
        escala_1_10: bool, unidad: str, area: bool,
    ) -> None:
        todas = [p for _, pts in series for p in pts]
        valores = [v for _, v in todas]
        if escala_1_10:
            lo, hi, marcas = 0.5, 10.5, [2, 4, 6, 8, 10]
        else:
            lo, hi, marcas = _ticks_bonitos(min(valores), max(valores))

        fechas = sorted({f for f, _ in todas})
        f_min, f_max = fechas[0], fechas[-1]
        if f_min == f_max:
            f_min, f_max = f_min - timedelta(days=3), f_max + timedelta(days=3)
        rango_dias = (f_max - f_min).days

        margen_izq, margen_inf = 10, 6
        px, pw = x + margen_izq, w - margen_izq - 2
        py, ph = y, h - margen_inf

        def mx(f: date) -> float:
            return px + (f - f_min).days / rango_dias * pw

        def my(v: float) -> float:
            return py + ph - (v - lo) / (hi - lo) * ph

        # Grilla horizontal + etiquetas del eje Y
        self.set_draw_color(*GRILLA)
        self.set_line_width(0.2)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*GRIS_OSCURO)
        decimales = 0 if escala_1_10 or all(float(m).is_integer() for m in marcas) else 1
        for m in marcas:
            ym = my(m)
            self.line(px, ym, px + pw, ym)
            self.set_xy(x, ym - 2)
            self.cell(margen_izq - 1.5, 4, f"{m:.{decimales}f}{unidad}", align="R")

        # Etiquetas del eje X: hasta 6 fechas repartidas entre las que hay datos
        n_etiquetas = min(6, len(fechas))
        idx = sorted({round(i * (len(fechas) - 1) / max(n_etiquetas - 1, 1)) for i in range(n_etiquetas)})
        formato = "%m/%y" if rango_dias > 330 else "%d/%m"
        for i in idx:
            f = fechas[i]
            self.set_xy(mx(f) - 8, py + ph + 1.2)
            self.cell(16, 4, f.strftime(formato), align="C")

        radio = 0.85 if len(fechas) <= 30 else (0.55 if len(fechas) <= 80 else 0)
        for n, (_, pts) in enumerate(series):
            color = COLORES_SERIES[n % len(COLORES_SERIES)]
            puntos = [(mx(f), my(v)) for f, v in pts]
            if area and len(puntos) > 1:
                with self.local_context(fill_opacity=0.13):
                    self.set_fill_color(*color)
                    self.polygon(puntos + [(puntos[-1][0], py + ph), (puntos[0][0], py + ph)], style="F")
            self.set_draw_color(*color)
            self.set_line_width(0.55)
            if len(puntos) > 1:
                self.polyline(puntos)
            if radio or len(puntos) == 1:
                self.set_fill_color(*color)
                for px_, py_ in puntos:
                    self.circle(px_, py_, radio or 0.85, style="F")
