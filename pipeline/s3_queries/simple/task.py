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


class Function(BaseModel):
    function: str = Field(...)
    expected: Any = Field(...)


class SimpleQueryOutput(BaseModel):
    user_query: str = Field(...)
    function_call: str = Field(...)
    function_schema: str = Field(...)
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")


class SimpleQuery(SingletonTemplate):
    """
    A scenario is a collection of tasks that are executed
    """

    scenario: str = Field(..., description="The domain of the scenario")
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    function_schema: str = Field(...)
    num_queries: int

    OutputSchema = SimpleQueryOutput

    def workflow(self):

        builder = WorkflowBuilder(
            scenario=self.scenario,
            function_schema=self.function_schema,
            num_queries=str(self.num_queries),
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

    def callback(self, result: List[TaskResult]) -> List[SimpleQueryOutput]:
        results = []
        for r in result:
            calls = get_tags(r.result, "function_call")
            queries = get_tags(r.result, "user_query")

            for q, c in zip(queries, calls):
                results.append(
                    SimpleQueryOutput(
                        user_query=q,
                        function_call=c,
                        function_schema=self.function_schema,
                        domain=self.domain,
                        subdomain=self.subdomain,
                    )
                )

        return results
