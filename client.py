import asyncio
from fastmcp import Client

client = Client("http://127.0.0.1:3003/mcp")


async def call_add_tool(a, b):
    print(f"--- Calling tool: add(a={a}, b={b}) ---")
    async with client:
        result = await client.call_tool("add", {"a": a, "b": b})
    print(f"✅ Server response: {result}")
    print(f"Result of {a} + {b} = {result.data}")


async def get_config_resource():
    print("--- Accessing resource: resource://config ---")
    async with client:
        result = await client.read_resource("resource://config")
    print("✅ Server response (config):")
    print(result.data if hasattr(result, "data") else result)


async def get_personalized_greeting(name):
    print(f"--- Accessing resource: greetings://{name} ---")
    async with client:
        result = await client.read_resource(f"greetings://{name}")
    print(f"✅ Server response:")
    print(result.data if hasattr(result, "data") else result)


if __name__ == "__main__":
    print("🚀 Starting MCP Client Demo...\n")

    async def main():
        await call_add_tool(15, 27)
        await get_config_resource()
        await get_personalized_greeting("Alice")
        print("🏁 Client demo finished.")

    asyncio.run(main())
