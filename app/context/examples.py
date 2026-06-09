"""Contexto estático: ejemplos de estimaciones previas.

Esto es el CORAZÓN de la arquitectura CAG (Context-Augmented Generation).
En lugar de tener una base de datos o un sistema de retrieval (RAG), inyectamos
estos ejemplos directamente en el prompt en cada llamada al LLM.

Funcionan como "few-shot examples": le enseñan al modelo el formato, el nivel de
detalle y el estilo de estimación que esperamos. Cuanto más representativos sean,
mejor será la calidad del output.

Cada ejemplo tiene dos partes:
  - meeting_summary: qué pedía el cliente (resumen de la transcripción original).
  - estimation: la estimación que se generó (desglose de tareas + totales).
"""

ESTIMATION_EXAMPLES = [
    {
        "meeting_summary": (
            "El cliente necesita una plataforma web de gestión de inventario para "
            "su cadena de tiendas. Quiere control de stock en tiempo real, alertas "
            "de reposición, gestión de proveedores y un panel con métricas de ventas. "
            "Acceso por roles (administrador, encargado de tienda, almacén)."
        ),
        "estimation": """## Estimación: Plataforma de Gestión de Inventario

### Desglose de tareas:
1. Diseño UI/UX: 40 horas
2. Backend API (CRUD inventario + proveedores): 60 horas
3. Autenticación y control de roles: 20 horas
4. Alertas de reposición (lógica + notificaciones): 25 horas
5. Dashboard con métricas de ventas: 30 horas
6. Testing y QA: 25 horas

**Total estimado: 200 horas**
**Equipo recomendado: 2 desarrolladores full-stack + 1 diseñador UX (part-time)**
**Duración estimada: 6-8 semanas**
**Supuestos: integración con un único sistema de punto de venta existente vía API REST.**
""",
    },
    {
        "meeting_summary": (
            "Una startup quiere una app móvil (iOS y Android) de reserva de clases "
            "de fitness. Necesita registro de usuarios, calendario de clases, reservas "
            "y cancelaciones, pasarela de pago para bonos, y notificaciones push de "
            "recordatorio. El backend debe ser compartido con su web actual."
        ),
        "estimation": """## Estimación: App de Reserva de Clases de Fitness

### Desglose de tareas:
1. Diseño UI/UX móvil (iOS + Android): 50 horas
2. Backend API (usuarios, clases, reservas): 70 horas
3. Integración pasarela de pago (Stripe): 30 horas
4. Notificaciones push: 20 horas
5. App móvil multiplataforma (React Native): 90 horas
6. Testing en dispositivos + QA: 35 horas

**Total estimado: 295 horas**
**Equipo recomendado: 1 desarrollador móvil + 2 desarrolladores backend + 1 diseñador UX**
**Duración estimada: 9-11 semanas**
**Supuestos: reutilización del backend web existente para autenticación de usuarios.**
""",
    },
]
