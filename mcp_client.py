import asyncio
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack
import json
import httpx
import argparse
import sys
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from dotenv import load_dotenv

# 导入模型配置
from model_config import ModelConfig
from config import Config  # 导入统一配置类

# 从 .env 加载环境变量
load_dotenv()

class MCPClient:
    def __init__(self, config_file: Optional[str] = "config.json"):
        # 初始化会话和客户端对象
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        
        # 使用模型配置
        self.model_config = ModelConfig(config_file)
        
    async def connect_to_server(self, server_script_path: str):
        """连接到 MCP 服务器 (stdio 模式)

        Args:
            server_script_path: 服务器脚本的路径 (.py 或 .js)
        """
        # 检查是否是Python模块调用
        if server_script_path.startswith("python "):
            parts = server_script_path.split()
            command = parts[0]
            args = parts[1:]
        else:
            is_python = server_script_path.endswith('.py')
            is_js = server_script_path.endswith('.js')
            if not (is_python or is_js):
                raise ValueError("服务器脚本必须是 .py 或 .js 文件")

            command = "python" if is_python else "node"
            args = [server_script_path]

        server_params = StdioServerParameters(
            command=command,
            args=args,
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
    
    async def connect_to_python_module(self, module_name: str):
        """连接到Python模块MCP服务器 (stdio模式)

        Args:
            module_name: 模块名称，如 mcp_server_fetch
        """
        server_params = StdioServerParameters(
            command="python",
            args=["-m", module_name],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # 列出可用的工具
        response = await self.session.list_tools()
        tools = response.tools
        print(f"\n已连接到 {module_name} 模块服务器，工具包括：", [tool.name for tool in tools])
    
    async def connect_to_sse_server(self, server_url: str):
        """连接到 MCP 服务器 (SSE 模式)

        Args:
            server_url: 服务器 URL，如 http://localhost:8000/sse
        """
        # 使用官方 SSE 客户端连接
        # sse_client 会建立 SSE 连接并返回通信流
        streams = await self.exit_stack.enter_async_context(sse_client(server_url))
        
        # 使用流创建 ClientSession
        # streams[0] 是从服务器接收消息的流
        # streams[1] 是向服务器发送消息的流
        self.session = await self.exit_stack.enter_async_context(ClientSession(streams[0], streams[1]))
        
        # 发送初始化请求给服务器
        await self.session.initialize()
        
        # 列出可用的工具
        response = await self.session.list_tools()
        tools = response.tools
        print("\n已连接到 SSE 服务器，工具包括：", [tool.name for tool in tools])

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
        try:
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

            # 处理直接工具调用的格式：工具名+空格+参数
            if " " in query and not query.startswith("fetch "):
                parts = query.split(" ", 1)
                tool_name = parts[0]
                tool_args_str = parts[1]
                
                # 检查工具是否存在
                tool_exists = False
                for tool in response.tools:
                    if tool.name == tool_name:
                        tool_exists = True
                        break
                
                if tool_exists:
                    try:
                        # 尝试解析参数
                        if tool_args_str.startswith("{") and tool_args_str.endswith("}"):
                            # JSON格式参数
                            tool_args = json.loads(tool_args_str)
                        else:
                            # 简单格式参数 - 假设是URL或其他简单值
                            tool_args = {"url": tool_args_str}
                        
                        # 直接调用工具
                        result = await self.session.call_tool(tool_name, tool_args)
                        return f"[直接调用工具 {tool_name}]\n{result.content}"
                    except Exception as e:
                        return f"工具调用错误: {str(e)}\n\n参数格式应为JSON或简单URL"
            
            # 处理fetch工具的特殊格式：fetch+网址
            if query.startswith("fetch "):
                url = query[6:].strip()  # 提取URL
                try:
                    print(f"正在获取网页内容: {url}")
                    
                    # 添加额外参数以处理超时问题
                    fetch_args = {
                        "url": url,
                        "max_length": 10000  # 增加最大长度
                    }
                    
                    # 设置超时参数
                    timeout_seconds = 30  # 可以设置更长时间
                    timeout_task = asyncio.create_task(asyncio.sleep(timeout_seconds))
                    fetch_task = asyncio.create_task(self.session.call_tool("fetch", fetch_args))
                    
                    # 使用 asyncio.wait 等待任务完成或超时
                    done, pending = await asyncio.wait(
                        [fetch_task, timeout_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # 如果是超时任务先完成，则取消 fetch 任务
                    if timeout_task in done:
                        fetch_task.cancel()
                        return f"获取网页内容超时（{timeout_seconds}秒）。可能网站响应较慢或无法访问。\n请尝试其他网址或稍后重试。"
                    
                    # 取消超时任务
                    timeout_task.cancel()
                    
                    # 获取结果
                    result = await fetch_task
                    
                    if not result.content:
                        return "获取的网页内容为空。可能网址无效或网站返回了空内容。"
                    
                    # 分析内容长度
                    content_length = len(str(result.content))
                    truncation_message = ""
                    if content_length >= 9000:  # 接近最大长度时
                        truncation_message = f"\n[内容已截断，共获取 {content_length} 字符。要获取更多内容，可使用 start_index 参数]\n"
                    
                    return f"[调用fetch工具获取网页内容]\n{truncation_message}{result.content}"
                    
                except asyncio.CancelledError:
                    return "获取网页内容的操作被取消。"
                except Exception as e:
                    error_type = type(e).__name__
                    error_msg = str(e)
                    
                    # 提供针对不同错误类型的友好提示
                    friendly_msg = "未知错误，请检查网址格式和网络连接。"
                    
                    if "Timeout" in error_type or "timeout" in error_msg.lower():
                        friendly_msg = "连接超时，可能网站响应较慢或无法访问。"
                    elif "ConnectionError" in error_type:
                        friendly_msg = "连接错误，无法建立与服务器的连接。"
                    elif "SSL" in error_type or "ssl" in error_msg.lower():
                        friendly_msg = "SSL证书验证失败，可能网站的证书存在问题。"
                    elif "DNS" in error_type or "dns" in error_msg.lower():
                        friendly_msg = "DNS解析失败，无法解析主机名。"
                    
                    traceback.print_exc()
                    return f"Fetch调用错误: {error_type}: {error_msg}\n\n{friendly_msg}\n\n正确用法: fetch https://example.com"

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
                        try:
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
                        except Exception as e:
                            error_msg = f"工具调用错误 ({tool_name}): {str(e)}"
                            final_text.append(error_msg)
                            import traceback
                            print("\n工具调用详细错误:")
                            traceback.print_exc()
                            break
                
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
        except Exception as e:
            import traceback
            print("\n处理查询时出错:")
            traceback.print_exc()
            return f"处理查询时出错: {str(e)}"

    async def chat_loop(self):
        """运行交互式聊天循环"""
        print("\nMCP 客户端已启动！")
        print("输入你的查询或输入 'quit' 退出。")

        import traceback
        while True:
            try:
                query = input("\n查询: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print("\n错误:")
                traceback.print_exc()
                print(f"\n错误摘要: {str(e)}")

    async def cleanup(self):
        """清理资源"""
        await self.exit_stack.aclose()

async def main():
    parser = argparse.ArgumentParser(description="MCP 客户端")
    parser.add_argument("server", nargs="?", help="服务器脚本路径或 SSE 服务器 URL")
    parser.add_argument("--mode", choices=["stdio", "sse"], default="stdio",
                      help="连接模式: stdio 或 sse")
    parser.add_argument("-m", "--module", help="直接启动Python模块作为MCP服务器")
    
    args = parser.parse_args()
    
    # 使用 -m 参数指定Python模块
    if args.module:
        if args.server:
            print("警告: 同时指定了服务器路径和模块名，将优先使用模块名")
        
        client = MCPClient()
        try:
            await client.connect_to_python_module(args.module)
            await client.chat_loop()
        except Exception as e:
            print(f"程序运行出错: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            await client.cleanup()
        return
    
    if not args.server:
        print("使用方法: python mcp_client.py <path_to_server_script> 或 python mcp_client.py --mode=sse <server_url>")
        print("          python mcp_client.py -m <module_name> (直接启动Python模块)")
        sys.exit(1)
    
    client = MCPClient()
    try:
        if args.mode == "stdio":
            # 标准输入输出模式 - 启动并连接到子进程服务器
            await client.connect_to_server(args.server)
        else:
            # SSE 模式 - 连接到运行中的 HTTP 服务器
            # args.server 应为 URL，如 http://localhost:8000/sse
            await client.connect_to_sse_server(args.server)
        
        await client.chat_loop()
    except Exception as e:
        print(f"程序运行出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 