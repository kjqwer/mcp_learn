import asyncio
import json
import httpx

# 定义MCP函数
FUNCTIONS = [
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
    },
    {
        "name": "fetch",
        "description": "获取网页内容",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的网页URL"
                }
            },
            "required": ["url"]
        }
    }
]

async def call_mcp_function(prompt, function_name=None):
    """调用MCP函数"""
    api_url = "http://localhost:8001/v1/chat/completions"
    
    # 构建请求
    payload = {
        "model": "qwen-max-latest",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "functions": FUNCTIONS
    }
    
    # 如果指定了函数名，强制使用该函数
    if function_name:
        payload["function_call"] = {"name": function_name}
    
    try:
        # 发送请求
        async with httpx.AsyncClient() as client:
            # 第一步：调用MCP完成接口，获取函数调用信息
            response = await client.post(
                api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code != 200:
                print(f"请求失败: {response.status_code}")
                print(response.text)
                return None
            
            result = response.json()
            print("\n函数调用响应:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # 如果没有函数调用，直接返回结果
            if not result.get("message", {}).get("function_call"):
                return result
            
            # 第二步：执行函数调用
            function_call = result["message"]["function_call"]
            print(f"\n调用函数: {function_call['name']}")
            arguments = json.loads(function_call["arguments"])
            print(f"参数: {arguments}")
            
            function_response = await client.post(
                f"http://localhost:8001/v1/functions/{function_call['name']}",
                json=arguments,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if function_response.status_code != 200:
                print(f"函数执行失败: {function_response.status_code}")
                print(function_response.text)
                return None
            
            function_result = function_response.json()
            print("\n函数执行结果:")
            print(json.dumps(function_result, indent=2, ensure_ascii=False))
            
            # 处理特定函数的结果
            if function_call["name"] == "calculate":
                if "result" in function_result["result"]:
                    print(f"\n计算结果: {function_result['result']['result']}")
            
            elif function_call["name"] == "get_weather":
                if "temperature" in function_result["result"]:
                    print("\n天气信息:")
                    weather = function_result["result"]
                    print(f"温度: {weather['temperature']}°C")
                    print(f"天气状况: {weather['condition']}")
                    print(f"湿度: {weather['humidity']}%")
            
            elif function_call["name"] == "fetch":
                if "content" in function_result["result"]:
                    content = function_result["result"]["content"]
                    print(f"\n网页内容摘要 ({len(content)} 字符):")
                    print(content[:500] + "..." if len(content) > 500 else content)
            
            return function_result
    
    except Exception as e:
        print(f"请求发生错误: {str(e)}")
        return None

async def test_calculate():
    """测试计算功能"""
    print("\n===== 测试计算功能 =====")
    expression = "2 + 3 * 4"
    print(f"计算表达式: {expression}")
    await call_mcp_function(f"请计算 {expression}", "calculate")

async def test_weather():
    """测试天气功能"""
    print("\n===== 测试天气功能 =====")
    city = "北京"
    print(f"查询城市: {city}")
    await call_mcp_function(f"{city}今天天气怎么样？", "get_weather")

async def test_fetch():
    """测试网页抓取功能"""
    print("\n===== 测试网页抓取功能 =====")
    url = "https://mcp-docs.cn/quickstart/server"
    print(f"抓取网页: {url}")
    await call_mcp_function(f"请获取以下网页的内容: {url}", "fetch")

async def interactive_test():
    """交互式测试"""
    print("\n===== 开始交互式测试 =====")
    print("请输入以下命令之一:")
    print("1. 计算表达式 (例如: '计算 1 + 2 * 3')")
    print("2. 查询天气 (例如: '北京天气怎么样')")
    print("3. 抓取网页 (例如: '获取网页 https://www.example.com')")
    print("4. 输入 '退出' 结束测试")
    
    while True:
        user_input = input("\n请输入命令: ")
        if user_input.lower() == '退出':
            break
        
        # 自动检测命令类型
        if '计算' in user_input or any(op in user_input for op in ['+', '-', '*', '/']):
            await call_mcp_function(user_input, "calculate")
        elif '天气' in user_input:
            await call_mcp_function(user_input, "get_weather")
        elif ('网页' in user_input or '抓取' in user_input) and 'http' in user_input:
            await call_mcp_function(user_input, "fetch")
        else:
            print("无法识别的命令，请使用上面列出的命令格式")

async def main():
    print("===== 测试集成MCP服务器功能 =====")
    
    # 测试计算功能
    await test_calculate()
    
    # 测试天气功能
    await test_weather()
    
    # 测试网页抓取功能
    await test_fetch()
    
    # 交互式测试
    await interactive_test()

if __name__ == "__main__":
    asyncio.run(main()) 