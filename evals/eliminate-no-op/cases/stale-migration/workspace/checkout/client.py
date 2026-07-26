import httpx

_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))


async def get_provider_status() -> dict:
    resp = await _client.get("https://provider.test/status")
    resp.raise_for_status()
    return resp.json()
