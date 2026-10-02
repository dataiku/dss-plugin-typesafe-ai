"""Typed questions (noul, choice, score) and the answers Jev returns for them.

See https://docs.typesafe.ai/primitives
"""
import json
import re

from typesafe_jev.client import TypeSafeError

QUESTION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
QUESTION_TYPES = ("noul", "choice", "score")


def required(value, label):
    if not isinstance(value, str) or not value.strip():
        raise TypeSafeError("%s is required" % label)
    return value.strip()


class QuestionSet:
    """Named questions about one input, sent to Jev in a single call."""

    def __init__(self, questions):
        if not isinstance(questions, dict) or not questions:
            raise TypeSafeError('Questions must be a non-empty JSON object: {"<name>": {"type": ..., "instructions": ...}}')
        for name, question in questions.items():
            self._validate(name, question)
        self.definitions = questions

    @staticmethod
    def _validate(name, question):
        if not QUESTION_NAME.fullmatch(name):
            raise TypeSafeError("Question name '%s' must start with a letter and contain only letters, digits or "
                                "underscores" % name)
        kind = (question or {}).get("type")
        if kind not in QUESTION_TYPES:
            raise TypeSafeError("Question '%s': type must be noul, choice or score, got %r" % (name, kind))
        if not question.get("instructions"):
            raise TypeSafeError("Question '%s': instructions are missing" % name)
        criteria = question.get("criteria")
        if kind == "choice" and not (isinstance(criteria, dict) and len(criteria) >= 2):
            raise TypeSafeError("Question '%s': a choice needs at least 2 options" % name)
        if kind == "score" and not (isinstance(criteria, list) and 2 <= len(criteria) <= 10):
            raise TypeSafeError("Question '%s': a score needs 2 to 10 levels" % name)

    @classmethod
    def from_config(cls, config):
        """From a component's Questions form, or its raw JSON."""
        if config.get("questions_mode") == "JSON":
            try:
                questions = json.loads(config.get("questions_json") or "")
            except ValueError as e:
                raise TypeSafeError("Questions JSON is not valid JSON: %s" % e) from e
            return cls(questions)
        return cls.from_form(config.get("questions") or [])

    @classmethod
    def from_form(cls, rows):
        questions = {}
        for row in rows:
            name = required(row.get("id"), "Question name")
            if name in questions:
                raise TypeSafeError("Question name '%s' is used twice" % name)
            questions[name] = cls._question_from_row(name, row)
        return cls(questions)

    @staticmethod
    def _question_from_row(name, row):
        kind = row.get("type")
        question = {"type": kind, "instructions": required(row.get("instructions"), "Question '%s'" % name)}
        if kind == "noul":
            yes, no = (row.get("yes_criteria") or "").strip(), (row.get("no_criteria") or "").strip()
            if bool(yes) != bool(no):
                raise TypeSafeError("Question '%s': describe both yes and no, or neither" % name)
            if yes:
                question["criteria"] = {"true": yes, "false": no}
        elif kind == "choice":
            options = {}
            for option in row.get("options") or []:
                key = required(option.get("key"), "Question '%s': option" % name)
                if key in options:
                    raise TypeSafeError("Question '%s': option '%s' is used twice" % (name, key))
                options[key] = required(option.get("description"), "Question '%s': option '%s'" % (name, key))
            question["criteria"] = options
        elif kind == "score":
            question["criteria"] = [required(level.get("description"), "Question '%s': level" % name)
                                    for level in row.get("levels") or []]
        return question

    def __contains__(self, name):
        return name in self.definitions

    def check(self, answers):
        """Jev's answers, verified to cover every question with the expected type."""
        if set(answers) != set(self.definitions):
            raise TypeSafeError("Jev answered %s, expected %s" % (sorted(answers), sorted(self.definitions)))
        checked = {}
        for name, answer in answers.items():
            kind = self.definitions[name]["type"]
            if answer.get("type") != kind or kind not in answer:
                raise TypeSafeError("Question '%s': expected a %s answer, got %s" % (name, kind, json.dumps(answer)[:200]))
            checked[name] = {"type": kind, kind: answer[kind]}
            if kind != "noul":
                checked[name]["confidence"] = answer["confidence"]
                checked[name]["probabilities"] = answer["probabilities"]
            if kind == "score":
                checked[name]["legend"] = answer["legend"]
        return checked

    def summary(self, answers):
        """One markdown line per checked answer."""
        lines = []
        for name, answer in answers.items():
            kind = answer["type"]
            if kind == "noul":
                lines.append("- **%s:** P(yes) %.2f" % (name, answer["noul"]))
                continue
            distribution = ", ".join("%s %.0f%%" % (k, 100 * v) for k, v in answer["probabilities"].items())
            if kind == "choice":
                lines.append("- **%s:** %s · confidence %.2f · options: %s"
                             % (name, answer["choice"], answer["confidence"], distribution))
            else:
                top = len(self.definitions[name]["criteria"]) - 1
                lines.append("- **%s:** score %.2f / %d · confidence %.2f · levels: %s"
                             % (name, answer["score"], top, answer["confidence"], distribution))
        return "\n".join(lines)


class GuardrailChecks(QuestionSet):
    """Yes/no checks, each flagged when the probability of yes reaches its threshold."""

    def __init__(self, questions, thresholds):
        super().__init__(questions)
        self.thresholds = thresholds

    @classmethod
    def from_form(cls, rows):
        if not rows:
            raise TypeSafeError("Add at least one check, or turn this direction off")
        questions = QuestionSet.from_form([dict(row, type="noul") for row in rows]).definitions
        thresholds = {}
        for row in rows:
            threshold = row.get("threshold")
            if threshold is None or not 0 <= float(threshold) <= 1:
                raise TypeSafeError("Check '%s': the threshold must be between 0 and 1" % row["id"])
            thresholds[row["id"].strip()] = float(threshold)
        return cls(questions, thresholds)

    def flagged(self, answers):
        return [name for name, answer in answers.items() if answer["noul"] >= self.thresholds[name]]
