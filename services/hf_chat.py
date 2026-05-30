"""
services/hf_chat.py — HuggingFace chat completion logic.

Pure business logic with no HTTP/FastAPI concerns.
"""

from config import CHAT_MODEL_ID, hf_client


def generate_chat_response(messages: list[dict], max_tokens: int = 1024) -> str:
    """
    Send a list of chat messages to the Qwen model via HuggingFace
    Inference API and return the generated text.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        max_tokens: Maximum tokens to generate.

    Returns:
        The assistant's reply as a plain string.

    Raises:
        Exception: Any error from the HuggingFace API.
    """
    completion = hf_client.chat.completions.create(
        model=CHAT_MODEL_ID,
        messages=messages,
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content
