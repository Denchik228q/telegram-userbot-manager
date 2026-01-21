import os
import logging
import asyncio
from telethon import TelegramClient, errors
from config_userbot import API_ID, API_HASH, SESSIONS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserbotSession:
    """Класс для управления userbot сессией"""
    
    def __init__(self, user_id: int, phone: str, session_name: str = None):
        self.user_id = user_id
        self.phone = phone
        self.session_name = session_name or f"user_{user_id}"
        self.session_path = os.path.join(SESSIONS_DIR, f"{self.session_name}.session")
        
        self.client = TelegramClient(
            self.session_path,
            API_ID,
            API_HASH,
            device_model="Desktop",
            system_version="Windows 10",
            app_version="4.9.0"
        )
        
        self.is_active = False
        self.messages_sent_today = 0
        self.cancel_flag = False
        
        logger.info(f"📱 Session created: {self.session_name}")
    
    async def send_code_request(self):
        """Отправка кода авторизации"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            
            result = await self.client.send_code_request(self.phone)
            logger.info(f"✅ Code sent to {self.phone}")
            return True, result.phone_code_hash
            
        except errors.FloodWaitError as e:
            logger.error(f"⏳ FloodWait: {e.seconds}s")
            return False, f"Подождите {e.seconds//60} минут"
        except errors.PhoneNumberInvalidError:
            logger.error(f"❌ Invalid phone: {self.phone}")
            return False, "Неверный формат номера"
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False, str(e)
    
    async def sign_in(self, code: str, phone_code_hash: str):
        """Вход с кодом"""
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=phone_code_hash)
            self.is_active = True
            logger.info(f"✅ Signed in: {self.phone}")
            return True, "Success"
        except errors.SessionPasswordNeededError:
            return False, "2FA"
        except errors.PhoneCodeInvalidError:
            return False, "Неверный код"
        except errors.PhoneCodeExpiredError:
            return False, "Код истёк"
        except Exception as e:
            logger.error(f"❌ Sign in error: {e}")
            return False, str(e)
    
    async def sign_in_2fa(self, password: str):
        """Вход с паролем 2FA"""
        try:
            await self.client.sign_in(password=password)
            self.is_active = True
            logger.info(f"✅ Signed in with 2FA")
            return True, "Success"
        except errors.PasswordHashInvalidError:
            return False, "Неверный пароль 2FA"
        except Exception as e:
            return False, str(e)
    
    async def send_message(self, username: str, message: str):
        """Отправка сообщения"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            
            username = username.replace('@', '')
            await self.client.send_message(username, message)
            self.messages_sent_today += 1
            logger.info(f"✅ Message sent to @{username}")
            return True, None
            
        except errors.FloodWaitError as e:
            logger.error(f"⏳ FloodWait: {e.seconds}s")
            return False, f"FloodWait: {e.seconds}s"
        except errors.UserIsBlockedError:
            return False, "Пользователь заблокировал вас"
        except errors.UserPrivacyRestrictedError:
            return False, "Настройки приватности"
        except errors.PeerFloodError:
            return False, "Слишком много запросов"
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            return False, str(e)
    
    async def mass_send(self, targets: list, messages: list, min_delay: int = 60, max_delay: int = 180):
        """Массовая рассылка"""
        results = {'sent': 0, 'failed': 0, 'errors': []}
        self.cancel_flag = False
        
        try:
            for target in targets:
                if self.cancel_flag:
                    break
                
                for message in messages:
                    if self.cancel_flag:
                        break
                    
                    success, error = await self.send_message(target, message)
                    
                    if success:
                        results['sent'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append({'target': target, 'error': error})
                        if 'FloodWait' in str(error):
                            break
                    
                    if not self.cancel_flag:
                        import random
                        delay = random.randint(min_delay, max_delay)
                        await asyncio.sleep(delay)
                
                if not self.cancel_flag and target != targets[-1]:
                    await asyncio.sleep(10)
        
        except Exception as e:
            logger.error(f"❌ Mass send error: {e}")
            results['errors'].append({'target': 'general', 'error': str(e)})
        
        return results
    
    def cancel_mailing(self):
        """Отменить рассылку"""
        self.cancel_flag = True
        logger.info(f"🛑 Cancel flag set")
    
    async def disconnect(self):
        """Отключение"""
        try:
            if self.client.is_connected():
                await self.client.disconnect()
            self.is_active = False
            logger.info(f"🔌 Disconnected")
        except Exception as e:
            logger.error(f"❌ Disconnect error: {e}")
    
    async def stop(self):
        """Остановка сессии"""
        await self.disconnect()


class UserbotManager:
    """Менеджер userbot сессий"""
    
    def __init__(self):
        self.sessions = {}
        logger.info("📦 UserbotManager initialized")
    
    async def create_session(self, user_id: int, phone: str):
        """Создать сессию"""
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        session = UserbotSession(user_id, phone, session_name)
        self.sessions[user_id] = session
        return session
    
    def get_session(self, user_id: int):
        """Получить сессию"""
        return self.sessions.get(user_id)
    
    def get_all_sessions(self):
        """Все сессии"""
        return list(self.sessions.values())
    
    async def remove_session(self, user_id: int):
        """Удалить сессию"""
        session = self.sessions.get(user_id)
        if session:
            await session.stop()
            del self.sessions[user_id]
    
    async def stop_all(self):
        """Остановить все"""
        for session in list(self.sessions.values()):
            await session.stop()
        self.sessions.clear()


manager = UserbotManager()