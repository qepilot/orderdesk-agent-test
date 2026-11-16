from pathlib import Path

import yaml

TEMPLATE = Path(__file__).resolve().parents[1] / "ci" / "restaurant-ci.yml"


def _load():
    return yaml.safe_load(TEMPLATE.read_text())


def test_ci_template_is_valid_yaml_triggering_only_on_pull_request_for_restaurant():
    doc = _load()
    triggers = doc.get("on", doc.get(True))  # YAML 1.1 parses bare `on` as True
    assert list(triggers) == ["pull_request"]
    assert triggers["pull_request"]["paths"] == ["restaurant/**"]


def test_ci_template_job_runs_check_script():
    jobs = _load()["jobs"]
    runs = [s.get("run") for job in jobs.values() for s in job["steps"]]
    assert "python restaurant/scripts/check.py" in runs
