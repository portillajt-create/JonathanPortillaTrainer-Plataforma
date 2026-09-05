"""
Textos legales de la plataforma (aviso de tratamiento de datos y términos y
condiciones).

Viven en un solo lugar porque se muestran en DOS pantallas distintas: en el
registro (app.py, para que el cliente los acepte antes de crear su cuenta) y
en "Guías y Recursos" (modules/recursos.py, para que pueda volver a
consultarlos después sin tener que cerrar sesión). Antes solo existían en
app.py; se movieron acá para no mantener el mismo texto legal copiado en dos
archivos.
"""

from __future__ import annotations

AVISO_TRATAMIENTO_DATOS = (
    "Jonathan Portilla, como responsable del tratamiento, recolecta y conserva los datos "
    "personales que usted suministra en este registro y en su ficha de onboarding —incluyendo "
    "información personal, antecedentes médicos, hábitos y variables de entrenamiento y "
    "nutrición— con la finalidad exclusiva de prestar el servicio de asesoría física y "
    "nutricional contratado. Esta información es de uso exclusivo del entrenador y no se "
    "comparte, cede ni comercializa con terceros. De conformidad con la Ley 1581 de 2012, usted "
    "tiene derecho a conocer, actualizar, rectificar y solicitar la eliminación de sus datos "
    "personales en cualquier momento, dirigiéndose directamente a su entrenador."
)

TERMINOS_CONDICIONES = (
    "**1. Objeto del servicio.** Esta plataforma presta un servicio de asesoría personalizada de "
    "entrenamiento físico y nutrición, prestado por Jonathan Portilla ('el entrenador'), e "
    "incluye: ficha de onboarding, asignación de rutinas y planes nutricionales, seguimiento "
    "semanal (check-ins) y notificaciones asociadas.\n\n"
    "**2. Registro y cuenta.** El usuario ('el cliente') debe registrarse con información veraz "
    "y es responsable de la confidencialidad de su contraseña. El acceso completo a la "
    "plataforma queda sujeto a la activación de la suscripción por parte del entrenador.\n\n"
    "**3. Planes y pagos.** Los planes disponibles son Mensual, Trimestral y Semestral, con las "
    "tarifas vigentes informadas por el entrenador fuera de la plataforma. El pago se gestiona "
    "directamente con el entrenador; la activación/renovación de la suscripción en la "
    "plataforma es manual.\n\n"
    "**4. Cancelación y reembolsos.** No se realizan reembolsos por pagos ya realizados. Los "
    "planes no se renuevan automáticamente: al vencer el periodo contratado, el cliente debe "
    "realizar un nuevo pago para que el entrenador reactive su suscripción.\n\n"
    "**5. Naturaleza del servicio y exención de responsabilidad.** Las rutinas y planes "
    "nutricionales son recomendaciones generales basadas en la información que el cliente "
    "reporta. El cliente declara no tener contraindicaciones médicas no informadas y asume la "
    "responsabilidad de consultar a un profesional de la salud antes de iniciar cualquier "
    "rutina si tiene alguna condición preexistente. El entrenador no se hace responsable por "
    "lesiones derivadas de la ejecución incorrecta de los ejercicios o de información médica "
    "no reportada por el cliente.\n\n"
    "**6. Uso aceptable.** El cliente se compromete a usar la plataforma únicamente para fines "
    "personales, no comerciales, y a no compartir su acceso con terceros.\n\n"
    "**7. Protección de datos.** El tratamiento de los datos personales se rige por el Aviso de "
    "tratamiento de datos personales de la plataforma.\n\n"
    "**8. Modificaciones.** El entrenador podrá actualizar estos términos; los cambios "
    "relevantes se comunicarán a los clientes activos.\n\n"
    "**9. Contacto.** Para dudas sobre estos términos, escribe a portillajt@gmail.com."
)
