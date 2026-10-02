import time

from dataiku.llm.python.blocks_graph import BlockHandler, NextBlock

from typesafe_jev.mesh import JevMesh, message_text
from typesafe_jev.questions import QuestionSet, required


class QuestionSetBlock(BlockHandler):
    """Asks typed questions about one input in one Jev call, and saves each answer to the agent state."""

    def process_stream(self, trace):
        config = self.block_config["config"]
        output_key = required(config.get("output_key"), "Save details as")
        questions = QuestionSet.from_config(config)
        if output_key in questions or output_key + "_summary" in questions:
            raise ValueError("'Save details as' must differ from the question names")
        state = self._input(config)
        jev = JevMesh(self.agent.project.get_llm(required(config.get("llm"), "TypeSafe Jev model")))

        with trace.subspan("DKU_AGENT_LLM_CALL") as llm_trace:
            started = time.monotonic()
            response = jev.completion(state, questions).execute()
            latency_ms = round((time.monotonic() - started) * 1000, 1)
            if response.trace:
                llm_trace.append_trace(response.trace)
        result = jev.result(response, questions)

        summary = questions.summary(result.answers)
        for name, answer in result.answers.items():
            self.turn.state_set(name, answer[answer["type"]])
        self.turn.state_set(output_key, {"answers": result.answers, "model": result.model, "latency_ms": latency_ms,
                                         "usage": {"input_tokens": result.input_tokens,
                                                   "output_tokens": result.output_tokens}})
        self.turn.state_set(output_key + "_summary", summary)
        self.record_inspector_input({"input_source": config.get("input_source"), "questions": questions.definitions})
        self.record_inspector_output(summary)
        self.record_inspector_metadata(model=result.model, inputTokens=result.input_tokens,
                                       outputTokens=result.output_tokens, latencyMs=latency_ms)
        yield NextBlock(self.block_config["defaultNextBlock"])

    def _input(self, config):
        source = config["input_source"]
        if source == "latest_user":
            users = [m for m in self.turn.initial_messages if m.get("role") == "user"]
            value = message_text(users[-1]).strip() if users else None
        elif source == "state":
            value = self.turn.state_get(required(config.get("input_key"), "Input key"))
        elif source == "scratchpad":
            value = self.sequence_context.scratchpad.get(required(config.get("input_key"), "Input key"))
        else:
            raise ValueError("Unknown input source: %s" % source)
        if value is None or value == "":
            raise ValueError("Nothing to judge: the %s is empty" % source.replace("_", " "))
        return value
