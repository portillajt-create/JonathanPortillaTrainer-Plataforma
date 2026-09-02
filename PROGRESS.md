# PROGRESS.md — Jonathan Portilla Trainer

> Estado del proyecto al **2026-09-02**. Último commit: `8135f05`. Árbol de trabajo limpio, todo pusheado a `main`.

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
| Entrenamiento | Constructor de rutinas por día (1-7), generador de rutina de ejemplo, reordenar ejercicios **y días completos**, RPE por rangos, gráfico de volumen por músculo |
| Progreso | **Importador de CSV de Hevy** + tabla de ejercicios estancados + gráfica de 1RM estimado por ejercicio + gráficas de check-in |

### Lado CLIENTE (6 páginas, `CLIENTE_PAGINAS` en `app.py:303`)
Mis Notificaciones · Mi Perfil (onboarding) · Mi Dieta · Mi Entrenamiento · Mi Progreso · Check-in Semanal

El cliente ve las mismas gráficas de progreso que el admin, **pero no el importador de CSV** (`render_admin` vs `render_cliente` en `modules/hevy_integration.py:55` y `:62`).

### Funcionalidades destacadas ya terminadas
- **Generador de dieta de ejemplo** (`utils/plan_alimentario.py`): ~25 alimentos con opciones colombianas, respeta alergias del onboarding, rota alimentos entre generaciones, porciones realistas, desvío máximo medido de **~4-5 g** sobre el objetivo de macros.
- **Generador de rutina de ejemplo** (`utils/plan_entrenamiento.py`): interpreta nombre + descripción por palabras clave (idioma ES/EN, casa/gimnasio, 2-7 días, split Full Body / Upper-Lower / PPL / Weider / Arnold o combinación de 2), ~120 ejercicios, autonombra cada día ("Full Body - A", "Push", "Pierna").
- **Historial real de entrenamiento vía CSV de Hevy** (ver §4) — ya cargado y probado con datos reales del cliente de prueba.
- **Análisis de progreso** (`utils/analisis_progreso.py`): 1RM estimado + detección de ejercicios estancados.
- **Check-in semanal**: el cliente reporta la semana **ya cerrada**, con recordatorio automático.
- **Centro de notificaciones** in-app + correo opcional.
- **Dos auditorías de seguridad OWASP completas** (una con Sonnet, otra con Opus) con todos los hallazgos Crítico/Alto/Medio/Bajo corregidos, salvo los dos diferidos (ver §6-§7).

---

## 3. En progreso

**Nada a medias.** Todo commiteado, pusheado y confirmado por el usuario. `git status` limpio.

Arco de la última sesión (commits `6d92e13` → `8135f05`), por si hace falta contexto:

1. `6d92e13` — **Regresión propia corregida**: al agregar las flechas de mover día (commit anterior), el expander quedó anidado en una columna de 14/16 de ancho; eso achicaba todo lo de adentro y Streamlit **esconde los botones +/- de un `number_input` cuando queda muy angosto** (desaparecieron en Series y Descanso). Se movieron las flechas a su propia fila **arriba** del expander. Mismo commit: default `RIR 2` → `RPE 8`.
2. `78988d4` / `d2dad1f` — RPE pasa de texto libre a `st.segmented_control` con 4 rangos fijos (`RANGOS_RPE` en `rutinas.py:60`), título "RPE", `width="stretch"` para que no se vea cortado. Valores viejos que no calzan (ej. "RIR 2") se muestran con el default preseleccionado, no rompen.
3. `93f78cc` — **Importación de historial de Hevy por CSV** (nuevo `utils/hevy_import.py`) + gráfica de progreso por ejercicio. Desbloquea `historial_entrenamientos`, que existía desde el Paso 1 pero **ningún código usaba**.
4. `6791820` — Decisión del usuario: se **desiste definitivamente** de sincronizar Hevy en automático. El aviso de "pendiente" ahora solo sale si el cliente no tiene historial cargado.
5. `c8ee39e` — **Bug real de paginación** (ver §4) + tabla "Ejercicios a tener en cuenta" + 1RM estimado + filtro de periodo + se elimina la gráfica de volumen.
6. `b108083` / `8135f05` — Dos correcciones de metodología a la detección de estancamiento, ambas señaladas por el usuario (ver §4).

---

## 4. Decisiones técnicas importantes (y el POR QUÉ)

### Stack
- **Streamlit + Supabase (PostgreSQL + Auth + RLS)**. *Por qué:* hosting gratuito, cero backend propio, y la autorización vive en la base de datos, no en el código.
- **La seguridad real es RLS, no el código Python.** Toda tabla tiene `enable row level security` + políticas por rol (`sql/001_schema_roles_rls.sql:532+`). *Por qué:* aunque alguien manipule el frontend, Postgres sigue negando. Corolario de la auditoría: las **vistas** necesitan `security_invoker = true` explícito o se saltan RLS (era una vulnerabilidad real, ya corregida).
- **No hay tabla de "entrenadores"**: un admin es una fila en `clientes` con `rol='admin'`. *Por qué:* hay un solo entrenador.
- **fpdf2** para el PDF de la ficha. *Por qué:* Python puro, sin dependencias de sistema (Cairo/Pango) que Streamlit Cloud no tiene.

### Hevy: CSV manual, NO sincronización automática (decisión cerrada)
El scraping/API automática **se descartó definitivamente** (decisión explícita del usuario, no una limitación temporal). La razón técnica completa está en `modules/hevy_integration.py:1-35`: la página pública se renderiza por JS y su API responde 401 sin credenciales; sortear eso sería rodear un control de acceso explícito de Hevy.

**Flujo adoptado:** el cliente exporta su CSV desde la app de Hevy (Perfil → Configuración → Exportar datos), se lo pasa al entrenador, y el entrenador lo sube en Progreso.

- `utils/hevy_import.py` parsea el CSV. **Cada fila del CSV es UNA serie**, pero `historial_entrenamientos` guarda **una fila por (cliente, fecha, ejercicio)** — así que se agrupa:
  - `series` = cantidad de series de trabajo (se excluyen las de calentamiento).
  - `peso_kg`/`repeticiones` = los de la **serie más pesada del día** (la "top set", métrica estándar de sobrecarga progresiva). Si no hay peso (ejercicios a peso corporal), se usa la de más repeticiones.
  - `volumen_total` = suma de peso × reps de todas las series de trabajo.
  - Fechas en español (`"30 ago 2026, 12:51"`) se parsean con un dict de meses propio — el locale del sistema no es confiable multiplataforma.
- El upsert es por `(cliente_id, fecha, ejercicio_nombre)`, así que **reimportar el mismo CSV no duplica**, actualiza.
- Verificado con el CSV real: 16.666 series → 4.993 registros agregados, 135 ejercicios, 692 días, 0 filas omitidas.

### 1RM estimado (fórmula de Epley) como métrica central
`calcular_e1rm()` en `utils/analisis_progreso.py:51` → `peso × (1 + reps/30)`.

*Por qué:* mirar solo el peso no dice nada — "60 kg × 8" y "65 kg × 6" no se comparan directo. El 1RM estimado los vuelve un solo número comparable (76.8 vs 78 kg). Se usa **tanto** en la gráfica como en la detección de estancamiento, para que ambas usen la misma definición de "progreso".

### Detección de estancamiento: 3 iteraciones hasta quedar bien
Está en `utils/analisis_progreso.py`. Vale la pena leer las 3 versiones porque cada una falló por una razón distinta:

1. **v1 — comparar peso y reps por separado.** Marcaba "mismas repeticiones" como problema. **Mal:** mantener las reps fijas mientras sube el peso es *exactamente* la progresión doble, o sea progreso, no estancamiento.
2. **v2 — última sesión contra el mejor dato reciente.** **Mal:** demasiado sensible; un solo día flojo (o una sesión de técnica con menos peso) marcaba el ejercicio. 42 de 135 ejercicios marcados.
3. **v3 (actual) — promedio de la mitad vieja vs. la mitad nueva de una ventana acotada por TIEMPO.** Constantes en `analisis_progreso.py:20-48`:
   - `SEMANAS_ACTIVO_MAX = 2` → si no lo entrena hace más de 2 semanas, **ni se considera** (no es parte de su rutina actual). No existe un motivo "sin entrenar hace X semanas": el usuario lo pidió quitar explícitamente.
   - `SEMANAS_VENTANA_PROGRESO = 6` → **la ventana se acota por tiempo, no por cantidad de sesiones.** *Por qué (bug real que reportó el usuario):* "las últimas 6 sesiones" de un ejercicio que se entrena cada 3-4 semanas pueden abarcar más de un año; si meses atrás hubo una marca alta, comparaba una mejora reciente real contra esa marca vieja y decía "sin progreso". Caso concreto verificado en Press de Banca: por conteo salía "100 kg → 82 kg, sin progreso"; por tiempo (4 sesiones en 6 semanas) el promedio reciente (87) **supera** al anterior (78) → sí progresa.
   - `MAX_SESIONES_VENTANA = 8`, `MIN_SESIONES_PROGRESO = 3`, `TOLERANCIA_PROGRESO = 0.01`.
   - Resultado con datos reales: de 24 marcados → **1**, y se verificó a mano que el resto sí venía mejorando.

> Si esta lista vuelve a salir muy larga o muy corta, el ajuste va en esas constantes — no en la lógica.

### Los generadores son por reglas, NO por IA
Decisión explícita del usuario tras conocer el costo real de la API. Ambos generadores usan diccionarios + regex por palabras clave. *Por qué importa:* cero costo por uso, cero latencia, determinista y auditable. **La UI siempre avisa que es interpretación por palabras clave, no IA**, y pide revisar antes de guardar — mantener ese aviso.

### Matemática del generador de dieta (`utils/plan_alimentario.py`)
- **Sistema de 3 ecuaciones (Cramer, `_det3`)** para los gramos exactos de los 3 alimentos de cada comida. *Por qué:* ningún alimento es macro-puro; calcular cada uno mirando solo "su" macro se pasaba del objetivo.
- **Sorteo-y-mejor-resultado** (`_mejores_2_combos`, 48 intentos): algunas combinaciones son imposibles de cuadrar; se sortean muchas y se eligen las 2 mejores. *Por qué:* escala solo al agregar alimentos. ~2 ms por dieta completa.
- **`MINIMO_GRAMOS` + penalización**: el solver no sabía que "5 g de pollo" no es una porción real. Se prefiere un ajuste de macros levemente peor a una porción impesable.
- **Alimentos descartados a propósito** (huevo entero, salmón): su relación grasa/proteína hacía fallar el sistema en >90% de los casos. Documentado en el código para que nadie los re-agregue sin saber.
- **`UNIDADES_ALIMENTO`**: las claras se muestran en unidades ("3 claras de huevo"). El cálculo interno sigue en gramos.

### Estado crudo/cocido
Todo alimento indica en su **nombre** cómo se pesa, y sus macros **deben** corresponder a ese estado (ya hubo un bug: "Carne de res magra" usaba valores de carne cruda). Hay una nota por defecto que le explica al cliente que crudo/cocido es *cuándo pesar*, no *cómo comer*.

### Detección de texto libre del cliente
- **Alergias** (`ALERGENOS`) y **respuestas negativas** (`es_respuesta_vacia_o_negativa` en `formato.py`) normalizan tildes con `unicodedata` NFKD. *Por qué:* la gente escribe "lacteos" sin tilde desde el celular; listar cada variante a mano no escala (ya se coló un bug así).
- Las respuestas negativas se comparan contra el **texto completo**, nunca como subcadena. *Por qué:* "No puedo correr por dolor en la rodilla" **sí** es una lesión real y debe disparar la alerta.

### Patrones de Streamlit (aprendidos a los golpes — leer antes de tocar UI)
- **PostgREST/Supabase corta cada consulta en 1000 filas por defecto, sin avisar.** Fue un bug real: el historial de 4.993 filas se cortaba en ~2023 y la gráfica se veía truncada. Toda consulta que pueda traer miles de filas debe paginar con `.range()` — ver `list_historial_entrenamientos` en `utils/queries.py:272`.
- **Anidar algo en una columna angosta achica TODO lo de adentro**, y Streamlit esconde los +/- de un `number_input` cuando queda muy angosto. Por eso las flechas de mover día van en su propia fila y no envolviendo el expander.
- **`st.container(key="x")` genera la clase CSS `st-key-x`** → así se aplica CSS a un widget puntual sin afectar toda la app.
- **Los emojis con Variation Selector-16 (⬆️⬇️) no se pueden recolorear por CSS** en Windows; las flechas de texto plano (↑↓) sí.
- **No se puede modificar el `session_state` de un widget ya instanciado en la misma corrida.** Para mover un día completo se guarda la intención en `session_state` y se aplica al **principio del siguiente render** (`rutinas.py:193`).
- **Los nombres de los 7 días se inicializan de una sola pasada, antes de todo** (`rutinas.py:167`). *Por qué:* inicializarlos dentro del bucle hacía que un movimiento pendiente leyera un día que esa corrida aún no había tocado → se perdía el nombre de ambos días.
- **Mensaje de éxito antes de `st.rerun()` se pierde.** Patrón del proyecto: guardar un flag en `session_state`, y mostrarlo con `.pop()` en el render siguiente.
- Los `on_change` **no se disparan dentro de `st.form`** hasta el submit; por eso el formulario de suscripción no usa `st.form`.

### Otras
- **Zona horaria Bogotá = UTC-5 fijo** (`utils/formato.py`), sin `zoneinfo`. *Por qué:* Colombia no tiene horario de verano; el servidor corre en UTC y `date.today()` cambiaba de día a las 7 p.m. hora local.
- **`escapar_markdown()` en todo texto escrito por el cliente.** *Por qué:* `st.markdown` interpreta markdown → un cliente podía inyectar `![](http://...)` y convertir la ficha en una baliza de rastreo.
- **Versiones de dependencias fijadas** (`==`) + `requirements-lock.txt`. *Por qué:* Streamlit Cloud reinstala en cada deploy y podía traer versiones no probadas.
- **Keep-alive con Playwright** (`.github/workflows/keep-alive.yml`), no `curl`. *Por qué:* curl termina en bucle de redirecciones; despertar la app requiere cookies + JS.

---

## 5. Convenciones del proyecto

**Idioma:** todo en español — comentarios, docstrings, UI, mensajes de commit, nombres de variables. Al cliente se le dice "asesorado" en textos de cara al usuario.

**Comentarios:** explican el **por qué**, no el qué. Cuando algo parece raro (un alimento ausente, un número mágico como `intentos=48` o `SEMANAS_VENTANA_PROGRESO = 6`), el comentario dice qué se probó y qué pasó, con los números de la verificación.

**Estructura:**
```
app.py                     Entrada: login, roles, navegación (option_menu), selector de cliente
config.py                  Credenciales: st.secrets (prod) → .env (local)
modules/<área>.py          Una página de negocio. Expone render_admin(cliente_id) y/o render_cliente(cliente_id)
utils/<helper>.py          Lógica pura sin UI (salvo theme.py, que es CSS)
utils/queries.py           TODO acceso a la base de datos pasa por acá
sql/001_*.sql              Esquema, funciones, triggers y políticas RLS (acumulativo)
```

**Lógica pura separada de la UI:** `hevy_import.py`, `analisis_progreso.py`, `plan_alimentario.py`, `plan_entrenamiento.py` **no importan Streamlit**. *Por qué:* se pueden probar directamente desde Python contra datos reales, sin levantar la app — así se verificaron el parseo del CSV y las 3 iteraciones del detector de estancamiento.

**`session_state`:** las claves se namespacean con el `cliente_id` → `f"rutina_bloques_{cliente_id}"`. *Por qué:* al cambiar de cliente en el selector, el estado de uno no debe filtrarse al otro.

**Flujo de trabajo acordado (no re-preguntar):**
1. Editar código
2. `python3 -m py_compile <archivos>` — siempre antes de commitear
3. Probar en local con servidor de desarrollo (ver §7 para el patrón)
4. **Confirmación explícita del usuario**
5. `git commit` + `git push origin main` → Streamlit Cloud redespliega solo

**Commits:** mensaje en español, cuerpo que explica el porqué y los números de verificación, cerrando con `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

**SQL:** no hay acceso directo a la base de datos. Los cambios de esquema se le entregan al usuario como **bloques SQL listos para pegar** en el SQL Editor de Supabase; él los corre y confirma.

**Escrituras masivas a la BD:** las hace el admin desde la app con su propia sesión (RLS aplica con su identidad). No se manejan contraseñas del usuario ni se escribe a la BD desde scripts locales.

---

## 6. Pendientes / próximos pasos (por prioridad)

1. **Alerta de estancamiento en cargas** — hay un `st.info` de "pendiente" visible en Entrenamiento (`rutinas.py:142`) que dice que hace falta `historial_entrenamientos`. **Ya no es cierto: la tabla tiene datos y `detectar_ejercicios_a_revisar()` ya hace exactamente ese análisis.** Falta solo conectarlo: llamar esa función desde `render_alertas_entrenamiento()` y reemplazar el `st.info` por la alerta real. Es la tarea más rentable que queda.
2. **Importar el historial del resto de los clientes** — el flujo ya funciona; es operativo, no de código. Ojo con el gotcha del nombre de archivo (§7).
3. **CAPTCHA en login y registro** — diferido explícitamente por el usuario. Hallazgo de auditoría: hoy no hay protección contra fuerza bruta ni registro automatizado. Supabase lo soporta nativo (Authentication → Settings → Bot Protection); es principalmente configuración.
4. **Cabeceras HTTP de seguridad** (CSP, HSTS, X-Frame-Options) — **no se puede** en Streamlit Community Cloud; requeriría proxy/hosting propio. Diferido conscientemente.
5. **Residual menor del generador de dieta** — ~50 de 6000 alimentos revisados salen con 5 g en vez de 10 g de frutos secos, solo en el bloque de Snack. Se baja subiendo `intentos` o ajustando `MINIMO_GRAMOS`.

---

## 7. Problemas conocidos y bloqueos

| Tema | Detalle |
|---|---|
| **CSV de Hevy sin extensión** | El archivo que descarga Hevy **no trae `.csv`** en el nombre, y `st.file_uploader(type=["csv"])` lo rechaza con un ícono rojo. Hay que renombrarlo agregándole `.csv` antes de subirlo. Le va a pasar con **cada** cliente. |
| **Nombres de ejercicio cambian con el tiempo** | Si el cliente renombró un ejercicio en Hevy, el historial queda partido en dos entradas distintas del selector. **No se hace merge automático a propósito**: "Press de Banca" y "Press de Banca Inclinado" son ejercicios distintos y agruparlos por parecido sería peor que el problema. |
| **Cabeceras HTTP** | Limitación de plataforma de Streamlit Community Cloud, no del código. |
| **Pruebas contra producción** | Automatizar el navegador contra `jonathanportillatrainer.streamlit.app` **no es confiable**: Streamlit Cloud envuelve la app en un iframe sandbox (`/~/+/`) que no existe en local, y las capturas fallan por `document.visibilityState === "hidden"`. **Probar siempre en local.** |
| **Hot-reload de Streamlit** | No detecta cambios en módulos importados fuera del directorio del script vigilado. Si un cambio "no aparece", **reiniciar el servidor**, no recargar el navegador. |
| **Ruido en consola de Plotly** | `<text> attribute y: Expected length, "-Infinity"` aparece en cada carga con varias gráficas apiladas. Es un quirk conocido de Plotly dentro de Streamlit durante el layout inicial; **no afecta lo que se ve** (verificado con capturas). Preexistente, no lo introdujo ningún cambio reciente. |
| **venv local** | Está en `C:\Users\Yonatan Portilla\pyenvs\jp_trainer_dashboard` (no en `.venv/` del repo). Le faltaba `fpdf2`; ya se instaló. Si falta otro paquete, es del venv, no de `requirements.txt`. |
| **Infeasibilidad estructural (dieta)** | Ciertas combinaciones de alimentos no pueden cuadrar los 3 macros por más gramos que se ajusten. Es matemática, no un bug. Documentado en `plan_alimentario.py`. |

**Patrón de prueba local:** crear una entrada temporal en `.claude/launch.json` apuntando a un `test_app.py` desechable en el directorio temporal, que hace `sys.path.insert` a la raíz del proyecto y **monkeypatchea** las funciones de `utils/queries.py` (`get_rutina_activa`, `list_historial_entrenamientos`, `guardar_rutina`...) con datos simulados, para renderizar la función real **sin tocar la base de datos**. Para probar guardados, mockear la función de escritura para que *capture* lo que se guardaría y mostrarlo con `st.json`. Manejar con las herramientas del navegador y **limpiar siempre** al terminar (parar el servidor, quitar la entrada de `launch.json`, borrar el directorio temporal).

**Dato útil para probar con datos reales:** el CSV real de Hevy del cliente de prueba está en `../Clientes/workout_data_Jonathan_Portilla.csv.csv` (sí, doble extensión). Se puede parsear con `parsear_csv_hevy()` y mockearlo en `list_historial_entrenamientos` para probar el análisis con 4.993 registros reales sin tocar la BD.

---

## 8. Archivos clave

| Archivo | Líneas | Para qué |
|---|---|---|
| `sql/001_schema_roles_rls.sql` | 671 | **Fuente de verdad del esquema**: 9 tablas, triggers, funciones `security definer`, todas las políticas RLS |
| `modules/rutinas.py` | 488 | Editor de rutinas (admin) + vista del cliente. Reordenar ejercicios y días, RPE por rangos |
| `utils/plan_alimentario.py` | 475 | Generador de dieta: alimentos, alergias, solver de macros, porciones mínimas |
| `utils/plan_entrenamiento.py` | 457 | Generador de rutina: detección por palabras clave, ~120 ejercicios, plantillas de split |
| `modules/checkin.py` | 403 | Check-in semanal, alertas de adherencia y deload |
| `app.py` | 375 | Login, recuperación de contraseña, roles, navegación, selector de cliente, bloqueo por suscripción vencida |
| `modules/nutricion.py` | 332 | Calculadora TDEE/macros y planificador de dieta |
| `utils/queries.py` | 307 | **Único punto de acceso a la BD.** Ojo con la paginación en `list_historial_entrenamientos` |
| `utils/theme.py` | 291 | CSS de identidad visual, incluidos los estilos `st-key-*` |
| `modules/admin_clientes.py` | 264 | Gestión de clientes y suscripciones |
| `modules/hevy_integration.py` | 261 | Página Progreso: importador de CSV, tabla de estancados, gráfica de 1RM, gráficas de check-in |
| `modules/onboarding.py` | 251 | Formulario del cliente + ficha del admin |
| `utils/auth.py` | 200 | Login, registro, recuperación de contraseña, carga de rol |
| `utils/pdf_export.py` | 149 | PDF de la ficha de onboarding |
| `utils/hevy_import.py` | 136 | Parseo/agregación del CSV de Hevy (sin Streamlit) |
| `utils/formato.py` | 125 | Fechas Bogotá, `escapar_markdown()`, `es_respuesta_vacia_o_negativa()` |
| `utils/analisis_progreso.py` | 122 | 1RM estimado (Epley) + detección de estancamiento (sin Streamlit) |

**Archivos de configuración:** `.streamlit/config.toml` (tema oscuro), `.env.example`, `requirements.txt` + `requirements-lock.txt` (versiones fijadas), `.github/workflows/keep-alive.yml`, `.github/dependabot.yml`.
