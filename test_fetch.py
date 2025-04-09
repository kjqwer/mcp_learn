import asyncio
import json
import httpx

async def test_fetch_function(url="https://www.example.com"):
    """测试fetch功能"""
    print(f"测试抓取网页: {url}")
    
    # 使用自定义MCP服务器的地址
    api_url = "http://localhost:8001/v1/chat/completions"
    
    # 定义fetch函数
    fetch_function = {
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
    
    # 构建请求
    payload = {
        "model": "qwen-max-latest",
        "messages": [
            {"role": "user", "content": f"请获取以下网页的内容: {url}"}
        ],
        "functions": [fetch_function],
        "function_call": {"name": "fetch"}
    }
    
    # 发送请求
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # 发送请求到combined_mcp_server
            print("正在发送请求到combined_mcp_server...")
            response = await client.post(
                api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                print("\n函数调用响应:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
                # 如果有function_call，则调用该函数
                if result.get("message", {}).get("function_call"):
                    function_call = result["message"]["function_call"]
                    print(f"\n调用函数: {function_call['name']}")
                    arguments = json.loads(function_call["arguments"])
                    print(f"参数: {arguments}")
                    
                    # 调用函数API
                    print("正在调用fetch功能...")
                    function_response = await client.post(
                        f"http://localhost:8001/v1/functions/{function_call['name']}",
                        json=arguments,
                        headers={"Content-Type": "application/json"},
                        timeout=60.0
                    )
                    
                    if function_response.status_code == 200:
                        function_result = function_response.json()
                        print("\n函数执行结果:")
                        print(json.dumps(function_result, indent=2, ensure_ascii=False))
                        
                        # 显示获取到的网页内容摘要
                        if "result" in function_result and "content" in function_result["result"]:
                            content = function_result["result"]["content"]
                            print(f"\n网页内容摘要 ({len(content)} 字符):")
                            print(content[:500] + "..." if len(content) > 500 else content)
                        else:
                            print("\n未找到网页内容，请检查响应结构。")
                    else:
                        print(f"函数执行失败: {function_response.status_code}")
                        print(function_response.text)
            else:
                print(f"请求失败: {response.status_code}")
                print(response.text)
    except Exception as e:
        print(f"请求发生错误: {str(e)}")

async def main():
    print("===== 测试集成MCP服务器的fetch功能 =====")
    print("确保combined_mcp_server.py已经启动并在端口8001运行")
    
    # 测试fetch功能
    await test_fetch_function()
    
    # 交互式测试
    print("\n===== 开始交互式测试 =====")
    print("输入要抓取的网页URL，或输入'退出'结束测试")
    
    while True:
        user_input = input("\n请输入URL (例如 https://www.example.com): ")
        if user_input.lower() == '退出':
            break
        
        if user_input.startswith('http'):
            await test_fetch_function(user_input)
        else:
            print("请输入有效的URL，应以http或https开头")

if __name__ == "__main__":
    asyncio.run(main()) 