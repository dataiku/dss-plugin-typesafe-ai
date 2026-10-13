# Changelog

## Version 1.1.0 - More decision-model providers
- The *Decision model provider* preset (formerly *TypeSafe API key*) now selects a provider: TypeSafe, OpenRouter, Cloudflare Workers AI (Clef, Clef-flash), OpenAI's Decisions API, or Microsoft Foundry (Microsoft-Decision-1)
- Every provider returns TypeSafe's answer shape, so the block, guardrail, reranker and models work unchanged

## Version 1.0.0 - Initial release - 2026-10-02
- TypeSafe Jev chat model and TypeSafe Jev reranker for the LLM Mesh, configured with a TypeSafe API key preset
- Jev Question Set block for Structured Visual Agents
- TypeSafe Jev guardrail for LLM connections, prompt recipes and retrieval-augmented LLMs
- Support for DSS's Classify text recipe and for prompt recipes through the Jev chat model
