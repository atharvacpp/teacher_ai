import asyncio
import websockets
import json

async def test():
    async with websockets.connect('ws://127.0.0.1:8000/ws/execute') as ws:
        code = """
#include <stdio.h>
int main() {
    char name[50];
    printf("Name:");
    scanf("%49s", name);
    printf("Hi %s\\n", name);
    return 0;
}
"""
        await ws.send(json.dumps({'code': code, 'language': 'c'}))
        
        # Read intro message
        res = await ws.recv()
        print('RCV:', repr(res))
        
        while True:
            try:
                res = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print('RCV:', repr(res))
                if "Name:" in res:
                    break
            except asyncio.TimeoutError:
                print("Timeout waiting for 'Name:' prompt!")
                break
        
        print("Sending 'Alice\\r'...")
        await ws.send("Alice\r")
        
        while True:
            try:
                res = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print('RCV:', repr(res))
                if "Process exited" in res or "killed" in res or "error" in res.lower():
                    break
            except websockets.ConnectionClosed:
                break
            except asyncio.TimeoutError:
                print("Timeout waiting for response to Alice!")
                break

asyncio.run(test())
