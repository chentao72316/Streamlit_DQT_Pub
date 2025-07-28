import streamlit as st
import requests
import json
from utils.config_loader import load_config

st.set_page_config(page_title="知识库助手", page_icon="💬")

config = load_config()
gpt_api = config["fastgpt"]["api"]
gpt_key = config["fastgpt"]["key"]
gpt_appid = config["fastgpt"]["appid"]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.markdown(
    """
    <div style="position:sticky;top:0;background:white;z-index:100;padding-bottom:1rem;">
        <h1 style="margin-bottom:0.2em;">💬 知识库助手（工会）</h1>
        <div style="color:#444;margin-bottom:1em;">
            本页面支持与知识库助手多轮对话，仿 fastgpt 聊天界面，适合知识问答、资料检索等场景。
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

def send_message(user_input):
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.spinner("正在生成回复..."):
        headers = {
            "Authorization": f"Bearer {gpt_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "app_id": gpt_appid,
            "messages": st.session_state.chat_history,
            "stream": False
        }
        try:
            resp = requests.post(gpt_api, headers=headers, data=json.dumps(payload), timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                reply = data.get("choices", [{}])[0].get("message", {}).get("content", "无回复")
                st.session_state.chat_history.append({"role": "assistant", "content": reply})
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": f"[接口错误] 状态码：{resp.status_code}"})
        except Exception as e:
            st.session_state.chat_history.append({"role": "assistant", "content": f"[异常] {e}"})

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_input("请输入您的问题：", key="user_input_form")
    submitted = st.form_submit_button("发送")
    if submitted and user_input.strip():
        send_message(user_input)

# 对话历史区，独立滚动，自动滚到底部
chat_html = """
<div id=\"chat-history\" style=\"height:400px;overflow-y:auto;border:1px solid #eee;padding:1em 1em 1em 1.5em;background:#fafbfc;border-radius:8px;\">
"""
for msg in st.session_state.chat_history:
    if msg["role"] == "user":
        chat_html += f"<div style='color:#1a73e8;margin-bottom:0.5em;'><b>用户：</b> {msg['content']}</div>"
    else:
        chat_html += f"<div style='color:#222;margin-bottom:0.5em;'><b>助手：</b> {msg['content']}</div>"
chat_html += """
</div>
<script>
    const chatDiv = window.parent.document.getElementById('chat-history');
    if(chatDiv){chatDiv.scrollTop = chatDiv.scrollHeight;}
</script>
"""

st.markdown("---")
st.markdown("#### 对话历史")
st.components.v1.html(chat_html, height=420, scrolling=False) 
