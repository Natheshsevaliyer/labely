"""Application entry-point: FastAPI app creation, lifespan, middleware, and exception handlers."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.database import init_database
from app.core.exceptions import (
    AppException,
    AuthenticationException,
    NotFoundException,
    ValidationException,
)
from app.core.redis_client import close_redis, init_redis, redis_client
from app.core.redis_queue import redis_queue
from app.core.response import ErrorResponse
from app.utils.logging_utils import setup_logging
from app.services.file_service import file_service

# ---------------------------------------------------------------------------
# Logging bootstrap
# ---------------------------------------------------------------------------
setup_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.ENVIRONMENT == "production",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry worker
# ---------------------------------------------------------------------------

async def _retry_worker() -> None:
    """Background task: requeue jobs whose retry delay has expired."""
    logger.info("Retry worker started")
    QUEUES = ["label_generation", "tracking_update", "shipment_confirmation"]

    while True:
        try:
            if not redis_client.is_initialized:
                logger.debug("Retry worker: Redis not ready, sleeping 60 s")
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(30)

            for queue in QUEUES:
                pattern = f"retry:{queue}:*"
                try:
                    async for key in redis_client.client.scan_iter(match=pattern):
                        try:
                            parts = key.split(":")
                            if len(parts) >= 3 and int(parts[-1]) <= datetime.now(timezone.utc).timestamp():
                                raw = await redis_client.client.get(key)
                                if raw:
                                    job = redis_client._deserialize(raw)
                                    if isinstance(job, dict):
                                        await redis_queue.enqueue(queue, job.get("data", {}))
                                        await redis_client.client.delete(key)
                                        logger.debug("Retry worker: requeued job from %s", key)
                        except (ValueError, IndexError) as exc:
                            logger.warning("Retry worker: bad key %s – %s", key, exc)
                except Exception as exc:
                    logger.error("Retry worker: error scanning queue '%s': %s", queue, exc)

        except asyncio.CancelledError:
            logger.info("Retry worker cancelled – shutting down")
            break
        except Exception as exc:
            logger.error("Retry worker: unexpected error: %s", exc, exc_info=True)
            await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s in %s mode", settings.APP_NAME, settings.ENVIRONMENT)

    init_database()
    logger.info("Database initialised")

    if await init_redis():
        logger.info("Redis initialised")
        asyncio.create_task(_retry_worker())
    else:
        logger.warning("Redis unavailable – running without Redis features")

    from app.services.file_service import file_service
    file_service.cleanup_old_files(minutes_old=settings.FILE_CLEANUP_MINUTES)
    logger.info("Old output files cleaned up")

    yield

    await close_redis()
    logger.info("Application shut down")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# CORS
# app/main.py

# ... other imports ...

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Middleware to ensure all responses include proper error handling and logging."""
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Unhandled exception in middleware for {request.method} {request.url.path}: {str(e)}", exc_info=True)
        # Let FastAPI's exception handlers take over
        raise

@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    """
    Simple CSRF protection: checks for a custom header on state-changing requests.
    """
    # Always allow OPTIONS (preflight requests) to pass through
    if request.method == "OPTIONS":
        return await call_next(request)
    
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        # Skip check for login/register as they don't have cookies yet
        # Note: Added /api/v1/ prefix to match your router
        safe_paths = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"]
        
        if request.url.path not in safe_paths:
            if not request.headers.get("X-Requested-With"):
                return JSONResponse(
                    status_code=403,
                    content={
                        "success": False,
                        "error": "CSRF Protection",
                        "message": "Missing X-Requested-With header"
                    }
                )
    
    return await call_next(request)
# --- END OF NEW BLOCK ---
# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

def _error_response(exc: AppException, debug_detail: bool = False) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.message,
            details=exc.details,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ).model_dump(),
    )


@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    logger.warning("Not found: %s %s – %s", request.method, request.url.path, exc.message)
    return _error_response(exc)


@app.exception_handler(ValidationException)
async def validation_handler(request: Request, exc: ValidationException):
    logger.warning("Validation error on %s: %s", request.url.path, exc.message)
    return _error_response(exc)


@app.exception_handler(AuthenticationException)
async def authentication_handler(request: Request, exc: AuthenticationException):
    logger.warning("Auth failure on %s: %s", request.url.path, exc.message)
    return _error_response(exc)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error("App error on %s: %s", request.url.path, exc.message)
    return _error_response(exc)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            details=str(exc) if settings.DEBUG else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(api_v1_router, prefix="/api/v1")


# ---------------------------------------------------------------------------
# Health / status endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "message": f"{settings.APP_NAME} API",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if settings.DEBUG else None,
    }


@app.get("/health")
async def health_check():
    import psutil
    from sqlalchemy import text

    from app.core.database import engine
    from app.services.srp.service import srp_service

    status: dict = {"status": "healthy", "services": {}}

    # Database
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        pool = engine.pool
        status["services"]["database"] = {
            "status": "connected",
            "checked_in": pool.checkedin(),
        }
        logger.debug("Health check: database OK")
    except Exception as exc:
        status["services"]["database"] = {"status": f"disconnected: {exc}"}
        status["status"] = "degraded"
        logger.error("Health check: database FAIL – %s", exc)

    # Redis
    try:
        if redis_client.is_initialized:
            ok = await redis_client.health_check()
            status["services"]["redis"] = {
                "status": "connected" if ok else "unavailable",
                "info": await redis_client.get_info() if ok else {},
            }
        else:
            status["services"]["redis"] = {"status": "not initialised"}
    except Exception as exc:
        status["services"]["redis"] = {"status": f"error: {exc}"}
        status["status"] = "degraded"
        logger.error("Health check: redis FAIL – %s", exc)

    # SRP
    # try:
    #     alive = srp_service.is_alive()
    #     status["services"]["srp"] = "alive" if alive else "unavailable"
    #     if not alive:
    #         status["status"] = "degraded"
    #         logger.warning("Health check: SRP unavailable")
    # except Exception as exc:
    #     status["services"]["srp"] = f"error: {exc}"
    #     status["status"] = "degraded"
    #     logger.error("Health check: SRP FAIL – %s", exc)

    # System
    status["system"] = {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage_percent": psutil.disk_usage("/").percent,
    }

    return status

# Add this periodic cleanup task
async def _periodic_file_cleanup():
    """Background task that cleans up old files every 30 minutes."""
    while True:
        try:
            await asyncio.sleep(1800)  # Run every 30 minutes
            file_service.cleanup_old_files(minutes_old=settings.FILE_CLEANUP_MINUTES)
            logger.info(f"Periodic file cleanup completed")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Periodic file cleanup failed: {e}")

# In your lifespan function, add:
cleanup_task = asyncio.create_task(_periodic_file_cleanup())


@app.get("/redis-status")
async def redis_status():
    """Lightweight Redis connectivity probe."""
    if redis_client.is_initialized:
        healthy = await redis_client.health_check()
        return {
            "initialised": True,
            "healthy": healthy,
            "info": await redis_client.get_info() if healthy else {},
        }
    return {"initialised": False, "healthy": False, "info": {}}
