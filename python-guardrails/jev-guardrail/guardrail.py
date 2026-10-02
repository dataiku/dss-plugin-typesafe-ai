import dataiku
from dataiku.llm.guardrails import BaseGuardrail

from typesafe_jev.mesh import JevMesh, message_text
from typesafe_jev.questions import GuardrailChecks


class JevGuardrail(BaseGuardrail):
    """Checks prompts and/or responses with yes/no Jev questions; blocks or audits when one is flagged."""

    def set_config(self, config, plugin_config):
        self.config = config
        self.checks = {}
        if config.get("check_queries"):
            self.checks["query"] = GuardrailChecks.from_form(config["query_checks"])
        if config.get("check_responses"):
            self.checks["response"] = GuardrailChecks.from_form(config["response_checks"])
        self.jev = JevMesh(dataiku.api_client().get_default_project().get_llm(config["llm"]))

    def process(self, input, trace):
        if "completionQuery" not in input:
            return input
        direction = "response" if "completionResponse" in input else "query"
        checks = self.checks[direction]
        messages = input["completionQuery"].get("messages") or []
        state = {"conversation": [{"role": m.get("role"), "text": message_text(m)}
                                  for m in messages if m.get("role") != "system"]}
        if direction == "response":
            state["response"] = input["completionResponse"].get("text")
        result, _latency_ms = self.jev.ask_traced(state, checks, trace, "TYPESAFE_JEV_GUARDRAIL_CHECK")
        answers = result.answers
        audit = [{"typesafeCheck": name, "typesafeNoul": answers[name]["noul"],
                  "typesafeThreshold": checks.thresholds[name], "typesafeDirection": direction} for name in answers]
        flagged = checks.flagged(answers)
        key = direction + "GuardrailResponse"
        if not flagged:
            input[key] = {"action": "PASS"}
        elif self.config["mode"] == "AUDIT":
            input[key] = {"action": "PASS_WITH_AUDIT", "auditData": audit}
        else:
            reasons = ", ".join("%s %.2f ≥ %.2f" % (name, answers[name]["noul"], checks.thresholds[name])
                                for name in flagged)
            input[key] = {"action": "FAIL", "auditData": audit,
                          "error": {"errorType": "TypeSafeGuardrail",
                                    "message": "TypeSafe %s check flagged: %s" % (direction, reasons)}}
        return input
