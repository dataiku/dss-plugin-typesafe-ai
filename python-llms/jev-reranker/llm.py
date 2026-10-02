from dataiku.llm.python import BaseRerankingModel

from typesafe_jev.client import TypeSafeError
from typesafe_jev.models import JevModel
from typesafe_jev.questions import QuestionSet


def text_of(parts):
    return "".join(p.get("text") or "" for p in parts if p.get("type") == "TEXT")


class JevReranker(JevModel, BaseRerankingModel):
    """Asks whether each document answers the query; the probability of yes is its relevance score."""

    def set_config(self, config, plugin_config):
        super().set_config(config, plugin_config)
        question = {"type": "noul", "instructions": config["rerank_instructions"]}
        yes, no = config.get("rerank_true"), config.get("rerank_false")
        if bool(yes) != bool(no):
            raise TypeSafeError("Reranker: describe both what counts as yes and what counts as no, or neither")
        if yes:
            question["criteria"] = {"true": yes, "false": no}
        self.questions = QuestionSet({"relevant": question})

    def process(self, query, settings, trace):
        text = text_of(query["queryParts"])
        states = [{"query": text, "document": text_of(d.get("parts") or [])} for d in query.get("documents") or []]
        responses = self.client.ask_each(states, self.questions.definitions)
        scores = [self.questions.check(r.get("answers"))["relevant"]["noul"] for r in responses]
        ranked = sorted(({"index": i, "relevanceScore": score} for i, score in enumerate(scores)),
                        key=lambda d: d["relevanceScore"], reverse=True)
        tokens = sum(r["usage"]["input_tokens"] for r in responses)
        cost = self.cost(tokens)
        # DSS bills estimatedCost on the reranking path; totalUsage carries the token counts into the trace.
        return {"documents": ranked, "estimatedCost": cost,
                "totalUsage": {"promptTokens": tokens, "totalTokens": tokens, "estimatedCost": cost}}
