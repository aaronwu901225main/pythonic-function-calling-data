You are tasked with generating a multi-turn function-calling dialogue that includes a **missing function** scenario. In this scenario, the user will ask the assistant to perform a task that requires a function NOT currently available in the tool list. The assistant must recognize that the required function is missing and inform the user. Then, the user will provide the missing function definition, and the assistant can proceed.

First, review the following information:

<scenario>
{{scenario}}
</scenario>

Now, familiarize yourself with the available functions:

<functions>
{{function_schemas}}
</functions>

The following function will be MISSING from the tool list initially, but will be provided by the user later:

<missing_function>
{{missing_function}}
</missing_function>

Generate a dialogue following these guidelines:

1. Format the dialogue as a sequence of <turn> blocks. Each <turn> contains:
   - Exactly one <query> (the user's message)
   - Zero or more pairs of <function_call> and <tool> tags
   - A <response> tag with the assistant's natural language reply

2. **CRITICAL: Function Calling Rule**
   - For ANY turn where the user asks for information or actions that CAN be handled by available functions, the assistant MUST make function calls. DO NOT answer with just natural language if a function can provide the information.
   - The assistant should ONLY respond with pure natural language (no function calls) in these specific cases:
     a) The user's request requires the MISSING function (the "miss" turn) - before user provides it
     b) The user is just making conversation, thanking, or saying goodbye
   - **IMPORTANT**: When the user provides the missing function definition, the assistant MUST immediately call that newly provided function to fulfill the original request

3. **Missing Function Turn Requirements:**
   - Exactly ONE turn pair must demonstrate the "missing function" scenario
   - In the FIRST turn of the pair: the user asks for something that SPECIFICALLY requires the missing function (not any available function)
   - The assistant recognizes it cannot fulfill the request because the needed function is missing, and asks the user to provide it
   - In the SECOND turn of the pair: the user provides the function definition **in JSON schema format** (same format as the tool list)
   - The assistant then calls the newly provided function

4. The missing function turn structure should look like:

<turn>
<query>
[User asks for something that SPECIFICALLY requires the missing function - this request cannot be fulfilled by any available function]
</query>
<response>
[Assistant explains it cannot perform this SPECIFIC task because the required function is not available, and asks the user to provide it. Be specific about what capability is missing.]
</response>
</turn>

<turn>
<query>
[User provides the missing function definition in JSON schema format, for example:]

好的，這是函數定義：
```json
{
  "name": "function_name",
  "description": "函數描述",
  "parameters": {
    "type": "dict",
    "properties": {
      "param1": {"type": "string", "description": "參數描述"}
    },
    "required": ["param1"]
  }
}
```
</query>
<function_call>
missing_function_name(param1=value1, ...)
</function_call>
<tool>
[Expected output of the missing function]
</tool>
<response>
[Assistant acknowledges receiving the function, executes it, and provides results]
</response>
</turn>

5. **Normal turns (non-miss) MUST use function calls.** Example of a CORRECT normal turn:

<turn>
<query>
[User asks for meeting details]
</query>
<function_call>
get_meeting_details(meeting_id=123)
</function_call>
<tool>
{"meeting_id": 123, "participants": ["Alice", "Bob"], ...}
</tool>
<response>
[Assistant summarizes the meeting details from the function output]
</response>
</turn>

6. Aim for {{total_turns}} total turns. The missing function scenario should occur naturally in the middle of the conversation (not at the very beginning).

7. For each <response>, write a helpful, natural language summary that:
   - Directly addresses the user's question
   - Summarizes the key information from the tool outputs (when functions are called)
   - Maintains a friendly and professional tone

8. Maintain consistency throughout the dialogue, using information from previous function calls.

Remember:
- Normal turns = MUST have function calls (unless it's just conversation/greetings)
- Miss turn = NO function call because the required function doesn't exist yet
- After user provides function = MUST call the newly provided function to complete the task

Output your entire response inside <dialogue> tags, containing multiple <turn> blocks as described above.
