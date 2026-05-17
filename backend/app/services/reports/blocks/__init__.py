"""Per-block server-side implementations.

Each block type owns one module here. The module exports two optional
callables matching the architecture spec §6.2:

    fetch_data(config, scope, db) -> dict | None
        Tenant-scoped read against the DB. Returns the block's `data`
        payload. None means "no data needed" (text blocks etc.).

    render_ai_summary(config, data, audience, llm) -> Iterable[str]
        Generator yielding markdown chunks for the block's
        ai_summary. None / missing means "this block has no AI text"
        (kpi_strip, vendor_risk_matrix don't carry AI text by default
        — the data IS the signal).

The executor (block_executor.py) resolves these by block type and
calls them in order. Adding a new AI-aware block = new module here.
"""
