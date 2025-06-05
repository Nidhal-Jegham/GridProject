import json
import logging
import requests
from storage import StorageManager
import re
from typing import Generator, Dict, Any
import subprocess

logger = logging.getLogger(__name__)

class ChatClient:
    """
    HTTP-based chat client for GridAI.
    Stores history in SQLite and forwards messages to the Ollama server.
    """
    def __init__(self, url: str = "http://127.0.0.1:11434"):
        self.url     = url.rstrip("/")
        self.storage = StorageManager()
        self.params  = {}

    def _generate_title(self, prompt: str, model: str) -> str:
        title_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that suggests chat titles."},
                {"role": "user",   "content": f"Generate a short (3-5 word) title for a conversation about: \"{prompt}\""}
            ],
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 10,
            "n": 1,
            "stream": False
        }
        r = requests.post(f"{self.url}/v1/chat/completions", json=title_payload, timeout=30)
        r.raise_for_status()
        title = r.json()["choices"][0]["message"]["content"].strip().strip('"')
        return title

    def send_message(self, chat_id: str, prompt: str, model: str) -> (str, list, str | None, dict | None):
        self.storage.create_chat(chat_id)
        self.storage.append_message(chat_id, "user", prompt)
        history = self.storage.fetch_history(chat_id)

        title = None
        if len(history) == 1:
            try:
                title = self._generate_title(prompt, 'llama3.2:3b')
                self.storage.set_chat_title(chat_id, title)
            except Exception as e:
                logger.warning(f"Failed to generate title: {e}")

        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": self.params.get("temperature", 0.7),
            "top_p":       self.params.get("top_p", 0.9),
            "max_tokens":  self.params.get("max_new_tokens", 4096),
            "n":           1,
            "stream":      False
        }

        resp = requests.post(f"{self.url}/v1/chat/completions", json=payload, timeout=300)
        resp.raise_for_status()
        raw_response = resp.json()["choices"][0]["message"]["content"].strip()

        # --- Extract <think> reasoning and final answer ---
        think_match = re.search(r"<think>\s*(.*?)\s*</think>\s*(.*)", raw_response, re.DOTALL)
        if think_match:
            reasoning    = think_match.group(1).strip()
            final_answer = think_match.group(2).strip()
            # Persist the reasoning as its own message
            self.storage.append_message(chat_id, "assistant_think", reasoning)
            reply = final_answer
        else:
            reasoning = None
            reply     = raw_response

        # Persist the final answer
        self.storage.append_message(chat_id, "assistant", reply)
        return reply, self.storage.fetch_history(chat_id), title, {"reasoning": reasoning, "raw": raw_response}

    def stream_message(self, chat_id: str, prompt: str, model: str) -> Generator[Dict[str, str], None, None]:
        """
        Streams a chat completion, splitting out <think>...</think> reasoning and the final answer.
        Yields dicts of the form {'type': 'think' or 'answer', 'text': delta_chunk}.
        Also generates a title on the first user message.
        """
        # Persist user prompt
        self.storage.append_message(chat_id, "user", prompt)
        history = self.storage.fetch_history(chat_id)

        # Generate chat title on first prompt
        if len(history) == 1:
            try:
                title = self._generate_title(prompt, "llama3.2:3b")
                self.storage.set_chat_title(chat_id, title)
            except Exception as e:
                logger.warning(f"Failed to generate title: {e}")

        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        payload = {
            "model":       model,
            "messages":    messages,
            "temperature": self.params.get("temperature", 0.7),
            "top_p":       self.params.get("top_p", 0.9),
            "max_tokens":  self.params.get("max_new_tokens", 4096),
            "n":           1,
            "stream":      True
        }

        collected     = ""
        reasoning_buf = ""
        answer_buf    = ""
        in_think      = False
        think_open    = "<think>"
        think_close   = "</think>"

        with requests.post(f"{self.url}/v1/chat/completions", json=payload, stream=True, timeout=300) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or line.startswith(b"data: [DONE]"):
                    continue

                piece = line.decode("utf-8").removeprefix("data: ")
                try:
                    token_data = json.loads(piece)
                    delta = token_data["choices"][0]["delta"].get("content", "")
                except Exception:
                    continue

                collected += delta

                # Enter reasoning phase
                if not in_think and think_open in collected:
                    in_think, collected = True, collected.split(think_open, 1)[1]

                # Still reasoning
                if in_think and think_close not in collected:
                    reasoning_buf += delta
                    yield {"type": "think", "text": delta}
                    continue

                # Close reasoning phase
                if in_think and think_close in collected:
                    before_close, after_close = collected.split(think_close, 1)
                    reasoning_buf += before_close
                    yield {"type": "think", "text": before_close}
                    
                    # Persist the full reasoning
                    self.storage.append_message(chat_id, "assistant_think", reasoning_buf.strip())
                    in_think, collected = False, ""
                    # leftover becomes answer
                    if after_close:
                        answer_buf += after_close
                        yield {"type": "answer", "text": after_close}
                    continue

                # Normal answer streaming
                answer_buf += delta
                yield {"type": "answer", "text": delta}

        # Persist only the final answer
        final_answer = answer_buf.strip()
        self.storage.append_message(chat_id, "assistant", final_answer)

    def list_chats(self) -> list:
        return self.storage.list_chats()

    def get_history(self, chat_id: str) -> list:
        return self.storage.fetch_history(chat_id)

    def close(self):
        self.storage.close()
