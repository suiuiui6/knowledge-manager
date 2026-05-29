import asyncio

async def main():
    print("async works")

if __name__ == "__main__":
    print("Starting...")
    asyncio.run(main())
    print("Done")
