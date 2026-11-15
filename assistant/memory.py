"""Optional extension: long-term memory. Lessons that carry over from one investigation to the next.

Rules that keep this from becoming a liability:
  - Only a person adds a lesson (verified_by is required). An agent's own conclusions are not facts.
  - A lesson is a hint, shown with its source, to be checked again against today's evidence.
  - Lessons are retrieved by relevance, a few at a time; the store is never dumped into the prompt.
  - Every lesson can be traced, edited and deleted: it is one line of JSON in a file under version control.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from .retrieval import BM25Index, Chunk


@dataclass(frozen=True)
class Lesson:
    lesson_id: str
    text: str
    tags: str
    source: str           # the investigation it came from, for example "issue-101"
    verified_by: str
    added: str


class LessonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def all(self) -> list[Lesson]:
        if not self.path.exists():
            return []
        return [Lesson(**json.loads(line)) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def add(self, text: str, *, tags: str, source: str, verified_by: str) -> Lesson:
        if not verified_by.strip():
            raise ValueError("a lesson must be verified by a person before it is stored")
        lesson = Lesson(f"L{len(self.all()) + 1:03d}", text.strip(), tags, source, verified_by, date.today().isoformat())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(lesson)) + "\n")
        return lesson

    def search(self, query: str, k: int = 3) -> list[Lesson]:
        lessons = self.all()
        if not lessons:
            return []
        index = BM25Index([Chunk(lesson.lesson_id, position, f"{lesson.tags}. {lesson.text}")
                           for position, lesson in enumerate(lessons)])
        return [lessons[position] for position, _ in index.search(query, k)]

    def prompt_for(self, task_text: str, k: int = 3) -> str:
        """The block added to the system prompt of a new investigation, or "" when nothing is relevant."""
        lessons = self.search(task_text, k)
        if not lessons:
            return ""
        lines = ["Lessons from earlier investigations that a person verified. They are hints, not evidence: "
                 "confirm each one against what you find today before relying on it."]
        lines += [f"- [{lesson.lesson_id}, from {lesson.source}] {lesson.text}" for lesson in lessons]
        return "\n".join(lines)
