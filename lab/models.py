"""Chooses the model for a lab: the real one when it is configured, otherwise the scripted stand-in."""

from __future__ import annotations

from assistant.llm import llm_status, make_model

from .scripts import SCRIPTS
from .standin import ScriptedModel


def model_for(script: str, *, force_standin: bool = False):
    """A live model if .env has one (and force_standin is False), else the stand-in playing `script`."""
    if not force_standin and llm_status().ready:
        return make_model()
    return ScriptedModel(SCRIPTS[script])


def using_live_model() -> bool:
    return llm_status().ready
