import asyncio
import os
import json
import httpx
from mcp_agent.core.fastagent import FastAgent

# 直接发送请求到本地MCP服务器
async def call_local_mcp(prompt, function_name=None):
    url = "http://localhost:8000/v1/chat/completions"
    
    # 设置函数定义
    functions = [
        {
            "name": "calculate",
            "description": "计算数学表达式",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式"
                    }
                },
                "required": ["expression"]
            }
        },
        {
            "name": "get_weather",
            "description": "获取城市天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
    ]
    
    # 准备请求数据
    payload = {
        "model": "qwen-max-latest",  # 使用qwen模型
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "functions": functions
    }
    
    # 如果指定了函数名，强制使用该函数
    if function_name:
        payload["function_call"] = {"name": function_name}
    
    # 发送请求
    async with httpx.AsyncClient() as client:
        headers = {"Content-Type": "application/json"}
        response = await client.post(url, json=payload, headers=headers)
        return response.json()

async def main():
    print("开始直接测试本地MCP服务器...")
    
    # 测试计算功能
    print("\n===== 测试计算功能 =====")
    calc_prompt = "请计算 2 + 3 * 4"
    try:
        calc_response = await call_local_mcp(calc_prompt, "calculate")
        print(f"计算响应: {json.dumps(calc_response, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"计算测试失败: {str(e)}")
    
    # 测试天气功能
    print("\n===== 测试天气功能 =====")
    weather_prompt = "北京今天天气怎么样？"
    try:
        weather_response = await call_local_mcp(weather_prompt, "get_weather")
        print(f"天气响应: {json.dumps(weather_response, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"天气测试失败: {str(e)}")
    
    # 交互式测试
    print("\n===== 开始交互式测试 =====")
    print("请输入以下命令之一:")
    print("1. 计算表达式 (例如: '计算 1 + 2 * 3')")
    print("2. 查询天气 (例如: '北京天气怎么样')")
    print("3. 输入 '退出' 结束测试")
    
    while True:
        user_input = input("\n请输入命令: ")
        if user_input.lower() == '退出':
            break
        
        try:
            if '计算' in user_input:
                response = await call_local_mcp(user_input, "calculate")
            elif '天气' in user_input:
                response = await call_local_mcp(user_input, "get_weather")
            else:
                print("无法识别的命令，请使用上面列出的命令格式")
                continue
            
            # 美化输出结果
            print(f"响应:\n{json.dumps(response, indent=2, ensure_ascii=False)}")
            
            # 如果有函数调用，尝试进一步解析结果
            if response.get("message", {}).get("function_call"):
                function_call = response["message"]["function_call"]
                print(f"\n函数调用: {function_call['name']}")
                print(f"参数: {json.loads(function_call['arguments'])}")
                
                # 如果是计算函数，直接输出结果
                if function_call["name"] == "calculate":
                    expression = json.loads(function_call["arguments"])["expression"]
                    try:
                        result = eval(expression, {"__builtins__": {}})
                        print(f"计算结果: {result}")
                    except Exception as e:
                        print(f"计算错误: {str(e)}")
                
                # 如果是天气函数，展示天气信息
                elif function_call["name"] == "get_weather":
                    city = json.loads(function_call["arguments"])["city"]
                    print(f"\n{city}天气信息请求已发送，结果将由MCP服务器返回")
            
        except Exception as e:
            print(f"请求失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 