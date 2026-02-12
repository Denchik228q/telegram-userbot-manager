"""
Управление Userbot'ами (Telethon)
"""
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError,
    UserIsBlockedError,
    UserPrivacyRestrictedError
)
from config import API_ID, API_HASH, SESSIONS_DIR
import os

logger = logging.getLogger(__name__)

class UserbotManager:
    def __init__(self):
        self.clients = {}  # {account_id: TelegramClient}
        self.sessions = {}  # {account_id: session_string}
    
    async def create_client(self, phone):
        """Создать нового клиента для авторизации"""
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()
        return client
    
    async def send_code(self, client, phone):
        """Отправить код подтверждения"""
        try:
            result = await client.send_code_request(phone)
            logger.info(f"✅ Code sent to {phone}")
            return result.phone_code_hash
        except PhoneNumberInvalidError:
            logger.error(f"❌ Invalid phone number: {phone}")
            raise ValueError("Неверный формат номера телефона")
        except FloodWaitError as e:
            logger.error(f"❌ Flood wait {e.seconds} seconds")
            raise ValueError(f"Слишком много попыток. Подождите {e.seconds} секунд")
        except Exception as e:
            logger.error(f"❌ Error sending code: {e}")
            raise
    
    async def sign_in(self, client, phone, code, phone_code_hash):
        """Войти с кодом"""
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            logger.info(f"✅ Signed in: {phone}")
            return True
        except SessionPasswordNeededError:
            logger.info(f"⚠️ 2FA required for {phone}")
            return False  # Требуется 2FA
        except PhoneCodeInvalidError:
            logger.error(f"❌ Invalid code for {phone}")
            raise ValueError("Неверный код подтверждения")
        except Exception as e:
            logger.error(f"❌ Sign in error: {e}")
            raise
    
    async def sign_in_2fa(self, client, password):
        """Войти с паролем 2FA"""
        try:
            await client.sign_in(password=password)
            logger.info("✅ 2FA passed")
            return True
        except Exception as e:
            logger.error(f"❌ 2FA error: {e}")
            raise ValueError("Неверный пароль двухфакторной аутентификации")
    
    async def get_session_string(self, client):
        """Получить строку сессии"""
        return client.session.save()
    
    async def load_client(self, account_id, session_string):
        """Загрузить клиента из сессии"""
        try:
            session = StringSession(session_string)
            client = TelegramClient(session, API_ID, API_HASH)
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"❌ Session expired for account {account_id}")
                return None
            
            self.clients[account_id] = client
            self.sessions[account_id] = session_string
            
            logger.info(f"✅ Client loaded for account {account_id}")
            return client
        except Exception as e:
            logger.error(f"❌ Error loading client {account_id}: {e}")
            return None
    
    async def get_me(self, client):
        """Получить информацию о текущем пользователе"""
        try:
            me = await client.get_me()
            return {
                'id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone': me.phone
            }
        except Exception as e:
            logger.error(f"❌ Error getting user info: {e}")
            return None
    
    async def send_message(self, client, target, message, **kwargs):
        """Отправить сообщение"""
        try:
            await client.send_message(target, message, **kwargs)
            logger.info(f"✅ Message sent to {target}")
            return True, None
        except FloodWaitError as e:
            logger.warning(f"⚠️ FloodWait {e.seconds}s for {target}")
            return False, f"FloodWait: {e.seconds}s"
        except UserIsBlockedError:
            logger.warning(f"⚠️ User blocked: {target}")
            return False, "User blocked bot"
        except UserPrivacyRestrictedError:
            logger.warning(f"⚠️ Privacy restricted: {target}")
            return False, "Privacy settings"
        except Exception as e:
            logger.error(f"❌ Error sending to {target}: {e}")
            return False, str(e)
    
    async def get_client(self, account_id):
        """Получить клиента по ID аккаунта"""
        return self.clients.get(account_id)
    
    async def disconnect_client(self, account_id):
        """Отключить клиента"""
        if account_id in self.clients:
            try:
                await self.clients[account_id].disconnect()
                del self.clients[account_id]
                if account_id in self.sessions:
                    del self.sessions[account_id]
                logger.info(f"✅ Client {account_id} disconnected")
            except Exception as e:
                logger.error(f"❌ Error disconnecting client {account_id}: {e}")
    
    async def disconnect_all(self):
        """Отключить всех клиентов"""
        for account_id in list(self.clients.keys()):
            await self.disconnect_client(account_id)
        logger.info("✅ All clients disconnected")
    
    def is_client_active(self, account_id):
        """Проверить активен ли клиент"""
        return account_id in self.clients