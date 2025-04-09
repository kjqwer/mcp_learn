from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
import uvicorn
import json
import asyncio
import httpx
import subprocess
import base64
import os
import re
import signal
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
import argparse

# 配置类
class Config:
    def __init__(self, config_file: Optional[str] = None, **kwargs):
        # 默认配置
        self.api_key = 'sk-3962e8a22f764dfdb96b2a3e90601cf5'
        self.api_base = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        self.model = 'qwen-max-latest'
        self.max_tokens = 2000
        self.temperature = 0.7
        
        # 从环境变量加载配置
        if os.environ.get("ALIYUN_API_KEY"):
            self.api_key = os.environ.get("ALIYUN_API_KEY")
        if os.environ.get("ALIYUN_API_BASE"):
            self.api_base = os.environ.get("ALIYUN_API_BASE")
        if os.environ.get("ALIYUN_MODEL"):
            self.model = os.environ.get("ALIYUN_MODEL")

        # 从配置文件加载
        if config_file and os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                for key, value in file_config.items():
                    setattr(self, key, value)
        
        # 从kwargs覆盖配置
        for key, value in kwargs.items():
            setattr(self, key, value)

# MCP相关模型定义
class MCPMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None

class MCPFunctionCall(BaseModel):
    name: str
    arguments: Dict[str, Any]

class MCPFunction(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]
    required: Optional[List[str]] = None

class MCPRequest(BaseModel):
    messages: List[MCPMessage]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    function_call: Optional[Union[str, Dict[str, Any]]] = None
    functions: Optional[List[MCPFunction]] = None
    stream: Optional[bool] = False

class MCPResponse(BaseModel):
    message: MCPMessage
    status: str = "success"

# 自定义工具定义
class Calculator:
    @staticmethod
    async def calculate(expression: str) -> Dict[str, Any]:
        """计算数学表达式
        
        Args:
            expression: 数学表达式，如 '2 + 2 * 3'
            
        Returns:
            计算结果
        """
        try:
            # 安全计算表达式
            result = eval(expression, {"__builtins__": {}})
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

class WeatherService:
    @staticmethod
    async def get_weather(city: str) -> Dict[str, Any]:
        """获取城市天气信息
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息
        """
        # 模拟天气数据
        weather_data = {
            "北京": {"temperature": 25, "condition": "晴天", "humidity": 45},
            "上海": {"temperature": 22, "condition": "多云", "humidity": 60},
            "广州": {"temperature": 28, "condition": "小雨", "humidity": 75},
            "深圳": {"temperature": 27, "condition": "阵雨", "humidity": 80},
        }
        
        if city in weather_data:
            return weather_data[city]
        else:
            return {"error": f"无法获取{city}的天气信息"}

class FetchService:
    _fetch_process = None
    _fetch_url = None
    _use_external_service = True  # 默认使用外部服务
    _external_service_urls = [
        "http://localhost:6277/v1",  # MCP Inspector代理
        "http://localhost:3000/v1"   # 标准fetch服务端口
    ]
    
    @classmethod
    def set_use_external_service(cls, use_external: bool):
        """设置是否使用外部fetch服务"""
        cls._use_external_service = use_external
        print(f"Fetch服务配置: {'使用外部服务' if use_external else '使用内部实现'}")
    
    @classmethod
    def add_external_service_url(cls, url: str):
        """添加外部服务URL"""
        if url not in cls._external_service_urls:
            cls._external_service_urls.insert(0, url)  # 添加到列表开头，优先使用
            print(f"添加外部Fetch服务URL: {url}")
    
    @classmethod
    async def start_fetch_server(cls):
        """启动fetch服务器"""
        if cls._use_external_service:
            # 使用外部服务，无需启动本地进程
            cls._fetch_url = None  # 会在fetch方法中尝试所有配置的URL
            print("已配置使用外部Fetch服务")
            return
        
        # 使用内部实现，启动本地进程
        if cls._fetch_process is None:
            try:
                # 使用uvx启动fetch服务
                cls._fetch_process = subprocess.Popen(
                    ["uvx", "mcp-server-fetch"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                print("内部Fetch服务已启动")
                
                # 等待服务器启动并获取URL
                await asyncio.sleep(2)  # 等待服务器启动
                cls._fetch_url = "http://localhost:8001/v1"  
                print(f"内部Fetch服务URL: {cls._fetch_url}")
            except Exception as e:
                print(f"启动内部Fetch服务失败: {str(e)}")
                cls._fetch_process = None
    
    @classmethod
    def stop_fetch_server(cls):
        """停止fetch服务器"""
        if cls._fetch_process is not None:
            cls._fetch_process.terminate()
            cls._fetch_process = None
            print("内部Fetch服务已停止")
    
    @staticmethod
    async def fetch(url: str) -> Dict[str, Any]:
        """获取网页内容
        
        Args:
            url: 要获取的网页URL
            
        Returns:
            网页内容
        """
        # 实现内部fetch逻辑
        async def internal_fetch():
            """使用简单的HTTP客户端实现基本的fetch功能"""
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    headers = {
                        "User-Agent": "ModelContextProtocol/1.0 (User-Specified; +https://github.com/modelcontextprotocol/servers)"
                    }
                    response = await client.get(url, headers=headers, follow_redirects=True)
                    
                    if response.status_code == 200:
                        content = response.text
                        # 简单处理HTML内容
                        if content.strip().startswith("<!DOCTYPE html>") or content.strip().startswith("<html"):
                            # 非常简单的HTML到纯文本转换
                            import re
                            # 移除HTML标签
                            text = re.sub(r'<[^>]+>', ' ', content)
                            # 移除多余空格
                            text = re.sub(r'\s+', ' ', text).strip()
                            # 移除特殊字符
                            text = re.sub(r'&[^;]+;', ' ', text)
                            return {"content": text, "url": url}
                        return {"content": content, "url": url}
                    else:
                        return {"error": f"获取失败，状态码: {response.status_code}", "url": url}
            except Exception as e:
                return {"error": f"内部fetch错误: {str(e)}", "url": url}
        
        # 如果使用外部服务
        if FetchService._use_external_service:
            # 尝试每个配置的外部服务
            for service_url in FetchService._external_service_urls:
                try:
                    # 调用外部fetch服务API
                    fetch_api_url = f"{service_url}/functions/fetch"
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            fetch_api_url, 
                            json={"url": url},
                            headers={"Content-Type": "application/json"}
                        )
                        
                        # 解析响应
                        if response.status_code == 200:
                            result = response.json()
                            content = result.get("result", {}).get("content")
                            if content:
                                return {"content": content, "url": url}
                        
                        print(f"外部服务 {service_url} 调用失败，尝试下一个...")
                except Exception as e:
                    print(f"调用外部服务 {service_url} 出错: {str(e)}")
                    continue  # 尝试下一个服务
            
            print("所有外部服务调用失败，使用内部实现...")
            
        # 如果外部服务都失败了或者配置使用内部实现，使用内部fetch逻辑
        return await internal_fetch()

# 函数映射
TOOLS_MAPPING = {
    "calculate": Calculator.calculate,
    "get_weather": WeatherService.get_weather,
    "fetch": FetchService.fetch,
}

# 创建FastAPI应用
app = FastAPI(title="集成式MCP服务器")
config = Config()

# 处理命令行参数
def parse_args():
    parser = argparse.ArgumentParser(description="集成式MCP服务器")
    parser.add_argument("--port", type=int, default=8001, help="服务器端口，默认8001")
    parser.add_argument("--fetch-internal", action="store_true", help="使用内部fetch实现而不是外部服务")
    parser.add_argument("--fetch-url", type=str, help="添加外部fetch服务URL")
    return parser.parse_args()

@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    # 初始化fetch服务
    args = parse_args()
    
    # 配置fetch服务
    if args.fetch_internal:
        FetchService.set_use_external_service(False)
    
    if args.fetch_url:
        FetchService.add_external_service_url(args.fetch_url)
    
    # 启动fetch服务
    background_tasks = BackgroundTasks()
    background_tasks.add_task(FetchService.start_fetch_server)
    await FetchService.start_fetch_server()

@app.on_event("shutdown")
def shutdown_event():
    """应用关闭时执行"""
    # 关闭fetch服务
    FetchService.stop_fetch_server()

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """处理MCP请求"""
    try:
        # 获取请求数据
        body = await request.json()
        mcp_request = MCPRequest(**body)
        
        # 检查是否有工具调用
        if mcp_request.functions and len(mcp_request.messages) > 0:
            last_message = mcp_request.messages[-1]
            
            # 如果最后一条消息是用户消息，则检查是否需要调用工具
            if last_message.role.lower() == "user":
                content = last_message.content if isinstance(last_message.content, str) else ""
                
                # 检查是否是计算请求
                if "计算" in content or "算一下" in content or "=" in content or "+" in content or "-" in content or "*" in content or "/" in content:
                    # 提取表达式（简化版）
                    expression = None
                    for func in mcp_request.functions:
                        if func.name == "calculate":
                            import re
                            match = re.search(r'[0-9+\-*/().\s]+', content)
                            if match:
                                expression = match.group().strip()
                    
                    if expression:
                        result = await Calculator.calculate(expression)
                        return {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "function_call": {
                                    "name": "calculate",
                                    "arguments": json.dumps({"expression": expression})
                                }
                            },
                            "status": "success"
                        }
                
                # 检查是否是天气请求
                elif "天气" in content or "气温" in content:
                    # 提取城市（简化版）
                    import re
                    match = re.search(r'(北京|上海|广州|深圳)', content)
                    if match:
                        city = match.group()
                        return {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "function_call": {
                                    "name": "get_weather",
                                    "arguments": json.dumps({"city": city})
                                }
                            },
                            "status": "success"
                        }
                
                # 检查是否是fetch请求
                elif "获取网页" in content or "抓取" in content or "fetch" in content:
                    # 提取URL（简化版）
                    import re
                    match = re.search(r'https?://\S+', content)
                    if match:
                        url = match.group().strip()
                        return {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "function_call": {
                                    "name": "fetch",
                                    "arguments": json.dumps({"url": url})
                                }
                            },
                            "status": "success"
                        }
        
        # 如果不需要调用工具或最后一条消息是function结果，则调用LLM API
        return await call_llm_api(mcp_request)
    
    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))

@app.post("/v1/functions/{function_name}")
async def handle_function_call(function_name: str, request: Request):
    """处理MCP函数调用"""
    try:
        # 获取请求数据
        body = await request.json()
        
        # 检查函数是否存在
        if function_name not in TOOLS_MAPPING:
            return HTTPException(status_code=404, detail=f"函数 {function_name} 不存在")
        
        # 调用对应的函数
        function = TOOLS_MAPPING[function_name]
        result = await function(**body)
        
        return {"result": result}
    
    except Exception as e:
        return HTTPException(status_code=500, detail=str(e))

async def call_llm_api(mcp_request: MCPRequest) -> Dict[str, Any]:
    """调用外部LLM API（阿里云灵积模型）"""
    try:
        async with httpx.AsyncClient() as client:
            # 准备请求数据
            payload = {
                "model": config.model,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content
                    } for msg in mcp_request.messages
                ],
                "max_tokens": mcp_request.max_tokens or config.max_tokens,
                "temperature": mcp_request.temperature or config.temperature,
            }
            
            # 添加函数调用相关参数
            if mcp_request.functions:
                payload["functions"] = [
                    {
                        "name": func.name,
                        "description": func.description,
                        "parameters": func.parameters
                    } for func in mcp_request.functions
                ]
            
            if mcp_request.function_call:
                payload["function_call"] = mcp_request.function_call
            
            # 发送请求到阿里云灵积API
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}"
            }
            
            response = await client.post(
                f"{config.api_base}/chat/completions",
                json=payload,
                headers=headers
            )
            
            # 解析响应
            if response.status_code == 200:
                response_json = response.json()
                
                # 提取并转换为MCP响应格式
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    assistant_message = response_json["choices"][0]["message"]
                    
                    return {
                        "message": {
                            "role": assistant_message.get("role", "assistant"),
                            "content": assistant_message.get("content"),
                            "function_call": assistant_message.get("function_call")
                        },
                        "status": "success"
                    }
            
            # 处理错误
            return {
                "message": {
                    "role": "assistant",
                    "content": "抱歉，我无法处理您的请求。"
                },
                "status": "error"
            }
    
    except Exception as e:
        return {
            "message": {
                "role": "assistant",
                "content": f"发生错误: {str(e)}"
            },
            "status": "error"
        }

# 主入口
if __name__ == "__main__":
    args = parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port) 