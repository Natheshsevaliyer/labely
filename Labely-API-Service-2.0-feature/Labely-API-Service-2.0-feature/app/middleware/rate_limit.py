import logging

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Create limiter
limiter = Limiter(key_func=get_remote_address)

def setup_rate_limiting(app: FastAPI):
    """Setup rate limiting for the app"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Skip for certain paths
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        # Create a proper async function with request parameter
        async def dummy_func(req: Request):
            return None

        try:
            # Apply limits based on path with proper request parameter
            if request.url.path.startswith("/api/auth"):
                # Auth endpoints
                limited_func = limiter.limit("10/minute")(dummy_func)
                await limited_func(request)  # Pass the request
                logger.debug(f"Rate limit applied to auth: {request.url.path}")

            elif request.url.path.startswith("/api/orders/generate-labels"):
                # Heavy operations
                limited_func = limiter.limit("20/hour")(dummy_func)
                await limited_func(request)
                logger.debug("Rate limit applied to label generation")

            elif "status" in request.url.path or "process" in request.url.path:
                # Status checks - higher limit
                limited_func = limiter.limit("200/minute")(dummy_func)
                await limited_func(request)
                logger.debug("Rate limit applied to status check")

            else:
                # Default
                limited_func = limiter.limit("100/minute")(dummy_func)
                await limited_func(request)
                logger.debug("Rate limit applied to general request")

        except RateLimitExceeded:
            # Re-raise to be caught by exception handler
            raise
        except Exception as e:
            # Log but don't block the request
            logger.error(f"Rate limiting error: {e}")

        return await call_next(request)
