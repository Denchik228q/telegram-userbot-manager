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
    """Класс для управления Telegram юзерботом"""
    
    def __init__(self):
        """Инициализация менеджера"""
        self.api_id = API_ID
        self.api_hash = API_HASH
        self.sessions_dir = SESSIONS_DIR
        self.sessions = {}  # Активные сессии {session_id: client}
        
        # Создаём директорию для сессий
        os.makedirs(self.sessions_dir, exist_ok=True)
        
        logger.info("📦 UserbotManager initialized")
    
    async def send_code(self, phone: str):
        """Отправка кода подтверждения на телефон"""
        try:
            # Создаём временного клиента для отправки кода
            client = TelegramClient(
                StringSession(),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            # Отправляем код
            result = await client.send_code_request(phone)
            
            logger.info(f"✅ Code sent to {phone}")
            
            # Сохраняем клиента временно
            self.sessions[f'temp_{phone}'] = client
            
            return {
                'success': True,
                'phone_code_hash': result.phone_code_hash
            }
            
        except Exception as e:
            logger.error(f"❌ Error sending code: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def sign_in(self, phone: str, code: str, phone_code_hash: str):
        """Авторизация с кодом"""
        try:
            # Получаем временного клиента
            client = self.sessions.get(f'temp_{phone}')
            
            if not client:
                return {
                    'success': False,
                    'error': 'Session not found. Please request code again.'
                }
            
            try:
                # Пытаемся авторизоваться
                await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                
                # Получаем session string
                session_string = client.session.save()
                
                # Сохраняем сессию
                self.sessions[session_string] = client
                
                # Удаляем временную сессию
                if f'temp_{phone}' in self.sessions:
                    del self.sessions[f'temp_{phone}']
                
                logger.info(f"✅ User signed in: {phone}")
                
                return {
                    'success': True,
                    'session_id': session_string
                }
                
            except SessionPasswordNeededError:
                # Требуется 2FA
                logger.info(f"⚠️ 2FA required for {phone}")
                return {
                    'success': False,
                    'password_required': True
                }
                
            except PhoneCodeInvalidError:
                logger.error(f"❌ Invalid code for {phone}")
                return {
                    'success': False,
                    'error': 'Неверный код'
                }
                
        except Exception as e:
            logger.error(f"❌ Error signing in: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def sign_in_2fa(self, phone: str, password: str):
        """Авторизация с паролем 2FA"""
        try:
            # Получаем временного клиента
            client = self.sessions.get(f'temp_{phone}')
            
            if not client:
                return {
                    'success': False,
                    'error': 'Session not found. Please start again.'
                }
            
            # Авторизуемся с паролем
            await client.sign_in(password=password)
            
            # Получаем session string
            session_string = client.session.save()
            
            # Сохраняем сессию
            self.sessions[session_string] = client
            
            # Удаляем временную сессию
            if f'temp_{phone}' in self.sessions:
                del self.sessions[f'temp_{phone}']
            
            logger.info(f"✅ User signed in with 2FA: {phone}")
            
            return {
                'success': True,
                'session_id': session_string
            }
            
        except Exception as e:
            logger.error(f"❌ Error with 2FA: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def connect_session(self, phone: str, session_string: str):
        """Подключение существующей сессии"""
        try:
            # Проверяем есть ли уже активная сессия
            if session_string in self.sessions:
                client = self.sessions[session_string]
                if client.is_connected():
                    logger.info(f"✅ Session already connected: {phone}")
                    return {
                        'success': True,
                        'client': client
                    }
            
            # Создаём клиента из session string
            client = TelegramClient(
                StringSession(session_string),
                self.api_id,
                self.api_hash
            )
            
            await client.connect()
            
            # Проверяем авторизацию
            if not await client.is_user_authorized():
                logger.error(f"❌ Session not authorized: {phone}")
                return {
                    'success': False,
                    'error': 'Session expired or invalid'
                }
            
            # Сохраняем клиента
            self.sessions[session_string] = client
            
            logger.info(f"✅ Session connected: {phone}")
            
            return {
                'success': True,
                'client': client
            }
            
        except Exception as e:
            logger.error(f"❌ Error connecting session: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def send_message(self, session_id: str, phone: str, target: str, message: str):
        """Отправка текстового сообщения через юзербот"""
        try:
            client = self.sessions.get(session_id)
            
            if not client or not client.is_connected():
                # Переподключаем
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Убираем @ если есть, и обрабатываем ссылки
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            # Отправляем сообщение
            await client.send_message(target, message)
            
            logger.info(f"✅ Message sent to {target} from {phone}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"❌ Error sending message to {target}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_photo(self, session_id: str, phone: str, target: str, photo_path: str, caption: str = ""):
        """Отправка фото через юзербот"""
        try:
            client = self.sessions.get(session_id)
            
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Обработка адреса
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            # Отправляем фото
            await client.send_file(target, photo_path, caption=caption)
            
            logger.info(f"✅ Photo sent to {target} from {phone}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"❌ Error sending photo to {target}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def send_video(self, session_id: str, phone: str, target: str, video_path: str, caption: str = ""):
        """Отправка видео через юзербот"""
        try:
            client = self.sessions.get(session_id)
            
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Обработка адреса
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            # Отправляем видео
            await client.send_file(target, video_path, caption=caption)
            
            logger.info(f"✅ Video sent to {target} from {phone}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"❌ Error sending video to {target}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_dialogs(self, session_id: str, phone: str, limit: int = 100):
        """Получение списка диалогов пользователя"""
        try:
            client = self.sessions.get(session_id)
            
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Получаем диалоги
            dialogs = await client.get_dialogs(limit=limit)
            
            result = []
            for dialog in dialogs:
                result.append({
                    'id': dialog.id,
                    'name': dialog.name,
                    'username': getattr(dialog.entity, 'username', None),
                    'is_user': dialog.is_user,
                    'is_group': dialog.is_group,
                    'is_channel': dialog.is_channel
                })
            
            logger.info(f"✅ Got {len(result)} dialogs for {phone}")
            return {'success': True, 'dialogs': result}
            
        except Exception as e:
            logger.error(f"❌ Error getting dialogs: {e}")
            return {'success': False, 'error': str(e)}
    
    async def disconnect_session(self, session_id: str):
        """Отключение сессии"""
        try:
            if session_id in self.sessions:
                client = self.sessions[session_id]
                await client.disconnect()
                del self.sessions[session_id]
                logger.info(f"✅ Session disconnected: {session_id[:20]}...")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error disconnecting session: {e}")
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
            logger.error(f"❌ Error disconnecting all sessions: {e}")