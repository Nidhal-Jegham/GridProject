import streamlit as st
import uuid
import os
import requests
from client import ChatClient
from auth import AuthManager
from streamlit_oauth import OAuth2Component

st.set_page_config(layout="wide")

# --- 1. Global CSS for layout & styling ---
st.markdown("""
<style>
  .appview-container .main .block-container {
    padding: 0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  #chat-container {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }
  #input-container {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #0e1117;
    padding: 0.5rem 1rem;
    border-top: 1px solid #333;
    z-index: 100;
  }
  .appview-container .main .block-container > section {
    margin-bottom: 60px;
  }

  /* Remove any max-width constraint so bubbles span naturally */
  .bubble {
    padding: 12px;
    border-radius: 12px;
    color: #FFF;
  }
  .user {
    background: #333333;
  }
  .bot {
    background: rgba(255,255,255,0.1);
  }
  .bot_thinking {
    background: rgba(0,0,0,0);
  }
  .login-overlay {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #0e1117;
    padding: 2rem;
    border: 1px solid #333;
    z-index: 200;
    width: 320px;
  }
  .top-right {
    position: fixed;
    top: 10px;
    right: 10px;
    z-index: 150;
  }
</style>
""", unsafe_allow_html=True)

# --- Authentication setup ---
auth = AuthManager()
if "user" not in st.session_state:
    st.session_state.user = None
if "show_login" not in st.session_state:
    st.session_state.show_login = False
if "show_register" not in st.session_state:
    st.session_state.show_register = False
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
GOOGLE_AUTHORIZATION_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
google_oauth = OAuth2Component(
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_AUTHORIZATION_BASE_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_SCOPE,
    GOOGLE_REDIRECT_URI,
)

# --- 2. Chat bubble helper ---
def render_bubble(message: str, role: str):
    if role == "user":
        cls, align = "user", "flex-end"
        st.markdown(f"""
            <div style="display:flex; justify-content:{align}; margin:6px 0;">
                <div class="bubble {cls}">
                    {message}
                </div>
            </div>
        """, unsafe_allow_html=True)

    elif role == "assistant_think":
        cls, align = "bot_thinking", "flex-start"
        st.markdown(f"""
            <div style="display:flex; justify-content:{align}; margin:6px 0; class="bubble {cls}">
                {message}
            </div>
        """, unsafe_allow_html=True)

    else:  # "assistant"
        cls, align = "bot", "flex-start"
        st.markdown(f"""
            <div style="display:flex; justify-content:{align}; margin:6px 0;">
                <div class="bubble {cls}">
                    {message}
                </div>
            </div>
        """, unsafe_allow_html=True)

# --- 3. Sidebar & model config ---
ALL_MODELS = {
    "LLaMA 3.2 3B":    {"name": "llama3.2:3b", "ram": "2.0 GB",  "supports_think": False},
    "LLaMA 3.1 8B":    {"name": "llama3.1:8b", "ram": "4.9 GB",  "supports_think": False},
    "Qwen 3 14B":      {"name": "qwen3:14b",  "ram": "9.3 GB",  "supports_think": True},
    "DeepSeek R1 70B": {"name": "deepseek-r1:70b","ram":"42 GB","supports_think": True},
    "LLaMA 3.1 70B":   {"name": "llama3.1:70b","ram":"39 GB",   "supports_think": False},
}
MODELS = ALL_MODELS if st.session_state.user else {"LLaMA 3.2 3B": ALL_MODELS["LLaMA 3.2 3B"]}
st.sidebar.title("**Choose a model:**")
selected = st.sidebar.selectbox("", list(MODELS.keys()))
cfg = MODELS[selected]
model_name = cfg["name"]
supports_think = cfg["supports_think"]

# --- 4. Generation parameters sidebar ---
st.sidebar.title("Generation Parameters")
with st.sidebar.expander("Adjust hyperparameters", expanded=False):
    if "params" not in st.session_state:
        st.session_state.params = {
            "max_new_tokens": 4096, "min_new_tokens": 256,
            "temperature": 0.7,     "top_p": 0.5,
            "top_k": 50,            "repetition_penalty": 1.2,
            "length_penalty": 2.0
        }
    p = st.session_state.params
    p["max_new_tokens"] = st.slider("Max new tokens", 16, 4096, p["max_new_tokens"])
    p["min_new_tokens"] = st.slider("Min new tokens", 0, 256, p["min_new_tokens"])
    p["temperature"]    = st.slider("Temperature", 0.1, 1.0, p["temperature"], 0.05)
    p["top_p"]          = st.slider("Top-p", 0.1, 1.0, p["top_p"], 0.05)
    p["top_k"]          = st.slider("Top-k", 0, 200, p["top_k"])

# --- 5. Initialize client & sessions ---
if "chat_client" not in st.session_state:
    st.session_state.chat_client = ChatClient()
client = st.session_state.chat_client
client.params = st.session_state.params

st.sidebar.title("Chats")
if st.sidebar.button("+ New Chat"):
    new_id = str(uuid.uuid4())
    client.storage.create_chat(new_id)
    st.session_state.current_chat = new_id

sidebar_radio_ph = st.sidebar.empty()
chats = client.storage.list_chats()
if not chats:
    new_id = str(uuid.uuid4())
    client.storage.create_chat(new_id)
    st.session_state.current_chat = new_id
    chats = client.storage.list_chats()
ids   = [c for c,_,_ in chats]
names = [t or "Chat" for _,_,t in chats]
idx = sidebar_radio_ph.radio(
    "Select Session", list(range(len(ids))),
    format_func=lambda i: names[i],
    index=ids.index(st.session_state.get("current_chat",""))
          if st.session_state.get("current_chat") in ids else 0
)
st.session_state.current_chat = ids[idx]
cid = st.session_state.current_chat

title_ph = st.empty()
initial_title = client.storage.get_chat_title(cid)
if initial_title:
    title_ph.markdown(f"## {initial_title}")

# --- Top right login/register controls ---
top_right = st.empty()
with top_right:
    st.markdown("<div class='top-right'>", unsafe_allow_html=True)
    if st.session_state.user:
        st.write(f"Logged in as {st.session_state.user}")
        if st.button("Logout", key="logout_btn"):
            st.session_state.user = None
            st.experimental_rerun()
    else:
        if st.button("Login", key="login_btn"):
            st.session_state.show_login = True
        if st.button("Make Account", key="register_btn"):
            st.session_state.show_register = True
    st.markdown("</div>", unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("<p style='text-align:center; font-size: 32px;'>\U0001F464</p>", unsafe_allow_html=True)

# --- Login / Register overlays ---
if st.session_state.show_login:
    with st.container():
        st.markdown("<div class='login-overlay'>", unsafe_allow_html=True)
        login_email = st.text_input("Email", key="login_email")
        login_pw = st.text_input("Password", type="password", key="login_pw_main")
        if st.button("Login", key="login_submit"):
            if auth.validate_user(login_email, login_pw):
                st.session_state.user = login_email
                st.session_state.show_login = False
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")
        oauth_res = google_oauth.authorize_button("Login with Google", key="google_login")
        if oauth_res and "token" in oauth_res:
            token = oauth_res.get("token")
            headers = {"Authorization": f"Bearer {token['access_token']}"}
            userinfo = requests.get("https://www.googleapis.com/oauth2/v1/userinfo", headers=headers).json()
            email = userinfo.get("email")
            if email:
                auth.login_with_google(email)
                st.session_state.user = email
                st.session_state.show_login = False
                st.experimental_rerun()
        if st.button("Create account", key="switch_to_register"):
            st.session_state.show_login = False
            st.session_state.show_register = True
        st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.show_register:
    with st.container():
        st.markdown("<div class='login-overlay'>", unsafe_allow_html=True)
        reg_email = st.text_input("Email", key="reg_email_main")
        reg_pw = st.text_input("Password", type="password", key="reg_pw_main")
        if st.button("Register", key="register_submit"):
            if "@" in reg_email and auth.create_user(reg_email, reg_pw):
                st.success("Account created")
                st.session_state.show_register = False
            else:
                st.error("User exists")
        if st.button("Back to login", key="switch_to_login"):
            st.session_state.show_register = False
            st.session_state.show_login = True
        st.markdown("</div>", unsafe_allow_html=True)

# --- 6. Create two columns: chat on left, blank placeholder on right ---
left_col, right_col = st.columns([4, 1])

# Use a container inside the left column for chat history
chat_container = left_col.container()

if "history" not in st.session_state:
    st.session_state.history = {}
if cid not in st.session_state.history:
    msgs = client.storage.fetch_history(cid)
    st.session_state.history[cid] = [(m['role'], m['content']) for m in msgs]
history = st.session_state.history[cid]

def draw_history():
    chat_container.empty()
    with chat_container:
        for role, text in history:
            if role == "assistant_think":
                with st.expander("Thinking…", expanded=False):
                    render_bubble(text, role)
            else:
                render_bubble(text, role)

if history:
    draw_history()

# --- 7. Input form & streaming ---
if not (st.session_state.show_login or st.session_state.show_register):
    with left_col.form("form", clear_on_submit=True):
        user_input = st.text_input("Your message…", key="input")
        send = st.form_submit_button("Send")
else:
    user_input = ""
    send = False

if send and user_input:
    history.append(("user", user_input))
    with chat_container:
        render_bubble(user_input, "user")

    with chat_container:
        if supports_think:
            think_exp = st.expander("Thinking…", expanded=False)
            think_ph  = think_exp.empty()
        answer_ph = st.empty()

    thinking_text = ""
    answer_text   = ""
    title_updated = False

    for chunk in client.stream_message(cid, user_input, model_name):
        # update title if needed
        if not title_updated:
            new_title = client.storage.get_chat_title(cid) or "Chat"
            if new_title != initial_title:
                title_ph.markdown(f"## {new_title}")
                chats = client.storage.list_chats()
                ids   = [c for c,_,_ in chats]
                names = [t or "Chat" for _,_,t in chats]
                idx = sidebar_radio_ph.radio(
                    "Select Session", list(range(len(ids))),
                    format_func=lambda i: names[i],
                    index=ids.index(cid)
                )
                st.session_state.current_chat = ids[idx]
            title_updated = True

        # unpack chunk
        ctype = chunk.get("type", "answer") if isinstance(chunk, dict) else "answer"
        text  = chunk.get("text", "")      if isinstance(chunk, dict) else chunk

        if ctype == "think" and supports_think:
            thinking_text += text
            think_ph.markdown(
                f"<div class='bubble bot_thinking'>{thinking_text}</div>",
                unsafe_allow_html=True
            )
        else:
            answer_text += text
            answer_ph.markdown(
                f"<div class='bubble bot'>{answer_text}</div>",
                unsafe_allow_html=True
            )

    history.append(("assistant_think", thinking_text))
    history.append(("assistant", answer_text))

# right_col is left empty for future use
