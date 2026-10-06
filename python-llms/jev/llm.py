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
            try:
                state, questions = parse_request(message_text(users[-1]) if users else None)
            except TypeSafeError as e:
                # DSS's connection test and Prompt Studio users send plain text: reply with an example request.
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
