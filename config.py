import os
import json
from typing import Dict, Any, Optional

class Config:
    def __init__(self, config_file: Optional[str] = None, **kwargs):
        # 默认配置
        self.api_key = ''  # 默认为空，需要从环境变量或配置文件加载
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
    
    def get_request_params(self) -> Dict[str, Any]:
        """返回请求参数字典"""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
    
    def get_client_params(self) -> Dict[str, Any]:
        """返回客户端参数字典"""
        if not self.api_key:
            print("警告: API密钥未设置，请在config.json中设置或通过环境变量ALIYUN_API_KEY设置")
        return {
            "api_key": self.api_key,
            "base_url": self.api_base,
        }

# 创建配置实例
config = Config("config.json") 