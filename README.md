# TypeSafe AI Plugin

This Dataiku DSS plugin brings System One decision models to the LLM Mesh: [TypeSafe](https://typesafe.ai)'s Jev, and decision models from OpenRouter, Cloudflare, OpenAI and Microsoft Foundry. It provides a Structured Visual Agent block, a guardrail and a reranker, all recorded in LLM Mesh usage, cost and traces.

A decision model answers typed questions with probabilities instead of generating text:

- **Yes / No** (`noul`): the probability of yes
- **Choice**: one option, with the probability of each option
- **Score**: a position on 2 to 10 ordered levels

See the [TypeSafe documentation](https://docs.typesafe.ai/primitives) for how to write good questions.

## Components

| Component | Type | What it does |
| --- | --- | --- |
| `Jev Question Set` | Structured Visual Agent block | Asks typed questions about one input in a single call and saves each answer to the agent state |
| `TypeSafe Jev guardrail` | Guardrail | Blocks or audits an LLM call when a yes/no check on the prompt or response reaches its threshold |
| `TypeSafe Jev` | LLM Mesh model (Chat completion) | Answers a TypeSafe request; used by the Structured Visual Agent block and the guardrail, and usable in prompt recipes, the Classify text recipe and code |
| `TypeSafe Jev reranker` | LLM Mesh model (Reranking) | Scores each retrieved document by the probability that it answers the query |
| `Decision model provider` | Parameter set | Selects the provider and holds its credentials |

## Prerequisites

- DSS 15.0 or later.
- The DSS built-in Python environment, which provides `requests`, the plugin's only third-party dependency. The plugin has no code environment of its own.
- Credentials for each hosted provider you use, for example a TypeSafe API key from the [TypeSafe console](https://console.typesafe.ai/settings/keys).

## Installation

Install from **Plugins > Add Plugin > From Git repository**, or run `make plugin` and upload `dist/dss-plugin-typesafe-ai-<version>.zip`.

Then:

1. In **Plugins > TypeSafe AI > Settings**, add a *Decision model provider* preset for each provider you use (see [Providers](#providers)).
2. In **Administration > Connections**, create a *Custom LLM* connection. For TypeSafe, name it `typesafe` and add two models, both using the preset:
   - id `jev`, type *TypeSafe Jev*, capability *Chat completion*
   - id `jev-reranker`, type *TypeSafe Jev reranker*, capability *Reranking*

The block and the guardrail default to `custom:typesafe:jev`; point them at another connection's model to use another provider. On each model, **Model** names the model to call: for TypeSafe it defaults to `jev-latest`, and you should pin a version such as `jev-1.13.0` once you have tuned thresholds on it. **Cost per million input tokens** feeds LLM Mesh cost tracking; set it to your contract.

The models retry connection errors, rate limits (429) and server errors up to 4 times with backoff, honoring `retry-after`. They don't retry timeouts, and the connection's LLM Mesh retry settings don't add retries on top.

## Providers

Each *Decision model provider* preset selects one provider. The LLM Mesh model that uses it names the model to call in its **Model** setting.

| Provider | Preset fields | Model setting | Notes |
| --- | --- | --- | --- |
| TypeSafe | API key; base URL only for a private endpoint | `jev-latest`, or a pinned version such as `jev-1.13.0` | |
| OpenRouter | API key | an OpenRouter model id, such as `perplexity/pplx-decider-v1.2` or `inception/mercury-decide` | Any decision model OpenRouter serves, through its System One API |
| Cloudflare Workers AI | API token, account ID | `clef` or `clef-flash` | |
| OpenAI Decisions API | API key | `gpt-6-luna` | The API has no field for yes/no criteria, so they are appended to the question text |
| Microsoft Foundry | API key, resource endpoint | your Microsoft-Decision-1 deployment name | |

Every provider returns the same answer shape, so the block, the guardrail, the reranker and code work the same whichever model answers. Set **Cost per million input tokens** on each model to that provider's price.

## Usage

### Structured Visual Agent: Jev Question Set block

- **Judge**: the latest user message, or a top-level agent state or scratchpad value (**Input key**).
- **Questions**: one row per question, with a name, a type, the question and its yes/no criteria, options or levels.
- **Save details as** (default `jev_judgments`).

Each answer is saved to the agent state under its question name, ready for a **Routing** block, for example `state["urgency"] >= 1.5 and state["team"] == "technical"`. The full answers, model, token usage and latency are saved under `jev_judgments`, and a readable summary under `jev_judgments_summary`.

All questions go in one call, so no question sees another's answer.

### TypeSafe Jev guardrail

Add it to the guardrails of an LLM connection, a prompt recipe or a retrieval-augmented LLM.

- **Check prompts** / **Check responses**: one or more yes/no checks for each, each with a **Threshold**: the check flags the call when the probability of yes is at least that value. The checks for one direction go in a single call.
- **When a check is flagged**: block the call, or let it through and record the probabilities as audit data.

If the TypeSafe call fails, block mode blocks the LLM call, and audit mode lets it through with the error in the audit data.

### TypeSafe Jev reranker

Select `custom:typesafe:jev-reranker` as the reranking model of a retrieval-augmented LLM or a Knowledge Bank search tool. The relevance question and its yes/no criteria can be changed in the model settings.

### Prompt recipes

The prompt must be a TypeSafe request, and the response is TypeSafe's JSON answer. Set the recipe's output validation to *JSON object*.

```json
{"state": "{{ticket_text}}", "questions": {"is_bug": {"type": "noul", "instructions": "Does the ticket report a product defect?"}}}
```

### Classify text recipe

Select `custom:typesafe:jev` as the LLM of a Classify text recipe with user-provided classes. Jev picks one of the classes, with a *none fits* option. The recipe only sends class names, and its output has no probabilities.

### From code

```python
import dataiku

dataiku.use_plugin_libs("typesafe-ai")
from typesafe_jev import JevMesh, QuestionSet

jev = JevMesh(dataiku.api_client().get_default_project().get_llm("custom:typesafe:jev"))
questions = QuestionSet({
    "team": {
        "type": "choice",
        "instructions": "Which team should own the request?",
        "criteria": {"billing": "Payments", "technical": "Defects", "general": "Anything else"},
    }
})

result = jev.ask("I was charged twice.", questions)
result.answers["team"]["choice"], result.answers["team"]["confidence"], result.cost_usd
```

`jev.ask_each(states, questions)` sends several inputs in one LLM Mesh batch and returns a `JevResult` or a `TypeSafeError` for each.

## Data handling

Inputs and questions are sent to the selected provider's API outside your DSS instance. Probabilities are not guarantees: fit thresholds on your own labelled data before relying on them.

## Release notes

See the [changelog](CHANGELOG.md) for a history of notable changes to this plugin.

## License

Copyright 2026 Dataiku SAS

This plugin is distributed under the [Apache License version 2.0](LICENSE).
