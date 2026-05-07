import httpx

# Define the registry here instead of main.py
pools: dict[str, httpx.AsyncClient] = {}

async def get_pools():
    """Simple getter to use as a FastAPI dependency if needed"""
    return pools