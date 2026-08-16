from cryptography.fernet import Fernet, InvalidToken
from bot.config import Config


class WebSessionManager:
    def __init__(self):
        self.cipher = Fernet(Config.ENCRYPTION_KEY.encode())

    def encrypt_credentials(self, username: str, password: str) -> tuple:
        enc_user = self.cipher.encrypt(username.encode()).decode()
        enc_pass = self.cipher.encrypt(password.encode()).decode()
        return enc_user, enc_pass

    def decrypt_credentials(self, enc_user: str, enc_pass: str) -> tuple:
        try:
            user = self.cipher.decrypt(enc_user.encode()).decode()
            pwd = self.cipher.decrypt(enc_pass.encode()).decode()
            return user, pwd
        except InvalidToken:
            # Key changed or data corrupted
            return None, None


session_manager = WebSessionManager()