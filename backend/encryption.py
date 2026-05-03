from cryptography.fernet import Fernet
from .config import settings

# Ensure the key is valid for Fernet
_fernet = Fernet(settings.ENCRYPTION_KEY.encode())

def encrypt_string(plain_text: str) -> str:
    if not plain_text:
        return ""
    return _fernet.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text: str) -> str:
    if not encrypted_text:
        return ""
    return _fernet.decrypt(encrypted_text.encode()).decode()
