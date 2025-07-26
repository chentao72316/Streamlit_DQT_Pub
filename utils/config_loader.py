import json
import os

def load_config(config_path=None):
    """
    加载项目根目录下的config.json配置文件
    :param config_path: 可选，指定配置文件路径
    :return: 配置字典
    """
    if config_path is None:
        # 默认查找项目根目录下的config.json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, 'config.json')
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"配置文件未找到: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f) 