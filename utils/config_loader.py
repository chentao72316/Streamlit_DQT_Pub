import json
import os
from typing import Dict, Any


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    智能加载配置（优先级：环境变量 > 配置文件）
    适配Streamlit Cloud Secrets和本地开发环境

    Args:
        config_path: 可选，指定配置文件路径

    Returns:
        配置字典

    Raises:
        FileNotFoundError: 当没有有效配置时抛出
        ValueError: 当关键配置缺失时抛出
    """
    # 1. 首先尝试从环境变量读取（生产环境）
    env_config = {
        "cos": {
            "secret_id": os.getenv("COS_SECRET_ID"),
            "secret_key": os.getenv("COS_SECRET_KEY"),
            "region": os.getenv("COS_REGION", "ap-chengdu"),  # 默认成都
            "bucket_name": os.getenv("COS_BUCKET")
        },
        "coze": {
            "api_key": os.getenv("COZE_API_KEY"),
            "bot_id": os.getenv("COZE_BOT_ID"),
            "train_workflow_id": os.getenv("COZE_TRAIN_WORKFLOW_ID"),
            "contract_workflow_id": os.getenv("COZE_CONTRACT_WORKFLOW_ID")
        },
        "fastgpt": {
            "api": os.getenv("FASTGPT_API"),
            "key": os.getenv("FASTGPT_KEY"),
            "appid": os.getenv("FASTGPT_APPID")
        }
    }

    # 检查关键环境变量是否已配置
    env_configured = any([
        env_config["cos"]["secret_id"],
        env_config["coze"]["api_key"],
        env_config["fastgpt"]["key"]
    ])

    if env_configured:
        # 验证必要配置
        required_keys = {
            "cos": ["secret_id", "secret_key", "bucket_name"],
            "coze": ["api_key", "contract_workflow_id"],
            "fastgpt": ["api", "key", "appid"]
        }

        for section, keys in required_keys.items():
            for key in keys:
                if not env_config[section].get(key):
                    raise ValueError(
                        f"环境变量缺失关键配置: {section.upper()}_{key.upper()}"
                    )
        return env_config

    # 2. 回退到本地config.json（开发环境）
    if config_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config.json")

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            "未找到任何有效配置！\n"
            "请选择以下任一种方式提供配置：\n"
            "1. 设置环境变量（生产环境）\n"
            "2. 创建config.json文件（开发环境）\n"
            f"预期配置文件路径: {config_path}"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        file_config = json.load(f)

    # 合并配置（环境变量优先）
    return {
        "cos": {**file_config.get("cos", {}), **env_config["cos"]},
        "coze": {**file_config.get("coze", {}), **env_config["coze"]},
        "fastgpt": {**file_config.get("fastgpt", {}), **env_config["fastgpt"]}
    }