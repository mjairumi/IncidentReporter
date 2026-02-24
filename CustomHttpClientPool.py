import httpx
from Logger import logger


class CustomHttpClientPool:
    _client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            raise RuntimeError("CustomHttpClientPool not initialized. Call startup() first.")
        return cls._client
    

    @classmethod
    async def startup(cls, max_connections: int = 100, max_keepalive: int = 20):
        cls._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=max_connections,          # Total concurrent connections
                max_keepalive_connections=max_keepalive, # How many to keep alive (reused)
                keepalive_expiry=30                      # Drop idle connections after 30s
            ),
            timeout=httpx.Timeout(
                connect=5,   # TCP + TLS handshake must complete in 5s
                read=10,     # Response must start arriving within 10s
                write=5,     # Request must be sent within 5s
                pool=5       # Wait max 5s for a free connection from pool
            ),
            headers={"User-Agent": "IncidentReporter/1.0"}
        )
        logger.info(
            f"[CustomHttpClientPool] Started — "
            f"max_connections={max_connections}, "
            f"max_keepalive={max_keepalive}"
        )

    @classmethod
    async def shutdown(cls):
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()
            logger.info("[CustomHttpClientPool] Shut down — all connections closed.")