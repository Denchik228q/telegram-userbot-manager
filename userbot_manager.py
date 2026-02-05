#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Userbot Manager module for Telegram Bot Manager
"""

import os
import asyncio
import logging
from typing import Dict, Optional, List
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)
from telethon.tl.types import InputPeerUser, InputPeerChannel, InputPeerChat

logger = logging.getLogger(__name__)

# Конфигурация Telegram API
API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')


class UserbotManager:
    """Менеджер юзерботов"""
    
    def __init__(self, db):
        """Инициализация менеджера"""
        self.db = db
        self.clients: Dict[int, TelegramClient] = {}
        self.sessions_dir = 'sessions'
        
        # Создаём директорию для сессий
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)
        
        logger.info("📦 UserbotManager initialized")
    
    async def create_client(self, phone: str, session_name: str) -> TelegramClient:
        """Создать клиент Telethon"""
        session_path = os.path.join(self.sessions_dir, f"{session_name}.session")
        client = TelegramClient(session_path, API_ID, API_HASH)
        return client
    
    async def connect_account(self, phone: str, session_name: str) -> tuple:
        """
        Начать процесс подключения аккаунта
        Возвращает: (client, code_hash) или (None, error_message)
        """
        try:
            client = await self.create_client(phone, session_name)
            await client.connect()
            
            if not await client.is_user_authorized():
                # Отправляем код
                result = await client.send_code_request(phone)
                return (client, result.phone_code_hash)
            else:
                # Уже авторизован
                return (client, None)
                
        except PhoneNumberInvalidError:
            return (None, "❌ Неверный номер телефона")
        except FloodWaitError as e:
            return (None, f"❌ Flood Wait: подождите {e.seconds} секунд")
        except Exception as e:
            logger.error(f"Error connecting account: {e}")
            return (None, f"❌ Ошибка подключения: {str(e)}")
    
    async def verify_code(self, client: TelegramClient, phone: str, code: str, 
                          phone_code_hash: str) -> tuple:
        """
        Проверить код подтверждения
        Возвращает: (success, needs_password, error_message)
        """
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            return (True, False, None)
            
        except SessionPasswordNeededError:
            # Требуется 2FA пароль
            return (False, True, None)
            
        except PhoneCodeInvalidError:
            return (False, False, "❌ Неверный код")
            
        except Exception as e:
            logger.error(f"Error verifying code: {e}")
            return (False, False, f"❌ Ошибка: {str(e)}")
    
    async def verify_password(self, client: TelegramClient, password: str) -> tuple:
        """
        Проверить 2FA пароль
        Возвращает: (success, error_message)
        """
        try:
            await client.sign_in(password=password)
            return (True, None)
            
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return (False, f"❌ Неверный пароль или ошибка: {str(e)}")
    
    async def get_account_info(self, client: TelegramClient) -> Optional[Dict]:
        """Получить информацию об аккаунте"""
        try:
            me = await client.get_me()
            return {
                'id': me.id,
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'username': me.username or '',
                'phone': me.phone or ''
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None
    
    async def load_account(self, account_id: int) -> bool:
        """Загрузить аккаунт из БД"""
        try:
            account = self.db.get_account(account_id)
            if not account:
                return False
            
            session_name = account['session_id']
            session_path = os.path.join(self.sessions_dir, f"{session_name}.session")
            
            if not os.path.exists(session_path):
                logger.error(f"Session file not found: {session_path}")
                return False
            
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            if await client.is_user_authorized():
                self.clients[account_id] = client
                logger.info(f"✅ Account {account_id} loaded successfully")
                return True
            else:
                logger.error(f"Account {account_id} not authorized")
                return False
                
        except Exception as e:
            logger.error(f"Error loading account {account_id}: {e}")
            return False
    
    async def send_message(self, client: TelegramClient, target: str, message: str) -> bool:
        """
        Отправить сообщение
        target может быть: username, phone, или ID
        """
        try:
            # Пытаемся отправить
            if target.startswith('@'):
                target = target[1:]
            
            await client.send_message(target, message)
            return True
            
        except FloodWaitError as e:
            logger.warning(f"FloodWait: {e.seconds}s for target {target}")
            return False
            
        except Exception as e:
            logger.error(f"Error sending message to {target}: {e}")
            return False
    
    async def get_client(self, account_id: int) -> Optional[TelegramClient]:
        """Получить клиент по ID аккаунта"""
        if account_id not in self.clients:
            if not await self.load_account(account_id):
                return None
        
        return self.clients.get(account_id)
    
    async def disconnect_account(self, account_id: int):
        """Отключить аккаунт"""
        if account_id in self.clients:
            try:
                await self.clients[account_id].disconnect()
                del self.clients[account_id]
                logger.info(f"✅ Account {account_id} disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting account {account_id}: {e}")
    
    async def disconnect_all(self):
        """Отключить все аккаунты"""
        for account_id in list(self.clients.keys()):
            await self.disconnect_account(account_id)
        logger.info("✅ All accounts disconnected")
    
    def __del__(self):
        """Деструктор - отключаем все клиенты"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.disconnect_all())
            else:
                loop.run_until_complete(self.disconnect_all())
        except:
            pass