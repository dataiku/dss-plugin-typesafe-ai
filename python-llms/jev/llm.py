import json

from dataiku.llm.python import BaseLLM

from typesafe_jev.classify import ClassifyPrompt
from typesafe_jev.client import TypeSafeError
from typesafe_jev.mesh import message_text
from typesafe_jev.models import JevModel, parse_request


class JevChatModel(JevModel, BaseLLM):
    """Jev as an LLM Mesh chat model.

    The last user message is a System One request {"state", "questions"}, and the reply is TypeSafe's JSON response.
    Prompts from DSS's Classify text recipe are answered in the format that recipe parses.
    """

    def process(self, query, settings, trace):
        messages = query["messages"]
        classify = ClassifyPrompt.parse(messages)
        if classify:
            response = self.client.ask(classify.state, classify.questions.definitions)
            text = json.dumps(classify.reply(classify.questions.check(response["answers"])))
        else:
            users = [m for m in messages if m.get("role") == "user"]
            text = message_text(users[-1]) if users else ""
            try:
                state, questions = parse_request(text)
            except TypeSafeError as e:
                # DSS's connection test and Prompt Studio users send plain text: reply with an example request.
                # A broken JSON request, or a system prompt such as a Classify text prompt this plugin doesn't
                # recognise, fails instead, so the example is never returned as a row's answer.
                if text.lstrip().startswith("{") or any(m.get("role") == "system" for m in messages):
                    raise
                return {"text": str(e)}
            response = self.client.ask(state, questions)
            text = json.dumps(response)
        prompt_tokens, completion_tokens = response["usage"]["input_tokens"], response["usage"]["output_tokens"]
        return {
            "text": text,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "totalTokens": prompt_tokens + completion_tokens,
            "estimatedCost": self.cost(prompt_tokens),
        }
