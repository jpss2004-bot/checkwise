"""Guard: the Alembic revision DAG must have exactly one head.

A second head means two migrations share a ``down_revision`` (a fork). That
makes ``alembic upgrade head`` ambiguous and breaks the deploy — the exact
class of error the 0057/0063 rechain risked. This test runs without a database
(it only reads the versions directory), so it is a cheap, always-on CI gate.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script_directory() -> ScriptDirectory:
    api_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(api_root / "alembic.ini"))
    # Anchor to absolute paths so the test passes regardless of the cwd pytest
    # is invoked from.
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_alembic_has_exactly_one_head() -> None:
    heads = _script_directory().get_heads()
    assert len(heads) == 1, (
        f"Expected exactly one Alembic head, found {len(heads)}: {heads}. "
        "A fork means two migrations share a down_revision — rechain the new "
        "migration onto the existing head before deploying."
    )


def test_alembic_chain_has_single_base() -> None:
    bases = _script_directory().get_bases()
    assert len(bases) == 1, (
        f"Expected exactly one Alembic base, found {len(bases)}: {bases}."
    )
