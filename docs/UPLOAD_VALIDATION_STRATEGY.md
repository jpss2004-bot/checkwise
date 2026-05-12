# Upload Validation Strategy

## Política V1.1

Solo se aceptan archivos PDF en el intake nativo.

Razones:

- Reduce errores del proveedor.
- Permite inspección técnica consistente.
- Evita mezclar XML/JPG/DOCX antes de tener parser específico.
- Alinea el flujo a revisión legal/documental.

## Validaciones Implementadas

- Extensión `.pdf`.
- MIME compatible con PDF.
- Tamaño máximo configurable con `MAX_UPLOAD_SIZE_BYTES`.
- Archivo no vacío.
- Hash SHA-256.
- Duplicado por hash.
- Cabecera PDF `%PDF-`.
- Parseo básico con `pypdf`.
- PDF cifrado/protegido.
- Conteo de páginas.
- Texto legible inicial.
- Posible PDF escaneado sin texto.

## Decisión sobre `pypdf`

Se agregó `pypdf` porque es una dependencia Python acotada para inspeccionar estructura PDF sin introducir OCR, navegadores headless ni servicios externos. En esta fase no hace dictamen legal; solo produce señales técnicas.

## Eventos

Cada carga puede registrar eventos como:

- `upload_started`
- `file_received`
- `file_hash_generated`
- `file_type_validated`
- `pdf_inspected`
- `duplicate_detected`
- `text_extracted`
- `requirement_mismatch_detected`
- `supplier_confirmed_submission`
- `human_review_required`

## Pendientes Técnicos Precisos

- Validar PDF/A cuando el cliente lo requiera.
- Añadir límites por número de páginas.
- Añadir antivirus/malware scanning antes de storage productivo.
- Implementar OCR para PDFs escaneados usando worker asíncrono.
- Separar `upload_attempts` si el negocio necesita auditar intentos rechazados antes de crear `submission`.
