
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.config import settings
security = HTTPBasic()
def verify_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    is_correct_username = secrets.compare_digest(
        credentials.username, settings.BASIC_AUTH_USERNAME
    )
    is_correct_password = secrets.compare_digest(
        credentials.password, settings.BASIC_AUTH_PASSWORD
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username