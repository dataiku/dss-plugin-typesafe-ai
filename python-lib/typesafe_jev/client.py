# Copyright 2026 Dataiku SAS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Clients for System One decision models: the TypeSafe (https://docs.typesafe.ai/api), OpenRouter, Cloudflare Workers AI,
OpenAI Decisions and Microsoft Foundry APIs."""
import json
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.typesafe.ai"
RETRYABLE_STATUSES = (429, 500, 502, 503, 504, 529)
MAX_PARALLEL_CALLS = 16


class TypeSafeError(Exception):
    pass


class HttpClient:
    """Calls a decision model's HTTP API, retrying connection errors, rate limits and server errors with backoff.

    This is the only retry layer. Timeouts are not retried, and failures are not handed to the LLM Mesh to retry
    again, so a hung API costs one timeout. Subclasses set the URL and authentication and translate requests and
    responses; every client returns TypeSafe's response shape: {"model", "answers", "usage"}.
    """

    LABEL = None
    URL = None

    def __init__(self, api_key, model, timeout, url):
        if not api_key:
            raise TypeSafeError("No API key: set one in the model's decision model provider preset.")
        self.url = url
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.auth_headers(api_key))
        # Judgments have no side effects, so retrying a POST is safe.
        retry = Retry(total=4, read=0, backoff_factor=1, status_forcelist=RETRYABLE_STATUSES,
                      allowed_methods=frozenset(["POST"]), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=MAX_PARALLEL_CALLS)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @classmethod
    def from_preset(cls, preset, model, timeout):
        return cls(preset.get("api_key"), model, timeout, cls.URL)

    def auth_headers(self, api_key):
        return {"Authorization": "Bearer " + api_key}

    def request(self, state, questions):
        return {"state": state, "model": self.model, "questions": questions}

    def response(self, body, questions):
        return body

    def ask(self, state, questions):
        try:
            resp = self.session.post(self.url, json=self.request(state, questions), timeout=self.timeout)
        except requests.RequestException as e:
            raise TypeSafeError("%s call failed: %s" % (self.LABEL, e)) from e
        if resp.status_code != 200:
            raise TypeSafeError("%s returned HTTP %s: %s" % (self.LABEL, resp.status_code, resp.text[:1000]))
        try:
            body = resp.json()
        except ValueError as e:
            raise TypeSafeError("%s returned a response that isn't JSON: %s" % (self.LABEL, resp.text[:200])) from e
        return self.response(body, questions)

    def ask_each(self, states, questions):
        """Asks the same questions about each state, in parallel; responses in the same order."""
        if not states:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_CALLS, len(states))) as pool:
            return list(pool.map(lambda state: self.ask(state, questions), states))


class JevClient(HttpClient):
    """TypeSafe's System One API."""

    LABEL = "TypeSafe API"

    @classmethod
    def from_preset(cls, preset, model, timeout):
        base_url = (preset.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        return cls(preset.get("api_key"), model, timeout, base_url + "/v1/systemone")


class OpenRouterClient(HttpClient):
    """OpenRouter's System One API (https://openrouter.ai/docs/guides/community/jev): TypeSafe's format for every decision
    model OpenRouter serves. `model` is OpenRouter's model id, such as perplexity/pplx-decider-v1.2."""

    LABEL = "OpenRouter"
    URL = "https://openrouter.ai/api/v1/systemone"


class CloudflareClient(HttpClient):
    """Cloudflare Workers AI (Clef, Clef-flash): TypeSafe's request format, wrapped in Cloudflare's envelope."""

    LABEL = "Cloudflare Workers AI"
    URL = "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/@cf/cloudflare/%s"

    @classmethod
    def from_preset(cls, preset, model, timeout):
        return cls(preset.get("api_key"), model, timeout, cls.URL % (preset["account_id"], model))

    def response(self, body, questions):
        if not body["success"]:
            raise TypeSafeError("%s returned errors: %s" % (self.LABEL, body["errors"]))
        return body["result"]


class OpenAIDecisionsClient(HttpClient):
    """OpenAI's Decisions API (https://developers.openai.com/api/docs/guides/decisions).

    noul questions become predicates; a predicate has no yes/no criteria, so they are appended to its instructions.
    """

    LABEL = "OpenAI Decisions API"
    URL = "https://api.openai.com/v1/decisions"

    def request(self, state, questions):
        return {"model": self.model, "input": state if isinstance(state, str) else json.dumps(state),
                "questions": [self._question(name, q) for name, q in questions.items()]}

    @staticmethod
    def _question(name, q):
        if q["type"] == "noul":
            instructions = q["instructions"]
            if q.get("criteria"):
                instructions += " Yes: %s No: %s" % (q["criteria"]["true"], q["criteria"]["false"])
            return {"type": "predicate", "name": name, "instructions": instructions}
        if q["type"] == "choice":
            return {"type": "choice", "name": name, "instructions": q["instructions"],
                    "choices": [{"value": k, "description": v} for k, v in q["criteria"].items()]}
        return {"type": "score", "name": name, "instructions": q["instructions"],
                "levels": [{"label": "Level %d" % i, "description": d} for i, d in enumerate(q["criteria"])]}

    def response(self, body, questions):
        answers = {}
        for a in body["answers"]:
            if a["type"] == "predicate":
                answers[a["name"]] = {"type": "noul", "noul": a["probability"]}
            elif a["type"] == "choice":
                answers[a["name"]] = {"type": "choice", "choice": a["choice"], "confidence": a["confidence"],
                                      "probabilities": {p["value"]: p["probability"] for p in a["probabilities"]}}
            else:
                answers[a["name"]] = {"type": "score", "score": a["score"], "confidence": a["confidence"],
                                      "probabilities": {str(p["value"]): p["probability"] for p in a["probabilities"]},
                                      "legend": {str(i): d for i, d in enumerate(questions[a["name"]]["criteria"])}}
        return {"model": body["model"], "answers": answers,
                "usage": {"input_tokens": body["usage"]["input_tokens"], "output_tokens": 0}}


class FoundryClient(HttpClient):
    """Microsoft Foundry (Microsoft-Decision-1): TypeSafe's request format at the Microsoft provider's systemone path,
    authenticated with an api-key header. `model` is the Foundry deployment name."""

    LABEL = "Microsoft Foundry"

    @classmethod
    def from_preset(cls, preset, model, timeout):
        url = preset["endpoint"].rstrip("/") + "/providers/microsoft/v1/systemone"
        return cls(preset.get("api_key"), model, timeout, url)

    def auth_headers(self, api_key):
        return {"api-key": api_key}


PROVIDERS = {
    "typesafe": JevClient,
    "openrouter": OpenRouterClient,
    "cloudflare": CloudflareClient,
    "openai": OpenAIDecisionsClient,
    "foundry": FoundryClient,
}


def client_from_preset(preset, model, timeout):
    """The client for the preset's provider. Presets saved before the provider setting existed are TypeSafe presets."""
    provider = preset.get("provider", "typesafe")
    if provider not in PROVIDERS:
        raise TypeSafeError("Unknown provider '%s' in the decision model provider preset" % provider)
    return PROVIDERS[provider].from_preset(preset, model, timeout)
