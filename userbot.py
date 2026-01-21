import os
import logging
import asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import InputPeerUser
from config_userbot import API_ID, API_HASH, SESSIONS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserbotSession:
    """Класс для управления одной userbot сессией"""
    
    def __init__(self, user_id: int, phone: str, session_name: str = None):
        self.user_id = user_id
        self.phone = phone
        self.session_name = session_name or f"user_{user_id}"
        self.session_path = os.path.join(SESSIONS_DIR, f"{self.session_name}.session")
        
        # Создаём клиент Telethon
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
            logger.info(f"🔑 Using API_ID: {API_ID}")
            logger.info(f"📞 Phone: {self.phone}")
            
            if not self.client.is_connected():
                logger.info("📡 Connecting to Telegram...")
                await self.client.connect()
                logger.info("✅ Connected!")
            
            logger.info(f"📤 Requesting code for {self.phone}")
            result = await self.client.send_code_request(self.phone)
            
            logger.info(f"✅ Code sent!")
            logger.info(f"📋 Phone hash: {result.phone_code_hash[:15]}...")
            
            return True, result.phone_code_hash
            
        except errors.ApiIdInvalidError:
            logger.error(f"❌ API_ID invalid!")
            return False, "Неверный API_ID. Получите свои данные на my.telegram.org"
        except errors.FloodWaitError as e:
            logger.error(f"⏳ FloodWait: {e.seconds} seconds")
            return False, f"Слишком много попыток. Подождите {e.seconds//60} минут"
        except errors.PhoneNumberInvalidError:
            logger.error(f"❌ Invalid phone: {self.phone}")
            return False, "Неверный формат номера. Используйте: +79123456789"
        except errors.PhoneNumberBannedError:
            logger.error(f"❌ Phone banned: {self.phone}")
            return False, "Этот номер заблокирован в Telegram"
        except Exception as e:
            logger.error(f"❌ Error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Ошибка: {str(e)}"
    
    async def sign_in(self, code: str, phone_code_hash: str):
        """Вход с кодом"""
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=phone_code_hash)
            self.is_active = True
            logger.info(f"✅ Signed in: {self.phone}")
            return True, "Success"
        except errors.SessionPasswordNeededError:
            logger.info(f"🔐 2FA required for {self.phone}")
            return False, "Требуется пароль 2FA"
        except errors.PhoneCodeInvalidError:
            logger.error(f"❌ Invalid code")
            return False, "Неверный код"
        except errors.PhoneCodeExpiredError:
            logger.error(f"❌ Code expired")
            return False, "Код истёк. Запросите новый"
        except Exception as e:
            logger.error(f"❌ Sign in error: {e}")
            return False, str(e)
    
    async def sign_in_2fa(self, password: str):
        """Вход с паролем 2FA"""
        try:
            await self.client.sign_in(password=password)
            self.is_active = True
            logger.info(f"✅ Signed in with 2FA: {self.phone}")
            return True, "Success"
        except errors.PasswordHashInvalidError:
            logger.error(f"❌ Invalid 2FA password")
            return False, "Неверный пароль 2FA"
        except Exception as e:
            logger.error(f"❌ 2FA error: {e}")
            return False, str(e)
    
    async def send_message(self, username: str, message: str):
        """Отправка сообщения"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            
            # Убираем @ если есть
            username = username.replace('@', '')
            
            # Отправляем сообщение
            await self.client.send_message(username, message)
            self.messages_sent_today += 1
            logger.info(f"✅ Message sent to @{username}")
            return True, None
            
        except errors.FloodWaitError as e:
            logger.error(f"⏳ FloodWait: {e.seconds}s for @{username}")
            return False, f"FloodWait: {e.seconds}s"
        except errors.UserIsBlockedError:
            logger.error(f"❌ Blocked by @{username}")
            return False, "Пользователь заблокировал вас"
        except errors.UserPrivacyRestrictedError:
            logger.error(f"❌ Privacy restricted: @{username}")
            return False, "Настройки приватности пользователя"
        except errors.UsernameNotOccupiedError:
            logger.error(f"❌ User not found: @{username}")
            return False, "Пользователь не найден"
        except errors.PeerFloodError:
            logger.error(f"❌ Too many requests!")
            return False, "Слишком много запросов. Подождите"
        except Exception as e:
            logger.error(f"❌ Send error to @{username}: {e}")
            return False, str(e)
    
    async def mass_send(self, targets: list, messages: list, min_delay: int = 60, max_delay: int = 180):
        """Массовая рассылка"""
        results = {
            'sent': 0,
            'failed': 0,
            'errors': []
        }
        
        self.cancel_flag = False
        
        try:
            for target in targets:
                if self.cancel_flag:
                    logger.info("🛑 Mailing cancelled by user")
                    break
                
                # Отправляем все сообщения этому получателю
                for message in messages:
                    if self.cancel_flag:
                        break
                    
                    success, error = await self.send_message(target, message)
                    
                    if success:
                        results['sent'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].append({
                            'target': target,
                            'error': error
                        })
                        # Если FloodWait - прерываем
                        if 'FloodWait' in str(error):
                            logger.error("🛑 FloodWait detected, stopping mailing")
                            break
                    
                    # Задержка между сообщениями
                    if not self.cancel_flag:
                        import random
                        delay = random.randint(min_delay, max_delay)
                        logger.info(f"⏳ Waiting {delay}s before next message...")
                        await asyncio.sleep(delay)
                
                # Дополнительная задержка между получателями
                if not self.cancel_flag and target != targets[-1]:
                    await asyncio.sleep(10)
        
        except Exception as e:
            logger.error(f"❌ Mass send error: {e}")
            results['errors'].append({
                'target': 'general',
                'error': str(e)
            })
        
        return results
    
    def cancel_mailing(self):
        """Отменить рассылку"""
        self.cancel_flag = True
        logger.info(f"🛑 Cancel flag set for {self.session_name}")
    
    async def disconnect(self):
        """Отключение"""
        try:
            if self.client.is_connected():
                await self.client.disconnect()
            self.is_active = False
            logger.info(f"🔌 Disconnected: {self.session_name}")
        except Exception as e:
            logger.error(f"❌ Disconnect error: {e}")
    
    async def stop(self):
        """Полная остановка сессии"""
        await self.disconnect()


class UserbotManager:
    """Менеджер для управления всеми userbot сессиями"""
    
    def __init__(self):
        self.sessions = {}
        logger.info("📦 UserbotManager initialized")
    
    async def create_session(self, user_id: int, phone: str) -> UserbotSession:
        """Создать новую сессию"""
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        session = UserbotSession(user_id, phone, session_name)
        self.sessions[user_id] = session
        logger.info(f"✅ Session created for user {user_id}")
        return session
    
    def get_session(self, user_id: int) -> UserbotSession:
        """Получить сессию пользователя"""
        return self.sessions.get(user_id)
    
    def get_all_sessions(self):
        """Получить все активные сессии"""
        return list(self.sessions.values())
    
    async def remove_session(self, user_id: int):
        """Удалить сессию"""
        session = self.sessions.get(user_id)
        if session:
            await session.stop()
            del self.sessions[user_id]
            logger.info(f"🗑️ Session removed for user {user_id}")
    
    async def stop_all(self):
        """Остановить все сессии"""
        for session in list(self.sessions.values()):
            await session.stop()
        self.sessions.clear()
        logger.info("🛑 All sessions stopped")


# Глобальный менеджер сессий
manager = UserbotManager()