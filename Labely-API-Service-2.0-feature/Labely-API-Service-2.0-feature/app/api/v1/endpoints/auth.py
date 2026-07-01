from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status, Response
from sqlalchemy.orm import Session

from app.api import deps  # This imports all dependencies including oauth2_scheme
from app.core.response import ApiResponse
from app.core.config import settings
from app.core.exceptions import AuthenticationException
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()

@router.post("/register", response_model=ApiResponse[UserResponse])
async def register(
    user_data: UserRegister,
    db: Session = Depends(deps.get_db)
) -> ApiResponse[UserResponse]:
    """Register a new user."""
    service = AuthService(db)
    user = await service.register(user_data)
    return ApiResponse(
        message="User registered successfully",
        data=UserResponse.model_validate(user)
    )

@router.post("/login", response_model=ApiResponse[Token])
async def login(
    request: Request,
    user_data: UserLogin,
    response: Response, # Add Response to set cookies
    db: Session = Depends(deps.get_db)
) -> ApiResponse[Token]:
    service = AuthService(db)
    result = await service.login(user_data, request)

    # Set Access Token Cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=result["access_token"],
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )

    # Set Refresh Token Cookie
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=result["refresh_token"],
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/api/v1/auth/refresh",
        max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
    )

    return ApiResponse(message="Login successful", data=Token(**result))

@router.post("/logout", response_model=ApiResponse[MessageResponse])
async def logout(
    response: Response,
    request: Request,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> ApiResponse[MessageResponse]:
    service = AuthService(db)
    
    # 1. Extract tokens from cookies to invalidate them
    access_token = request.cookies.get(settings.COOKIE_NAME)
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)

    if access_token:
        await service.logout(access_token)
    
    if refresh_token:
        service.revoke_refresh_token(refresh_token, user_id=current_user.id)
    
    # 2. Tell the browser to delete the cookies
    response.delete_cookie(key=settings.COOKIE_NAME)
    response.delete_cookie(key=settings.REFRESH_COOKIE_NAME, path="/api/v1/auth/refresh")
    
    return ApiResponse(message="Logged out successfully")

@router.post("/logout-all", response_model=ApiResponse[MessageResponse])
async def logout_all_devices(
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> ApiResponse[MessageResponse]:
    """Logout user from all devices"""
    service = AuthService(db)
    count = await service.logout_all_devices(current_user.id)
    return ApiResponse(message=f"Logged out from {count} devices successfully")

@router.get("/sessions", response_model=ApiResponse[List[Dict[str, Any]]])
async def get_active_sessions(
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> ApiResponse[List[Dict[str, Any]]]:
    """Get all active sessions for the current user"""
    service = AuthService(db)
    sessions = await service.get_active_sessions(current_user.id)
    return ApiResponse(data=sessions)

@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_info(
    current_user = Depends(deps.get_current_user)
) -> ApiResponse[UserResponse]:
    """Get current user information."""
    return ApiResponse(data=UserResponse.model_validate(current_user))

@router.post("/forgot-password", response_model=ApiResponse[MessageResponse])
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(deps.get_db)
) -> ApiResponse[MessageResponse]:
    """Request password reset."""
    service = AuthService(db)
    result = await service.forgot_password(
        request.email,
        background_tasks
    )
    return ApiResponse(message=result["message"], data=result)

@router.post("/reset-password", response_model=ApiResponse[MessageResponse])
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(deps.get_db)
) -> ApiResponse[MessageResponse]:
    """Reset password using token."""
    service = AuthService(db)
    result = service.reset_password(request.token, request.new_password)
    return ApiResponse(message=result["message"], data=result)

@router.post("/change-password", response_model=ApiResponse[MessageResponse])
async def change_password(
    request: ChangePasswordRequest,
    current_user = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
) -> ApiResponse[MessageResponse]:
    """Change password for authenticated user."""
    service = AuthService(db)
    result = service.change_password(
        current_user.id,
        request.old_password,
        request.new_password
    )
    return ApiResponse(message=result["message"], data=result)

@router.post("/refresh", response_model=ApiResponse[Token])
async def refresh_token(
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db)
) -> ApiResponse[Token]:
    # Read refresh token from cookie
    refresh_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    
    if not refresh_token:
        raise AuthenticationException("Refresh token missing")

    service = AuthService(db)
    result = service.refresh_access_token(refresh_token)
    
    # Set NEW access token in cookie (use runtime settings)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=result["access_token"],
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
    )
    
    return ApiResponse(data=Token(**result), message="Token refreshed")

__all__ = ["router"]
