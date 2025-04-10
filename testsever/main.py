from typing import Dict, Any, Optional, List, Union
import httpx
import re
import os
import json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp.server.fastmcp import FastMCP
from config import Config  # 导入新的配置类

# 初始化 FastMCP server
mcp = FastMCP("combined-tools")

# 获取当前脚本所在目录
current_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(os.path.dirname(current_dir), "config.json")
config = Config(config_path if os.path.exists(config_path) else None)

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

# 添加文本摘要工具
@mcp.tool()
async def summarize_text(text: str, max_length: int = 100) -> Dict[str, Any]:
    """将文本摘要为指定长度
    
    Args:
        text: 要摘要的文本
        max_length: 摘要的最大长度（字符数）
    """
    try:
        # 调用千问模型进行摘要
        async with httpx.AsyncClient() as client:
            payload = {
                "model": config.model,
                "messages": [
                    {"role": "system", "content": f"请将以下文本摘要为不超过{max_length}个字符的简短摘要:"},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}"
            }
            
            response = await client.post(
                f"{config.api_base}/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    summary = response_json["choices"][0]["message"]["content"]
                    return {"summary": summary}
            
            return {"error": "摘要生成失败", "details": response.text}
    except Exception as e:
        return {"error": f"摘要工具错误: {str(e)}"}

# 添加文本翻译工具
@mcp.tool()
async def translate_text(text: str, target_language: str = "英语") -> Dict[str, Any]:
    """将文本翻译为目标语言
    
    Args:
        text: 要翻译的文本
        target_language: 目标语言，如"英语"、"法语"、"日语"等
    """
    try:
        # 调用千问模型进行翻译
        async with httpx.AsyncClient() as client:
            payload = {
                "model": config.model,
                "messages": [
                    {"role": "system", "content": f"请将以下文本翻译为{target_language}:"},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 1000,
                "temperature": 0.3,
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}"
            }
            
            response = await client.post(
                f"{config.api_base}/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    translation = response_json["choices"][0]["message"]["content"]
                    return {"translation": translation}
            
            return {"error": "翻译失败", "details": response.text}
    except Exception as e:
        return {"error": f"翻译工具错误: {str(e)}"}

# 添加文本分析工具
@mcp.tool()
async def analyze_sentiment(text: str) -> Dict[str, Any]:
    """分析文本的情感倾向
    
    Args:
        text: 要分析的文本
    """
    try:
        # 调用千问模型进行情感分析
        async with httpx.AsyncClient() as client:
            payload = {
                "model": config.model,
                "messages": [
                    {"role": "system", "content": "请分析以下文本的情感倾向，并给出积极、消极或中性的评价，以及0-10的情感分数和简短理由:"},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 500,
                "temperature": 0.3,
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}"
            }
            
            response = await client.post(
                f"{config.api_base}/chat/completions",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                response_json = response.json()
                if "choices" in response_json and len(response_json["choices"]) > 0:
                    analysis = response_json["choices"][0]["message"]["content"]
                    return {"analysis": analysis}
            
            return {"error": "情感分析失败", "details": response.text}
    except Exception as e:
        return {"error": f"情感分析工具错误: {str(e)}"}

# 主入口
if __name__ == "__main__":
    # 初始化并运行 server
    mcp.run(transport='stdio') 