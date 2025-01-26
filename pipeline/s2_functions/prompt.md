You are tasked with generating a user query and function signatures based on a given scenario. Follow these steps carefully:

1. Read the following scenario:
<scenario>
{{scenario}}
</scenario>

2. Based on the scenario, generate function signatures that covers the possible queries based on the scenario. For each function, you should provide:
   - Function name
   - Function parameters (name and type for each)
   - Return type for each function
   - Expected return value when function is correctly called


Example output:

<function>
<signature>
```python
def manage_docker_container(container_name: str, action: str) -> str: 
      """Manages Docker containers (start, stop, status). 
                   :param container_name: The name of the Docker container. 
                   :param action: The action to perform ('start', 'stop', 'status'). 
                   :return: A string indicating the result of the action. 
                   :raises ValueError: If an invalid action is provided.
       """ 
       pass
```
</signature>
<expected>
"success"
</expected>
</function>

<function>
<signature>
```python
def analyze_video_performance(video_id: str, target_demographics: list) -> dict: 
"""Analyzes video ad performance metrics for specific demographics. 
:param video_id: Unique identifier for the video ad 
:param target_demographics: List of demographic groups to analyze 
:return: Dictionary containing performance metrics 
  - engagement_rate (float): Percentage of viewers who interacted 
  - completion_rate (float): Percentage of viewers who watched till end
  - conversion_rate (float): Percentage of viewers who took desired action 
:raises ValueError: If video_id is invalid or demographics list is empty""" 
pass 
```
</signature>
<expected>
{"engagement_rate":0.7, "completion_rate":0.9, "conversion_rate": 0.04}
</expected>
</function>


Generate as many functions as you deem necessary to address the user query and scenario, with each function enclosed in its own <function> tags.

Remember to consider the scenario carefully and create functions that would be useful in addressing the user query you generated.