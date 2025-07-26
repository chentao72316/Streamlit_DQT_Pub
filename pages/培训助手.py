import streamlit as st
import requests
import json
from utils.config_loader import load_config
import os
from io import BytesIO
import base64
from qcloud_cos import CosConfig, CosS3Client

# 文档内容提取工具
from typing import Optional

def extract_text(file: bytes, filename: str) -> str:
    ext = os.path.splitext(filename)[-1].lower()
    if ext == ".txt":
        try:
            return file.decode("utf-8", errors="ignore")
        except Exception:
            return "（无法预览该格式内容）"
    elif ext == ".docx":
        try:
            from docx import Document
            doc = Document(BytesIO(file))
            text = "\n".join([p.text for p in doc.paragraphs])
            return text
        except Exception:
            return "（无法预览该格式内容）"
    elif ext == ".pdf":
        try:
            import PyPDF2
            pdf = PyPDF2.PdfReader(BytesIO(file))
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text
        except Exception:
            return "（无法预览该格式内容）"
    else:
        return "（无法预览该格式内容）"

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
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_key = f"train_helper/{timestamp}_{filename}"
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

def get_mime_type(ext):
    """获取文件的MIME类型"""
    mime_types = {
        'pdf': 'application/pdf',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'txt': 'text/plain'
    }
    return mime_types.get(ext, 'application/octet-stream')

st.set_page_config(page_title="培训助手", page_icon="📚")
st.title("📚 培训助手智能体")

st.markdown("""
本页面支持上传培训文档，设置各类题型数量，自动调用智能体生成培训内容，显示处理过程，并可下载生成结果。
""")

config = load_config()
api_key = config["coze"]["api_key"]
workflow_id = config["coze"].get("train_workflow_id")  # 需在 config.json 配置 train_workflow_id

uploaded_file = st.file_uploader("请上传培训文档（支持PDF/DOCX/TXT）", type=["pdf", "docx", "txt"])

# 题型数量输入，四列展示
with st.form("题型设置"):
    st.markdown("#### 请选择各类题型数量：")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        choice_cnt = st.number_input("选择题数量", min_value=0, max_value=100, value=1, step=1)
    with col2:
        fill_in_blank_cnt = st.number_input("填空题数量", min_value=0, max_value=100, value=1, step=1)
    with col3:
        true_false_cnt = st.number_input("判断题数量", min_value=0, max_value=100, value=1, step=1)
    with col4:
        short_answer_cnt = st.number_input("简答题数量", min_value=0, max_value=100, value=1, step=1)
    submit_btn = st.form_submit_button("生成培训内容")

if uploaded_file:
    file_content = uploaded_file.read()
    st.success(f"已上传文件：{uploaded_file.name}")
    # 展示文件内容片段，自动格式识别
    with st.expander("查看文档内容片段"):
        content_text = extract_text(file_content, uploaded_file.name)
        st.text(content_text[:1000] if content_text else "无法预览内容")
    
    if submit_btn:
        with st.spinner("正在上传文件到腾讯云COS..."):
            cos_url = upload_to_cos(file_content, uploaded_file.name)
        if not cos_url:
            st.error("文件上传失败，无法进行培训内容生成")
            st.stop()
        with st.spinner("正在调用智能体生成内容，请稍候..."):
            base_url = "https://api.coze.cn/v1/workflow/stream_run"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "workflow_id": workflow_id,
                "parameters": {
                    "choice_cnt": int(choice_cnt),
                    "fill_in_blank_cnt": int(fill_in_blank_cnt),
                    "true_false_cnt": int(true_false_cnt),
                    "short_answer_cnt": int(short_answer_cnt),
                    "knowledge_file": cos_url
                }
            }
            with st.expander("调试信息"):
                st.json(data)
            try:
                response = requests.post(base_url, headers=headers, data=json.dumps(data, ensure_ascii=False), timeout=600, stream=True)
                st.write("响应状态码:", response.status_code)
                if response.status_code == 200:
                    train_result = ""
                    with st.expander("流式生成进度"):
                        for line in response.iter_lines(decode_unicode=False):
                            if line and line.startswith(b"data: "):
                                data_str = line[6:].decode('utf-8', errors='replace')
                                try:
                                    data_json = json.loads(data_str)
                                    content = data_json.get("content", "")
                                    if content:
                                        train_result += content
                                        st.write(content)
                                except Exception:
                                    train_result += data_str
                                    st.write(data_str)
                    if train_result:
                        st.success("生成完成！")
                        with st.expander("查看生成过程与结果"):
                            st.write(train_result)
                            import re
                            match = re.search(r'(https?://[^\s]+)', train_result)
                            if match:
                                download_url = match.group(1)
                                st.markdown(f"**[点击下载生成的培训内容]({download_url})**")
                    else:
                        st.warning("生成完成但未获取到结果内容")
                        st.write("请检查API响应格式")
                else:
                    st.error(f"生成失败，状态码：{response.status_code}")
                    st.text(response.text)
            except Exception as e:
                st.error(f"生成过程中发生错误：{e}")
else:
    st.info("请先上传培训文档，并设置题型数量。") 