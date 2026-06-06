"""
services/hf_chat.py — HuggingFace chat completion logic.

Pure business logic with no HTTP/FastAPI concerns.
"""

from config import CHAT_MODEL_ID, hf_client


def generate_chat_response(messages: list[dict], max_tokens: int = 1024, temperature: float = 0.7) -> str:
    """
    Send a list of chat messages to the Qwen model via HuggingFace
    Inference API and return the generated text.

    Args:
        messages: List of dicts with 'role' and 'content' keys.
        max_tokens: Maximum tokens to generate.
        temperature: Controls randomness (higher = more random).

    Returns:
        The assistant's reply as a plain string.

    Raises:
        Exception: Any error from the HuggingFace API.
    """
    completion = hf_client.chat.completions.create(
        model=CHAT_MODEL_ID,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return completion.choices[0].message.content


def stream_chat_response(messages: list[dict], max_tokens: int = 1024):
    """
    Generator that streams chat completions from HuggingFace.
    Yields string chunks as they arrive.
    """
    stream = hf_client.chat.completions.create(
        model=CHAT_MODEL_ID,
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
    )
    for chunk in stream:
        if getattr(chunk.choices[0].delta, "content", None):
            yield chunk.choices[0].delta.content
