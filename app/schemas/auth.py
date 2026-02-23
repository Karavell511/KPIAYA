from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
