#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Менеджер Telegram Userbot
"""

import os
import logging
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.sessions import StringSession
from config_userbot import API_ID, API_HASH, SESSIONS_DIR

logger = logging.getLogger(__name__)


class UserbotManager:
    """Класс для управления юзерботом"""
    
    def __init__(self):
        """Инициализация"""
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.sessions_dir = SESSIONS_DIR
        self.sessions = {}
        os.makedirs(self.sessions_dir, exist_ok=True)
        logger.info("📦 UserbotManager initialized")
    
    async def send_code(self, phone: str):
        """Отправка кода"""
        try:
            client = TelegramClient(StringSession(), self.api_id, self.api_hash)
            await client.connect()
            result = await client.send_code_request(phone)
            self.sessions[f'temp_{phone}'] = client
            logger.info(f"✅ Code sent to {phone}")
            return {'success': True, 'phone_code_hash': result.phone_code_hash}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def sign_in(self, phone: str, code: str, phone_code_hash: str):
        """Авторизация"""
        try:
            client = self.sessions.get(f'temp_{phone}')
            if not client:
                return {'success': False, 'error': 'Session not found'}
            
            try:
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                session_string = client.session.save()
                self.sessions[session_string] = client
                if f'temp_{phone}' in self.sessions:
                    del self.sessions[f'temp_{phone}']
                logger.info(f"✅ Signed in: {phone}")
                return {'success': True, 'session_id': session_string}
            except SessionPasswordNeededError:
                return {'success': False, 'password_required': True}
            except PhoneCodeInvalidError:
                return {'success': False, 'error': 'Неверный код'}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def sign_in_2fa(self, phone: str, password: str):
        """Авторизация с 2FA"""
        try:
            client = self.sessions.get(f'temp_{phone}')
            if not client:
                return {'success': False, 'error': 'Session not found'}
            
            await client.sign_in(password=password)
            session_string = client.session.save()
            self.sessions[session_string] = client
            if f'temp_{phone}' in self.sessions:
                del self.sessions[f'temp_{phone}']
            logger.info(f"✅ Signed in with 2FA: {phone}")
            return {'success': True, 'session_id': session_string}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def connect_session(self, phone: str, session_string: str):
        """Подключение сессии"""
        try:
            if session_string in self.sessions:
                client = self.sessions[session_string]
                if client.is_connected():
                    return {'success': True, 'client': client}
            
            client = TelegramClient(StringSession(session_string), self.api_id, self.api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                return {'success': False, 'error': 'Session expired'}
            
            self.sessions[session_string] = client
            logger.info(f"✅ Session connected: {phone}")
            return {'success': True, 'client': client}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
                        return {'success': False, 'error': str(e)}
    
    async def send_message(self, session_id: str, phone: str, target: str, message: str):
        """Отправка сообщения"""
        try:
            client = self.sessions.get(session_id)
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            await client.send_message(target, message)
            logger.info(f"✅ Message sent to {target}")
            return {'success': True}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_photo(self, session_id: str, phone: str, target: str, photo_path: str, caption: str = ""):
        """Отправка фото"""
        try:
            client = self.sessions.get(session_id)
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            await client.send_file(target, photo_path, caption=caption)
            logger.info(f"✅ Photo sent to {target}")
            return {'success': True}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_video(self, session_id: str, phone: str, target: str, video_path: str, caption: str = ""):
        """Отправка видео"""
        try:
            client = self.sessions.get(session_id)
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            await client.send_file(target, video_path, caption=caption)
            logger.info(f"✅ Video sent to {target}")
            return {'success': True}
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def disconnect_session(self, session_id: str):
        """Отключение сессии"""
        try:
            if session_id in self.sessions:
                client = self.sessions[session_id]
                await client.disconnect()
                del self.sessions[session_id]
                logger.info(f"✅ Session disconnected")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    async def disconnect_all(self):
        """Отключение всех сессий"""
        try:
            for session_id, client in list(self.sessions.items()):
                try:
                    await client.disconnect()
                except:
                    pass
            self.sessions.clear()
            logger.info("✅ All sessions disconnected")
        except Exception as e:
            logger.error(f"❌ Error: {e}")