from typing import List, Type, Any, Dict

from dria import SingletonTemplate
from dria.models import TaskResult
from pydantic import BaseModel, Field

from dria_workflows import *
from dria.factory.utilities import (
    get_tags,
    parse_json,
    get_abs_path,
    extract_backtick_label,
)
from .parser import parse_signature


class Function(BaseModel):
    function: str = Field(...)
    expected: Any = Field(...)


class FunctionsOutput(BaseModel):
    scenario: str = Field(..., description="The domain of the scenario")
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    functions: List[Function] = Field(...)


class Functions(SingletonTemplate):
    """
    A scenario is a collection of tasks that are executed
    """

    scenario: str = Field(..., description="The domain of the scenario")
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    OutputSchema = FunctionsOutput

    def workflow(self):

        builder = WorkflowBuilder(
            scenario=self.scenario
            # num_queries=str(self.num_queries),
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

    def callback(self, result: List[TaskResult]) -> List[FunctionsOutput]:
        results = []
        for r in result:
            fs = get_tags(r.result, "function")

            functions = []
            for function in fs:
                signature = get_tags(function, "signature")[0]
                expected = get_tags(function, "expected")[0]

                schema = extract_backtick_label(signature, "python")[0]
                parsed = parse_signature(schema)
                return_type = parsed["return_type"]
                if "list" in return_type.lower() or "dict" in return_type.lower():
                    expected = parse_json(expected)
                elif return_type == "int":
                    expected = int(expected)
                elif return_type == "float":
                    expected = float(expected)
                elif return_type == "bool":
                    expected = bool(expected)
                elif return_type == "None":
                    expected = None
                else:
                    expected = str(expected).strip()
                functions.append(Function(function=schema, expected=expected))

            results.append(
                FunctionsOutput(
                    scenario=self.scenario,
                    domain=self.domain,
                    subdomain=self.subdomain,
                    functions=functions,
                )
            )

        return results
