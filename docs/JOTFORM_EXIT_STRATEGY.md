# JotForm Exit Strategy

## Diagnóstico

JotForm fue útil para validar operación, pero no debe ser el destino final de CheckWise. Sus límites naturales son:

- Trazabilidad regulatoria limitada.
- Difícil modelar requisitos versionados.
- UX de formulario genérico.
- Validaciones documentales insuficientes.
- Dependencia externa en un flujo crítico.
- Dificultad para crear auditabilidad completa por cliente/proveedor/periodo/requisito.

## Decisión Recomendada

Usar estrategia híbrida temporal:

1. Mantener JotForm/Sheets como puente operativo mientras se estabiliza el intake nativo.
2. Construir importador idempotente JotForm/Sheets hacia PostgreSQL.
3. Migrar cliente/proveedor piloto al intake nativo.
4. Comparar calidad, tiempos de revisión y errores.
5. Apagar JotForm por etapas cuando el portal nativo cubra los flujos críticos.

## Lo Que No Conviene

- Embeber JotForm como experiencia principal del portal.
- Duplicar lógica regulatoria entre JotForm y CheckWise.
- Seguir usando Sheets como fuente canónica.

## Criterio de Salida

JotForm puede dejar de usarse cuando CheckWise tenga:

- Wizard por tipo de carga.
- Catálogo real de requisitos versionados.
- Storage productivo.
- Validaciones PDF/OCR suficientes.
- Revisión humana interna.
- Importador histórico probado.
- Reportes generados desde PostgreSQL.
