from typing import Dict, Any, Optional, List, Union
import httpx
import re
import os
import json
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP server
mcp = FastMCP("combined-tools")

# 配置类
class Config:
    def __init__(self, config_file: Optional[str] = None, **kwargs):
        # 默认配置
        self.api_key = 'sk-3962e8a22f764dfdb96b2a3e90601cf5'
        self.api_base = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        self.model = 'qwen-max-latest'
        self.max_tokens = 2000
        self.temperature = 0.7
        self.handlers_config = {
            "image": {
                "enabled": True,
                "functions": {
                    "detect_sensor": True,
                    "recognize_text": True
                }
            }
        }
        
        # 从环境变量加载配置
        if os.environ.get("ALIYUN_API_KEY"):
            self.api_key = os.environ.get("ALIYUN_API_KEY")
        if os.environ.get("ALIYUN_API_BASE"):
            self.api_base = os.environ.get("ALIYUN_API_BASE")
        if os.environ.get("ALIYUN_MODEL"):
            self.model = os.environ.get("ALIYUN_MODEL")
        
        # 从配置文件加载
        if config_file and os.path.exists(config_file):
            self._load_from_file(config_file)
            
        # 从kwargs覆盖
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
    
    def _load_from_file(self, config_file):
        """从配置文件加载配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                for key, value in file_config.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}")

# 创建配置实例
config = Config()

# 计算器工具
@mcp.tool()
async def calculate(expression: str) -> Dict[str, Any]:
    """计算数学表达式
    
    Args:
        expression: 数学表达式，如 '2 + 2 * 3'
    """
    try:
        # 安全计算表达式
        result = eval(expression, {"__builtins__": {}})
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}

# 天气服务工具
@mcp.tool()
async def get_weather(city: str) -> Dict[str, Any]:
    """获取城市天气信息
    
    Args:
        city: 城市名称
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

# 网页获取工具
@mcp.tool()
async def fetch(url: str) -> Dict[str, Any]:
    """获取网页内容
    
    Args:
        url: 要获取的网页URL
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "User-Agent": "ModelContextProtocol/1.0 (MCP-Server; +https://github.com/modelcontextprotocol/servers)"
            }
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            if response.status_code == 200:
                content = response.text
                # 简单处理HTML内容
                if content.strip().startswith("<!DOCTYPE html>") or content.strip().startswith("<html"):
                    # 简单的HTML到纯文本转换
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
        return {"error": f"获取网页错误: {str(e)}", "url": url}

# 添加 LLM 对话功能
@mcp.tool()
async def chat(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """与大模型对话
    
    Args:
        messages: 对话历史，格式为 [{"role": "user", "content": "你好"}, ...]
    """
    try:
        async with httpx.AsyncClient() as client:
            # 准备请求数据
            payload = {
                "model": config.model,
                "messages": messages,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
            
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
                
                # 提取回复内容
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    assistant_message = response_json["choices"][0]["message"]
                    return {
                        "response": assistant_message.get("content", ""),
                        "role": assistant_message.get("role", "assistant")
                    }
            
            # 处理错误
            return {
                "error": f"API请求失败: {response.status_code}",
                "details": response.text
            }
    
    except Exception as e:
        return {"error": f"调用LLM出错: {str(e)}"}

# 主入口
if __name__ == "__main__":
    # 初始化并运行 server
    mcp.run(transport='stdio') 