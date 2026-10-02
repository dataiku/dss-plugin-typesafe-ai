"""Asking a Jev chat model of the LLM Mesh."""
import json
from dataclasses import dataclass

from typesafe_jev.client import TypeSafeError


def message_text(message):
    """Text of an LLM Mesh chat message: content, TEXT parts or tool outputs."""
    if message.get("content") is not None:
        return message["content"]
    texts = [p.get("text") or "" for p in message.get("parts") or [] if p.get("type") == "TEXT"]
    texts += [o.get("output") or "" for o in message.get("toolOutputs") or []]
    return "\n".join(texts)


@dataclass
class JevResult:
    answers: dict
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class JevMesh:
    """A Jev chat model of the LLM Mesh, e.g. project.get_llm("custom:typesafe:jev")."""

    def __init__(self, llm):
        self.llm = llm

    @staticmethod
    def request(state, questions):
        return json.dumps({"state": state, "questions": questions.definitions}, default=str)

    def completion(self, state, questions):
        return self.llm.new_completion().with_message(self.request(state, questions))

    @staticmethod
    def result(response, questions):
        if not response.success:
            raise TypeSafeError(response.get_raw().get("errorMessage") or "LLM Mesh call failed")
        try:
            payload = json.loads(response.text)
            answers = payload["answers"]
        except (TypeError, ValueError, KeyError) as e:
            raise TypeSafeError("Not a TypeSafe response, is this LLM the Jev model? Got: %s"
                                % (response.text or "")[:200]) from e
        usage = response.total_usage
        return JevResult(answers=questions.check(answers), model=payload["model"], input_tokens=usage["promptTokens"],
                         output_tokens=usage["completionTokens"], cost_usd=usage["estimatedCost"])

    def ask(self, state, questions):
        return self.result(self.completion(state, questions).execute(), questions)

    def ask_each(self, states, questions):
        """One LLM Mesh batch; each item is a JevResult, or the TypeSafeError for that state."""
        completions = self.llm.new_completions()
        for state in states:
            completions.new_completion().with_message(self.request(state, questions))
        results = []
        for response in completions.execute().responses:
            try:
                results.append(self.result(response, questions))
            except TypeSafeError as e:
                results.append(e)
        return results
