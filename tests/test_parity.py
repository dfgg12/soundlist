"""T1.7: Parity - import then export equals original JSON for all channels."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.models import Channel
from app.serializer import channel_to_dict
from scripts.import_json import run_import

LISTS_DIR = Path(__file__).parent.parent / "lists"

pytestmark = pytest.mark.skipif(
    not LISTS_DIR.exists(),
    reason="lists/ directory not present",
)

# Channels with known duplicate trigger_words in the source JSON;
# the importer deduplicates them, so parity is checked after dedup.
_KNOWN_DUPES: dict[str, set[str]] = {
    "PuertoRicanPup": {"KEKW"},
}


@pytest.fixture()
def imported_engine(tmp_engine):
    """Run importer once and return the engine."""
    run_import(LISTS_DIR)
    return tmp_engine


def _load_original(rel_path: str) -> dict:
    path = LISTS_DIR.parent / rel_path
    return json.loads(path.read_text(encoding="utf-8"))


def _channel_ids() -> list[tuple[str, str]]:
    """Return (slug, rel_path) pairs from the original index.json."""
    index_path = LISTS_DIR / "index.json"
    if not index_path.exists():
        return []
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return list(index.items())


@pytest.mark.parametrize("slug,rel_path", _channel_ids())
def test_channel_parity(slug: str, rel_path: str, imported_engine):
    """Exported channel JSON must equal the original file content."""
    original_path = LISTS_DIR.parent / rel_path
    if not original_path.exists():
        pytest.skip(f"original file missing: {original_path}")

    original = json.loads(original_path.read_text(encoding="utf-8"))

    with Session(imported_engine) as session:
        channel = session.exec(
            select(Channel).where(Channel.slug == slug)
        ).first()
        assert channel is not None, f"channel {slug!r} not in DB"
        exported = channel_to_dict(channel, session)

    orig_sounds = original.get("sounds", [])
    exp_sounds = exported.get("sounds", [])

    # Remove known duplicate trigger_words from the original before comparison.
    # The importer upserts (last write wins) so keep only the last occurrence
    # and at the position it was last seen.
    dupes = _KNOWN_DUPES.get(slug, set())
    if dupes:
        last_idx: dict[str, int] = {}
        for i, s in enumerate(orig_sounds):
            tw = s.get("trigger_word", "")
            if tw in dupes:
                last_idx[tw] = i
        deduped = [
            s for i, s in enumerate(orig_sounds)
            if s.get("trigger_word", "") not in dupes
            or last_idx.get(s.get("trigger_word", "")) == i
        ]
        orig_sounds = deduped

    assert len(exp_sounds) == len(orig_sounds), (
        f"{slug}: exported {len(exp_sounds)} triggers, "
        f"original has {len(orig_sounds)}"
    )

    for i, (exp, orig) in enumerate(zip(exp_sounds, orig_sounds, strict=True)):
        # Some source files omit trigger_cooldown; serializer always emits it.
        normalized = {"trigger_cooldown": 0, **orig}
        assert exp == normalized, (
            f"{slug} sound[{i}] mismatch:\n  got: {exp}\n  want: {normalized}"
        )
