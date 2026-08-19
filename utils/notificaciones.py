"""
Centro de notificaciones (in-app + correo) — Paso 3.

Cualquier módulo que necesite avisarle algo a un cliente (dieta
actualizada, rutina actualizada, y más adelante las alertas automáticas
de estancamiento/deload/vencimiento de los Pasos 5 y 6) pasa por
`crear_notificacion`: siempre crea el registro in-app en `notificaciones`
y, si hay credenciales SMTP configuradas en .env, intenta además el envío
de correo. Si no hay SMTP configurado, la notificación in-app se crea
igual y el correo simplemente se omite (email_enviado queda en False).
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText

import streamlit as st

from config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from utils.queries import get_cliente
from utils.supabase_client import get_supabase_client


def crear_notificacion(cliente_id: str, tipo: str, titulo: str, mensaje: str, creado_por: str | None) -> None:
    email_enviado = _intentar_enviar_email(cliente_id, titulo, mensaje)

    supabase = get_supabase_client()
    supabase.table("notificaciones").insert(
        {
            "cliente_id": cliente_id,
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "email_enviado": email_enviado,
            "creado_por": creado_por,
        }
    ).execute()


def _intentar_enviar_email(cliente_id: str, titulo: str, mensaje: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD):
        return False

    cliente = get_cliente(cliente_id)
    destinatario = cliente.get("email") if cliente else None
    if not destinatario:
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
        st.warning(f"La notificación in-app se guardó, pero el correo no pudo enviarse: {exc}")
        return False
