import json
from pocketflow import Node, Flow, AsyncNode
#from utils import call_llm, get_tools, exec_steps
import yaml
import sys
from utils.stream_llm import stream_llm
from utils.mcp import *

class GetToolsNode(AsyncNode):
    async def prep_async(self, shared):
        """Initialize and get tools"""
        #user_message = shared.get("user_message", "")
        websocket = shared.get("websocket")
        
        #conversation_history = shared.get("conversation_history", [])
        #conversation_history.append({"role": "user", "content": user_message})
        
        return websocket

    async def exec_async(self, prep_res):
        """Retrieve tools from the MCP server"""
        websocket = prep_res
        
        await websocket.send_text(json.dumps({"type": "start", "content": ""}))
        
        tools = await mcp_get_tools()
        print(tools)
        #await websocket.send_text(json.dumps(tools))
        #await websocket.send_text(json.dumps({"type": "end", "content": ""}))
        return tools

    async def post_async(self, shared, prep_res, exec_res):
        """Store tools and process to decision node"""
        tools = exec_res
        shared["tools"] = tools
        
        # Format tool information for later use
        tool_info = []
        for i, tool in enumerate(tools, 1):
            properties = tool.inputSchema.get('properties', {})
            required = tool.inputSchema.get('required', [])
            
            params = []
            for param_name, param_info in properties.items():
                param_type = param_info.get('type', 'unknown')
                req_status = "(Required)" if param_name in required else "(Optional)"
                params.append(f"    - {param_name} ({param_type}): {req_status}")
            
            tool_info.append(f"[{i}] {tool.name}\n  Description: {tool.description}\n  Parameters:\n" + "\n".join(params))
        
        shared["tool_info"] = "\n".join(tool_info)
        return "decide"

class DecideToolNode(AsyncNode):
    async def prep_async(self, shared):
        """Prepare the prompt for LLM to process the question"""
        tool_info = shared["tool_info"]
        question = shared["user_message"]
        
        prompt = f"""
### CONTEXT
You are an assistant that can use tools via Model Context Protocol (MCP).

### ACTION SPACE
{tool_info}

### TASK
Answer this question: "{question}"

## NEXT ACTION
Analyze the question, extract any numbers or parameters, and decide which tool to use.
Return your response in this yaml format:

```
thinking: |
    <your step-by-step reasoning about what the question is asking and what numbers to extract>
steps: 
    - tool: <name of the tool to use>
      reason: <why you chose this tool>
      parameters:
        <parameter_name>: <parameter_value>
        <parameter_name>: <parameter_value>
    - tool: <name of the tool to use>
      reason: <why you chose this tool>
      parameters:
        <parameter_name>: <parameter_value>
        <parameter_name>: <parameter_value>
```
IMPORTANT: 
1. Extract numbers from the question properly
2. Use proper indentation (4 spaces) for multi-line fields
3. Use the | character for multi-line text fields
4. Use "$STEP_RESULT_[n]" as parameter_value if it's the result of the nth step 
5. If no tool is choose, leave the steps array empty
6. check schema of related tables before provide parameters, in order to generate correct SQL.
"""
        conversation_history = shared.get("conversation_history", [])
        conversation_history.append({"role": "user", "content": prompt})
        shared["conversation_history"] = conversation_history
        websocket = shared["websocket"]
        return conversation_history, websocket

    async def exec_async(self, prep_res):
        """Call LLM to process the question and decide which tool to use"""
        print("🤔 Analyzing question and deciding which tool to use...")
        messages, websocket = prep_res

        full_response = ""
        async for chunk_content in stream_llm(messages):
            full_response += chunk_content
            await websocket.send_text(json.dumps({
                "type": "chunk", 
                "content": chunk_content
            }))
        
        await websocket.send_text(json.dumps({"type": "end", "content": ""}))
        
        return full_response

    async def post_async(self, shared, prep_res, exec_res):
        """Extract decision from YAML and save to shared context"""
        try:
            yaml_str = exec_res.split("```")[1].split("```")[0].strip()
            decision = yaml.safe_load(yaml_str)
            
            #shared["tool_name"] = decision["tool"]
            #shared["parameters"] = decision["parameters"]
            shared["thinking"] = decision.get("thinking", "")
            shared["steps"] = decision.get("steps", [])
            
            #print(f"💡 Selected tool: {decision['tool']}")
            #print(f"🔢 Extracted parameters: {decision['parameters']}")
            print(f"💡 Selected tools: {decision['steps']}")
            
            return "execute"
        except Exception as e:
            print(f"❌ Error parsing LLM response: {e}")
            print("Raw response:", exec_res)
            return None

class ExecuteToolNode(AsyncNode):
    async def prep_async(self, shared):
        """Prepare tool execution parameters"""
        return shared["steps"]

    async def exec_async(self, prep_res):
        """Execute the chosen tool"""
        steps = prep_res
        print(f"🔧 Executing tool '{steps}'")
        if len(steps) == 0:
            return "No tool selected, exiting."
        results = await exec_steps(steps)
        return results

    async def post_async(self, shared, prep_res, exec_res):
        print(f"\n✅ Final Answer: {exec_res}")
        shared["result"] = exec_res
        return "echo"

class EchoNode(AsyncNode):
    async def prep_async(self, shared):
        """Prepare tool execution parameters"""
        return shared["result"], shared["websocket"], shared["user_message"], shared["conversation_history"]

    async def exec_async(self, prep_res):
        """Call LLM to process the question and decide which tool to use"""
        print("🤔 Analyzing question and deciding which tool to use...")
        result, websocket, question, messages = prep_res

        prompt = f"""
### CONTEXT
You are an assistant that can use tools via Model Context Protocol (MCP).
### TASK
Answer this question: "{question}"
## NEXT ACTION
translate the result to a human readable format, like nature language, the result is: {result}
return your result in markdown format
IMPORTANT: 
1. directly return the result, don't add any explanation.
2. do not contain thinking.
"""

        messages.append({"role": "user", "content": prompt})
        #messages = [{"role": "user", "content": prompt}]

        await websocket.send_text(json.dumps({"type": "start", "content": ""}))

        full_response = ""
        async for chunk_content in stream_llm(messages):
            full_response += chunk_content
            await websocket.send_text(json.dumps({
                "type": "chunk", 
                "content": chunk_content
            }))
        
        await websocket.send_text(json.dumps({"type": "end", "content": ""}))
        
        return full_response

    async def post_async(self, shared, prep_res, exec_res):
        print(f"\n✅ Final Answer: {exec_res}")
        return "done"


if __name__ == "__main__":
    # Default question
    #default_question = "What is 982713504867129384651 plus 73916582047365810293746529 subtract 12 subtract 32?"
    #default_question = "i want to create a table in mysql, the name is students, the schema contains id, name, age, sex, email, phone, address, create time, update time. i need to sort by age often, create index for it."
    default_question = "check the schema of students table and fill in 1 lines to students table for testing, use random value for each column."

    # Get question from command line if provided with --
    question = default_question
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            question = arg[2:]
            break
    
    print(f"🤔 Processing question: {question}")
    
    # Create nodes
    get_tools_node = GetToolsNode()
    decide_node = DecideToolNode()
    execute_node = ExecuteToolNode()
    
    # Connect nodes
    get_tools_node - "decide" >> decide_node
    decide_node - "execute" >> execute_node
    
    # Create and run flow
    flow = Flow(start=get_tools_node)
    shared = {"question": question}
    flow.run(shared)