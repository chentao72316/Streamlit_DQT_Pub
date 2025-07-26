import streamlit as st
import requests
import json
from io import BytesIO
from utils.config_loader import load_config
import base64
from qcloud_cos import CosConfig, CosS3Client
import sys
import os
from datetime import datetime

def extract_text(file_content, filename):
    """支持PDF/DOCX/TXT的文本提取"""
    ext = filename.split('.')[-1].lower()
    if ext == 'txt':
        for encoding in ['utf-8', 'gbk', 'gb2312']:
            try:
                return file_content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return "无法解码文本内容"
    elif ext == 'pdf':
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(BytesIO(file_content))
            return "\n".join([page.extract_text() for page in reader.pages])
        except Exception:
            return "PDF解析失败"
    elif ext == 'docx':
        try:
            from docx import Document
            doc = Document(BytesIO(file_content))
            return "\n".join([p.text for p in doc.paragraphs])
        except Exception:
            return "DOCX解析失败"
    else:
        return "不支持的文件格式"

def upload_to_cos(file_content, filename):
    """上传文件到腾讯云COS并返回公网url"""
    try:
        config = load_config()
        cos_config = config.get("cos", {})
        secret_id = cos_config.get("secret_id")
        secret_key = cos_config.get("secret_key")
        region = cos_config.get("region", "ap-beijing")
        bucket_name = cos_config.get("bucket_name")
        if not all([secret_id, secret_key, bucket_name]):
            st.error("腾讯云COS配置不完整，请在config.json中配置secret_id、secret_key和bucket_name")
            return None
        cos_config_obj = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key
        )
        client = CosS3Client(cos_config_obj)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_key = f"contract_audit/{timestamp}_{filename}"
        response = client.put_object(
            Bucket=bucket_name,
            Body=file_content,
            Key=file_key,
            StorageClass='STANDARD',
            EnableMD5=False
        )
        cos_url = f"https://{bucket_name}.cos.{region}.myqcloud.com/{file_key}"
        st.success(f"文件已成功上传到腾讯云COS: {cos_url}")
        return cos_url
    except Exception as e:
        st.error(f"腾讯云COS上传失败: {str(e)}")
        return None

def upload_to_coze_file_api(file_content, filename, api_key):
    """
    上传文件到 Coze 官方 API，返回 file_id
    :param file_content: 文件二进制内容
    :param filename: 文件名
    :param api_key: Coze API Key
    :return: file_id (str) 或 None
    """
    url = "https://api.coze.cn/v1/files/upload"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    files = {
        "file": (filename, file_content)
    }
    try:
        response = requests.post(url, headers=headers, files=files, timeout=60)
        if response.status_code == 200:
            res = response.json()
            # 兼容官方返回结构
            file_id = res.get("data", {}).get("id")
            if file_id:
                st.success(f"文件已上传到 Coze，file_id: {file_id}")
                return file_id
            else:
                st.error(f"Coze 文件上传返回异常: {res}")
        else:
            st.error(f"Coze 文件上传失败，状态码: {response.status_code}, 内容: {response.text}")
    except Exception as e:
        st.error(f"Coze 文件上传异常: {str(e)}")
    return None

def create_coze_workflow_data(workflow_id, file_id, filename, ext, prompt_text=""):
    """
    构造 Coze 工作流 API 请求参数
    :param workflow_id: 工作流ID
    :param file_id: Coze文件ID
    :param filename: 文件名
    :param ext: 文件扩展名
    :param prompt_text: 审核提示
    :return: dict
    """
    return {
        "workflow_id": workflow_id,
        "parameters": {
            "question": prompt_text or "请审核以下合同内容，并提供详细的审核意见",
            "file": json.dumps({
                "file_id": file_id,
                "file_name": filename,
                "suffix_type": ext
            }, ensure_ascii=False)
        }
    }

def get_mime_type(ext):
    """获取文件的MIME类型"""
    mime_types = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain'
    }
    return mime_types.get(ext, 'application/octet-stream')

st.set_page_config(page_title="合同审核", page_icon="📄")
st.title("📄 合同审核智能体")

st.markdown("""
本页面支持上传合同初稿，自动调用智能体进行审核，显示审核过程，并可下载审核结果。
""")

config = load_config()
api_key = config["coze"]["api_key"]
workflow_id = config["coze"].get("contract_workflow_id")  # 需在 config.json 配置 workflow_id

uploaded_file = st.file_uploader("请上传合同初稿（支持PDF/DOCX/TXT）", type=["pdf", "docx", "txt"])

if uploaded_file:
    file_content = uploaded_file.read()
    st.success(f"已上传文件：{uploaded_file.name} ({uploaded_file.size/1024:.1f}KB)")
    with st.expander("查看合同内容片段"):
        content_text = extract_text(file_content, uploaded_file.name)
        st.text(content_text[:1000] if content_text else "无法预览内容")
    if st.button("开始审核"):
        with st.spinner("正在上传文件到腾讯云COS..."):
            cos_url = upload_to_cos(file_content, uploaded_file.name)
        if not cos_url:
            st.error("文件上传失败，无法进行合同审核")
            st.stop()
        with st.spinner("正在调用 Coze 工作流审核，请稍候..."):
            data = {
                "workflow_id": workflow_id,
                "parameters": {
                    "file": cos_url
                }
            }
            base_url = "https://api.coze.cn/v1/workflow/stream_run"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            with st.expander("调试信息"):
                st.write("请求数据:")
                st.write(json.dumps(data, ensure_ascii=False))
                st.json(data)
                st.write("请求URL:", base_url)
                st.write("请求头:", headers)
                st.write("cos_url:", cos_url)
            try:
                response = requests.post(base_url, headers=headers, data=json.dumps(data, ensure_ascii=False), timeout=120, stream=True)
                st.write("响应状态码:", response.status_code)
                if response.status_code == 200:
                    audit_result = ""
                    with st.expander("流式审核进度"):
                        for line in response.iter_lines(decode_unicode=False):
                            if line and line.startswith(b"data: "):
                                data_str = line[6:].decode('utf-8', errors='replace')
                                try:
                                    data_json = json.loads(data_str)
                                    content = data_json.get("content", "")
                                    if content:
                                        audit_result += content
                                        st.write(content)
                                except Exception:
                                    # 不是JSON，直接当文本
                                    audit_result += data_str
                                    st.write(data_str)
                    if audit_result:
                        st.success("审核完成！")
                        with st.expander("审核结果"):
                            st.markdown(audit_result)
                        st.download_button(
                            label="下载审核结果",
                            data=audit_result,
                            file_name=f"{uploaded_file.name}_审核结果.txt",
                            mime="text/plain"
                        )
                    else:
                        st.error("未获取到有效审核内容")
                else:
                    st.error(f"请求失败 (状态码 {response.status_code})")
                    st.text(response.text)
            except Exception as e:
                st.error(f"审核过程中发生错误：{str(e)}")
else:
    st.info("请先上传合同文件。")