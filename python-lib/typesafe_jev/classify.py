"""Answering DSS's Classify text recipe (user-provided classes) with a Jev choice question.

The recipe sends every prompt-driven LLM a fixed prompt: a system message listing {"class_name": ..., "class_id": n}
objects, few-shot user/assistant pairs, then the row as a final user message "text to classify: ...". It parses
{"class_name", "class_id"} back, with "" and -1 when no class fits.
"""
import json
import re

from typesafe_jev.client import TypeSafeError
from typesafe_jev.mesh import message_text
from typesafe_jev.questions import QuestionSet

SYSTEM_PREFIX = "You are a helpful assistant that classifies the following text into one of these classes"
TEXT_PREFIX = "text to classify: "
CLASS_ENTRY = re.compile(r'\{"class_name":(".*?(?<!\\)"),"class_id":(\d+)\}')
DESCRIPTION = re.compile(re.escape(SYSTEM_PREFIX) + r" \((.*?)\): ", re.S)
NO_CLASS = "no_class_fits"


class ClassifyPrompt:
    def __init__(self, text, class_names, description):
        self.state = {"text": text}
        self.class_names = class_names
        instructions = "Which class does the `text` belong to?"
        if description:
            instructions += " The classes describe: %s" % description
        criteria = {name: name for name in class_names}
        criteria[NO_CLASS] = "None of the other classes fits the text"
        self.questions = QuestionSet({"class": {"type": "choice", "instructions": instructions, "criteria": criteria}})

    @classmethod
    def parse(cls, messages):
        """The prompt, if these messages come from the Classify text recipe; None otherwise."""
        system = [message_text(m) for m in messages if m.get("role") == "system"]
        if not system or not system[0].startswith(SYSTEM_PREFIX):
            return None
        names = []
        for name, class_id in CLASS_ENTRY.findall(system[0]):
            if int(class_id) != len(names):
                raise TypeSafeError("Unexpected Classify text prompt: class ids are not 0..n-1")
            names.append(json.loads(name))
        if len(names) < 2:
            raise TypeSafeError("Unexpected Classify text prompt: found %d classes, Jev needs at least 2" % len(names))
        if NO_CLASS in names:
            raise TypeSafeError("Class name '%s' is reserved by the TypeSafe plugin" % NO_CLASS)
        rows = [m for m in messages if m.get("role") == "user" and not m.get("partOfExample")]
        if not rows:
            raise TypeSafeError("Unexpected Classify text prompt: there is no text to classify")
        text = message_text(rows[-1])
        if not text.startswith(TEXT_PREFIX):
            raise TypeSafeError("Unexpected Classify text prompt: the last user message has no '%s' prefix"
                                % TEXT_PREFIX.strip())
        description = DESCRIPTION.match(system[0])
        return cls(text[len(TEXT_PREFIX):], names, description and description.group(1))

    def reply(self, answers):
        choice = answers["class"]["choice"]
        if choice == NO_CLASS:
            return {"class_name": "", "class_id": -1}
        return {"class_name": choice, "class_id": self.class_names.index(choice)}
