from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

_EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$"


class RegisterRequest(BaseModel):
    """Public sign-up. Unknown fields (such as ``role`` or ``is_admin``) are rejected:
    there are no roles, and a client never chooses anything about its own permissions."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254, pattern=_EMAIL_PATTERN)
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=80)
    age_confirmed: StrictBool = Field(
        default=False,
        description="The person answered Yes to 'Are you 18 years of age or older?'. "
        "Required; it is never assumed.",
    )

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        return " ".join(value.split())


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    age_confirmed: StrictBool = Field(
        default=False,
        description="Older accounts that never confirmed their age send Yes here once.",
    )


class RegisterOut(BaseModel):
    user: UserOut
    verification_required: bool
    code_sent: bool
    resend_after_seconds: int
    code_ttl_minutes: int


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    code: str = Field(pattern=r"^[0-9]{6,10}$", description="The code from the email.")


class PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=254)
    code: str = Field(pattern=r"^[0-9]{6,10}$")
    new_password: str = Field(min_length=1, max_length=128)


class CodeSentOut(BaseModel):
    resend_after_seconds: int
    code_ttl_minutes: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    created_at: datetime
    email_verified: bool = False
    age_confirmed: bool = False

    @classmethod
    def of(cls, user) -> UserOut:  # type: ignore[no-untyped-def]
        out = cls.model_validate(user)
        out.email_verified = user.email_verified_at is not None
        out.age_confirmed = user.age_confirmed_at is not None
        return out


class AuthStatus(BaseModel):
    """Public information the sign-in page needs before anyone is signed in."""

    has_users: bool
    registration_open: bool
    email_verification: bool = False
    mode: Literal["local", "server", "hybrid"] = "server"
    accounts: bool = True
