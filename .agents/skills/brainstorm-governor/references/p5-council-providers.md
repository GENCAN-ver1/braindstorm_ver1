# P5 Multi-provider Council Boundary

Read this reference only when a real multi-model Council is requested. Use `scripts/p5_council.py` for configuration, request isolation, adapter registration, result validation, and synthesis admission. This layer remains outside governor core.

## Supported provider profiles

The built-in profiles were verified against official documentation on 2026-08-20. All three expose OpenAI-compatible chat-completion APIs with Bearer authentication:

| Provider | Default China base URL | Credential environment variable | Official documentation |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | [Create Chat Completion](https://api-docs.deepseek.com/api/create-chat-completion) |
| Kimi / Moonshot | `https://api.moonshot.cn/v1` | `MOONSHOT_API_KEY` | [Kimi API quick start](https://platform.kimi.com/docs/overview) |
| MiniMax | `https://api.minimaxi.com/v1` | `MINIMAX_API_KEY` | [OpenAI-compatible text chat](https://platform.minimaxi.com/docs/api-reference/text-chat-openai) |

For international deployments, configure the official regional base URL instead of modifying core code. Kimi documents `https://api.moonshot.ai/v1`; MiniMax documents `https://api.minimax.io/v1`. Model IDs are deliberately not pinned in code because provider catalogs change independently of the governor contract.

## Configuration boundary

Start from `config/council-providers.example.json`. The example is disabled and stores only:

```text
provider
enabled
protocol
base_url
model
credential_env
timeout_seconds
max_output_tokens
provider_options
```

Set `model` explicitly when enabling a provider. `credential_env` contains an environment-variable name, never a secret value. Credential-like keys are rejected inside `provider_options`. The runtime adapter resolves the environment variable immediately before the API call and must not persist it.

Validate a configuration with:

```text
python scripts/p5_council.py validate-config < config/council-providers.example.json
```

## Independence contract

Each Council member receives only:

```text
member_id
provider
shared_frame
question
assigned_dimension
hard_constraints
evidence_summary
output_contract
```

Members never receive peer outputs. One provider cannot impersonate multiple independent members in the same Council run. External evidence is marked `DATA_ONLY` and cannot become provider or governor instruction.

The provider adapter implements:

```text
invoke(config, member_request) -> CouncilMemberResult
```

It returns a normalized output and optional token usage. Raw HTTP/SDK payloads remain transient. Failures return a structured error with no output.

## Synthesis admission

Collect all member results before building `CouncilSynthesisInput`. At least `minimum_successful_members`—never fewer than two—must succeed, and successful members must use distinct providers. Failed providers are excluded without rewriting their result as an opinion.

The external synthesizer receives normalized successful outputs only. It extracts agreements, disagreements, a recommendation, and decisive uncertainties. It cannot write the governor state or change a `LOCKED` decision directly; the main Agent still owns validation, convergence, evidence checks, and persistence.

## Integration sequence

```text
CouncilRuntimeConfig
  → council_readiness
  → prepare_member_requests
  → provider adapters invoke independently
  → validate CouncilMemberResult
  → build_synthesis_input
  → external CouncilSynthesizer
  → main Agent validation and P6 quality gate
```

Use the existing P5 `council_gate` for the final label. Only label the run `COUNCIL` after at least two real independent providers succeed and a named external adapter is configured.

## Current boundary

P5 now defines DeepSeek, Kimi, and MiniMax provider interfaces and validated configuration, but it does not perform HTTP calls. Concrete SDK/HTTP adapters, retries, rate-limit handling, concurrent dispatch, and live cost baselines belong to the full-runtime implementation.

