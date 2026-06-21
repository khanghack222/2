"""
Password Service - Encrypted password storage
"""
import os
import secrets
import string
from cryptography.fernet import Fernet
from typing import List, Dict, Optional
from data.repositories import PasswordRepository


class PasswordService:
    """Manage encrypted passwords"""

    def __init__(
        self,
        password_repo: PasswordRepository,
        encryption_key: Optional[str] = None
    ):
        """
        Initialize password service

        Args:
            password_repo: Password repository
            encryption_key: Fernet key (auto-generated if not provided)
        """
        self.password_repo = password_repo

        if encryption_key:
            self.fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        else:
            # Generate new key (should be saved in production)
            self.fernet = Fernet(Fernet.generate_key())

    def generate_password(self, length: int = 16) -> str:
        """
        Generate a secure random password

        Args:
            length: Password length

        Returns:
            Generated password
        """
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def encrypt_password(self, password: str) -> bytes:
        """Encrypt a password"""
        return self.fernet.encrypt(password.encode())

    def decrypt_password(self, encrypted: bytes) -> str:
        """Decrypt a password"""
        return self.fernet.decrypt(encrypted).decode()

    async def save_password(
        self,
        user_id: int,
        label: str,
        password: str
    ) -> int:
        """
        Save an encrypted password

        Args:
            user_id: Telegram user ID
            label: Password label
            password: Plain password

        Returns:
            Password ID
        """
        encrypted = self.encrypt_password(password)
        return await self.password_repo.create(
            user_id=user_id,
            label=label,
            password=encrypted
        )

    async def get_passwords(self, user_id: int) -> List[Dict]:
        """
        Get all passwords for a user (decrypted)

        Args:
            user_id: Telegram user ID

        Returns:
            List of password dicts with decrypted passwords
        """
        passwords = await self.password_repo.get_by_user(user_id)
        result = []

        for pwd in passwords:
            try:
                decrypted = self.decrypt_password(pwd['password'])
                result.append({
                    'id': pwd['id'],
                    'label': pwd['label'],
                    'password': decrypted
                })
            except Exception:
                # Skip corrupted passwords
                continue

        return result

    async def delete_password(self, password_id: int, user_id: int) -> bool:
        """
        Delete a password

        Args:
            password_id: Password ID
            user_id: User ID for security

        Returns:
            True if deleted
        """
        return await self.password_repo.delete(password_id, user_id)
