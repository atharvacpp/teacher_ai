import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
client = InferenceClient(api_key=os.getenv("HUGGINGFACE_API_KEY"))

# Red 1x1 pixel base64 image
b64_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": b64_img}
            },
            {
                "type": "text",
                "text": "Describe this image."
            }
        ]
    }
]

try:
    completion = client.chat.completions.create(
        model="Qwen/Qwen2-VL-7B-Instruct", 
        messages=messages, 
        max_tokens=100
    )
    print("SUCCESS:")
    print(completion.choices[0].message.content)
except Exception as e:
    print(f"FAILED: {e}")
