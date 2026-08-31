# PROGRESS.md — Jonathan Portilla Trainer

> Estado del proyecto al **2026-08-30**. Último commit: `9702041`. Árbol de trabajo limpio, todo pusheado a `main`.

---

## 1. Objetivo del proyecto

Plataforma web de asesorías de entrenamiento y nutrición para **un solo entrenador** (Jonathan Portilla) y sus asesorados: el entrenador gestiona clientes, suscripciones, fichas, dietas y rutinas; cada cliente entra con su propia cuenta a ver su plan, reportar su check-in semanal y seguir su progreso.

No es un SaaS multi-entrenador: hay **un** admin y N clientes.

---

## 2. Estado actual (funcionando en producción)

**En vivo:** https://jonathanportillatrainer.streamlit.app
**Repo:** https://github.com/portillajt-create/JonathanPortillaTrainer-Plataforma (rama `main`, **público**)
**Deploy:** Streamlit Community Cloud, auto-redeploy en cada push a `main`. No hay pasos manuales.

### Autenticación
- Login / registro de clientes (auto-servicio), logout.
- Recuperación de contraseña por correo (flujo `token_hash` vía `st.query_params`).
- Confirmación de correo **desactivada** a propósito: el cliente entra apenas se registra.
- SMTP propio configurado en Supabase (Gmail + App Password).
- Roles `admin` / `cliente` en `public.clientes.rol`.

### Lado ADMIN (5 páginas, `ADMIN_PAGINAS` en `app.py:251`)
| Página | Qué hace |
|---|---|
| Gestión de Clientes | Alta/baja de clientes, suscripciones (Mensual/Trimestral/Semestral con vencimiento auto-calculado), alertas de vencimiento, eliminar cliente |
| Ficha del Atleta | Vista de solo lectura del onboarding + descarga en PDF, con alerta roja si hay patologías/lesiones reales |
| Nutrición y Macros | Calculadora TDEE + macros interactiva, generador de dieta de ejemplo, notas automáticas |
| Entrenamiento | Constructor de rutinas por día (1-7), generador de rutina de ejemplo, reordenar ejercicios y días, gráfico de volumen por músculo |
| Progreso | Gráficas de peso corporal y adherencia/bienestar a partir de los check-ins |

### Lado CLIENTE (6 páginas, `CLIENTE_PAGINAS` en `app.py:303`)
Mis Notificaciones · Mi Perfil (onboarding) · Mi Dieta · Mi Entrenamiento · Mi Progreso · Check-in Semanal

### Funcionalidades destacadas ya terminadas
- **Generador de dieta de ejemplo** (`utils/plan_alimentario.py`): ~25 alimentos con opciones colombianas, respeta alergias del onboarding, rota alimentos entre generaciones, porciones realistas, desvío máximo medido de **~4-5 g** sobre el objetivo de macros.
- **Generador de rutina de ejemplo** (`utils/plan_entrenamiento.py`): interpreta el nombre + descripción por palabras clave (idioma ES/EN, casa/gimnasio, 2-7 días, split Full Body / Upper-Lower / PPL / Weider / Arnold o combinación de 2) y arma la rutina con ~120 ejercicios, autonombrando cada día ("Full Body - A", "Push", "Pierna").
- **Check-in semanal**: el cliente reporta la semana **ya cerrada**, con recordatorio automático.
- **Centro de notificaciones** in-app + correo opcional.
- **Dos auditorías de seguridad OWASP completas** (una con Sonnet, otra con Opus) con todos los hallazgos Crítico/Alto/Medio/Bajo corregidos, salvo los dos diferidos (ver §7).

---

## 3. En progreso

**Nada a medias.** La última tarea (mover un día completo arriba/abajo en el editor de rutinas) quedó terminada, verificada, commiteada, pusheada y confirmada por el usuario. `git status` limpio.

Para contexto, el último bloque de trabajo de la sesión (commits `f546e94` → `9702041`) fue:

1. `f546e94` / `27f869f` — Mostrar "(N ejercicios)" junto al título de cada día, con guion separador: `Día 1: Upper - A - (7 ejercicios)`.
2. `fcf703c` / `40c7f93` — **Bug real**: la alerta de patologías/lesiones (y el aviso de alergias en Nutrición) se disparaba con cualquier texto no vacío, incluido "No" / "Ninguna" que escriben los clientes. Se creó `es_respuesta_vacia_o_negativa()` en `utils/formato.py`.
3. `7fab8c1` — El generador de rutinas ahora también pone el nombre de cada día.
4. `2ba8440` — **Bug real**: el generador de dieta producía porciones absurdas ("5 g de pechuga"). Se agregó `MINIMO_GRAMOS` + penalización al elegir combinaciones.
5. `9702041` — Flechas ↑↓ para mover un día completo. Destapó **dos bugs de Streamlit** documentados en el código (ver §4, "Patrones de estado de Streamlit").

---

## 4. Decisiones técnicas importantes (y el POR QUÉ)

### Stack
- **Streamlit + Supabase (PostgreSQL + Auth + RLS)**. *Por qué:* hosting gratuito, cero backend propio que mantener, y la autorización vive en la base de datos y no en el código de la app.
- **La seguridad real es RLS, no el código Python.** Toda tabla tiene `enable row level security` + políticas por rol (`sql/001_schema_roles_rls.sql:532+`). *Por qué:* aunque alguien manipule el frontend, Postgres sigue negando el acceso. Corolario descubierto en la auditoría: las **vistas** necesitan `security_invoker = true` explícito o se saltan RLS (era una vulnerabilidad real, ya corregida).
- **No hay tabla de "entrenadores"**: un admin es una fila en `clientes` con `rol='admin'`. *Por qué:* hay un solo entrenador; una tabla aparte era complejidad sin uso.
- **fpdf2** para el PDF de la ficha. *Por qué:* Python puro, sin dependencias de sistema (Cairo/Pango) que Streamlit Cloud no tiene.

### Los generadores son por reglas, NO por IA
Decisión explícita del usuario tras conocer el costo real de la API. Ambos generadores (`plan_alimentario.py`, `plan_entrenamiento.py`) usan diccionarios + regex por palabras clave. *Por qué importa:* cero costo por uso, cero latencia, resultado determinista y auditable. **La UI siempre avisa que es interpretación por palabras clave, no IA**, y pide revisar antes de guardar — mantener ese aviso si se toca algo.

### Matemática del generador de dieta (`utils/plan_alimentario.py`)
- **Sistema de 3 ecuaciones (Cramer, `_det3`)** para calcular los gramos exactos de los 3 alimentos de cada comida. *Por qué:* ningún alimento es macro-puro (la avena tiene proteína, las almendras tienen carbos); calcular cada uno mirando solo "su" macro daba totales muy por encima del objetivo.
- **Sorteo-y-mejor-resultado** (`_mejores_2_combos`, 48 intentos): algunas combinaciones son matemáticamente imposibles de cuadrar; en vez de curar a mano pares "seguros", se sortean muchas y se eligen las 2 mejores. *Por qué:* escala solo al agregar alimentos nuevos. Cada intento es un sistema 3x3 → 2 ms por dieta completa.
- **`MINIMO_GRAMOS` + penalización**: el solver no sabía que "5 g de pollo" no es una porción real. *Por qué:* se prefiere un ajuste de macros levemente peor a una porción que nadie puede pesar.
- **Alimentos descartados a propósito** (huevo entero, salmón): su relación grasa/proteína hacía fallar el sistema en >90% de los casos. Está documentado en el código para que nadie los "re-agregue" sin saber.
- **`UNIDADES_ALIMENTO`**: las claras se muestran en unidades ("3 claras de huevo"), no en gramos. El cálculo interno sigue en gramos.

### Estado crudo/cocido
Todo alimento indica en su **nombre** cómo se pesa, y sus valores de macros **deben** corresponder a ese estado. Ya hubo un bug por esto ("Carne de res magra" usaba valores de carne cruda). Hay una nota por defecto que le explica al cliente que crudo/cocido es *cuándo pesar*, no *cómo comer*.

### Detección de texto libre del cliente
- **Alergias** (`ALERGENOS` en `plan_alimentario.py`) y **respuestas negativas** (`es_respuesta_vacia_o_negativa` en `formato.py`) normalizan tildes con `unicodedata` NFKD. *Por qué:* la gente escribe "lacteos" sin tilde desde el celular; listar cada variante acentuada a mano no escala (ya se coló un bug así).
- Las respuestas negativas se comparan contra el **texto completo**, nunca como subcadena. *Por qué:* "No puedo correr por dolor en la rodilla" **sí** es una lesión real y debe disparar la alerta.

### Patrones de estado de Streamlit (aprendidos a los golpes)
- **`st.container(key="x")` genera la clase CSS `st-key-x`** → es el mecanismo para aplicar CSS a un widget puntual sin afectar toda la app (flechas, listas, selector de cliente).
- **Los emojis con Variation Selector-16 (⬆️⬇️) no se pueden recolorear por CSS** en Windows; las flechas de texto plano (↑↓) sí. Por eso los botones usan ↑↓.
- **No se puede modificar el `session_state` de un widget ya instanciado en la misma corrida.** Para mover un día completo se guarda la intención en `session_state` y se aplica al **principio del siguiente render** (`rutinas.py:187`).
- **Los nombres de los 7 días se inicializan de una sola pasada, antes de todo** (`rutinas.py:161-176`). *Por qué:* inicializarlos dentro del bucle hacía que un movimiento pendiente leyera un día que esa corrida aún no había tocado → se perdía el nombre de ambos días.
- Los `on_change` **no se disparan dentro de `st.form`** hasta el submit; por eso el formulario de suscripción no usa `st.form`.

### Otras
- **Zona horaria Bogotá = UTC-5 fijo** (`utils/formato.py`), sin `zoneinfo`. *Por qué:* Colombia no tiene horario de verano; el servidor corre en UTC y `date.today()` cambiaba de día a las 7 p.m. hora local.
- **`escapar_markdown()` en todo texto escrito por el cliente.** *Por qué:* `st.markdown` interpreta markdown → un cliente podía inyectar `![](http://...)` y convertir la ficha en una baliza de rastreo que carga sola al abrirla.
- **Versiones de dependencias fijadas** (`==`, no `>=`) + `requirements-lock.txt`. *Por qué:* hallazgo de auditoría — Streamlit Cloud reinstala en cada deploy y podía traer versiones no probadas.
- **Keep-alive con Playwright** (`.github/workflows/keep-alive.yml`), no `curl`. *Por qué:* se probó curl y termina en bucle de redirecciones; despertar la app requiere cookies + JS.
- **Hevy diferido** con la razón completa documentada en `modules/hevy_integration.py:1-30`.

---

## 5. Convenciones del proyecto

**Idioma:** todo en español — comentarios, docstrings, UI, mensajes de commit, nombres de variables. Al cliente se le dice "asesorado" en textos de cara al usuario.

**Comentarios:** explican el **por qué**, no el qué. Cuando algo parece raro (un alimento ausente, un número mágico como `intentos=48`), el comentario dice qué se probó y qué pasó. Varios incluyen los números de la verificación.

**Estructura:**
```
app.py                  Entrada: login, roles, navegación (option_menu), selector de cliente
config.py               Credenciales: st.secrets (prod) → .env (local)
modules/<área>.py       Una página de negocio. Expone render_admin(cliente_id) y/o render_cliente(cliente_id)
utils/<helper>.py       Lógica compartida sin UI (salvo theme.py, que es CSS)
utils/queries.py        TODO acceso a la base de datos pasa por acá
sql/001_*.sql           Esquema, funciones, triggers y políticas RLS (acumulativo)
```

**`session_state`:** las claves se namespacean con el `cliente_id` → `f"rutina_bloques_{cliente_id}"`. *Por qué:* al cambiar de cliente en el selector, el estado de uno no debe filtrarse al otro.

**Flujo de trabajo acordado (no re-preguntar):**
1. Editar código
2. `python3 -m py_compile <archivos>` — siempre antes de commitear
3. Probar en local con servidor de desarrollo (ver §7 para el patrón de prueba)
4. **Confirmación explícita del usuario**
5. `git commit` + `git push origin main` → Streamlit Cloud redespliega solo

**Commits:** mensaje en español, cuerpo que explica el porqué y los números de verificación cuando aplica, cerrando con `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

**SQL:** no hay acceso directo a la base de datos. Los cambios de esquema se le entregan al usuario como **bloques SQL listos para pegar** en el SQL Editor de Supabase; él los corre y confirma.

---

## 6. Pendientes / próximos pasos (por prioridad)

1. **CAPTCHA en login y registro** — diferido explícitamente por el usuario. Hallazgo de la auditoría: hoy no hay protección contra fuerza bruta ni registro automatizado. Supabase soporta hCaptcha/Turnstile nativo (Authentication → Settings → Bot Protection); es principalmente configuración.
2. **Alerta de estancamiento en cargas** (3+ semanas sin progresar peso) — hay un `st.info` de "pendiente" visible en la página de Entrenamiento (`rutinas.py:136`). **Bloqueado**: necesita datos en `historial_entrenamientos`, que hoy está vacía porque depende de Hevy.
3. **Integración con Hevy** — bloqueada (ver §7). Solo viable vía API oficial con la cuenta Pro del propio entrenador. El campo de perfil de Hevy en el onboarding ya está y se conserva.
4. **Cabeceras HTTP de seguridad** (CSP, HSTS, X-Frame-Options) — **no se puede** en Streamlit Community Cloud; requeriría un proxy/hosting propio. Diferido conscientemente.
5. **Residual menor del generador de dieta** — ~50 de 6000 alimentos revisados salen con 5 g en vez de 10 g de frutos secos, solo en el bloque de Snack (10% del día). Se puede bajar subiendo `intentos` o ajustando `MINIMO_GRAMOS`.

---

## 7. Problemas conocidos y bloqueos

| Tema | Detalle |
|---|---|
| **Hevy** | El perfil "público" se renderiza por JS y su API (`api.hevyapp.com`) responde 401 sin credenciales. Ni siquiera con navegador headless hay peso/reps por serie. No se sortea ese control de acceso a propósito. |
| **Cabeceras HTTP** | Limitación de plataforma de Streamlit Community Cloud, no del código. |
| **Pruebas contra producción** | Automatizar el navegador contra `jonathanportillatrainer.streamlit.app` **no es confiable**: Streamlit Cloud envuelve la app en un iframe sandbox (`/~/+/`) que no existe en local, y las capturas fallan por `document.visibilityState === "hidden"`. **Probar siempre en local.** |
| **Hot-reload de Streamlit** | No detecta cambios en módulos importados fuera del directorio del script vigilado. Si un cambio "no aparece", **reiniciar el servidor**, no recargar el navegador. |
| **venv local** | Está en `C:\Users\Yonatan Portilla\pyenvs\jp_trainer_dashboard` (no en `.venv/` del repo). Le faltaba `fpdf2`; ya se instaló. Si falta otro paquete, es del venv, no de `requirements.txt`. |
| **Infeasibilidad estructural** | Ciertas combinaciones de alimentos no pueden cuadrar los 3 macros por más gramos que se ajusten. Es matemática, no un bug. Documentado en `plan_alimentario.py`. |

**Patrón de prueba local** (usado en toda la sesión): crear una entrada temporal en `.claude/launch.json` apuntando a un `test_app.py` desechable en el directorio temporal, que hace `sys.path.insert` a la raíz del proyecto y **monkeypatchea** las funciones de `utils/queries.py` (`get_rutina_activa`, `get_onboarding`, `guardar_rutina`...) con datos simulados, para renderizar la función real sin tocar la base de datos. Manejar con las herramientas del navegador y **limpiar siempre** al terminar (parar el servidor, quitar la entrada de `launch.json`, borrar el directorio temporal).

---

## 8. Archivos clave

| Archivo | Líneas | Para qué |
|---|---|---|
| `app.py` | 375 | Login, recuperación de contraseña, roles, navegación, selector de cliente, bloqueo por suscripción vencida |
| `sql/001_schema_roles_rls.sql` | 671 | **Fuente de verdad del esquema**: 9 tablas, triggers, funciones `security definer`, todas las políticas RLS |
| `utils/plan_alimentario.py` | 475 | Generador de dieta: base de alimentos, alergias, solver de macros, porciones mínimas |
| `modules/rutinas.py` | 473 | Editor de rutinas (admin) + vista del cliente. Reordenar ejercicios y días |
| `utils/plan_entrenamiento.py` | 457 | Generador de rutina: detección por palabras clave, ~120 ejercicios, plantillas de split |
| `modules/checkin.py` | 403 | Check-in semanal, alertas de adherencia y deload |
| `modules/nutricion.py` | 332 | Calculadora TDEE/macros y planificador de dieta |
| `utils/theme.py` | 291 | CSS de identidad visual, incluidos los estilos con `st-key-*` |
| `modules/admin_clientes.py` | 264 | Gestión de clientes y suscripciones |
| `modules/onboarding.py` | 251 | Formulario del cliente + ficha del admin |
| `utils/queries.py` | 251 | **Único punto de acceso a la base de datos** |
| `utils/auth.py` | 200 | Login, registro, recuperación de contraseña, carga de rol |
| `utils/formato.py` | 125 | Fechas Bogotá, `escapar_markdown()`, `es_respuesta_vacia_o_negativa()` |
| `utils/pdf_export.py` | 149 | PDF de la ficha de onboarding |

**Archivos de configuración:** `.streamlit/config.toml` (tema oscuro), `.env.example` (plantilla de credenciales), `requirements.txt` + `requirements-lock.txt` (versiones fijadas), `.github/workflows/keep-alive.yml`, `.github/dependabot.yml`.
