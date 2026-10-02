"""What the Jev chat model and the Jev reranker share."""
import json

from typesafe_jev.client import JevClient, TypeSafeError

EXAMPLE_REQUEST = {
    "state": "I was charged twice for my October invoice.",
    "questions": {
        "is_billing": {"type": "noul", "instructions": "Is the request about billing or payments?"},
        "team": {"type": "choice", "instructions": "Which team should own the request?",
                 "criteria": {"billing": "Payments and invoices", "technical": "Product defects", "general": "Anything else"}},
        "urgency": {"type": "score", "instructions": "How urgent is the request?",
                    "criteria": ["Can wait days", "Needs an answer today", "Blocks work now"]}
    }
}
REQUEST_FORMAT_HINT = (
    "Jev answers typed questions, not free text. Send the last user message as a JSON request like this one:\n\n%s\n\n"
    "Question types: noul (probability of yes), choice (one option), score (ordered levels). "
    "See https://docs.typesafe.ai/primitives" % json.dumps(EXAMPLE_REQUEST, indent=2)
)


def parse_request(text):
    """(state, questions) from a {"state", "questions"} request."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None
    if not isinstance(payload, dict) or "state" not in payload or not isinstance(payload.get("questions"), dict):
        raise TypeSafeError(REQUEST_FORMAT_HINT)
    return payload["state"], payload["questions"]


class JevModel:
    """Base for the plugin's LLM Mesh models: API client and cost tracking."""

    def set_config(self, config, plugin_config):
        self.config = config
        self.client = JevClient.from_preset(config["typesafe_api"], config["model"], int(config["timeout_sec"]))

    def cost(self, tokens):
        return tokens * float(self.config["cost_per_million_input_tokens"]) / 1e6
