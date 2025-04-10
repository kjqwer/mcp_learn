from typing import Optional, Dict, Any
from config import Config  # 导入统一配置类

class ModelConfig:
    def __init__(self, config_file: Optional[str] = None, **kwargs):
        # 使用统一配置类
        self.config = Config(config_file, **kwargs)
        
    def get_request_params(self) -> Dict[str, Any]:
        """返回请求参数字典"""
        return self.config.get_request_params()
    
    def get_client_params(self) -> Dict[str, Any]:
        """返回客户端参数字典"""
        return self.config.get_client_params() 