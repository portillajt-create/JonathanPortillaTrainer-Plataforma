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

from config import ADMIN_NOTIFICATION_EMAIL, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER
from utils.queries import get_cliente
from utils.supabase_client import get_supabase_client


def crear_notificacion(cliente_id: str, tipo: str, titulo: str, mensaje: str, creado_por: str | None) -> None:
    cliente = get_cliente(cliente_id)
    destinatario = cliente.get("email") if cliente else None
    email_enviado = _enviar_email(destinatario, titulo, mensaje) if destinatario else False

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


def notificar_admin_nuevo_cliente(nombre_completo: str, email: str) -> None:
    """
    Avisa por correo al entrenador cuando un cliente nuevo se autorregistra.
    No pasa por la tabla "notificaciones" (esa es solo para avisos admin -> cliente);
    esto es un correo directo, sin registro in-app ni pantalla que lo muestre.

    mostrar_error=False: este envío se dispara desde la pantalla PÚBLICA de
    registro (cualquier visitante anónimo la alcanza). Si falla, no debe
    mostrarle a ese visitante el detalle crudo del error SMTP — eso filtraría
    el correo del entrenador y detalles internos de su configuración de correo.
    Es un aviso "mejor esfuerzo": el registro ya se completó igual.
    """
    _enviar_email(
        ADMIN_NOTIFICATION_EMAIL,
        "Nuevo cliente registrado en tu plataforma",
        f"{nombre_completo or 'Un nuevo usuario'} ({email}) acaba de crear una cuenta en "
        "Jonathan Portilla Trainer. Actívale la suscripción desde 'Gestión de Clientes' cuando quieras.",
        mostrar_error=False,
    )


def _enviar_email(destinatario: str, titulo: str, mensaje: str, mostrar_error: bool = True) -> bool:
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
        if mostrar_error:
            st.warning(f"El correo a {destinatario} no pudo enviarse: {exc}")
        return False
