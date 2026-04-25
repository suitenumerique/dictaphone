"""Pydantic models for authentication-related operations."""

from pydantic import BaseModel, Field


class PKCEAuthenticationRequestModel(BaseModel):
    """Model for generating PKCE authentication requests."""

    code_challenge: str = Field(min_length=43, pattern=r"^[A-Za-z0-9\-_]+$")
    code_challenge_method: str = "S256"
    state: str = Field(min_length=43, pattern=r"^[A-Za-z0-9\-_]+$")


class PKCETokenExchangeModel(BaseModel):
    """Model for exchanging PKCE tokens."""

    code: str
    code_verifier: str = Field(min_length=43, pattern=r"^[A-Za-z0-9\-_]+$")
