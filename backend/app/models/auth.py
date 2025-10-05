"""Pydantic schemas and domain models for authentication flows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Payload required to create a new user account."""

    email: EmailStr
    password: str = Field(min_length=8)
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile token")


class LoginRequest(BaseModel):
    """Payload used to authenticate an existing user."""

    email: EmailStr
    password: str
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile token")


class PasswordResetRequest(BaseModel):
    """Initiate a password reset flow for a user."""

    email: EmailStr
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile token")


class PasswordResetConfirmRequest(BaseModel):
    """Complete a password reset using a token issued via e-mail."""

    token: str
    password: str = Field(min_length=8)
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile token")


class VerificationConfirmRequest(BaseModel):
    """Confirm e-mail ownership using a verification token."""

    token: str
    turnstile_token: str | None = Field(default=None, description="Cloudflare Turnstile token")


class MessageResponse(BaseModel):
    """Generic response wrapper containing a human readable message."""

    message: str


class UserResponse(BaseModel):
    """Public representation of a user account."""

    id: int
    email: EmailStr | None = None
    username: str | None = None
    display_name: str | None = None
    identifier: str | None = None
    is_verified: bool = False
    points: int = 0
    created_at: datetime
    updated_at: datetime


class AuthResponse(MessageResponse):
    """Response returned after successful authentication or verification."""

    user: UserResponse | None = None


class RegisterResponse(MessageResponse):
    """Response returned after attempting to register a new account."""

    user: UserResponse | None = None


class PublicAuthConfig(BaseModel):
    """Publicly exposed authentication configuration values for the frontend."""

    turnstile_site_key: str | None = None
    turnstile_disabled: bool = False
    verification_base_url: str
    password_reset_base_url: str
    verification_token_ttl_hours: int
    password_reset_token_ttl_hours: int


@dataclass(slots=True)
class User:
    """Domain representation of a persisted user."""

    id: int
    email: str
    password_hash: str
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


@dataclass(slots=True)
class VerificationToken:
    """Verification token issued to confirm account ownership."""

    token: str
    user: User | None
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime


@dataclass(slots=True)
class PasswordResetToken:
    """Password reset token issued to allow password changes."""

    token: str
    user: User | None
    expires_at: datetime
    consumed_at: datetime | None
    created_at: datetime
