import streamlit as st
import requests
import json
from io import BytesIO
from utils.config_loader import load_config
from qcloud_cos import CosConfig, CosS3Client
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
        region = cos_config.get("region", "ap-chengdu")
        bucket_name = cos_config.get("bucket_name")
        
        if not all([secret_id, secret_key, bucket_name]):
            st.error("腾讯云COS配置不完整")
            return None
            
        cos_config_obj = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
        client = CosS3Client(cos_config_obj)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_key = f"contract_audit/{timestamp}_{filename}"
        
        client.put_object(Bucket=bucket_name, Body=file_content, Key=file_key)
        cos_url = f"https://{bucket_name}.cos.{region}.myqcloud.com/{file_key}"
        st.success(f"文件已上传到腾讯云COS")
        return cos_url
    except Exception as e:
        st.error(f"腾讯云COS上传失败: {str(e)}")
        return None

def get_stream_styles():
    """获取流式显示的CSS样式"""
    return """
    <style>
    .stream-content {
        font-family: 'Microsoft YaHei', 'SimSun', sans-serif;
        font-size: 14px;
        line-height: 1.6;
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border-left: 4px solid #007bff;
        margin: 8px 0;
        white-space: pre-wrap;
        word-wrap: break-word;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .progress-info {
        color: #007bff;
        font-weight: bold;
        background-color: #e3f2fd;
        padding: 8px;
        border-radius: 5px;
        margin: 5px 0;
    }
    .error-content {
        background-color: #ffebee;
        border-left-color: #f44336;
        color: #c62828;
    }
    .audit-link {
        font-family: 'Microsoft YaHei', 'SimSun', sans-serif;
        font-size: 16px;
        font-weight: 600;
        color: #1976d2;
        margin: 8px 0;
        padding: 8px;
        background-color: #f5f5f5;
        border-radius: 4px;
        border-left: 3px solid #1976d2;
    }
    .audit-link a {
        color: #1976d2;
        text-decoration: none;
        font-weight: 500;
    }
    .audit-link a:hover {
        text-decoration: underline;
    }
    </style>
    """

def display_audit_result(result_text):
    """统一显示审核结果，确保链接格式一致"""
    # 添加样式
    st.markdown(get_stream_styles(), unsafe_allow_html=True)
    
    # 处理结果文本，统一链接显示格式
    processed_text = result_text
    
    # 使用markdown显示，确保格式一致
    st.markdown(processed_text, unsafe_allow_html=True)

def process_stream_response(response):
    """处理流式响应"""
    audit_result = ""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    with st.expander("🔄 流式审核进度", expanded=True):
        st.markdown(get_stream_styles(), unsafe_allow_html=True)
        
        progress_info = st.empty()
        content_display = st.empty()
        error_display = st.empty()
        
        content_count = error_count = 0
        
        for i, line in enumerate(response.iter_lines(decode_unicode=False)):
            if line and line.startswith(b"data: "):
                data_str = line[6:].decode('utf-8', errors='replace')
                try:
                    data_json = json.loads(data_str)
                    content = data_json.get("content", "")
                    if content:
                        audit_result += content
                        content_count += 1
                        
                        content_display.markdown(f"""
                        <div class="stream-content">
                        <strong>📝 内容片段 #{content_count}:</strong><br>
                        {content}
                        </div>
                        """, unsafe_allow_html=True)
                        
                        progress = min((i + 1) / 100, 0.95)
                        progress_bar.progress(progress)
                        status_text.text(f"🔄 正在审核中... ({progress*100:.0f}%)")
                        
                        progress_info.markdown(f"""
                        <div class="progress-info">
                        📊 <strong>审核进度:</strong> {progress*100:.0f}% | 
                        📝 <strong>已接收内容:</strong> {content_count} 个片段 | 
                        📏 <strong>总长度:</strong> {len(audit_result)} 字符
                        </div>
                        """, unsafe_allow_html=True)
                        
                except Exception:
                    audit_result += data_str
                    error_count += 1
                    error_display.markdown(f"""
                    <div class="stream-content error-content">
                    <strong>⚠️ 原始数据 #{error_count}:</strong><br>
                    {data_str}
                    </div>
                    """, unsafe_allow_html=True)
    
    progress_bar.progress(1.0)
    status_text.text("✅ 审核完成！")
    
    st.success(f"""
    🎉 **审核完成！**
    
    📊 **统计信息：**
    - 总内容长度：{len(audit_result)} 字符
    - 内容片段数：{content_count} 个
    - 原始数据片段：{error_count} 个
    - 处理数据包：{i+1} 个
    - 状态：✅ 成功
    """)
    
    return audit_result

# 初始化session_state
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
if 'audit_result' not in st.session_state:
    st.session_state.audit_result = ""
if 'uploaded_filename' not in st.session_state:
    st.session_state.uploaded_filename = ""

st.set_page_config(page_title="合同审核", page_icon="📄")
st.title("📄 合同审核智能体")
st.markdown("本页面支持上传合同初稿，自动调用智能体进行审核，显示审核过程，并可下载审核结果。")

config = load_config()
api_key = config["coze"]["api_key"]
workflow_id = config["coze"].get("contract_workflow_id")

# 如果审核已完成，显示结果页面
if st.session_state.audit_completed and st.session_state.audit_result:
    st.success("✅ 审核已完成！")
    
    with st.expander("📄 审核结果详情", expanded=True):
        display_audit_result(st.session_state.audit_result)
    
    st.download_button(
        label="📥 下载审核结果",
        data=st.session_state.audit_result,
        file_name=f"{st.session_state.uploaded_filename}_审核结果.txt",
        mime="text/plain",
        help="点击下载审核结果文件"
    )
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 重新审核", type="secondary"):
            st.session_state.audit_completed = False
            st.session_state.audit_result = ""
            st.session_state.uploaded_filename = ""
            st.rerun()
    
    with col2:
        st.info("💡 提示：点击'重新审核'可以上传新文件进行审核")
    
    st.stop()

# 文件上传区域
uploaded_file = st.file_uploader("请上传合同初稿（支持PDF/DOCX/TXT）", type=["pdf", "docx", "txt"])

if uploaded_file:
    file_content = uploaded_file.read()
    st.success(f"已上传文件：{uploaded_file.name} ({uploaded_file.size/1024:.1f}KB)")
    
    with st.expander("查看合同内容片段"):
        content_text = extract_text(file_content, uploaded_file.name)
        st.text(content_text[:1000] if content_text else "无法预览内容")
    
    if st.button("🚀 开始审核", type="primary"):
        with st.spinner("正在上传文件到腾讯云COS..."):
            cos_url = upload_to_cos(file_content, uploaded_file.name)
        
        if not cos_url:
            st.error("文件上传失败，无法进行合同审核")
            st.stop()
        
        with st.spinner("正在调用 Coze 工作流审核，请稍候..."):
            data = {
                "workflow_id": workflow_id,
                "parameters": {"file": cos_url}
            }
            
            with st.expander("调试信息"):
                st.json(data)
                st.write("cos_url:", cos_url)
            
            try:
                response = requests.post(
                    "https://api.coze.cn/v1/workflow/stream_run",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    data=json.dumps(data, ensure_ascii=False),
                    timeout=120,
                    stream=True
                )
                
                if response.status_code == 200:
                    audit_result = process_stream_response(response)
                    
                    if audit_result:
                        st.session_state.audit_completed = True
                        st.session_state.audit_result = audit_result
                        st.session_state.uploaded_filename = uploaded_file.name
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("未获取到有效审核内容")
                else:
                    st.error(f"请求失败 (状态码 {response.status_code})")
                    st.text(response.text)
            except Exception as e:
                st.error(f"审核过程中发生错误：{str(e)}")
else:
    st.info("请先上传合同文件。")