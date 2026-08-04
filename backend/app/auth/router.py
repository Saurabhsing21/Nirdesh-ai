from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import CurrentUserDependency, get_auth_service
from app.auth.email import OtpDeliveryError
from app.auth.schemas import (
    CurrentUserResponse,
    RequestOtpBody,
    RequestOtpResponse,
    TokenResponse,
    VerifyOtpBody,
)
from app.auth.service import AuthService, InvalidOtpError
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/request-otp",
    response_model=RequestOtpResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_otp(
    body: RequestOtpBody,
    service: AuthServiceDependency,
) -> RequestOtpResponse:
    try:
        await service.request_otp(str(body.email))
    except OtpDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OTP delivery failed",
        ) from exc
    return RequestOtpResponse(
        message="If the email can receive messages, an OTP has been sent.",
        expires_in_seconds=service.otp_ttl_seconds,
    )


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(
    body: VerifyOtpBody,
    service: AuthServiceDependency,
) -> TokenResponse:
    try:
        token = await service.verify_otp(str(body.email), body.code)
    except InvalidOtpError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TokenResponse(
        access_token=token,
        expires_in_seconds=service.access_token_ttl_seconds,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUserDependency) -> User:
    return user
