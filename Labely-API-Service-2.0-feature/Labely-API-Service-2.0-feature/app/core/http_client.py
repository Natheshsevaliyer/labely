import httpx

# Create a reusable HTTP client with timeouts
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=20.0,
        pool=10.0
    ),
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=100
    )
)

# For sync operations
sync_http_client = httpx.Client(
    timeout=30.0,
    limits=httpx.Limits(
        max_keepalive_connections=20,
        max_connections=100
    )
)
