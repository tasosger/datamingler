from __future__ import annotations

import json
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from .xmlio import save_datasources_xml

DEFAULT_PROJECT_ID = "default"
DEFAULT_PROJECT_NAME = "Example Project"

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    description: str = ""


class ProjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> list[Project]:
        projects = []
        for path in sorted(self.root.iterdir()):
            if path.is_dir() and (path / "project.json").exists():
                projects.append(self.get(path.name))
        return projects

    def get(self, project_id: str) -> Project:
        project_id = validate_project_id(project_id)
        path = self.project_dir(project_id) / "project.json"
        if not path.exists():
            raise KeyError(f"Project {project_id!r} does not exist")
        data = json.loads(path.read_text(encoding="utf-8"))
        return Project(
            id=str(data.get("id") or project_id),
            name=str(data.get("name") or project_id),
            description=str(data.get("description") or ""),
        )

    def create(
        self,
        project_id: str,
        name: str,
        *,
        description: str = "",
        datasources_template: str | Path | None = None,
        replace: bool = False,
    ) -> Project:
        project_id = validate_project_id(project_id)
        project = Project(id=project_id, name=name.strip() or project_id, description=description.strip())
        project_dir = self.project_dir(project_id)
        project_file = project_dir / "project.json"
        if project_file.exists() and not replace:
            raise ValueError(f"Project {project_id!r} already exists")

        project_dir.mkdir(parents=True, exist_ok=True)
        project_file.write_text(json.dumps(asdict(project), indent=2), encoding="utf-8")

        datasources_xml = project_dir / "datasources.xml"
        if datasources_template:
            if replace or not datasources_xml.exists():
                shutil.copyfile(datasources_template, datasources_xml)
            self._copy_referenced_files(datasources_xml, Path(datasources_template).parent)
        elif not datasources_xml.exists():
            save_datasources_xml({}, datasources_xml)
        return project

    def ensure_default(self, datasources_template: str | Path) -> Project:
        if not self.exists(DEFAULT_PROJECT_ID):
            return self.create(
                DEFAULT_PROJECT_ID,
                DEFAULT_PROJECT_NAME,
                description="Bundled sample graph and datasource definitions.",
                datasources_template=datasources_template,
                replace=False,
            )
        datasources_xml = self.project_dir(DEFAULT_PROJECT_ID) / "datasources.xml"
        if datasources_xml.exists():
            self._copy_referenced_files(datasources_xml, Path(datasources_template).parent)
        return self.get(DEFAULT_PROJECT_ID)

    def exists(self, project_id: str) -> bool:
        project_id = validate_project_id(project_id)
        return (self.project_dir(project_id) / "project.json").exists()

    def project_dir(self, project_id: str) -> Path:
        return self.root / validate_project_id(project_id)

    def datasources_xml(self, project_id: str) -> Path:
        path = self.project_dir(project_id) / "datasources.xml"
        if not path.exists():
            raise KeyError(f"Project {project_id!r} has no datasource definition file")
        return path

    def _copy_referenced_files(self, datasources_xml: Path, template_dir: Path) -> None:
        root = ET.parse(datasources_xml).getroot()
        project_dir = datasources_xml.parent
        for element in root.findall("datasource"):
            filename = _child_text(element, "filename")
            if not filename:
                continue
            source_dir = Path(_child_text(element, "path") or ".")
            if source_dir.is_absolute():
                continue
            source = template_dir / source_dir / filename
            if not source.exists() or not source.is_file():
                continue
            target_dir = project_dir / source_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target_dir / filename)


def validate_project_id(project_id: str | None) -> str:
    value = (project_id or DEFAULT_PROJECT_ID).strip()
    if not _PROJECT_ID_RE.match(value):
        raise ValueError(
            "Project id must start with a letter or number and contain only letters, numbers, '-' or '_'"
        )
    return value


def _child_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()
