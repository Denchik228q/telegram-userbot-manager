#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Userbot Manager module for Telegram Bot Manager"""

import os
import asyncio
import logging
from typing import Dict, Optional
from telethon import TelegramClient

logger = logging.getLogger(__name__)

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')


class UserbotManager:
    """Менеджер юзерботов"""
    
    def __init__(self, db):
        """Инициализация менеджера"""
        self.db = db
        self.clients = {}
        self.sessions_dir = 'sessions'
        
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)
        
        logger.info("📦 UserbotManager initialized")
    
    async def create_client(self, phone: str, session_name: str):
        """Создать клиент Telethon"""
        session_path = os.path.join(self.sessions_dir, f"{session_name}.session")
        client = TelegramClient(session_path, API_ID, API_HASH)
        return client