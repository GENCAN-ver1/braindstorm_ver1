#!/usr/bin/env python3
"""Validate a P7 web-host development manifest without mutating the project."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "p7.1"
TASK_STATUSES = {"pending", "in_progress", "done", "blocked"}
ACCEPTANCE_STATUSES = {"unverified", "pass", "fail", "blocked"}
GATE_STATUSES = {"CONTRACT_READY", "DEVELOPING", "NEEDS_INPUT", "BLOCKED", "COMMIT"}
DATA_CLASSIFICATIONS = {"public", "internal", "confidential", "restricted"}
BASE_CONTROLS = {"input-validation", "output-encoding", "secret-management", "dependency-review"}
AUTH_CONTROLS = {"authentication", "authorization", "session-protection"}
FRONTEND_STATES = {"loading", "empty", "error", "success"}
P6_KEYS = {
    "approved_artifact_path",
    "locked_decisions",
    "open_questions",
    "non_goals",
    "acceptance_criteria",
    "risks",
    "next_validation",
}
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ValidationError(Exception):
    """Raised for CLI or document-loading errors, not contract violations."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"file not found: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_list(value: Any) -> bool:
    return isinstance(value, list)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Validator:
    def __init__(self, root: Path, manifest: dict[str, Any]) -> None:
        self.root = root.resolve()
        self.manifest = manifest
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.commit = False
        self.contract_ready = False
        self.p6: dict[str, Any] | None = None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def obj(self, parent: dict[str, Any], key: str) -> dict[str, Any]:
        value = parent.get(key)
        if not isinstance(value, dict):
            self.error(f"{key} must be an object")
            return {}
        return value

    def list_field(self, parent: dict[str, Any], key: str, context: str) -> list[Any]:
        value = parent.get(key)
        if not is_list(value):
            self.error(f"{context}.{key} must be an array")
            return []
        return value

    def resolve_path(
        self,
        value: Any,
        context: str,
        must_exist: bool = False,
        allow_absolute_inside_root: bool = False,
    ) -> Path | None:
        if not isinstance(value, str) or not value.strip():
            self.error(f"{context} must be a non-empty relative path")
            return None
        candidate = Path(value)
        if ".." in candidate.parts or (candidate.is_absolute() and not allow_absolute_inside_root):
            self.error(f"{context} must stay inside project.root: {value!r}")
            return None
        resolved = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            self.error(f"{context} resolves outside project.root: {value!r}")
            return None
        if must_exist and not resolved.exists():
            self.error(f"{context} does not exist: {value!r}")
        return resolved

    def validate(self) -> None:
        if self.manifest.get("schema_version") != SCHEMA_VERSION:
            self.error(f"schema_version must equal {SCHEMA_VERSION!r}")

        project = self.obj(self.manifest, "project")
        if not isinstance(project.get("name"), str) or not project.get("name", "").strip():
            self.error("project.name must be a non-empty string")
        if project.get("root") != ".":
            self.error("project.root must be '.'; pass the actual project root with --root")

        gate = self.obj(self.manifest, "gate")
        gate_status = gate.get("status")
        if gate_status not in GATE_STATUSES:
            self.error(f"gate.status must be one of {sorted(GATE_STATUSES)}")
        self.commit = gate_status == "COMMIT"
        self.contract_ready = gate_status == "CONTRACT_READY"
        if not isinstance(gate.get("summary"), str) or not gate.get("summary", "").strip():
            self.error("gate.summary must be a non-empty string")

        self.validate_source()
        acceptance_ids = self.validate_acceptance()
        self.validate_scope()
        self.validate_architecture()
        self.validate_tasks(acceptance_ids)
        self.validate_frontend()
        self.validate_security()
        self.validate_commit_gate()

    def validate_source(self) -> None:
        source = self.obj(self.manifest, "source")
        handoff = self.resolve_path(source.get("handoff_path"), "source.handoff_path", must_exist=True)
        expected = source.get("handoff_sha256")
        if not isinstance(expected, str) or not SHA_RE.fullmatch(expected):
            self.error("source.handoff_sha256 must be 64 lowercase hexadecimal characters")
        if handoff is None or not handoff.is_file():
            return
        if isinstance(expected, str) and SHA_RE.fullmatch(expected) and sha256(handoff) != expected:
            self.error("source handoff SHA-256 does not match source.handoff_sha256")
        try:
            p6 = load_json(handoff)
        except ValidationError as exc:
            self.error(str(exc))
            return
        if not isinstance(p6, dict):
            self.error("P6 handoff must be a JSON object")
            return
        missing = sorted(P6_KEYS - set(p6))
        extra = sorted(set(p6) - P6_KEYS)
        if missing:
            self.error(f"P6 handoff is missing keys: {missing}")
        if extra:
            self.error(f"P6 handoff contains disallowed keys: {extra}")
        for key in ("locked_decisions", "open_questions", "non_goals", "acceptance_criteria", "risks"):
            if not is_list(p6.get(key)):
                self.error(f"P6 handoff {key} must be an array")
        approved = self.resolve_path(
            p6.get("approved_artifact_path"),
            "P6 approved_artifact_path",
            must_exist=True,
            allow_absolute_inside_root=True,
        )
        if approved is not None and not approved.is_file():
            self.error("P6 approved_artifact_path must identify a file")
        self.p6 = p6

    def validate_scope(self) -> None:
        scope = self.obj(self.manifest, "scope")
        in_scope = self.list_field(scope, "in_scope", "scope")
        non_goals = self.list_field(scope, "non_goals", "scope")
        if not in_scope:
            self.error("scope.in_scope must not be empty")
        if self.p6 and is_list(self.p6.get("non_goals")):
            actual = {canonical(item) for item in non_goals}
            missing = [item for item in self.p6["non_goals"] if canonical(item) not in actual]
            if missing:
                self.error(f"scope.non_goals does not preserve all P6 non_goals: {missing!r}")

    def validate_acceptance(self) -> set[str]:
        entries = self.manifest.get("acceptance")
        if not is_list(entries):
            self.error("acceptance must be an array")
            return set()
        ids: set[str] = set()
        source_criteria: list[Any] = []
        for index, entry in enumerate(entries):
            context = f"acceptance[{index}]"
            if not isinstance(entry, dict):
                self.error(f"{context} must be an object")
                continue
            item_id = entry.get("id")
            if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
                self.error(f"{context}.id has an invalid format")
            elif item_id in ids:
                self.error(f"duplicate acceptance id: {item_id}")
            else:
                ids.add(item_id)
            if "criterion" not in entry:
                self.error(f"{context}.criterion is required")
            source = entry.get("source")
            if source not in {"handoff", "derived"}:
                self.error(f"{context}.source must be 'handoff' or 'derived'")
            elif source == "handoff" and "criterion" in entry:
                source_criteria.append(entry["criterion"])
            status = entry.get("status")
            if status not in ACCEPTANCE_STATUSES:
                self.error(f"{context}.status must be one of {sorted(ACCEPTANCE_STATUSES)}")
            evidence = self.list_field(entry, "evidence", context)
            require_evidence = status == "pass"
            if require_evidence and not evidence:
                self.error(f"{context}.evidence must not be empty when status is pass")
            for evidence_index, path in enumerate(evidence):
                self.resolve_path(path, f"{context}.evidence[{evidence_index}]", must_exist=require_evidence)
            if self.contract_ready and status != "unverified":
                self.error(f"{context}.status must be unverified at CONTRACT_READY")
            if self.contract_ready and evidence:
                self.error(f"{context}.evidence must be empty at CONTRACT_READY")
        if self.p6 and is_list(self.p6.get("acceptance_criteria")):
            actual = {canonical(item) for item in source_criteria}
            missing = [item for item in self.p6["acceptance_criteria"] if canonical(item) not in actual]
            if missing:
                self.error(f"acceptance does not map all P6 acceptance criteria: {missing!r}")
        return ids

    def validate_architecture(self) -> None:
        architecture = self.obj(self.manifest, "architecture")
        entrypoints = self.list_field(architecture, "entrypoints", "architecture")
        components = self.list_field(architecture, "components", "architecture")
        decisions = self.list_field(architecture, "decisions", "architecture")
        if self.contract_ready:
            if entrypoints or components or decisions:
                self.error("architecture must remain undecided at CONTRACT_READY")
            return
        if not entrypoints:
            self.error("architecture.entrypoints must not be empty")
        for index, path in enumerate(entrypoints):
            self.resolve_path(path, f"architecture.entrypoints[{index}]", must_exist=self.commit)
        component_ids: set[str] = set()
        dependencies: dict[str, list[str]] = {}
        for index, component in enumerate(components):
            context = f"architecture.components[{index}]"
            if not isinstance(component, dict):
                self.error(f"{context} must be an object")
                continue
            component_id = component.get("id")
            if not isinstance(component_id, str) or not ID_RE.fullmatch(component_id):
                self.error(f"{context}.id has an invalid format")
                continue
            if component_id in component_ids:
                self.error(f"duplicate component id: {component_id}")
            component_ids.add(component_id)
            self.resolve_path(component.get("path"), f"{context}.path", must_exist=self.commit)
            if not isinstance(component.get("responsibility"), str) or not component.get("responsibility", "").strip():
                self.error(f"{context}.responsibility must be a non-empty string")
            deps = self.list_field(component, "depends_on", context)
            dependencies[component_id] = [dep for dep in deps if isinstance(dep, str)]
            if len(dependencies[component_id]) != len(deps):
                self.error(f"{context}.depends_on must contain only strings")
        if not components:
            self.error("architecture.components must not be empty")
        for component_id, deps in dependencies.items():
            for dep in deps:
                if dep == component_id:
                    self.error(f"component {component_id} depends on itself")
                elif dep not in component_ids:
                    self.error(f"component {component_id} has unknown dependency {dep}")
        self.detect_cycles(dependencies, "component")
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict) or not all(
                isinstance(decision.get(key), str) and decision.get(key, "").strip()
                for key in ("decision", "rationale")
            ):
                self.error(f"architecture.decisions[{index}] requires non-empty decision and rationale")

    def validate_tasks(self, acceptance_ids: set[str]) -> None:
        tasks = self.manifest.get("tasks")
        if not is_list(tasks):
            self.error("tasks must be an array")
            return
        if self.contract_ready:
            if tasks:
                self.error("tasks must remain empty at CONTRACT_READY")
            return
        task_ids: set[str] = set()
        task_map: dict[str, dict[str, Any]] = {}
        dependencies: dict[str, list[str]] = {}
        in_progress = 0
        for index, task in enumerate(tasks):
            context = f"tasks[{index}]"
            if not isinstance(task, dict):
                self.error(f"{context} must be an object")
                continue
            task_id = task.get("id")
            if not isinstance(task_id, str) or not ID_RE.fullmatch(task_id):
                self.error(f"{context}.id has an invalid format")
                continue
            if task_id in task_ids:
                self.error(f"duplicate task id: {task_id}")
            task_ids.add(task_id)
            task_map[task_id] = task
            if not isinstance(task.get("title"), str) or not task.get("title", "").strip():
                self.error(f"{context}.title must be a non-empty string")
            status = task.get("status")
            if status not in TASK_STATUSES:
                self.error(f"{context}.status must be one of {sorted(TASK_STATUSES)}")
            in_progress += int(status == "in_progress")
            deps = self.list_field(task, "depends_on", context)
            dependencies[task_id] = [dep for dep in deps if isinstance(dep, str)]
            if len(dependencies[task_id]) != len(deps):
                self.error(f"{context}.depends_on must contain only strings")
            outputs = self.list_field(task, "outputs", context)
            acceptance_refs = self.list_field(task, "acceptance_ids", context)
            if status == "done" and not outputs:
                self.error(f"{context}.outputs must not be empty when status is done")
            for output_index, path in enumerate(outputs):
                self.resolve_path(path, f"{context}.outputs[{output_index}]", must_exist=status == "done")
            for acceptance_id in acceptance_refs:
                if not isinstance(acceptance_id, str) or acceptance_id not in acceptance_ids:
                    self.error(f"{context} references unknown acceptance id {acceptance_id!r}")
        if in_progress > 1:
            self.error("at most one task may be in_progress")
        if not tasks:
            self.error("tasks must not be empty")
        for task_id, deps in dependencies.items():
            for dep in deps:
                if dep == task_id:
                    self.error(f"task {task_id} depends on itself")
                elif dep not in task_ids:
                    self.error(f"task {task_id} has unknown dependency {dep}")
                elif task_map[task_id].get("status") in {"in_progress", "done"} and task_map[dep].get("status") != "done":
                    self.error(f"task {task_id} started before dependency {dep} was done")
        self.detect_cycles(dependencies, "task")

    def detect_cycles(self, graph: dict[str, list[str]], label: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                self.error(f"{label} dependency cycle includes {node}")
                return
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                if dependency in graph:
                    visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    def validate_frontend(self) -> None:
        frontend = self.obj(self.manifest, "frontend")
        applicable = frontend.get("applicable")
        states = self.list_field(frontend, "states", "frontend")
        accessibility = self.list_field(frontend, "accessibility_checks", "frontend")
        responsive = self.list_field(frontend, "responsive_checks", "frontend")
        if self.contract_ready:
            if applicable is not None or states or accessibility or responsive:
                self.error("frontend must remain undecided at CONTRACT_READY")
            return
        if not isinstance(applicable, bool):
            self.error("frontend.applicable must be boolean")
            return
        if applicable:
            missing = sorted(FRONTEND_STATES - set(item for item in states if isinstance(item, str)))
            if missing:
                self.error(f"frontend.states is missing required states: {missing}")
            if self.commit and not accessibility:
                self.error("frontend.accessibility_checks must not be empty on COMMIT")
            if self.commit and not responsive:
                self.error("frontend.responsive_checks must not be empty on COMMIT")

    def validate_security(self) -> None:
        security = self.obj(self.manifest, "security")
        auth_required = security.get("auth_required")
        boundaries = self.list_field(security, "trust_boundaries", "security")
        controls = self.list_field(security, "controls", "security")
        secret_sources = self.list_field(security, "secret_sources", "security")
        if self.contract_ready:
            if (
                security.get("data_classification") != "unclassified"
                or auth_required is not None
                or boundaries
                or controls
                or secret_sources
            ):
                self.error("security must remain undecided at CONTRACT_READY")
            return
        if security.get("data_classification") not in DATA_CLASSIFICATIONS:
            self.error(f"security.data_classification must be one of {sorted(DATA_CLASSIFICATIONS)}")
        if not isinstance(auth_required, bool):
            self.error("security.auth_required must be boolean")
        if not boundaries:
            self.error("security.trust_boundaries must not be empty")
        control_set = {item for item in controls if isinstance(item, str)}
        missing = BASE_CONTROLS - control_set
        if auth_required is True:
            missing |= AUTH_CONTROLS - control_set
        if missing:
            self.error(f"security.controls is missing required controls: {sorted(missing)}")
        for index, name in enumerate(secret_sources):
            if not isinstance(name, str) or not ENV_RE.fullmatch(name):
                self.error(f"security.secret_sources[{index}] must be an environment-variable name, not a value")

    def validate_commit_gate(self) -> None:
        if not self.commit:
            return
        for index, task in enumerate(self.manifest.get("tasks", [])):
            if isinstance(task, dict) and task.get("status") != "done":
                self.error(f"tasks[{index}] must be done on COMMIT")
        for index, entry in enumerate(self.manifest.get("acceptance", [])):
            if isinstance(entry, dict) and entry.get("status") != "pass":
                self.error(f"acceptance[{index}] must pass on COMMIT")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--manifest", default="p7-manifest.json", help="manifest path, relative to --root by default")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    try:
        raw = load_json(manifest_path)
        if not isinstance(raw, dict):
            raise ValidationError("manifest must be a JSON object")
        validator = Validator(root, raw)
        validator.validate()
        result = {
            "valid": not validator.errors,
            "schema_version": raw.get("schema_version"),
            "gate_status": raw.get("gate", {}).get("status") if isinstance(raw.get("gate"), dict) else None,
            "errors": validator.errors,
            "warnings": validator.warnings,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    except ValidationError as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)], "warnings": []}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
