You are tasked with generating user queries and corresponding parameters as a function call for a given function. The function is defined as follows:

{{function_schema}}

Your task is to:

1. Generate a realistic user query that would require the use of this function. User query should explicitly state special names in double quotes.
2. Based on the user query you generated, provide appropriate parameters for the function as a function call
3. generate num_query distinct query-param pairs.

Use following format for function_call:

<function_call>
variable_name = function_name(param_1=value, param_2=value)
</function_call>

<user_query>
[Insert the generated user query here]
</user_query>
<function_call>
[Insert the function params here]
</function_call>

Ensure that the user query is relevant to the function's purpose and that the function parameters accurately reflect the requirements specified in the user query.

Generate {{num_queries}} different queries