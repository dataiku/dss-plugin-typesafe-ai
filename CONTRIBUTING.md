# Contributing to the TypeSafe AI plugin

Thank you for helping improve this plugin.

## Before making a change

- Search the existing issues before opening a new one.
- For a substantial change, open an issue first so the scope can be agreed. Small fixes can go directly to a pull request.
- Never include API keys, customer data, instance URLs or identifiers copied from a real Dataiku environment.

## Repository layout

| Path | Content |
| --- | --- |
| `plugin.json` | Plugin metadata and version |
| `python-lib/typesafe_jev/` | Shared library: API client, mesh adapter, question and classification logic |
| `python-llms/` | `jev` and `jev-reranker` LLM Mesh connections |
| `python-guardrails/` | Jev guardrail |
| `python-structured-agent-blocks/` | Question Set block for Structured Visual Agents |
| `parameter-sets/` | TypeSafe API key preset |

## Dependencies

The plugin has no code environment: it runs on the DSS built-in Python environment, which provides its only third-party dependency, `requests` (with `urllib3`), along with the `dataiku` package. If a change needs another package, add a plugin code environment (`code-env/python/desc.json` and `code-env/python/spec/requirements.txt`) in the same pull request and update the README prerequisites.

## Code conventions

- Every source file starts with the Apache 2.0 preamble (copy it from any existing `.py` file).
- Fail loudly on malformed data and failed API calls instead of falling back silently.
- Comment only non-obvious code or decisions.

## Opening a pull request

1. Fork the repository and create a focused branch from `master`.
2. Make the smallest coherent change.
3. Update `CHANGELOG.md` and, for a release, the `version` in `plugin.json`.
4. Build the archive with `make` and install it in a DSS instance to check the affected component.
5. Open a pull request against `master` summarizing the behavior changed and the checks you ran.

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE).
