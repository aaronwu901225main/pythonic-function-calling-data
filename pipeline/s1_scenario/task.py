from typing import List, Type

from dria import SingletonTemplate
from dria.models import TaskResult
from pydantic import BaseModel, Field

from dria_workflows import *
from dria.factory.utilities import get_tags, get_abs_path


class ScenarioOutput(BaseModel):
    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    entities: str = Field(..., description="The entities in the scenario")
    scenario: str = Field(..., description="List of generated instructions")


class Scenario(SingletonTemplate):
    """
    A scenario is a collection of tasks that are executed
    """

    domain: str = Field(..., description="The domain of the scenario")
    subdomain: str = Field(..., description="The subdomain of the scenario")
    num_scenarios: int = Field(default=10, description="The number of scenarios")
    entities: str = Field(..., description="The entities in the scenario")

    OutputSchema = ScenarioOutput

    def workflow(self):

        builder = WorkflowBuilder(
            domain=self.domain,
            subdomain=self.subdomain,
            entities=self.entities,
            num_scenarios=str(self.num_scenarios),
        )
        builder.set_max_tokens(850)
        builder.set_max_time(105)
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

    def callback(self, result: List[TaskResult]) -> List[ScenarioOutput]:
        results = []
        for r in result:
            scenario = get_tags(r.result, "scenario")
            for sce in scenario:
                results.append(
                    ScenarioOutput(
                        domain=self.domain,
                        subdomain=self.subdomain,
                        entities=self.entities,
                        scenario=sce.strip(),
                    )
                )
        return results
