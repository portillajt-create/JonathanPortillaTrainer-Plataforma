"""
Helpers de acceso a datos compartidos entre módulos (a partir del Paso 2).

Centraliza las consultas a Supabase que usa más de un módulo (lista de
clientes para selectores, datos de suscripción, datos de onboarding), para
no repetir la misma lógica en admin_clientes.py, onboarding.py y app.py.
"""

from __future__ import annotations

from typing import Any

from utils.supabase_client import get_supabase_client


def admin_eliminar_cliente(cliente_id: str) -> None:
    """
    Elimina por completo la cuenta de un cliente (auth.users + todo lo que
    cuelga de él en cascada) vía la función SQL "admin_delete_cliente",
    que valida server-side que quien llama sea admin. Ver sql/001_schema_roles_rls.sql.
    """
    supabase = get_supabase_client()
    supabase.rpc("admin_delete_cliente", {"target_id": cliente_id}).execute()


def list_clientes(rol: str | None = "cliente") -> list[dict[str, Any]]:
    """Lista clientes (por defecto solo rol='cliente') ordenados por nombre."""
    supabase = get_supabase_client()
    query = supabase.table("clientes").select("id, email, nombre_completo, rol, correo_confirmado, created_at")
    if rol:
        query = query.eq("rol", rol)
    resp = query.order("nombre_completo").execute()
    return resp.data or []


def get_cliente(cliente_id: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    resp = supabase.table("clientes").select("*").eq("id", cliente_id).maybe_single().execute()
    return resp.data if resp else None


def update_cliente_hevy_url(cliente_id: str, hevy_perfil_url: str) -> None:
    supabase = get_supabase_client()
    supabase.table("clientes").update({"hevy_perfil_url": hevy_perfil_url}).eq("id", cliente_id).execute()


def list_clientes_con_suscripcion() -> list[dict[str, Any]]:
    """
    Lista todos los clientes con los datos de su suscripción (si existe),
    combinando public.clientes con la vista public.vista_suscripciones.

    La vista solo contiene filas de clientes que YA tienen una suscripción
    creada, así que los clientes nuevos (sin suscripción todavía) aparecen
    igual en el resultado con estado="Sin suscripción".
    """
    supabase = get_supabase_client()
    resp = (
        supabase.table("vista_suscripciones")
        .select("cliente_id, tipo_plan, estado, fecha_ultimo_pago, fecha_vencimiento, dias_restantes, por_vencer, vencida")
        .execute()
    )
    suscripciones_por_cliente = {fila["cliente_id"]: fila for fila in (resp.data or [])}

    resultado = []
    for cliente in list_clientes(rol="cliente"):
        suscripcion = suscripciones_por_cliente.get(cliente["id"], {})
        resultado.append(
            {
                "cliente_id": cliente["id"],
                "nombre_completo": cliente["nombre_completo"],
                "email": cliente["email"],
                "correo_confirmado": bool(cliente.get("correo_confirmado")),
                "tipo_plan": suscripcion.get("tipo_plan"),
                "estado": suscripcion.get("estado", "Sin suscripción"),
                "fecha_ultimo_pago": suscripcion.get("fecha_ultimo_pago"),
                "fecha_vencimiento": suscripcion.get("fecha_vencimiento"),
                "dias_restantes": suscripcion.get("dias_restantes"),
                "por_vencer": bool(suscripcion.get("por_vencer")),
                "vencida": bool(suscripcion.get("vencida")),
            }
        )
    return resultado


def get_suscripcion_vista(cliente_id: str) -> dict[str, Any] | None:
    """Suscripción de UN cliente con los campos calculados (dias_restantes, vencida, por_vencer)."""
    supabase = get_supabase_client()
    resp = (
        supabase.table("vista_suscripciones")
        .select("*")
        .eq("cliente_id", cliente_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


def upsert_suscripcion(cliente_id: str, **campos: Any) -> None:
    supabase = get_supabase_client()
    payload = {"cliente_id": cliente_id, **campos}
    supabase.table("suscripciones").upsert(payload, on_conflict="cliente_id").execute()


def get_onboarding(cliente_id: str) -> dict[str, Any] | None:
    supabase = get_supabase_client()
    resp = (
        supabase.table("onboarding")
        .select("*")
        .eq("cliente_id", cliente_id)
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


def upsert_onboarding(cliente_id: str, **campos: Any) -> None:
    supabase = get_supabase_client()
    payload = {"cliente_id": cliente_id, **campos}
    supabase.table("onboarding").upsert(payload, on_conflict="cliente_id").execute()


def get_dieta_activa(cliente_id: str) -> dict[str, Any] | None:
    """
    Trae el plan nutricional vigente del cliente (activa=true).

    "dietas" no tiene unique(cliente_id) a propósito: cada vez que el
    admin guarda un plan nuevo se desactiva el anterior y se inserta uno
    nuevo, conservando así un historial de planes por cliente.
    """
    supabase = get_supabase_client()
    resp = (
        supabase.table("dietas")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("activa", True)
        .order("fecha_actualizacion", desc=True)
        .limit(1)
        .execute()
    )
    filas = resp.data or []
    return filas[0] if filas else None


def guardar_dieta(cliente_id: str, actualizado_por: str, **campos: Any) -> None:
    """Desactiva el/los plan(es) vigente(s) del cliente e inserta el nuevo como activo."""
    supabase = get_supabase_client()
    supabase.table("dietas").update({"activa": False}).eq("cliente_id", cliente_id).eq("activa", True).execute()
    payload = {"cliente_id": cliente_id, "actualizado_por": actualizado_por, "activa": True, **campos}
    supabase.table("dietas").insert(payload).execute()


def get_rutina_activa(cliente_id: str) -> dict[str, Any] | None:
    """
    Trae la rutina vigente del cliente (activa=true), igual que "dietas":
    sin unique(cliente_id) a propósito, para conservar historial de rutinas
    anteriores cuando el admin asigna una nueva.
    """
    supabase = get_supabase_client()
    resp = (
        supabase.table("rutinas")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("activa", True)
        .order("fecha_asignacion", desc=True)
        .limit(1)
        .execute()
    )
    filas = resp.data or []
    return filas[0] if filas else None


def guardar_rutina(cliente_id: str, creado_por: str, **campos: Any) -> None:
    """Desactiva la rutina vigente del cliente e inserta la nueva como activa."""
    supabase = get_supabase_client()
    supabase.table("rutinas").update({"activa": False}).eq("cliente_id", cliente_id).eq("activa", True).execute()
    payload = {"cliente_id": cliente_id, "creado_por": creado_por, "activa": True, **campos}
    supabase.table("rutinas").insert(payload).execute()


def list_checkins(cliente_id: str) -> list[dict[str, Any]]:
    """Historial de check-ins semanales del cliente, ordenado cronológicamente."""
    supabase = get_supabase_client()
    resp = (
        supabase.table("checkin_semanal")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("semana_fecha")
        .execute()
    )
    return resp.data or []


def get_checkin_semana(cliente_id: str, semana_fecha) -> dict[str, Any] | None:
    """Check-in de una semana puntual (para precargar el formulario si ya se envió)."""
    supabase = get_supabase_client()
    resp = (
        supabase.table("checkin_semanal")
        .select("*")
        .eq("cliente_id", cliente_id)
        .eq("semana_fecha", semana_fecha.isoformat())
        .maybe_single()
        .execute()
    )
    return resp.data if resp else None


def upsert_checkin(cliente_id: str, **campos: Any) -> None:
    """Un check-in por semana: reenviar el formulario la misma semana actualiza en vez de duplicar."""
    supabase = get_supabase_client()
    payload = {"cliente_id": cliente_id, **campos}
    supabase.table("checkin_semanal").upsert(payload, on_conflict="cliente_id,semana_fecha").execute()


def list_notificaciones(cliente_id: str) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    resp = (
        supabase.table("notificaciones")
        .select("*")
        .eq("cliente_id", cliente_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


def marcar_notificacion_leida(notificacion_id: str) -> None:
    supabase = get_supabase_client()
    supabase.table("notificaciones").update({"leida": True}).eq("id", notificacion_id).execute()


def marcar_todas_notificaciones_leidas(cliente_id: str) -> None:
    supabase = get_supabase_client()
    supabase.table("notificaciones").update({"leida": True}).eq("cliente_id", cliente_id).eq("leida", False).execute()


def descartar_alerta(cliente_id: str, tipo: str, semana_referencia: str, descartada_por: str | None) -> None:
    """Oculta una alerta calculada (sin notificar al cliente), identificada por la semana que la disparó."""
    supabase = get_supabase_client()
    payload = {
        "cliente_id": cliente_id,
        "tipo": tipo,
        "semana_referencia": semana_referencia,
        "descartada_por": descartada_por,
    }
    supabase.table("alertas_descartadas").upsert(payload, on_conflict="cliente_id,tipo,semana_referencia").execute()


def guardar_historial_entrenamientos(cliente_id: str, filas: list[dict[str, Any]]) -> int:
    """
    Upsert masivo del historial de entrenamientos importado de Hevy (ver
    utils/hevy_import.py). Upsert por (cliente_id, fecha, ejercicio_nombre)
    — el mismo que la unique constraint de la tabla — así reimportar el
    mismo CSV (o uno más reciente que se solapa en fechas) actualiza en
    vez de duplicar. Se manda en lotes: PostgREST tiene un límite práctico
    de tamaño de payload por request y esto puede ser miles de filas.
    """
    if not filas:
        return 0
    supabase = get_supabase_client()
    filas_con_cliente = [{**fila, "cliente_id": cliente_id} for fila in filas]
    TAMANO_LOTE = 500
    total = 0
    for i in range(0, len(filas_con_cliente), TAMANO_LOTE):
        lote = filas_con_cliente[i : i + TAMANO_LOTE]
        supabase.table("historial_entrenamientos").upsert(
            lote, on_conflict="cliente_id,fecha,ejercicio_nombre"
        ).execute()
        total += len(lote)
    return total


def list_historial_entrenamientos(cliente_id: str) -> list[dict[str, Any]]:
    """
    Historial de entrenamientos reales del cliente (una fila por día+ejercicio),
    ordenado por fecha.

    Se pagina en bloques de 1000: PostgREST (Supabase) limita cada request a
    1000 filas por defecto, sin avisar — con varios años de historial real
    importado (miles de filas), una sola llamada sin paginar devolvía
    solo las 1000 filas más antiguas y las gráficas de progreso se veían
    "cortadas" mucho antes de la fecha real más reciente.
    """
    supabase = get_supabase_client()
    TAMANO_PAGINA = 1000
    filas: list[dict[str, Any]] = []
    inicio = 0
    while True:
        resp = (
            supabase.table("historial_entrenamientos")
            .select("*")
            .eq("cliente_id", cliente_id)
            .order("fecha")
            .range(inicio, inicio + TAMANO_PAGINA - 1)
            .execute()
        )
        pagina = resp.data or []
        filas.extend(pagina)
        if len(pagina) < TAMANO_PAGINA:
            break
        inicio += TAMANO_PAGINA
    return filas


def list_alertas_descartadas(tipo: str) -> set[tuple[str, str]]:
    supabase = get_supabase_client()
    resp = supabase.table("alertas_descartadas").select("cliente_id, semana_referencia").eq("tipo", tipo).execute()
    return {(fila["cliente_id"], fila["semana_referencia"]) for fila in (resp.data or [])}
