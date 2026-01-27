#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Менеджер Telegram Userbot
"""

import os
import logging
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    ChannelPrivateError, 
    InviteHashExpiredError,
    UserAlreadyParticipantError,
    FloodWaitError
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat
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
    
    async def is_group_or_channel(self, client, target: str):
        """Проверка: группа/канал или личный аккаунт"""
        try:
            entity = await client.get_entity(target)
            # Проверяем тип: Channel (публичный канал/супергруппа) или Chat (обычная группа)
            if isinstance(entity, (Channel, Chat)):
                return True, entity
            else:
                # Это личный аккаунт
                return False, None
        except Exception as e:
            logger.error(f"Error checking entity {target}: {e}")
            return False, None

            async def can_send_messages(self, client, target: str):
        """Проверка: можем ли писать в чат"""
        try:
            # Форматируем таргет
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('http://t.me/'):
                target = target.replace('http://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            entity = await client.get_entity(target)
            
            from telethon.tl.types import Channel, Chat, User
            
            # Если это личка - можем писать
            if isinstance(entity, User):
                logger.info(f"✅ {target} is User - can write")
                return True
            
            # Если это обычная группа - можем писать
            if isinstance(entity, Chat):
                logger.info(f"✅ {target} is Chat - can write")
                return True
            
            # Если это канал/супергруппа
            if isinstance(entity, Channel):
                # Получаем права
                try:
                    permissions = await client.get_permissions(entity)
                    
                    # Проверяем конкретные права
                    if hasattr(permissions, 'is_banned') and permissions.is_banned:
                        logger.warning(f"❌ {target} - user is BANNED")
                        return False
                    
                    if hasattr(permissions, 'send_messages'):
                        can_send = permissions.send_messages
                        logger.info(f"{'✅' if can_send else '❌'} {target} - send_messages={can_send}")
                        return can_send
                    
                    # Если канал broadcast (только админы пишут)
                    if entity.broadcast:
                        logger.warning(f"❌ {target} - is broadcast channel (admins only)")
                        return False
                    
                    # Проверяем default_banned_rights
                    if entity.default_banned_rights:
                        can_send = not entity.default_banned_rights.send_messages
                        logger.info(f"{'✅' if can_send else '❌'} {target} - default rights: {can_send}")
                        return can_send
                    
                    # Если нет явных запретов - можем писать
                    logger.info(f"✅ {target} - no restrictions")
                    return True
                    
                except Exception as perm_err:
                    logger.error(f"⚠️ Can't check permissions for {target}: {perm_err}")
                    # Если не можем проверить - лучше попробовать отправить
                    return True
            
            # Неизвестный тип - пробуем писать
            logger.warning(f"⚠️ {target} - unknown type: {entity.__class__.__name__}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking {target}: {e}")
            # При ошибке проверки - пробуем отправить
            return True

    
    async def join_chat(self, session_id: str, phone: str, target: str):
        """Вступление в группу/канал"""
        try:
            client = self.sessions.get(session_id)
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Обработка разных форматов ссылок
            original_target = target
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('http://t.me/'):
                target = target.replace('http://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            # Проверка типа ссылки
            if '+' in target or 'joinchat/' in target:
                # Приватная ссылка-инвайт
                invite_hash = target.split('+')[-1] if '+' in target else target.split('joinchat/')[-1]
                try:
                    await client(ImportChatInviteRequest(invite_hash))
                    logger.info(f"✅ Joined via invite: {original_target}")
                    return {'success': True, 'joined': True, 'type': 'invite'}
                except UserAlreadyParticipantError:
                    logger.info(f"✅ Already member (invite): {original_target}")
                    return {'success': True, 'joined': False, 'already_member': True}
                except InviteHashExpiredError:
                    logger.error(f"❌ Invite expired: {original_target}")
                    return {'success': False, 'error': 'Invite expired', 'skippable': True}
                except FloodWaitError as e:
                    logger.error(f"❌ Flood wait {e.seconds}s: {original_target}")
                    return {'success': False, 'error': f'Flood wait {e.seconds}s', 'skippable': True}
                except Exception as e:
                    logger.error(f"❌ Error joining via invite: {e}")
                    return {'success': False, 'error': str(e), 'skippable': True}
            else:
                # Публичный канал/группа или личный аккаунт
                try:
                    # Проверяем тип
                    is_group, entity = await self.is_group_or_channel(client, target)
                    
                    if not is_group:
                        # Это личный аккаунт - пропускаем вступление
                        logger.info(f"⏭️ Skipping user account: {original_target}")
                        return {'success': True, 'joined': False, 'is_user': True}
                    
                    # Это группа/канал - проверяем участие
                    try:
                        participant = await client.get_permissions(entity)
                        if participant:
                            logger.info(f"✅ Already member: {original_target}")
                            return {'success': True, 'joined': False, 'already_member': True}
                    except:
                        pass
                    
                    # Вступаем
                    await client(JoinChannelRequest(entity))
                    logger.info(f"✅ Joined channel: {original_target}")
                    return {'success': True, 'joined': True, 'type': 'public'}
                    
                except ChannelPrivateError:
                    logger.error(f"❌ Channel is private: {original_target}")
                    return {'success': False, 'error': 'Channel is private', 'skippable': True}
                except FloodWaitError as e:
                    logger.error(f"❌ Flood wait {e.seconds}s: {original_target}")
                    return {'success': False, 'error': f'Flood wait {e.seconds}s', 'skippable': True}
                except Exception as e:
                    logger.error(f"❌ Error joining: {e}")
                    return {'success': False, 'error': str(e), 'skippable': True}
                    
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return {'success': False, 'error': str(e), 'skippable': True}
    
        async def send_message(self, session_id: str, phone: str, target: str, message: str):
        """Отправка сообщения"""
        try:
            client = self.sessions.get(session_id)
            if not client or not client.is_connected():
                connect_result = await self.connect_session(phone, session_id)
                if not connect_result['success']:
                    return {'success': False, 'error': 'Session not connected'}
                client = connect_result['client']
            
            # Форматирование таргета
            original_target = target
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('http://t.me/'):
                target = target.replace('http://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            logger.info(f"🔄 Attempting to send to: {target}")
            
            try:
                # Получаем entity
                entity = await client.get_entity(target)
                logger.info(f"✅ Entity found: {entity.__class__.__name__} - {getattr(entity, 'title', target)}")
                
                # Проверяем права ЕЩЁ РАЗ перед отправкой
                try:
                    permissions = await client.get_permissions(entity)
                    logger.info(f"📋 Permissions: send_messages={getattr(permissions, 'send_messages', 'unknown')}")
                except Exception as perm_err:
                    logger.warning(f"⚠️ Can't get permissions: {perm_err}")
                
                # Пытаемся отправить
                await client.send_message(entity, message)
                logger.info(f"✅ Message sent to {target}")
                return {'success': True}
                
            except Exception as send_err:
                error_msg = str(send_err)
                logger.error(f"❌ Send error for {target}: {error_msg}")
                
                # Детальная информация об ошибке
                if "can't write" in error_msg.lower():
                    logger.error(f"❌ WRITE FORBIDDEN in {target}")
                elif "flood" in error_msg.lower():
                    logger.error(f"❌ FLOOD WAIT in {target}")
                elif "banned" in error_msg.lower():
                    logger.error(f"❌ BANNED in {target}")
                else:
                    logger.error(f"❌ UNKNOWN ERROR in {target}: {error_msg}")
                
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
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
            
            original_target = target
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('http://t.me/'):
                target = target.replace('http://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            logger.info(f"🔄 Attempting to send photo to: {target}")
            
            try:
                entity = await client.get_entity(target)
                logger.info(f"✅ Entity found: {entity.__class__.__name__}")
                
                await client.send_file(entity, photo_path, caption=caption)
                logger.info(f"✅ Photo sent to {target}")
                return {'success': True}
                
            except Exception as send_err:
                logger.error(f"❌ Send photo error for {target}: {send_err}")
                return {'success': False, 'error': str(send_err)}
                
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
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
            
            original_target = target
            if target.startswith('https://t.me/'):
                target = target.replace('https://t.me/', '')
            if target.startswith('http://t.me/'):
                target = target.replace('http://t.me/', '')
            if target.startswith('@'):
                target = target[1:]
            
            logger.info(f"🔄 Attempting to send video to: {target}")
            
            try:
                entity = await client.get_entity(target)
                logger.info(f"✅ Entity found: {entity.__class__.__name__}")
                
                await client.send_file(entity, video_path, caption=caption)
                logger.info(f"✅ Video sent to {target}")
                return {'success': True}
                
            except Exception as send_err:
                logger.error(f"❌ Send video error for {target}: {send_err}")
                return {'success': False, 'error': str(send_err)}
                
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def disconnect_session(self, session_id: str):
        """Отключение сессии"""
        try:
            if session_id in self.sessions:
                client = self.sessions[session_id]
                await client.disconnect()
                del self.sessions[session_id]
                logger.info("✅ Session disconnected")
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