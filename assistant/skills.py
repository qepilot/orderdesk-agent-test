"""Optional extension: skills. Reusable instructions that the agent loads only when a task needs them.

A skill is a folder with a SKILL.md file: a short header (name, description) and a body of
instructions. Only the descriptions are always in the prompt, a line each. The body is loaded
through a tool call when the model decides the task matches. This is progressive disclosure:
the agent can know about fifty procedures and pay the context cost of only the one it uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from .guards import ToolError
from .tools import Tool
from .workspace import COURSE_DIR

SKILLS_DIR = COURSE_DIR / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


def discover_skills(folder: Path = SKILLS_DIR) -> list[Skill]:
    skills = []
    for path in sorted(folder.glob("*/SKILL.md")):
        header, _, body = path.read_text(encoding="utf-8").removeprefix("---\n").partition("\n---\n")
        meta = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        skills.append(Skill(meta.get("name", path.parent.name), meta.get("description", ""), body.strip()))
    return skills


def skills_prompt(skills: list[Skill]) -> str:
    """The always-present part: one line per skill."""
    lines = ["Skills you can load with load_skill when a task matches (load at most the ones you need, before you "
             "start gathering evidence):"]
    lines += [f"- {skill.name}: {skill.description}" for skill in skills]
    return "\n".join(lines)


class LoadSkillArgs(BaseModel):
    name: str = Field(description="The skill name exactly as listed.")


def skill_tool(skills: list[Skill]) -> Tool:
    by_name = {skill.name: skill for skill in skills}

    def load_skill(name: str) -> str:
        skill = by_name.get(name)
        if skill is None:
            raise ToolError("unknown_skill", f"No skill '{name}'. Available: {', '.join(by_name)}.")
        return f"<skill name=\"{skill.name}\">\n{skill.body}\n</skill>\nFollow this procedure for the current task."

    return Tool("load_skill", "Load the full instructions of one skill by name. Skills are trusted procedures "
                "written by this team.", load_skill, LoadSkillArgs)
