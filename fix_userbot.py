content = '''from telethon import TelegramClient, events, errors
from telethon.tl.types import InputPeerUser, InputPeerChat, InputPeerChannel
import asyncio
import logging
from datetime import datetime, timedelta
import random
import os
from config_userbot import *
from database import Database

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)
logger.info(f"📁 Sessions directory: {SESSIONS_DIR}")


class UserbotSession:
    """Класс для управления сессией userbot"""
    
    def __init__(self, user_id, phone, session_name):
        self.user_id = user_id
        self.phone = phone
        self.session_name = os.path.join(SESSIONS_DIR, session_name)
        self.client = None
        self.is_active = False
        self.messages_sent_today = 0
        self.last_reset = datetime.now()
        logger.info(f"📝 Session: {self.session_name}.session")
    
    async def send_code_request(self):
        """Запрос кода авторизации"""
        try:
            logger.info(f"🔍 Code request for {self.phone}")
            if self.client is None:
                self.client = TelegramClient(
                    self.session_name,
                    API_ID,
                    API_HASH,
                    flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD
                )
            if not self.client.is_connected():
                await self.client.connect()
            result = await self.client.send_code_request(self.phone)
            logger.info(f"✅ Code sent to {self.phone}")
            return True, result.phone_code_hash
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False, str(e)
    
    async def sign_in(self, code, phone_code_hash):
        """Вход по коду"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.sign_in(self.phone, code, phone_code_hash=phone_code_hash)
            self.is_active = True
            logger.info(f"✅ Signed in: {self.phone}")
            return True, "✅ Авторизация успешна!"
        except errors.SessionPasswordNeededError:
            return False, "Требуется 2FA пароль"
        except Exception as e:
            logger.error(f"❌ Sign in error: {e}")
            return False, str(e)
    
    async def sign_in_2fa(self, password):
        """Вход с 2FA"""
        try:
            if not self.client.is_connected():
                await self.client.connect()
            await self.client.sign_in(password=password)
            self.is_active = True
            logger.info(f"✅ 2FA signed in: {self.phone}")
            return True, "✅ Авторизация успешна!"
        except Exception as e:
            logger.error(f"❌ 2FA error: {e}")
            return False, str(e)
    
    async def start(self):
        """Запуск клиента"""
        try:
            if self.client is None:
                self.client = TelegramClient(
                    self.session_name,
                    API_ID,
                    API_HASH,
                    flood_sleep_threshold=FLOOD_SLEEP_THRESHOLD
                )
            if not self.client.is_connected():
                await self.client.connect()
            if not await self.client.is_user_authorized():
                return False
            self.is_active = True
            me = await self.client.get_me()
            logger.info(f"✅ Started: {self.phone} (@{me.username or 'N/A'})")
            return True
        except Exception as e:
            logger.error(f"❌ Start error: {e}")
            return False
    
    def reset_daily_counter(self):
        now = datetime.now()
        if (now - self.last_reset).days >= 1:
            self.messages_sent_today = 0
            self.last_reset = now
    
    async def send_message(self, target, message):
        try:
            self.reset_daily_counter()
            if self.messages_sent_today >= DAILY_MESSAGE_LIMIT:
                return False, "Превышен лимит"
            target = str(target).strip()
            message = str(message)
            if target.startswith('@'):
                entity = target
            elif target.isdigit():
                entity = int(target)
            else:
                entity = target
            await self.client.send_message(entity, message)
            self.messages_sent_today += 1
            return True, None
        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            return False, str(e)
    
    async def mass_send(self, targets, messages, delay_min=30, delay_max=120):
        if isinstance(messages, str):
            messages = [messages]
        if not isinstance(messages, list):
            messages = [str(messages)]
        results = {'sent': 0, 'failed': 0, 'errors': []}
        for idx, target in enumerate(targets, 1):
            try:
                target = str(target).strip()
                self.reset_daily_counter()
                if self.messages_sent_today >= DAILY_MESSAGE_LIMIT:
                    results['errors'].append({'target': target, 'error': 'Лимит'})
                    break
                target_success = True
                target_error = None
                for msg_idx, message in enumerate(messages, 1):
                    message = str(message)
                    success, error = await self.send_message(target, message)
                    if not success:
                        target_success = False
                        target_error = error
                        break
                    if msg_idx < len(messages):
                        await asyncio.sleep(random.randint(3, 7))
                if target_success:
                    results['sent'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({'target': target, 'error': target_error})
                if idx < len(targets):
                    delay = random.randint(delay_min, delay_max)
                    await asyncio.sleep(delay)
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({'target': target, 'error': str(e)})
        return results
    
    async def stop(self):
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            self.is_active = False


class UserbotManager:
    def __init__(self):
        self.sessions = {}
        logger.info("👤 Manager initialized")
    
    async def create_session(self, user_id, phone):
        session_name = f"user_{user_id}_{phone.replace('+', '')}"
        session = UserbotSession(user_id, phone, session_name)
        self.sessions[user_id] = session
        return session
    
    def get_session(self, user_id):
        return self.sessions.get(user_id)
    
    async def remove_session(self, user_id):
        session = self.sessions.get(user_id)
        if session:
            await session.stop()
            del self.sessions[user_id]
    
    async def stop_all(self):
        for session in list(self.sessions.values()):
            await session.stop()
        self.sessions.clear()


manager = UserbotManager()


if __name__ == "__main__":
    print("⚠️  Запустите: python manager_bot.py")
'''

with open('userbot.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Файл userbot.py создан!")