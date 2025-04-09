from typing import Optional, Dict, Any

class ModelConfig:
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
        
    def get_request_params(self) -> Dict[str, Any]:
        """返回请求参数字典"""
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
    
    def get_client_params(self) -> Dict[str, Any]:
        """返回客户端参数字典"""
        return {
            "api_key": self.api_key,
            "base_url": self.api_base,
        } 