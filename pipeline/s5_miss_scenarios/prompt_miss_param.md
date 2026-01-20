You are tasked with generating a multi-turn function-calling dialogue that includes a **missing parameter** scenario. In this scenario, the user will ask the assistant to perform a task but will NOT provide all required parameters. The assistant must ask for clarification, and then the user provides the missing information.

First, review the following information:

<scenario>
{{scenario}}
</scenario>

Now, familiarize yourself with the available functions:

<functions>
{{function_schemas}}
</functions>

The following function will be used in the missing parameter scenario:

<target_function>
{{target_function}}
</target_function>

The missing parameter(s) that the user will initially omit:

<missing_params>
{{missing_params}}
</missing_params>

Generate a dialogue following these guidelines:

1. Format the dialogue as a sequence of <turn> blocks. Each <turn> contains:
   - Exactly one <query> (the user's message)
   - Zero or more pairs of <function_call> and <tool> tags
   - A <response> tag with the assistant's natural language reply

2. **CRITICAL: Function Calling Rule**
   - For ANY turn where the user asks for information or actions that CAN be handled by available functions AND provides sufficient parameters, the assistant MUST make function calls. DO NOT answer with just natural language if a function can provide the information.
   - The assistant should ONLY respond with pure natural language (no function calls) in these specific cases:
     a) The user's request is missing required parameters (the "miss" turn) - assistant asks for the missing info
     b) The user is just making conversation, thanking, or saying goodbye
   - **IMPORTANT**: When the user provides the missing parameter(s), the assistant MUST immediately call the function with complete parameters

3. **Missing Parameter Turn Requirements:**
   - At least ONE turn must demonstrate the "missing parameter" scenario
   - In this turn, the user asks for something but omits the required parameter(s) listed in <missing_params>
   - **CRITICAL**: The missing parameter(s) must NOT appear anywhere in the previous conversation. The user should not have mentioned this information before.
   - The assistant should NOT call the function but instead ask for the missing information
   - The NEXT turn should have the user provide ONLY the missing parameter(s)
   - After receiving the parameter(s), the assistant can then make the function call

3. The missing parameter turn structure should look like:

<turn>
<query>
[User asks for something but omits required parameter(s) - these parameters must NOT have been mentioned in any previous turn]
</query>
<response>
[Assistant asks for the specific missing parameter(s), explaining why they are needed]
</response>
</turn>

<turn>
<query>
[User provides ONLY the missing parameter value(s), NOT repeating the original request]
</query>
<function_call>
function_name(all_params_including_missing=values)
</function_call>
<tool>
[Expected output]
</tool>
<response>
[Assistant provides the result]
</response>
</turn>

4. Other turns should proceed normally with complete information, building a coherent conversation.

5. Aim for {{total_turns}} total turns, with {{miss_turns}} turn(s) being the "incomplete request + user provides params" pair.

6. For each <response>, write a helpful, natural language summary that:
   - Directly addresses the user's question
   - Summarizes the key information from the tool outputs
   - Maintains a friendly and professional tone

7. Maintain consistency throughout the dialogue, using information from previous function calls.

8. **IMPORTANT**: Ensure the missing parameter(s) are truly "new" information that hasn't appeared anywhere in the conversation before. This makes the scenario realistic - the assistant genuinely doesn't have this information.

Remember:
- Normal turns with complete info = MUST have function calls
- Miss turn (incomplete request) = NO function call, ask for missing parameter(s)
- After user provides parameters = MUST call the function with complete parameters
- Greetings/goodbye = no function call needed

Remember to stay within the context of the given scenario. The missing parameter scenario should feel natural within the conversation flow.

Output your entire response inside <dialogue> tags, containing multiple <turn> blocks as described above.
