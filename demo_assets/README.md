# CheckWise Demo Assets

Assets seguros para presentar CheckWise V1 sin usar datos reales sensibles.

## Contenido

- `sample_documents/checkwise_demo_opinion_sat.pdf`: documento ficticio para cargar en el intake.
- `screenshots/`: capturas reales del sistema local.
- `CheckWise_Demo_Guide.pdf`: versión PDF ligera de `docs/DEMO_GUIDE.md`.

## Regenerar PDF de muestra

```bash
python3 scripts/reports/generate_demo_assets.py
```

El PDF de muestra incluye texto visible para que las validaciones de lectura puedan detectarlo.
