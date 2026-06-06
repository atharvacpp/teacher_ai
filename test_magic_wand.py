import asyncio
from services.pipeline_b_execution import stream_magic_wand

async def test():
    code = "def add(a, b): return a + b\n\nprint(add(1, '2'))"
    async for chunk in stream_magic_wand(code, "python"):
        print(chunk.strip())

if __name__ == "__main__":
    asyncio.run(test())
