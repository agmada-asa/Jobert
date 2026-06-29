from cryptography.fernet import Fernet
from .config import settings

_fernet = Fernet(settings.ENCRYPTION_KEY.encode()) if settings.ENCRYPTION_KEY else None

def encrypt_string(plain_text: str) -> str:
    if not plain_text:
        return ""
    if not _fernet:
        raise RuntimeError("ENCRYPTION_KEY is required before storing integration secrets")
    return _fernet.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text: str) -> str:
    if not encrypted_text:
        return ""
    if not _fernet:
        return ""
    return _fernet.decrypt(encrypted_text.encode()).decode()
