from pocketflow import AsyncFlow
from nodes import StreamingChatNode
from mcp_nodes import GetToolsNode, DecideToolNode, ExecuteToolNode, EchoNode

def create_streaming_chat_flow():
    #chat_node = StreamingChatNode()
    get_tools_node = GetToolsNode()
    decide_node = DecideToolNode()
    execute_node = ExecuteToolNode()
    echo_node = EchoNode()
    get_tools_node - "decide" >> decide_node
    decide_node - "execute" >> execute_node
    execute_node - "echo" >> echo_node
    return AsyncFlow(start=get_tools_node) 