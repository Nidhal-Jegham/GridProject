import os
import json
import shlex
import logging
from dotenv import load_dotenv
from remote import SSHClientWrapper
from storage import StorageManager

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatClient:
    """
    Local client that sends prompts to a remote llama_server via SSH,
    persists chat history locally, and returns responses along with updated history.
    """
    def __init__(self):
        # Initialize SSH connection
        self.ssh = SSHClientWrapper()
        self.ssh.connect()

        # Initialize storage manager for local chat persistence
        self.storage = StorageManager()

        # Remote Python interpreter and script paths
        self.remote_python = os.getenv("REMOTE_PYTHON_PATH", "python3")
        self.remote_script = os.getenv(
            "REMOTE_LLAMA_SCRIPT_PATH",
            "~/llama_server.py"
        )
        self.model_path = os.getenv(
            "REMOTE_MODEL_PATH",
            "~/models/Llama-3-3b"
        )

    def send_message(self, chat_id: str, prompt: str) -> (str, list):
        """
        Send a prompt to the remote model via SSH, persist messages locally,
        and return (response, full_history).
        """
        # Ensure chat session exists
        self.storage.create_chat(chat_id)

        # Record user message locally
        self.storage.append_message(chat_id, "user", prompt)

        # Fetch full history for context
        history = self.storage.fetch_history(chat_id)

        # Prepare payload for remote inference
        payload = json.dumps({
            "chat_id": chat_id,
            "prompt": prompt,
            "history": history
        })
        quoted = shlex.quote(payload)
        cmd = (
            f"echo {quoted} | {self.remote_python} {self.remote_script}"
            f" --model-path {shlex.quote(self.model_path)}"
        )

        logger.info(f"Running remote inference cmd: {cmd}")
        try:
            out = self.ssh.execute_command(cmd)
            data = json.loads(out)
            response = data.get("response")
        except Exception as e:
            logger.error(f"Error during remote inference: {e}")
            raise

        # Persist assistant response locally
        self.storage.append_message(chat_id, "assistant", response)

        # Return response and updated history
        full_history = self.storage.fetch_history(chat_id)
        return response, full_history

    def list_chats(self) -> list:
        """Return a list of all chat sessions (chat_id, created_at)."""
        return self.storage.list_chats()

    def get_history(self, chat_id: str) -> list:
        """Fetch the full history for a given chat_id."""
        return self.storage.fetch_history(chat_id)

    def close(self):
        """Close SSH and storage connections."""
        self.ssh.close()
        self.storage.close()

# Example usage:
# if __name__ == '__main__':
#     client = ChatClient()
#     response, history = client.send_message("session1", "Hello, Llama!")
#     print("Response:", response)
#     print("History:", history)
#     client.close()