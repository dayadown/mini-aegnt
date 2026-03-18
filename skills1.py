from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tools.description import SKILL_TOOL_HANDLERS


@dataclass
class SkillInfo:
    name: str
    description: str
    location: str
    content: str
@dataclass
class SkillResult:
    content: str
    name: str
    dir: str

class SkillsManager:
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.skills: dict[str, SkillInfo] = {}

    def load(self):
        skills_dir = self.workspace_dir / "skills"
        if not skills_dir.is_dir():
            return self

        for md_file in skills_dir.rglob("SKILL.md"):
            skill = self._parse(md_file)
            if skill:
                self.skills[skill.name] = skill
                SKILL_TOOL_HANDLERS.add(skill.name)

        return self

    def _parse(self, path: Path) -> Optional[SkillInfo]:
        try:
            content = path.read_text(encoding="utf-8")
            frontmatter, body = "", content

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    body = parts[2].strip()

            data = {}
            for line in frontmatter.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip()] = value.strip()

            name = data.get("name")
            description = data.get("description", "")

            if not name:
                return None

            return SkillInfo(
                name=name,
                description=description,
                location=str(path),
                content=body,
            )
        except Exception:
            return None

    def get(self, name: str) -> Optional[SkillInfo]:
        return self.skills.get(name)

    def all(self) -> list[SkillInfo]:
        return list(self.skills.values())

    def build_system_prompt(self) -> str:
        if not self.skills:
            return "No skills available."

        lines = [
            "## Available Skills",
            "",
            "| Name | Description |",
            "|------|-------------|",
        ]
        for s in self.skills.values():
            lines.append(f"| `{s.name}` | {s.description} |")

        return "\n".join(lines)

    def execute(self, name: str) -> SkillResult:
        skill = self.get(name)
        if not skill:
            names = ", ".join([s.name for s in self.all()]) or "none"
            raise ValueError(f'Skill "{name}" not found. Available: {names}')
        base_dir = str(Path(skill.location).parent)

        content = "\n".join([
            f"<skill_content name=\"{name}\">",
            f"# Skill: {name}",
            "",
            skill.content.strip(),
            f"Base directory for this skill: {base_dir}",
            "</skill_content>",
        ])
        return SkillResult(content=content, name=name, dir=base_dir)

    def to_tools(self) -> list[dict]:
        """将所有skill转换为tool定义列表"""
        return [self.to_tool_def(s) for s in self.skills.values()]

    def to_tool_def(self, skill: SkillInfo) -> dict:
        """将单个skill转换为tool定义"""
        return {
            "name": skill.name,
            "description": f"Load skill: {skill.description}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": f"Skill name to load (e.g., {skill.name})"
                    }
                },
                "required": ["name"]
            }
        }