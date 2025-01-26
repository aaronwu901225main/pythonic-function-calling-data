You are tasked with generating parallel user queries and corresponding parameters as a function call for a given function. 

A parallel query is a single query that requires calling the same function with different parameters multiple times.

The function is defined as follows:

{{function_schema}}


Your task is to:

1. Generate a realistic user query that would require the use of this function with different parameters. User query should explicitly state special names in double quotes.
3. Based on the user query you generated, provide appropriate parameters for the function as a function call
4. generate num_query distinct query-function pairs.

Use following format for function_calls:

<function_calls>
variable_name = function_name(param_1=value, param_2=value)
</function_calls>

<user_query>
[Insert the generated parallel user query here]
</user_query>
<function_calls>
[Insert function calls here]
</function_calls>

Example #1:

<user_query>
I'm doing a bit of market research and I have a list of Amazon Standard Identification Numbers (ASINs) for products I'm interested in: 'B075H2B962', 'B08BHXG144', 'B07ZPKBL9V', and 'B08PPDJWC8'. Could you look up the product names for these ASINs to streamline my analysis?
</user_query>
<function_calls>
product_1 = get_product_name_by_amazon_ASIN(ASIN='B075H2B962')
product_2 = get_product_name_by_amazon_ASIN(ASIN='B08BHXG144')
product_3 = get_product_name_by_amazon_ASIN(ASIN='B07ZPKBL9V')
product_4 = get_product_name_by_amazon_ASIN(ASIN='B08PPDJWC8')
</function_calls>

Example #2:

<user_query>
Please sort the list [5, 2, 9, 1, 7] in ascending order, [3, 8, 6, 4] in descending order, [10, 20, 30, 40, 50] in ascending order, and [100, 200, 300, 400, 500] in descending order.
</user_query>
<function_calls>
sorted_1_ascending = sort_array(array=[5, 2, 9, 1, 7])
sorted_1_descending= sort_array(array=[3, 8, 6, 4], reverse=True)
sorted_2_ascending = sort_array(array=[10, 20, 30, 40, 50])
sorted_2_descending = sort_array(array=[100, 200, 300, 400, 500], reverse=True)
</function_calls>


Ensure that the user query is relevant to the function's purpose and that the function parameters accurately reflect the requirements specified in the user query.

Generate {{num_queries}} different queries