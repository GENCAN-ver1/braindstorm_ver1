# P7 Skill Routing

`p7-web-host-development` owns the development flow. The Skills below are capabilities only: they may advise or execute a bounded P7 task, but they may not change the P6 handoff, P7 architecture contract, task DAG, security boundary, acceptance criteria, gate status, or authorization requirements.

```yaml
version: p7-skill-routing-v1

authority:
  product_governor: brainstorm-governor
  development_governor: p7-web-host-development
  precedence:
    - brainstorm-governor owns P0-P6 product decisions and handoff
    - p7-web-host-development owns P7 architecture, scheduling, security, and acceptance
    - external skills are capability-only and cannot override either governor

capabilities:
  development_workflow:
    provider: superpowers@openai-curated
    canonical_skills:
      - writing-plans
      - using-git-worktrees
      - test-driven-development
      - subagent-driven-development
      - verification-before-completion
    constraints:
      - using-git-worktrees requires an authorized isolated-worktree workflow
      - subagent-driven-development is optional and requires delegation to be allowed
      - the bundled brainstorming skill is excluded because brainstorm-governor owns P0-P6

  react_implementation:
    provider: vercel-labs/agent-skills
    canonical_skill: vercel-react-best-practices

  interface_review:
    provider: vercel-labs/agent-skills
    canonical_skill: web-design-guidelines

  api_implementation:
    provider: github/awesome-copilot
    canonical_skill: openapi-to-application-code

  agent_policy:
    provider: github/awesome-copilot
    canonical_skill: agent-governance

  release_security:
    provider: github/awesome-copilot
    canonical_skill: security-review

  playwright_e2e:
    provider: browser@openai-bundled
    canonical_skill: control-in-app-browser
    capability_name: PLAYWRIGHT_E2E

routes:
  architecture:
    required:
      - writing-plans
    optional:
      - using-git-worktrees

  backend:
    required:
      - test-driven-development
      - verification-before-completion
    optional:
      - openapi-to-application-code

  frontend:
    required:
      - vercel-react-best-practices
      - verification-before-completion
    review:
      - web-design-guidelines

  external_capability:
    required:
      - agent-governance
      - test-driven-development
    review:
      - security-review

  integration:
    required:
      - control-in-app-browser
      - verification-before-completion

  release:
    required:
      - security-review
      - verification-before-completion

excluded_from_routing:
  - skill: brainstorming
    provider: superpowers@openai-curated
    reason: brainstorm-governor exclusively owns product brainstorming and P0-P6 contracts
  - capability: full-stack-autonomous-orchestration
    reason: p7-web-host-development remains the development Governor
```

The `PLAYWRIGHT_E2E` capability is provided by the existing `control-in-app-browser` Skill and its Playwright-backed browser API. Do not install a second testing orchestrator solely to obtain a different name. Use it for browser launch, navigation, form interaction, assertions, E2E execution, and failure evidence; P7 remains responsible for mapping that evidence to acceptance IDs.
