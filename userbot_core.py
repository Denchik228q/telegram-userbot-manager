#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Userbot Manager module"""

import os
import asyncio
import logging
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)

logger = logging.getLogger(__name__)

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')


class UserbotManager:
    """Менеджер юзерботов"""
    
    def __init__(self, db):
        """Инициализация - ОБЯЗАТЕЛЬНО с параметром db"""
        self.db = db
        self.clients = {}
        self.sessions_dir = 'sessions'
        
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)
        
        logger.info("📦 UserbotManager initialized")
    
    async def create_client(self, phone: str, session_name: str):
        """Создать клиент"""
        session_path = os.path.join(self.sessions_dir, f"{session_name}.session")
        return TelegramClient(session_path, API_ID, API_HASH)
    
    async def connect_account(self, phone: str, session_name: str):
        """Начать подключение"""
        try:
            client = await self.create_client(phone, session_name)
            await client.connect()
            
            if not await client.is_user_authorized():
                result = await client.send_code_request(phone)
                return (client, result.phone_code_hash)
            else:
                return (client, None)
        except Exception as e:
            logger.error(f"Error connecting: {e}")
            return (None, f"❌ Ошибка: {str(e)}")
    
    async def verify_code(self, client, phone: str, code: str, phone_code_hash: str):
        """Проверить код"""
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            return (True, False, None)
        except SessionPasswordNeededError:
            return (False, True, None)
        except PhoneCodeInvalidError:
            return (False, False, "❌ Неверный код")
        except Exception as e:
            return (False, False, f"❌ Ошибка: {str(e)}")
    
    async def verify_password(self, client, password: str):
        """Проверить 2FA пароль"""
        try:
            await client.sign_in(password=password)
            return (True, None)
        except Exception as e:
            return (False, f"❌ Неверный пароль: {str(e)}")
    
    async def get_account_info(self, client):
        """Получить инфо об аккаунте"""
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
            logger.error(f"Error getting info: {e}")
            return None
    
    async def load_account(self, account_id: int):
        """Загрузить аккаунт из БД"""
        try:
            account = self.db.get_account(account_id)
            if not account:
                return False
            
            session_name = account['session_id']
            session_path = os.path.join(self.sessions_dir, f"{session_name}.session")
            
            if not os.path.exists(session_path):
                return False
            
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            if await client.is_user_authorized():
                self.clients[account_id] = client
                logger.info(f"✅ Account {account_id} loaded")
                return True
            return False
        except Exception as e:
            logger.error(f"Error loading account: {e}")
            return False
    
    async def send_message(self, client, target: str, message: str):
        """Отправить сообщение"""
        try:
            if target.startswith('@'):
                target = target[1:]
            await client.send_message(target, message)
            return True
        except FloodWaitError as e:
            logger.warning(f"FloodWait: {e.seconds}s")
            return False
        except Exception as e:
            logger.error(f"Error sending: {e}")
            return False
    
    async def get_client(self, account_id: int):
        """Получить клиент"""
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
            except:
                pass
    
    async def disconnect_all(self):
        """Отключить все"""
        for aid in list(self.clients.keys()):
            await self.disconnect_account(aid)