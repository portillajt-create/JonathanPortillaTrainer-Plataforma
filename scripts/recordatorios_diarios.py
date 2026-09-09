"""
Cron de recordatorios automáticos — corre FUERA de la app, disparado por
GitHub Actions (.github/workflows/recordatorios.yml) una vez al día.
No importa Streamlit ni ningún módulo de la app que dependa de sesión
(utils/supabase_client.py, config.py) — es un script standalone.

⚠️ Usa la clave service_role de Supabase (nunca la anon key), que ignora
RLS por diseño. Por eso este script NUNCA debe ejecutarse desde la app ni
desde el navegador de nadie — solo desde este entorno de servidor
controlado (GitHub Actions), con la clave guardada como GitHub Secret,
jamás en el repo. Es el mismo patrón de "backend seguro" que se descartó
para el scraper de Hevy (Paso 5) pero que aquí sí aplica correctamente:
GitHub Actions no es público como el navegador de un cliente.

Reemplaza el modelo anterior "on visit" de dos avisos manuales (decisión
del usuario, 2026-09-09):
  - Check-in de la semana pasada faltante: antes solo se generaba cuando
    el cliente entraba a "Mis Notificaciones"; ahora corre solo, los
    lunes/miércoles/viernes — hasta 3 avisos por semana mientras la
    semana ya cerrada siga sin reportarse.
  - Suscripción por vencer: antes exigía que el admin entrara a Gestión
    de Clientes y le diera clic a "Recordar" cliente por cliente; ahora
    se envía sola, UNA ÚNICA VEZ por ciclo de vencimiento, el día en que
    quedan ≤2 días (mismo umbral que el badge de vista_suscripciones).

La ventana de la semana EN CURSO (habilitada desde el jueves) NO cambia:
este cron nunca avisa de eso, solo de la semana YA CERRADA — sigue siendo
una opción que el cliente usa por su cuenta si quiere adelantarla.

Se apoya en vista_suscripciones (no recalcula fechas a mano) para que el
badge "🟡 Por vencer" que ve el admin y el criterio de este cron sean
siempre la MISMA fuente de verdad, no dos cálculos que puedan divergir.
"""

from __future__ import annotations

import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402  (import tras el sys.path.insert)

from utils.formato import hoy_bogota  # noqa: E402
from utils.semanas_checkin import rango_semana, semana_a_reportar  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

# Mismas variables SMTP que ya usa la app (utils/notificaciones.py) — el
# cron NO reutiliza ese módulo directamente porque importa `streamlit`
# (config.py también), y este script no lo necesita.
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = os.environ.get("SMTP_PORT", "587")
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER

# weekday(): lunes=0 ... domingo=6. Decisión del usuario: check-in solo
# lunes/miércoles/viernes; vencimiento corre TODOS los días (para no
# depender de que el vencimiento caiga justo en uno de esos 3 días).
DIAS_CHECKIN = {0, 2, 4}

# Un cliente avisó (2026-09-09) que el correo solo traía el texto, sin forma
# de entrar directo a la plataforma a hacer lo que se le pide. Se agrega al
# final de cada mensaje; la mayoría de clientes de correo (Gmail, Outlook,
# Apple Mail...) auto-detectan la URL como link aunque el correo sea texto
# plano, sin necesidad de mandarlo como HTML.
URL_PLATAFORMA = "https://jonathanportillatrainer.streamlit.app"


def _enviar_email(destinatario: str | None, titulo: str, mensaje: str) -> bool:
    """Igual que utils/notificaciones.py:_enviar_email, sin depender de
    Streamlit — si algo falla, se imprime al log del Action en vez de
    st.warning(), y la notificación in-app se crea de todos modos."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and destinatario):
        return False
    try:
        email_msg = MIMEText(mensaje)
        email_msg["Subject"] = titulo
        email_msg["From"] = SMTP_FROM
        email_msg["To"] = destinatario
        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(email_msg)
        return True
    except Exception as exc:
        print(f"  ! correo a {destinatario} no se pudo enviar: {exc}")
        return False


def _crear_notificacion(supabase, cliente_id: str, tipo: str, titulo: str, mensaje: str, email: str | None) -> None:
    """Igual que utils/notificaciones.py:crear_notificacion, pero con
    creado_por=None (nadie la dispara, es automática) e insertando directo
    en la tabla en vez de vía RPC — con service_role no hace falta rodear
    la policy de insert como sí hace falta cuando la dispara el cliente
    (ver crear_notificacion_sistema en el esquema SQL)."""
    email_enviado = _enviar_email(email, titulo, mensaje) if email else False
    supabase.table("notificaciones").insert(
        {
            "cliente_id": cliente_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "email_enviado": email_enviado,
            "creado_por": None,
        }
    ).execute()


def procesar_checkins_faltantes(supabase, clientes_por_id: dict[str, dict[str, Any]], suscripciones: list[dict]) -> None:
    if hoy_bogota().weekday() not in DIAS_CHECKIN:
        print("Hoy no es lunes/miércoles/viernes — se omite el recordatorio de check-in.")
        return

    semana = semana_a_reportar()
    if semana is None:
        print("Todavía no arranca el periodo de seguimiento — se omite el recordatorio de check-in.")
        return

    # Mismo criterio que determina si el cliente puede entrar a la app:
    # si no tiene acceso (inactivo/vencido), no tiene sentido pedirle un
    # check-in que no podría ni siquiera ver confirmado.
    activos = {s["cliente_id"] for s in suscripciones if s["estado"] == "Activo" and not s["vencida"]}

    resp = supabase.table("checkin_semanal").select("cliente_id").eq("semana_fecha", semana.isoformat()).execute()
    ya_reportaron = {c["cliente_id"] for c in (resp.data or [])}

    avisados = 0
    for cliente_id in activos - ya_reportaron:
        cliente = clientes_por_id.get(cliente_id)
        if not cliente or not cliente.get("email"):
            continue
        fecha_creacion = (cliente.get("created_at") or "")[:10]
        if fecha_creacion and date.fromisoformat(fecha_creacion) > semana:
            continue  # el cliente todavía no existía esa semana

        _crear_notificacion(
            supabase,
            cliente_id,
            "checkin_faltante",
            "Check-in semanal pendiente",
            (
                f"Todavía no reportaste tu check-in de la semana del {rango_semana(semana)}. "
                "Tienes hasta el domingo para completarlo en 'Check-in Semanal' y que tu "
                "entrenador pueda dar seguimiento a tu progreso.\n\n"
                f"Entra aquí: {URL_PLATAFORMA}"
            ),
            cliente.get("email"),
        )
        avisados += 1
    print(f"Check-in: {avisados} cliente(s) avisado(s) de la semana {semana.isoformat()}.")


def procesar_vencimientos(supabase, clientes_por_id: dict[str, dict[str, Any]], suscripciones: list[dict]) -> None:
    """Una sola vez por CICLO de vencimiento: antes de avisar, se revisa si
    ya existe una notificación de este tipo creada en o después de la
    fecha del último pago vigente — así, si el cliente renueva (cambia su
    fecha_ultimo_pago), un aviso viejo de un ciclo anterior no bloquea el
    aviso del ciclo nuevo."""
    candidatos = [s for s in suscripciones if s["estado"] == "Activo" and s["por_vencer"] and not s["vencida"]]

    avisados = 0
    for s in candidatos:
        cliente_id = s["cliente_id"]
        cliente = clientes_por_id.get(cliente_id)
        if not cliente or not cliente.get("email"):
            continue

        fecha_ultimo_pago = s.get("fecha_ultimo_pago") or "1900-01-01"
        resp = (
            supabase.table("notificaciones")
            .select("id")
            .eq("cliente_id", cliente_id)
            .eq("tipo", "alerta_vencimiento")
            .gte("created_at", f"{fecha_ultimo_pago}T00:00:00")
            .limit(1)
            .execute()
        )
        if resp.data:
            continue  # ya se avisó en este ciclo de vencimiento

        _crear_notificacion(
            supabase,
            cliente_id,
            "alerta_vencimiento",
            "Tu suscripción está por vencer",
            (
                "Tu plan de asesoría vence pronto. Contacta a tu entrenador para renovarlo y no "
                "perder acceso a tu dieta, rutina y seguimiento."
            ),
            cliente.get("email"),
        )
        avisados += 1
    print(f"Vencimiento: {avisados} cliente(s) avisado(s).")


def main() -> None:
    print(f"=== Recordatorios diarios — {datetime.now().isoformat()} (hoy Bogotá: {hoy_bogota().isoformat()}) ===")
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    resp = supabase.table("clientes").select("id, email, created_at, rol").eq("rol", "cliente").execute()
    clientes_por_id = {c["id"]: c for c in (resp.data or [])}
    print(f"{len(clientes_por_id)} cliente(s) en total.")

    resp = supabase.table("vista_suscripciones").select("*").execute()
    suscripciones = resp.data or []

    procesar_checkins_faltantes(supabase, clientes_por_id, suscripciones)
    procesar_vencimientos(supabase, clientes_por_id, suscripciones)
    print("=== Fin ===")


if __name__ == "__main__":
    main()
