import sys
from pathlib import Path

import pytest

COURSE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COURSE_DIR))

from assistant.app import build_assistant  # noqa: E402
from assistant.workspace import Workspace, default_workspace  # noqa: E402
from lab.scripts import SCRIPTS  # noqa: E402
from lab.standin import ScriptedModel  # noqa: E402


@pytest.fixture(scope="session")
def workspace(tmp_path_factory) -> Workspace:
    """The real workshop data, with output (traces, outbox, state) redirected to a temporary folder."""
    default_workspace()          # builds the database when it is missing
    return Workspace(out=tmp_path_factory.mktemp("out"))


@pytest.fixture
def scripted():
    return lambda name: ScriptedModel(SCRIPTS[name])


@pytest.fixture
def run_script(workspace):
    def run(name: str, task: str = "task", **options):
        assistant = build_assistant(ScriptedModel(SCRIPTS[name]), workspace=workspace, task=task, **options)
        return assistant.agent.run(task), assistant
    return run
