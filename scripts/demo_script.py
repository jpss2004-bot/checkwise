"""Voice-over script for the CheckWise demo video.

One narration clip per scene. Each entry: (scene_id, text). The text is
Mexican Spanish, written so that edge-tts pronounces it naturally
(numbers spelled out where the ASR would otherwise read digit-by-digit;
no technical jargon in the prose).

Scene IDs match the keys consumed by scripts/record_demo.py — the
recording script reads each clip's actual duration via ffprobe and sets
the corresponding scene's settle time, so the video paces itself to
the narration automatically.
"""
from __future__ import annotations

SCRIPT: list[tuple[str, str]] = [
    (
        "intro",
        "CheckWise. La plataforma de cumplimiento documental REPSE "
        "pensada para tres roles distintos: el proveedor que sube sus "
        "documentos, el cliente que supervisa su portafolio, y el "
        "revisor humano que toma cada decisión. Esto es una "
        "demostración guiada.",
    ),
    (
        "landing",
        "La página pública resume la propuesta en una sola frase: "
        "cumplimiento REPSE guiado, trazable y accionable. Hay un solo "
        "llamado a la acción principal, sin distracciones.",
    ),
    (
        "provider_login",
        "Iniciamos sesión como proveedor con una cuenta de demostración. "
        "El subtítulo del formulario aclara desde el inicio que si tu "
        "acceso es temporal, CheckWise te pedirá rotar tu contraseña.",
    ),
    (
        "workspace_entry",
        "Antes de entrar al dashboard, el sistema confirma quién eres. "
        "Este paso humano evita que un proveedor caiga directo a un "
        "panel de datos sin contexto.",
    ),
    (
        "provider_dashboard",
        "El dashboard del proveedor está centrado en una sola pregunta: "
        "¿qué sigue? Cada tarjeta corresponde a un documento por subir, "
        "ordenado por urgencia. No hay menús que adivinar ni tablas que "
        "filtrar.",
    ),
    (
        "compliance_pulse",
        "En la sección de reportes, el proveedor ve primero su pulso de "
        "cumplimiento: estado general, atención requerida, próximos "
        "vencimientos y acciones priorizadas. Cuatro indicadores que "
        "responden ¿cómo estoy hoy? en menos de cinco segundos.",
    ),
    (
        "report_editor",
        "Cada reporte puede generarse con inteligencia artificial, "
        "refinarse con un copiloto en lenguaje natural, y actualizarse "
        "con los datos del día. La barra de herramientas también ofrece "
        "una vista previa imprimible y la descarga directa en PDF.",
    ),
    (
        "print_page",
        "La vista imprimible cumple con los requisitos ejecutivos: "
        "cabecera corrida en cada página, número de página al pie, y un "
        "sello visible de cuándo se generaron los datos. Listo para "
        "enviarse al cliente sin retoques.",
    ),
    (
        "client_login",
        "Cambiemos de rol. Ahora entramos como cliente, quien supervisa "
        "todo un portafolio de proveedores.",
    ),
    (
        "client_dashboard",
        "El dashboard del cliente abre con un titular humano: tienes "
        "tres proveedores en amarillo, cuatrocientos treinta y dos "
        "hallazgos obligatorios. Es la lectura ejecutiva de tres "
        "segundos, antes de cualquier tabla.",
    ),
    (
        "vendor_detail",
        "Al abrir un proveedor, la narrativa se descompone en seis "
        "secciones: acciones sugeridas, atención inmediata, entregas "
        "recientes, documentos por estado, próximos vencimientos, y "
        "notas del revisor. Todo en una sola página.",
    ),
    (
        "admin_login",
        "Por último, el rol del revisor interno de Legal Shelf, "
        "responsable de aprobar o rechazar cada documento.",
    ),
    (
        "reviewer_queue",
        "La bandeja del revisor declara la doctrina del producto desde "
        "el subtítulo: ningún documento se aprueba sin un humano. La "
        "automatización no firma. El revisor decide.",
    ),
    (
        "reviewer_detail",
        "Al abrir un envío, el revisor tiene cuatro acciones explícitas: "
        "aprobar, rechazar, pedir aclaración, o registrar una excepción "
        "legal. Cada decisión queda en la bitácora de trazabilidad.",
    ),
    (
        "outro",
        "CheckWise. Cumplimiento documental REPSE con expediente "
        "trazable y revisión humana obligatoria. Operado por Legal "
        "Shelf, en México. Gracias por ver la demostración.",
    ),
]

# Voice + prosody — Dalia is Microsoft's Mexican Spanish female voice,
# warm and clear. The -7% rate slows her slightly for a measured,
# executive cadence. +0% pitch keeps it natural.
VOICE = "es-MX-DaliaNeural"
RATE = "-7%"
PITCH = "+0Hz"
