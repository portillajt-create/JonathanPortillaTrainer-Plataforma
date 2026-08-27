-- =====================================================================
-- JONATHAN PORTILLA TRAINER — Dashboard de Asesorías
-- PASO 1: Esquema de base de datos, roles y Row Level Security (RLS)
-- Motor: Supabase (PostgreSQL) + Supabase Auth
-- =====================================================================
-- Cómo usarlo:
--   1. Abre tu proyecto en https://app.supabase.com
--   2. Ve a "SQL Editor" -> "New query"
--   3. Pega este archivo completo y dale "Run"
--   4. Sigue las instrucciones del "PASO MANUAL DE BOOTSTRAP" al final
--      para convertir tu propio usuario en Admin la primera vez.
-- =====================================================================

-- Extensión necesaria para generar UUIDs
create extension if not exists "pgcrypto";

-- =====================================================================
-- 1. TABLA: clientes
--    Extiende auth.users. Guarda el rol (admin/cliente) y datos básicos.
--    Un admin es simplemente un registro con rol = 'admin'; no hay una
--    tabla separada de "entrenadores" para mantener el modelo simple.
-- =====================================================================
create table if not exists public.clientes (
    id                uuid primary key references auth.users (id) on delete cascade,
    email             text not null,
    nombre_completo   text not null default '',
    rol               text not null default 'cliente' check (rol in ('admin', 'cliente')),
    hevy_perfil_url   text,                       -- se sincroniza también en onboarding
    correo_confirmado boolean not null default false,  -- se pone en true vía trigger cuando confirma el correo
    created_at        timestamptz not null default now()
);

comment on table public.clientes is 'Perfil de cada usuario (admin o cliente), 1:1 con auth.users';

-- =====================================================================
-- 2. TABLA: suscripciones
--    Estado comercial del cliente: plan, fechas, activo/inactivo.
--    Relación 1:1 con clientes (se actualiza in place; no guarda historial
--    de renovaciones en Paso 1).
-- =====================================================================
create table if not exists public.suscripciones (
    id                  uuid primary key default gen_random_uuid(),
    cliente_id          uuid not null unique references public.clientes (id) on delete cascade,
    tipo_plan           text check (tipo_plan in ('Mensual', 'Trimestral', 'Semestral', 'Personalizado')),
    estado              text not null default 'Activo' check (estado in ('Activo', 'Inactivo')),
    fecha_ultimo_pago   date,
    fecha_vencimiento   date,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

comment on table public.suscripciones is 'Estado del plan/suscripción de cada cliente, gestionado exclusivamente por el admin';

-- Vista de conveniencia: calcula días restantes y una bandera de alerta
-- (no se puede usar columna generada porque CURRENT_DATE no es inmutable)
create or replace view public.vista_suscripciones as
select
    s.*,
    c.nombre_completo,
    c.email,
    (s.fecha_vencimiento - current_date)                       as dias_restantes,
    (s.estado = 'Activo' and s.fecha_vencimiento is not null
        and s.fecha_vencimiento - current_date <= 5)            as por_vencer,
    (s.estado = 'Activo' and s.fecha_vencimiento is not null
        and s.fecha_vencimiento < current_date)                 as vencida
from public.suscripciones s
join public.clientes c on c.id = s.cliente_id;

-- =====================================================================
-- 3. TABLA: onboarding
--    Formulario de anamnesis inicial (una vez por cliente).
-- =====================================================================
create table if not exists public.onboarding (
    id                      uuid primary key default gen_random_uuid(),
    cliente_id              uuid not null unique references public.clientes (id) on delete cascade,
    fecha_nacimiento        date,
    sexo                    text check (sexo in ('Hombre', 'Mujer')),
    altura_cm               numeric,
    peso_kg                 numeric,    -- peso de referencia; el peso semanal real vive en checkin_semanal
    ocupacion               text,
    ciudad_pais             text,
    patologias              text,       -- texto libre / lista separada por comas
    lesiones                text,
    medicamentos            text,
    nivel_experiencia       text check (nivel_experiencia in ('Principiante', 'Intermedio', 'Avanzado')),
    disponibilidad_dias     int check (disponibilidad_dias between 0 and 7),
    equipamiento            text,       -- ej: "Gimnasio completo", "Mancuernas en casa"
    horas_sueno_promedio    numeric,
    nivel_estres_habitual   int check (nivel_estres_habitual between 1 and 10),
    comidas_dia             int,
    alergias_alimentarias   text,
    objetivo_principal      text check (objetivo_principal in
                                ('Fuerza', 'Hipertrofia', 'Pérdida de grasa', 'Recomposición', 'Salud general')),
    hevy_perfil_url         text,       -- https://hevy.com/user/USERNAME
    fecha_registro          timestamptz not null default now()
);

comment on table public.onboarding is 'Formulario de anamnesis inicial que llena el cliente al registrarse';

-- =====================================================================
-- 4. TABLA: checkin_semanal
--    Seguimiento subjetivo + peso corporal, llenado por el cliente cada semana.
-- =====================================================================
create table if not exists public.checkin_semanal (
    id                          uuid primary key default gen_random_uuid(),
    cliente_id                  uuid not null references public.clientes (id) on delete cascade,
    semana_fecha                date not null default current_date,
    adherencia_dieta            int check (adherencia_dieta between 1 and 10),
    adherencia_entrenamiento    int check (adherencia_entrenamiento between 1 and 10),
    calidad_sueno                int check (calidad_sueno between 1 and 10),
    nivel_estres                int check (nivel_estres between 1 and 10),
    fatiga                      int check (fatiga between 1 and 10),
    peso_corporal_kg            numeric,
    notas                       text,
    created_at                  timestamptz not null default now(),
    unique (cliente_id, semana_fecha)
);

comment on table public.checkin_semanal is 'Check-in semanal de adherencia, sueño, estrés, fatiga y peso corporal';

-- =====================================================================
-- 5. TABLA: dietas
--    Plan nutricional vigente por cliente (macros, calorías, tipo de dieta).
--    Gestionada exclusivamente por el admin.
-- =====================================================================
create table if not exists public.dietas (
    id                      uuid primary key default gen_random_uuid(),
    cliente_id              uuid not null references public.clientes (id) on delete cascade,
    tdee                    numeric,
    calorias_objetivo       numeric,
    proteinas_g             numeric,
    carbohidratos_g         numeric,
    grasas_g                numeric,
    tipo_dieta              text check (tipo_dieta in
                                ('Flexible', 'Ciclado de carbohidratos', 'Definición', 'Volumen', 'Mantenimiento')),
    plan_comidas            text,       -- menú de ejemplo (editable) generado a partir de los macros
    notas                   text,       -- notas adicionales libres del entrenador, aparte del menú
    sexo                    text check (sexo in ('Hombre', 'Mujer')),
    nivel_actividad         text,       -- clave de FACTORES_ACTIVIDAD en nutricion.py
    ajuste_pct              numeric,    -- % de ajuste sobre el TDEE usado
    proteina_g_kg           numeric,    -- g de proteína por kg de peso usado
    grasa_pct               numeric,    -- % de calorías de grasa usado
    activa                  boolean not null default true,
    actualizado_por         uuid references public.clientes (id) on delete set null,
    fecha_actualizacion     timestamptz not null default now()
);

comment on table public.dietas is 'Plan nutricional asignado por el entrenador; dispara notificación al guardar';

-- =====================================================================
-- 6. TABLA: rutinas
--    Bloques de entrenamiento asignados por el admin.
--    Los ejercicios de cada rutina se guardan como JSONB para no
--    multiplicar tablas: cada elemento = {dia, ejercicio, series,
--    repeticiones, rpe_rir, descanso_min, notas}.
-- =====================================================================
create table if not exists public.rutinas (
    id                  uuid primary key default gen_random_uuid(),
    cliente_id          uuid not null references public.clientes (id) on delete cascade,
    nombre_rutina       text not null,
    descripcion         text,
    bloques             jsonb not null default '[]'::jsonb,
    activa              boolean not null default true,
    creado_por          uuid references public.clientes (id) on delete set null,
    fecha_asignacion    timestamptz not null default now()
);

comment on table public.rutinas is 'Rutinas asignadas por el entrenador; "bloques" guarda ejercicios/series/reps/RPE en JSON';

-- =====================================================================
-- 7. TABLA: historial_entrenamientos
--    Datos REALES levantados por el cliente, obtenidos por scraping del
--    perfil público de Hevy (Paso 5). Es de solo lectura para el cliente;
--    el proceso de scraping corre en el backend con la service_role key,
--    que ignora RLS por diseño.
-- =====================================================================
create table if not exists public.historial_entrenamientos (
    id                  uuid primary key default gen_random_uuid(),
    cliente_id          uuid not null references public.clientes (id) on delete cascade,
    fecha               date not null,
    ejercicio_nombre    text not null,
    peso_kg             numeric,
    series              int,
    repeticiones        int,
    volumen_total       numeric,   -- peso_kg * series * repeticiones (calculado al insertar)
    fuente              text not null default 'hevy_scraping',
    created_at          timestamptz not null default now(),
    unique (cliente_id, fecha, ejercicio_nombre)
);

comment on table public.historial_entrenamientos is 'Entrenamientos reales extraídos del perfil público de Hevy';

-- =====================================================================
-- 8. TABLA: notificaciones
--    Centro de notificaciones in-app (+ correo) para el cliente.
-- =====================================================================
create table if not exists public.notificaciones (
    id              uuid primary key default gen_random_uuid(),
    cliente_id      uuid not null references public.clientes (id) on delete cascade,
    tipo            text not null check (tipo in
                        ('dieta_actualizada', 'rutina_actualizada', 'alerta_vencimiento',
                         'alerta_deload', 'alerta_estancamiento', 'alerta_adherencia_dieta',
                         'checkin_faltante', 'general')),
    titulo          text not null,
    mensaje         text not null,
    leida           boolean not null default false,
    email_enviado   boolean not null default false,
    creado_por      uuid references public.clientes (id) on delete set null,
    created_at      timestamptz not null default now()
);

comment on table public.notificaciones is 'Notificaciones in-app/email disparadas al cliente por acciones del admin o alertas automáticas';

-- =====================================================================
-- 9. TABLA: alertas_descartadas
--    Permite al admin descartar una alerta calculada (deload, adherencia a
--    la dieta, etc.) de la vista del Centro de Alertas SIN notificar al
--    cliente. Se identifica por (cliente_id, tipo, semana_referencia) — la
--    fecha de la semana más reciente que disparó la alerta — así que si la
--    misma condición vuelve a aparecer en una semana distinta, se muestra
--    de nuevo (descartar no es "silenciar para siempre").
-- =====================================================================
create table if not exists public.alertas_descartadas (
    id                  uuid primary key default gen_random_uuid(),
    cliente_id          uuid not null references public.clientes (id) on delete cascade,
    tipo                text not null,
    semana_referencia   date not null,
    descartada_por      uuid references public.clientes (id) on delete set null,
    descartada_en       timestamptz not null default now(),
    unique (cliente_id, tipo, semana_referencia)
);

comment on table public.alertas_descartadas is 'Alertas calculadas que el admin descartó de la vista, sin notificar al cliente';

-- =====================================================================
-- ÍNDICES (mejoran los filtros por cliente_id y fecha que usará el dashboard)
-- =====================================================================
create index if not exists idx_suscripciones_cliente on public.suscripciones (cliente_id);
create index if not exists idx_checkin_cliente_fecha on public.checkin_semanal (cliente_id, semana_fecha);
create index if not exists idx_dietas_cliente on public.dietas (cliente_id);
create index if not exists idx_rutinas_cliente on public.rutinas (cliente_id);
create index if not exists idx_historial_cliente_fecha on public.historial_entrenamientos (cliente_id, fecha);
create index if not exists idx_notificaciones_cliente on public.notificaciones (cliente_id, leida);

-- =====================================================================
-- TRIGGER: updated_at automático en suscripciones
-- =====================================================================
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_suscripciones_updated_at on public.suscripciones;
create trigger trg_suscripciones_updated_at
    before update on public.suscripciones
    for each row execute function public.set_updated_at();

-- =====================================================================
-- TRIGGER: auto-crear fila en "clientes" cuando alguien se registra en
-- Supabase Auth. Todo usuario nuevo entra como rol = 'cliente' por
-- defecto; el admin se promueve manualmente (ver bootstrap al final).
-- =====================================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.clientes (id, email, nombre_completo, rol)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'nombre_completo', ''),
        'cliente'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- =====================================================================
-- TRIGGER: marca clientes.correo_confirmado = true en el momento en que
-- Supabase confirma el correo del usuario (auth.users.email_confirmed_at
-- pasa de null a una fecha). Solo actúa en esa transición específica,
-- así que no hace nada en el resto de updates que Supabase hace sobre
-- auth.users (last_sign_in_at, etc.) — mismo patrón que handle_new_user().
-- =====================================================================
create or replace function public.sync_correo_confirmado()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.email_confirmed_at is not null and old.email_confirmed_at is null then
        update public.clientes set correo_confirmado = true where id = new.id;
    end if;
    return new;
end;
$$;

drop trigger if exists on_auth_user_confirmed on auth.users;
create trigger on_auth_user_confirmed
    after update on auth.users
    for each row execute function public.sync_correo_confirmado();

-- =====================================================================
-- FUNCIÓN HELPER PARA RLS: obtiene el rol del usuario autenticado.
-- Es "security definer" para poder leer la tabla "clientes" sin caer en
-- recursión infinita de políticas RLS al evaluarse a sí misma.
-- =====================================================================
create or replace function public.get_my_role()
returns text
language sql
security definer
stable
set search_path = public
as $$
    select rol from public.clientes where id = auth.uid();
$$;

create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
    select coalesce(public.get_my_role() = 'admin', false);
$$;

-- =====================================================================
-- TRIGGER DE SEGURIDAD: un cliente nunca puede auto-promoverse a admin
-- ni auto-reactivarse editando su propia fila de "clientes". También
-- blinda "correo_confirmado" para que no pueda falsear ese badge (aunque
-- no le daría acceso real, ya que Supabase Auth es quien controla el
-- login de verdad con auth.users.email_confirmed_at).
-- (La política RLS ya limita qué filas puede tocar; este trigger blinda
-- esas columnas incluso si en el futuro se relaja esa política).
--
-- La condición "auth.uid() is not null" es clave: solo aplica este blindaje
-- a peticiones que llegan autenticadas vía PostgREST con el JWT de un
-- usuario de la app (que es el único camino por el que alguien podría
-- intentar auto-promoverse). Las ejecuciones desde el SQL Editor de
-- Supabase, con la service_role key, o desde el trigger interno
-- sync_correo_confirmado (disparado por Supabase Auth, sin JWT de usuario)
-- no tienen auth.uid() y por lo tanto NO quedan bloqueadas; así el
-- bootstrap manual del primer Admin (ver instrucciones al final de este
-- archivo) sí puede cambiar el rol, y la confirmación real de correo sí
-- puede marcar el badge.
-- =====================================================================
create or replace function public.prevent_role_self_escalation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is not null and not public.is_admin() and new.rol is distinct from old.rol then
        new.rol := old.rol;
    end if;
    -- correo_confirmado es solo informativo para el admin (el bloqueo real de
    -- acceso lo hace Supabase Auth con auth.users.email_confirmed_at), pero
    -- igual se blinda para que un cliente no pueda falsear el badge llamando
    -- directo a la API; solo el trigger sync_correo_confirmado (o un admin)
    -- puede cambiarlo.
    if auth.uid() is not null and not public.is_admin() and new.correo_confirmado is distinct from old.correo_confirmado then
        new.correo_confirmado := old.correo_confirmado;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_prevent_role_escalation on public.clientes;
create trigger trg_prevent_role_escalation
    before update on public.clientes
    for each row execute function public.prevent_role_self_escalation();

-- =====================================================================
-- TRIGGER DE SEGURIDAD: la policy notificaciones_update deja actualizar
-- cualquier columna de una notificación propia (solo la app, a nivel de
-- UI, restringe eso a marcarla como leída). Un cliente con conocimientos
-- técnicos podría llamar directo a la API de Supabase y reescribir el
-- título/mensaje de su propia notificación. Este trigger blinda todas
-- las columnas salvo "leida" para peticiones no-admin, mismo patrón que
-- prevent_role_self_escalation.
-- =====================================================================
create or replace function public.prevent_notificacion_tamper()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is not null and not public.is_admin() then
        new.cliente_id := old.cliente_id;
        new.tipo := old.tipo;
        new.titulo := old.titulo;
        new.mensaje := old.mensaje;
        new.email_enviado := old.email_enviado;
        new.creado_por := old.creado_por;
        new.created_at := old.created_at;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_prevent_notificacion_tamper on public.notificaciones;
create trigger trg_prevent_notificacion_tamper
    before update on public.notificaciones
    for each row execute function public.prevent_notificacion_tamper();

-- =====================================================================
-- FUNCIÓN: admin_delete_cliente — permite al admin eliminar la cuenta
-- completa de un cliente (auth.users + todo lo que cuelga de él por
-- "on delete cascade") desde la app, sin exponer la service_role key.
-- La app solo tiene la clave "anon", que no puede borrar de auth.users
-- directamente; esta función corre con los privilegios de quien la creó
-- (security definer, mismo patrón que is_admin()/handle_new_user()) y
-- por eso sí puede. Bloquea a cualquiera que no sea admin autenticado, y
-- al propio admin borrarse a sí mismo por error.
-- =====================================================================
create or replace function public.admin_delete_cliente(target_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if auth.uid() is null or not public.is_admin() then
        raise exception 'No autorizado para eliminar clientes';
    end if;
    if target_id = auth.uid() then
        raise exception 'No puedes eliminar tu propia cuenta de administrador';
    end if;
    delete from auth.users where id = target_id;
end;
$$;

grant execute on function public.admin_delete_cliente(uuid) to authenticated;

-- =====================================================================
-- ROW LEVEL SECURITY (RLS)
-- Regla general en todas las tablas:
--   - Admin (is_admin() = true): acceso total (select/insert/update/delete)
--   - Cliente: solo puede ver/tocar sus propias filas (cliente_id = auth.uid())
--   - Tablas de "solo lectura para el cliente" (suscripciones, dietas,
--     rutinas, historial_entrenamientos) no tienen policy de insert/update/
--     delete para clientes: solo el admin (o el backend con service_role
--     para el scraping de Hevy) puede escribir en ellas.
-- =====================================================================

alter table public.clientes                 enable row level security;
alter table public.suscripciones            enable row level security;
alter table public.onboarding                enable row level security;
alter table public.checkin_semanal          enable row level security;
alter table public.dietas                   enable row level security;
alter table public.rutinas                  enable row level security;
alter table public.historial_entrenamientos enable row level security;
alter table public.notificaciones           enable row level security;

-- ---------- clientes ----------
drop policy if exists clientes_select on public.clientes;
create policy clientes_select on public.clientes
    for select using (id = auth.uid() or public.is_admin());

drop policy if exists clientes_update on public.clientes;
create policy clientes_update on public.clientes
    for update using (id = auth.uid() or public.is_admin());
    -- La columna "rol" queda blindada por el trigger prevent_role_self_escalation

drop policy if exists clientes_admin_delete on public.clientes;
create policy clientes_admin_delete on public.clientes
    for delete using (public.is_admin());

-- Nota: el INSERT en "clientes" ocurre únicamente vía el trigger
-- handle_new_user() (security definer), por eso no se necesita una
-- policy de INSERT para usuarios normales.

-- ---------- suscripciones (solo admin escribe, cliente solo lee la suya) ----------
drop policy if exists suscripciones_select on public.suscripciones;
create policy suscripciones_select on public.suscripciones
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists suscripciones_admin_write on public.suscripciones;
create policy suscripciones_admin_write on public.suscripciones
    for all using (public.is_admin()) with check (public.is_admin());

-- ---------- onboarding (cliente llena/edita la suya; admin todo) ----------
drop policy if exists onboarding_select on public.onboarding;
create policy onboarding_select on public.onboarding
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists onboarding_insert on public.onboarding;
create policy onboarding_insert on public.onboarding
    for insert with check (cliente_id = auth.uid() or public.is_admin());

drop policy if exists onboarding_update on public.onboarding;
create policy onboarding_update on public.onboarding
    for update using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists onboarding_admin_delete on public.onboarding;
create policy onboarding_admin_delete on public.onboarding
    for delete using (public.is_admin());

-- ---------- checkin_semanal (cliente crea/lee el suyo; admin todo) ----------
drop policy if exists checkin_select on public.checkin_semanal;
create policy checkin_select on public.checkin_semanal
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists checkin_insert on public.checkin_semanal;
create policy checkin_insert on public.checkin_semanal
    for insert with check (cliente_id = auth.uid() or public.is_admin());

drop policy if exists checkin_update on public.checkin_semanal;
create policy checkin_update on public.checkin_semanal
    for update using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists checkin_admin_delete on public.checkin_semanal;
create policy checkin_admin_delete on public.checkin_semanal
    for delete using (public.is_admin());

-- ---------- dietas (solo admin escribe, cliente solo lee la suya) ----------
drop policy if exists dietas_select on public.dietas;
create policy dietas_select on public.dietas
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists dietas_admin_write on public.dietas;
create policy dietas_admin_write on public.dietas
    for all using (public.is_admin()) with check (public.is_admin());

-- ---------- rutinas (solo admin escribe, cliente solo lee la suya) ----------
drop policy if exists rutinas_select on public.rutinas;
create policy rutinas_select on public.rutinas
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists rutinas_admin_write on public.rutinas;
create policy rutinas_admin_write on public.rutinas
    for all using (public.is_admin()) with check (public.is_admin());

-- ---------- historial_entrenamientos (cliente solo lee el suyo) ----------
-- El scraper de Hevy (Paso 5) corre en el backend con la service_role key,
-- que por diseño de Supabase se salta RLS, así que no necesita policy de
-- insert aquí. Dejamos también la vía de admin por si se necesita
-- corregir datos manualmente desde el panel.
drop policy if exists historial_select on public.historial_entrenamientos;
create policy historial_select on public.historial_entrenamientos
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists historial_admin_write on public.historial_entrenamientos;
create policy historial_admin_write on public.historial_entrenamientos
    for all using (public.is_admin()) with check (public.is_admin());

-- ---------- notificaciones (cliente lee las suyas y solo puede marcarlas leídas) ----------
drop policy if exists notificaciones_select on public.notificaciones;
create policy notificaciones_select on public.notificaciones
    for select using (cliente_id = auth.uid() or public.is_admin());

drop policy if exists notificaciones_update on public.notificaciones;
create policy notificaciones_update on public.notificaciones
    for update using (cliente_id = auth.uid() or public.is_admin());
    -- La app solo debe exponerle al cliente la posibilidad de cambiar "leida";
    -- se refuerza a nivel de aplicación en el Paso 6.

drop policy if exists notificaciones_admin_insert on public.notificaciones;
create policy notificaciones_admin_insert on public.notificaciones
    for insert with check (public.is_admin());

drop policy if exists notificaciones_admin_delete on public.notificaciones;
create policy notificaciones_admin_delete on public.notificaciones
    for delete using (public.is_admin());

-- ---------- alertas_descartadas (exclusivo admin; el cliente nunca las ve) ----------
alter table public.alertas_descartadas enable row level security;

drop policy if exists alertas_descartadas_admin_all on public.alertas_descartadas;
create policy alertas_descartadas_admin_all on public.alertas_descartadas
    for all using (public.is_admin()) with check (public.is_admin());

-- =====================================================================
-- PASO MANUAL DE BOOTSTRAP (ejecutar UNA sola vez, después de registrar
-- tu propio usuario Admin desde la pantalla de login/signup de la app):
--
--   update public.clientes
--   set rol = 'admin'
--   where email = 'TU_CORREO_DE_ENTRENADOR@ejemplo.com';
--
-- Esto solo funciona corriéndolo tú mismo desde el SQL Editor de Supabase
-- (que usa privilegios de servicio y por lo tanto ignora RLS). Ningún
-- cliente puede hacer esto desde la app: el trigger
-- prevent_role_self_escalation lo bloquea.
-- =====================================================================
