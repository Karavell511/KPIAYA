from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
