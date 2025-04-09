import asyncio
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack
import json
import httpx

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dotenv import load_dotenv
import os
import sys

# 导入模型配置
from model_config import ModelConfig

# 从 .env 加载环境变量
load_dotenv()

class MCPClient:
    def __init__(self):
        # 初始化会话和客户端对象
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # 使用模型配置
        self.model_config = ModelConfig()
        
    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器

        Args:
            server_script_path: 服务器脚本的路径 (.py 或 .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("服务器脚本必须是 .py 或 .js 文件")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # 列出可用的工具
        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到服务器，工具包括：", [tool.name for tool in tools])

    async def call_qwen_api(self, messages: List[Dict[str, Any]], tools=None) -> Dict[str, Any]:
        """调用阿里云千问 API

        Args:
            messages: 消息历史
            tools: 可用工具列表

        Returns:
            API 响应
        """
        client_params = self.model_config.get_client_params()
        request_params = self.model_config.get_request_params()
        
        # 准备请求数据
        payload = {
            "model": request_params["model"],
            "messages": messages,
            "max_tokens": request_params["max_tokens"],
            "temperature": request_params["temperature"],
        }
        
        # 如果有工具，添加到请求中
        if tools:
            payload["tools"] = tools
        
        # 发送请求到阿里云灵积API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {client_params['api_key']}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{client_params['base_url']}/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"API请求失败: {response.status_code}, {response.text}")

    async def process_query(self, query: str) -> str:
        """使用千问和可用的工具处理查询，支持链式工具调用"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        } for tool in response.tools]

        # 初始千问 API 调用
        response = await self.call_qwen_api(messages, available_tools)
        final_text = []
        
        # 最大链式调用次数，防止无限循环
        max_chain_calls = 5
        chain_count = 0
        
        # 循环处理工具调用，直到模型不再调用工具或达到最大调用次数
        while chain_count < max_chain_calls:
            chain_count += 1
            
            if "choices" not in response or len(response["choices"]) == 0:
                break
            
            assistant_message = response["choices"][0]["message"]
            
            # 如果没有工具调用，结束循环
            if "tool_calls" not in assistant_message or not assistant_message["tool_calls"]:
                content = assistant_message.get("content", "")
                if not isinstance(content, str):
                    content = str(content)
                final_text.append(content)
                break
            
            # 处理所有工具调用
            has_tool_calls = False
            for tool_call in assistant_message["tool_calls"]:
                if tool_call["type"] == "function":
                    has_tool_calls = True
                    function_call = tool_call["function"]
                    tool_name = function_call["name"]
                    tool_args = json.loads(function_call["arguments"])
                    
                    # 执行工具调用
                    result = await self.session.call_tool(tool_name, tool_args)
                    final_text.append(f"[调用工具 {tool_name}，参数 {tool_args}]")
                    
                    # 确保内容是字符串
                    assistant_content = assistant_message.get("content", "")
                    if not isinstance(assistant_content, str):
                        assistant_content = str(assistant_content)
                    
                    # 添加助手消息到历史
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                        "tool_calls": assistant_message["tool_calls"]
                    })
                    
                    # 确保工具结果是可序列化的
                    try:
                        tool_result_content = json.dumps(result.content)
                    except TypeError:
                        tool_result_content = str(result.content)
                    
                    # 添加工具结果到历史
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": tool_result_content
                    })
            
            # 如果没有工具调用，结束循环
            if not has_tool_calls:
                break
            
            # 获取下一个响应
            response = await self.call_qwen_api(messages, available_tools)
        
        # 添加最终响应
        if chain_count >= max_chain_calls and "choices" in response and len(response["choices"]) > 0:
            final_text.append("(达到最大链式调用次数限制)")
            final_text.append(response["choices"][0]["message"].get("content", ""))
        
        return "\n".join(final_text)

    async def chat_loop(self):
        """运行交互式聊天循环"""
        print("\nMCP 客户端已启动！")
        print("输入你的查询或输入 'quit' 退出。")

        while True:
            try:
                query = input("\n查询: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\n错误: {str(e)}")

    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("使用方法: python mcp_client.py <path_to_server_script>")
        sys.exit(1)

    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 