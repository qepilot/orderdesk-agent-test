"""Hand-written sample outputs for Module 1 (no tools yet), used when no model is configured."""

from __future__ import annotations

import json
from pathlib import Path

from .standin import CannedModel

SAMPLES = json.loads((Path(__file__).resolve().parent / "samples" / "module_1.json").read_text(encoding="utf-8"))


def canned(*keys: str) -> CannedModel:
    """A stand-in model that answers with the named samples, in order. "roles_104.dba" picks a nested one."""
    answers = []
    for key in keys:
        value = SAMPLES
        for part in key.split("."):
            value = value[part]
        answers.append(value)
    return CannedModel(answers)
