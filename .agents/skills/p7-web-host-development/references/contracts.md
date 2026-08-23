# P7 Contracts

Read this at intake and before final handoff. `p7-manifest.json` is the canonical development state; chat history is not.

## P6 input contract

The source handoff is UTF-8 JSON with these keys:

```json
{
  "approved_artifact_path": "artifacts/approved-product.md",
  "locked_decisions": [],
  "open_questions": [],
  "non_goals": [],
  "acceptance_criteria": [],
  "risks": [],
  "next_validation": ""
}
```

Arrays may contain strings or structured JSON values. P7 treats their meaning as immutable. The handoff and approved artifact paths must stay inside the repository and exist. The P6 runtime emits `approved_artifact_path` as an absolute path, so P7 accepts that field only when it resolves inside `project.root`; P7-owned manifest paths remain repository-relative. The manifest pins the handoff SHA-256 so a resumed run cannot unknowingly use changed authority.

## Development manifest

Use `schema_version: "p7.1"` and repository-relative POSIX-style paths. Required shape:

```json
{
  "schema_version": "p7.1",
  "project": {"name": "example", "root": "."},
  "source": {"handoff_path": "artifacts/p6-handoff.json", "handoff_sha256": "<64 lowercase hex>"},
  "scope": {"in_scope": ["web implementation"], "non_goals": []},
  "architecture": {
    "entrypoints": ["src/app"],
    "components": [{"id": "web", "path": "src/app", "responsibility": "Render the approved flow", "depends_on": []}],
    "decisions": [{"decision": "Reuse the host router", "rationale": "Existing host convention"}]
  },
  "tasks": [{
    "id": "T1", "title": "Implement the primary flow", "status": "done",
    "depends_on": [], "outputs": ["src/app/page.tsx"], "acceptance_ids": ["A1"]
  }],
  "frontend": {
    "applicable": true,
    "states": ["loading", "empty", "error", "success"],
    "accessibility_checks": ["keyboard", "focus", "labels", "contrast"],
    "responsive_checks": ["small", "medium", "large"]
  },
  "security": {
    "data_classification": "public",
    "auth_required": false,
    "trust_boundaries": ["browser-to-host"],
    "controls": ["input-validation", "output-encoding", "secret-management", "dependency-review"],
    "secret_sources": []
  },
  "acceptance": [{
    "id": "A1", "criterion": "Source criterion copied exactly", "source": "handoff",
    "status": "pass", "evidence": ["artifacts/acceptance/A1.txt"]
  }],
  "gate": {"status": "COMMIT", "summary": "All contracted checks passed"}
}
```

Task status is one of `pending`, `in_progress`, `done`, or `blocked`. Acceptance status is one of `unverified`, `pass`, `fail`, or `blocked`. Gate status is one of `CONTRACT_READY`, `DEVELOPING`, `NEEDS_INPUT`, `BLOCKED`, or `COMMIT`.

`CONTRACT_READY` is the bootstrap-only stop after source authority is pinned and before architecture work begins. At this stop:

- `architecture.entrypoints`, `architecture.components`, `architecture.decisions`, and `tasks` are empty arrays.
- `frontend.applicable` is `null`; its state and check arrays are empty.
- `security.data_classification` is `"unclassified"`, `security.auth_required` is `null`, and its boundary, control, and secret-source arrays are empty.
- Every handoff acceptance criterion is mapped with `status: "unverified"` and empty evidence.

These sentinels are legal only at `CONTRACT_READY`; later gates must replace them with validated development decisions.

Every P6 non-goal must appear unchanged in `scope.non_goals`. Every P6 acceptance criterion must have one `source: "handoff"` acceptance entry whose `criterion` is structurally equal to the source value. Derived implementation checks use `source: "derived"` and may strengthen verification but may not replace or weaken source criteria.

## Path and evidence rules

All P7-owned recorded paths are relative to `project.root`, contain no `..`, and resolve inside the repository. The P6-owned `approved_artifact_path` may be absolute as described above. On `COMMIT`, handoff, approved artifact, entrypoints, component paths, task outputs, and acceptance evidence must exist. Evidence is a durable file such as a test report, captured command output, screenshot, or signed manual-check note; a statement in chat is not evidence.
