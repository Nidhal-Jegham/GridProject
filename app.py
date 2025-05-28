import streamlit as st
import uuid
from client import ChatClient

# Initialize ChatClient
if 'chat_client' not in st.session_state:
    st.session_state.chat_client = ChatClient()
client = st.session_state.chat_client

# Initialize current chat session
if 'current_chat' not in st.session_state:
    st.session_state.current_chat = None

st.sidebar.title("🗂️ Chats")
# New chat button
def new_chat():
    new_id = str(uuid.uuid4())
    client.storage.create_chat(new_id)
    st.session_state.current_chat = new_id

st.sidebar.button("+ New Chat", on_click=new_chat)

# List existing chats
chats = client.list_chats()
chat_ids = [cid for cid, _ in chats]
if chat_ids:
    selected = st.sidebar.radio(
        "Select Session", chat_ids,
        index=chat_ids.index(st.session_state.current_chat) if st.session_state.current_chat in chat_ids else 0
    )
    st.session_state.current_chat = selected
else:
    st.sidebar.info("No chats yet. Click + New Chat to start.")

# Main chat area
if st.session_state.current_chat:
    st.title(f"Chat Session: {st.session_state.current_chat}")
    # Display chat history
    history = client.get_history(st.session_state.current_chat)
    for msg in history:
        role = msg['role']
        content = msg['content']
        if role == 'user':
            st.markdown(f"**You:** {content}")
        else:
            st.markdown(f"**Assistant:** {content}")

    # Input box
    def send_message():
        user_input = st.session_state.user_input.strip()
        if user_input:
            client.send_message(st.session_state.current_chat, user_input)
            st.session_state.user_input = ""
            st.experimental_rerun()

    if 'user_input' not in st.session_state:
        st.session_state.user_input = ""

    st.text_input("Your message:", key='user_input', on_change=send_message)
else:
    st.title("Welcome to Llama 3 Chat")
    st.write("Create or select a chat session from the sidebar to begin.")
