#!/usr/bin/env python3
"""
llama_server.py

A simple CLI-based chat inference script for Llama 3 3B (or any compatible HF model).
Reads a JSON payload from stdin with keys:
  - chat_id: (optional) unique identifier for the chat session
  - prompt: the new user message (string)
  - history: list of {role: "user"/"assistant", content: string}

Outputs a JSON to stdout with:
  - response: the generated assistant reply
  - new_history: updated list including the prompt and response

Usage (on remote host):
  echo '{"chat_id": "abc123", "prompt": "Hello", "history": []}' |
    python llama_server.py --model-path "/path/to/llama-3-3b" --max-new-tokens 256
"""
import sys
import json
import argparse
import logging
import torch
from transformers import LlamaForCausalLM, LlamaTokenizer

# Setup logging
def get_logger():
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
    return logging.getLogger(__name__)

logger = get_logger()

def load_model(model_path: str):
    """Load the tokenizer and model to GPU (if available)"""
    logger.info(f"Loading model and tokenizer from {model_path}")
    tokenizer = LlamaTokenizer.from_pretrained(model_path)
    model = LlamaForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto"
    )
    model.eval()
    return tokenizer, model


def generate_response(tokenizer, model, prompt: str, history: list, max_new_tokens: int = 256) -> str:
    """
    Constructs a single input sequence from history + prompt and returns the generated continuation.
    Adjust the formatting tokens (e.g., <s>, USER:, ASSISTANT:) as needed for your fine-tuning.
    """
    # Build the sequence string
    sequence = ""
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            sequence += f"<s>USER: {content}</s>"
        else:
            sequence += f"<s>ASSISTANT: {content}</s>"
    sequence += f"<s>USER: {prompt}</s><s>ASSISTANT:"

    # Tokenize and move to device
    inputs = tokenizer(sequence, return_tensors="pt").to(model.device)
    logger.info(f"Generating up to {max_new_tokens} tokens...")

    # Generate without sampling (greedy); adjust do_sample or temperature if desired
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            do_sample=False
        )

    # Decode only the newly generated tokens
    generated_ids = output_ids[0][inputs['input_ids'].shape[-1]:]
    response = tokenizer.decode(generated_ids, skip_special_tokens=True)
    return response


def main():
    parser = argparse.ArgumentParser(description="Llama 3 3B chat inference CLI")
    parser.add_argument(
        "--model-path", required=True,
        help="Local path or HF repo ID for the Llama model"
    )
    parser.add_argument(
        "--max-new-tokens", type=int, default=256,
        help="Maximum number of tokens to generate"
    )
    args = parser.parse_args()

    tokenizer, model = load_model(args.model_path)

    # Read JSON input from stdin
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON input: {e}")
        sys.exit(1)

    chat_id = data.get("chat_id")
    prompt = data.get("prompt")
    history = data.get("history", [])

    if prompt is None:
        logger.error("`prompt` field is required in input JSON.")
        sys.exit(1)

    logger.info(f"Chat({chat_id}) Received prompt: {prompt}")
    response = generate_response(tokenizer, model, prompt, history, args.max_new_tokens)
    logger.info(f"Chat({chat_id}) Generated response: {response}")

    new_history = history + [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response}
    ]

    # Output the result as JSON
    print(json.dumps({"response": response, "new_history": new_history}))

if __name__ == "__main__":
    main()
