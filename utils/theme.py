"""
Identidad visual: CSS que le da a los componentes nativos de Streamlit
(contenedores con borde, métricas, expanders, botones) el look de tarjeta
elevada con esquinas redondeadas y sombra que se ve en la guía de marca,
por encima de lo que el theming nativo de .streamlit/config.toml ya cubre
(colores base). Se inyecta una sola vez desde app.py.
"""

CSS = """
<style>
/* Contenedores con borde (st.container(border=True)): tarjeta elevada */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    background: linear-gradient(180deg, rgba(255,255,255,0.035), rgba(255,255,255,0));
    box-shadow: 0 10px 28px rgba(0,0,0,0.45);
}

/* Expanders (Gestión de Clientes, Mis Notificaciones, días de Entrenamiento): mismo tratamiento */
[data-testid="stExpander"] {
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    overflow: hidden;
    box-shadow: 0 6px 18px rgba(0,0,0,0.35);
}
[data-testid="stExpander"] summary {
    border-radius: 14px !important;
}

/* Métricas (st.metric): tarjeta compacta en vez de texto plano.
   El valor por defecto de Streamlit es grande y no hace wrap, así que
   textos largos ("Pérdida de grasa") se cortaban con "...". Achicamos la
   fuente y permitimos que baje de línea en vez de truncar. */
[data-testid="stMetric"] {
    background: #101012;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 14px 16px;
}
[data-testid="stMetricValue"] {
    font-size: 1.3rem !important;
    white-space: normal !important;
    overflow-wrap: break-word !important;
    line-height: 1.25 !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.82rem !important;
}

/* Botones: esquinas redondeadas + leve elevación al pasar el mouse */
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
    border-radius: 10px !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
}
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.5);
    filter: brightness(1.12);
}

/* Botones type="primary": mismo degradado cian-azul de la landing page,
   para que la acción principal de cada pantalla se sienta parte de la
   misma identidad. Texto oscuro porque el degradado es claro.
   Usamos [kind^="primary"] (empieza con) en vez de [kind="primary"]
   (igual exacto) porque los botones dentro de un st.form usan
   kind="primaryFormSubmit", no "primary" a secas. */
.stButton > button[kind^="primary"],
.stFormSubmitButton > button[kind^="primary"],
.stDownloadButton > button[kind^="primary"] {
    background: linear-gradient(120deg, #5EEAD4, #3B82F6) !important;
    border: none !important;
    color: #04110F !important;
}

/* Alertas/notificaciones (st.success/info/warning/error): esquinas redondeadas */
[data-testid="stAlertContainer"] {
    border-radius: 12px !important;
}

/* Sidebar: separación sutil del contenido principal + aire alrededor del logo */
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebarHeader"] {
    padding: 20px 18px 6px 18px;
}

/* Inputs de texto/número/área: esquinas redondeadas consistentes */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input {
    border-radius: 10px !important;
}
</style>
"""


# En móvil, seleccionar una opción del menú lateral (streamlit_option_menu)
# no cierra el sidebar solo — es un comportamiento nativo de Streamlit, no
# de nuestro código. En vez de depender del mensaje interno que emite el
# componente al seleccionar una opción (frágil: cambia según la versión de
# streamlit-option-menu y no se pudo confirmar de forma fiable en
# producción), observamos directamente el contenedor de contenido principal
# (stMain): cualquier navegación de página lo muta. Si en ese momento la
# pantalla es angosta y el sidebar sigue abierto, simulamos el clic en el
# botón nativo de colapsar. Un <script> inyectado con st.markdown no se
# ejecuta (los navegadores lo ignoran si se inserta vía innerHTML), así que
# usamos st.components.v1.html (un iframe) y desde ahí enganchamos todo al
# window.parent real, que es mismo origen.
_SIDEBAR_AUTOCOLLAPSE_JS = """
<script>
(function () {
    var top = window.parent;
    if (top.__jpAutoCollapseSidebarInit) return;
    top.__jpAutoCollapseSidebarInit = true;

    function maybeCollapse() {
        if (top.innerWidth >= 768) return;
        var sidebar = top.document.querySelector('[data-testid="stSidebar"]');
        if (!sidebar || sidebar.getAttribute("aria-expanded") !== "true") return;
        var collapseBtn = top.document.querySelector('[data-testid="stSidebarCollapseButton"] button');
        if (collapseBtn) collapseBtn.click();
    }

    function attachObserver() {
        var main = top.document.querySelector('[data-testid="stMain"]');
        if (!main) {
            setTimeout(attachObserver, 500);
            return;
        }
        var lastRun = 0;
        new top.MutationObserver(function () {
            var now = Date.now();
            if (now - lastRun < 200) return;
            lastRun = now;
            maybeCollapse();
        }).observe(main, {childList: true, subtree: true});
    }
    attachObserver();
})();
</script>
"""


def inject() -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    st.markdown(CSS, unsafe_allow_html=True)
    components.html(_SIDEBAR_AUTOCOLLAPSE_JS, height=0)


def render_perfil_sidebar(nombre: str, rol: str) -> None:
    """
    Tarjeta de perfil del sidebar (avatar con iniciales + nombre + badge de
    rol), en reemplazo de st.success()/st.info() — esas cajas usan el verde/
    azul semántico de Streamlit sin importar el tema, así que no seguían la
    paleta negro/gris/blanco pedida.
    """
    import html as _html

    import streamlit as st

    nombre_seguro = _html.escape(nombre)
    iniciales = _html.escape(_iniciales(nombre))
    es_admin = rol.strip().lower().startswith("admin")
    badge_bg = "linear-gradient(120deg, #5EEAD4, #3B82F6)" if es_admin else "#2A2A2E"
    badge_color = "#04110F" if es_admin else "#E6E6E6"
    etiqueta = "ADMINISTRADOR" if es_admin else "ASESORADO"

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;
            background:#141416;border:1px solid rgba(255,255,255,0.08);
            border-radius:14px;padding:14px 16px;margin-bottom:16px;
            box-shadow:0 8px 20px rgba(0,0,0,0.35);">
          <div style="width:42px;height:42px;min-width:42px;border-radius:50%;
              background:#232326;border:1px solid rgba(255,255,255,0.12);
              display:flex;align-items:center;justify-content:center;
              font-size:15px;font-weight:700;color:#FFFFFF;">{iniciales}</div>
          <div style="min-width:0;">
            <div style="color:#FFFFFF;font-weight:600;font-size:14.5px;
                line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{nombre_seguro}</div>
            <span style="display:inline-block;margin-top:5px;padding:2px 10px;
                border-radius:999px;font-size:10.5px;font-weight:700;letter-spacing:.04em;
                background:{badge_bg};color:{badge_color};">{etiqueta}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _iniciales(nombre: str) -> str:
    partes = nombre.strip().split()
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()


# Colores para gráficas Plotly sobre el fondo negro de la app. Plotly no
# hereda el theming de Streamlit, así que sin esto usa su gris oscuro por
# defecto para textos/ejes — prácticamente invisible sobre negro.
PLOTLY_FONT_COLOR = "#F2F2F2"
PLOTLY_GRID_COLOR = "rgba(255,255,255,0.10)"


def estilizar_grafico(fig):
    """Aplica fondo transparente + texto/ejes/leyenda/hover legibles en tema oscuro."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=PLOTLY_FONT_COLOR),
        legend=dict(font=dict(color=PLOTLY_FONT_COLOR)),
        hoverlabel=dict(bgcolor="#1A1A1C", font_color="#FFFFFF", bordercolor="rgba(255,255,255,0.15)"),
    )
    fig.update_xaxes(color=PLOTLY_FONT_COLOR, gridcolor=PLOTLY_GRID_COLOR, zerolinecolor=PLOTLY_GRID_COLOR)
    fig.update_yaxes(color=PLOTLY_FONT_COLOR, gridcolor=PLOTLY_GRID_COLOR, zerolinecolor=PLOTLY_GRID_COLOR)
    return fig


# Estilos para streamlit_option_menu (menú lateral con iconos): pastillas
# redondeadas sobre el fondo negro, resaltando la opción activa con un gris
# más claro en vez de invertir a blanco (así el icono se mantiene legible
# tanto en estado normal como seleccionado).
MENU_STYLES = {
    "container": {"padding": "0!important", "background-color": "transparent"},
    "icon": {"color": "#CFCFCF", "font-size": "16px"},
    "nav-link": {
        "font-size": "14px",
        "text-align": "left",
        "margin": "3px 0",
        "padding": "10px 14px",
        "border-radius": "10px",
        "color": "#D6D6D6",
        "background-color": "#131315",
        "--hover-color": "#1c1c1f",
    },
    "nav-link-selected": {
        "background": "linear-gradient(120deg, rgba(94,234,212,0.16), rgba(59,130,246,0.16))",
        "border": "1px solid rgba(94,234,212,0.35)",
        "color": "#FFFFFF",
        "font-weight": "600",
    },
}
