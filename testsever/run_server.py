import os
import sys

# 确保当前工作目录正确
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 导入并运行主服务器
from main import mcp

if __name__ == "__main__":
    mcp.run(transport='stdio') 