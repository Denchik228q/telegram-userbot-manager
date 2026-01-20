import asyncio
import logging
import os
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, errors
from telethon.tl.functions.messages import SendMessageRequest
from config_userbot import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), 'sessions')
os.makedirs(SESSIONS_DIR, exist_ok=True)
logger.info(f"📁 Sessions directory: {SESSIONS_DIR}")


class UserbotSession:
    def __init__(self, user_id, phone, session_name):
        self.user_id = user_id
        self.phone = phone
        self.session_path = os.path.join(SESSIONS_DIR, f"{session_name}.session")
        self.client = TelegramClient(
            self.session_path,
            API_ID,
            API_HASH,
            flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD
        )
        self.is_active = False
        self.messages_sent_today = 0
        self.last_reset = datetime.now()
        self._cancelled = False
        logger.info(f"📱 Session created for {phone}")
    
    def reset_daily_counter(self):
        """Сброс счетчика сообщений в начале нового дня"""
        now = datetime.now()
        if now.date() > self.last_reset.date():
            self.messages_sent_today = 0
            self.last_reset = now
            logger.info(f"🔄 Counter reset for {self.phone}")
    
    def cancel_mailing(self):
        """Отменить рассылку"""
        self._cancelled = True
        logger.info(f"🛑 Mailing cancelled for {self.phone}")
    
    async def send_code_request(self):
        """Отправка кода авторизации"""
        try:
            await self.client.connect()
            result = await self.client.send_code_request(self.phone)
            logger.info(f"✅ Code sent to {self.phone}")
            return True, result.phone_code_hash
        except Exception as e:
            logger.error(f"❌ Send code error: {e}")
            return False, str(e)
    
    async def sign_in(self, code, phone_hash):
        """Вход с кодом"""
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=phone_hash)
            self.is_active = True
            logger.info(f"✅ Signed in: {self.phone}")
            return True, "Success"
        except errors.SessionPasswordNeededError:
            logger.info(f"🔐 2FA required for {self.phone}")
            return False, "Требуется 2FA пароль"
        except Exception as e:
            logger.error(f"❌ Sign in error: {e}")
            return False, str(e)
    
    async def sign_in_2fa(self, password):
        """Вход с 2FA паролем"""
        try:
            await self.client.sign_in(password=password)
            self.is_active = True
            logger.info(f"✅ 2FA signed in: {self.phone}")
            return True, "Success"
        except Exception as e:
            logger.error(f"❌ 2FA error: {e}")
            return False, str(e)
    
    async def send_message(self, target, message):
        """Отправка одного сообщения"""
        try:
            self.reset_daily_counter()
            
            if self.messages_sent_today >= DAILY_MESSAGE_LIMIT:
                return False, "Достигнут дневной лимит"
            
            await self.client.send_message(target, message)
            self.messages_sent_today += 1
            
            logger.info(f"📤 Message sent to {target} ({self.messages_sent_today}/{DAILY_MESSAGE_LIMIT})")
            return True, "Sent"
            
        except errors.FloodWaitError as e:
            wait_seconds = e.seconds
            logger.warning(f"⏳ FloodWait {wait_seconds}s for {target}")
            return False, f"FloodWait {wait_seconds}s"
        except Exception as e:
            logger.error(f"❌ Send error to {target}: {e}")
            return False, str(e)
    
    async def mass_send(self, targets, messages, min_delay, max_delay):
        """Массовая рассылка с задержками"""
        results = {
            'sent': 0,
            'failed': 0,
            'errors': []
        }
        
        self._cancelled = False
        
        for target in targets:
            if self._cancelled:
                logger.info(f"🛑 Mailing cancelled by user")
                break
            
            for message in messages:
                if self._cancelled:
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
                    
                    if 'FloodWait' in error:
                        wait_time = int(error.split()[1].replace('s', ''))
                        logger.warning(f"⏳ Waiting {wait_time}s due to FloodWait")
                        await asyncio.sleep(wait_time)
                
                delay = random.randint(min_delay, max_delay)
                logger.info(f"⏱️ Waiting {delay}s before next message")
                await asyncio.sleep(delay)
        
        logger.info(f"✅ Mailing complete: {results['sent']} sent, {results['failed']} failed")
        return results
    
    async def stop(self):
        """Остановка сессии"""
        try:
            if self.client.is_connected():
                await self.client.disconnect()
            self.is_active = False
            logger.info(f"🛑 Session stopped: {self.phone}")
        except Exception as e:
            logger.error(f"❌ Stop error: {e}")


class UserbotManager:
    def __init__(self):
        self.sessions = {}
        logger.info("👤 Manager initialized")
    
    async def create_session(self, user_id, phone):
        """Создание новой сессии"""
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        session = UserbotSession(user_id, phone, session_name)
        self.sessions[user_id] = session
        return session
    
    def get_session(self, user_id):
        """Получить сессию пользователя"""
        return self.sessions.get(user_id)
    
    def get_all_sessions(self):
        """Получить все активные сессии"""
        return list(self.sessions.values())
    
    async def remove_session(self, user_id):
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


manager = UserbotManager()