import json
import warnings
from typing import List, Type, Any, Dict

from dria import SingletonTemplate
from dria.models import TaskResult
from pydantic import BaseModel, Field

# Suppress dria_workflows "schema" shadows warning
warnings.filterwarnings("ignore", message="Field name \"schema\" in \"Task\" shadows an attribute")
from dria_workflows import *
from dria_workflows.workflows.interface import MessageInput

from dria.factory.utilities import (
    get_tags,
    parse_json,
    get_abs_path,
    extract_backtick_label,
)


class Function(BaseModel):
    function: str = Field(...)
    expected: Any = Field(...)


class MultiTurnOutput(BaseModel):
    trace: List[Dict[str, str]] = Field(...)
    function_schemas: List[str] = Field(...)
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")


class MultiTurnQuery(SingletonTemplate):
    """
    A scenario is a collection of tasks that are executed
    """

    scenario: str = Field(..., description="The domain of the scenario")
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    function_schemas: List[Function]

    OutputSchema = MultiTurnOutput

    def workflow(self):

        builder = WorkflowBuilder(
            scenario=self.scenario,
            function_schemas=json.dumps(
                [f.model_dump() for f in self.function_schemas]
            ),
        )
        builder.set_max_tokens(800)
        builder.set_max_time(85)
        builder.set_max_steps(3)

        builder.generative_step(
            path=get_abs_path("prompt.md"),
            operator=Operator.GENERATION,
            outputs=[Write.new("output")],
        )

        flow = [Edge(source="0", target="_end")]

        builder.flow(flow)
        builder.set_return_value("output")
        return builder.build()

    def callback(self, result: List[TaskResult]) -> List[MultiTurnOutput]:
        results = []
        for r in result:
            # Prefer parsing by <turn> blocks to support multiple calls per turn
            dialogue_blocks = get_tags(r.result, "dialogue")
            traces = []
            if dialogue_blocks:
                dlg = dialogue_blocks[0]
                turn_blocks = get_tags(dlg, "turn")
                if turn_blocks:
                    for tb in turn_blocks:
                        q_blocks = get_tags(tb, "query")
                        if not q_blocks:
                            continue
                        q = q_blocks[0]
                        traces.append({"query": q})
                        fcs = get_tags(tb, "function_call")
                        tls = get_tags(tb, "tool")
                        for c, t in zip(fcs, tls):
                            traces.append({"function_call": c})
                            traces.append({"tool": t})
                else:
                    # Fallback to legacy flat parsing
                    queries = get_tags(dlg, "query")
                    calls = get_tags(dlg, "function_call")
                    tool_response = get_tags(dlg, "tool")
                    for q, c, t in zip(queries, calls, tool_response):
                        traces.append({"query": q})
                        traces.append({"function_call": c})
                        traces.append({"tool": t})
            else:
                # Fallback if no <dialogue> wrapper found
                queries = get_tags(r.result, "query")
                calls = get_tags(r.result, "function_call")
                tool_response = get_tags(r.result, "tool")
                for q, c, t in zip(queries, calls, tool_response):
                    traces.append({"query": q})
                    traces.append({"function_call": c})
                    traces.append({"tool": t})

            results.append(
                MultiTurnOutput(
                    trace=traces,
                    function_schemas=[f.function for f in self.function_schemas],
                    domain=self.domain,
                    subdomain=self.subdomain,
                )
            )

        return results
