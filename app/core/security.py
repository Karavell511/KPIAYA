import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

from jose import JWTError, jwt

from app.core.config import settings


class AuthError(Exception):
    pass


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str) -> str:
    return create_token(subject, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(subject: str) -> str:
    return create_token(subject, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise AuthError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise AuthError("Invalid token type")
    return payload


def verify_telegram_init_data(init_data: str) -> dict:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    hash_value = parsed.pop("hash", None)
    if not hash_value:
        raise AuthError("Missing hash")

    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(parsed.items(), key=lambda x: x[0])])
    secret = hmac.new(b"WebAppData", settings.telegram_webapp_secret.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calculated_hash, hash_value):
        raise AuthError("Invalid telegram initData signature")

    user_data = parsed.get("user")
    if not user_data:
        raise AuthError("Missing user payload")
    return json.loads(user_data)
