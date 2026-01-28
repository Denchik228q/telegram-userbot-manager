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
from telethon.tl.types import Channel, Chat, User
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
            if isinstance(entity, (Channel, Chat)):
                return True, entity
            else:
                return False, None
        except Exception as e:
            logger.error(f"Error checking entity {target}: {e}")
            return False, None
    
    async def send_message(self, session_id: str, phone: str, target: str, message: str):
    """Отправка сообщения"""
    try:
        logger.info(f"=" * 60)
        logger.info(f"📨 SEND_MESSAGE STARTED")
        logger.info(f"🎯 Target: {target}")
        logger.info(f"=" * 60)
        
        client = self.sessions.get(session_id)
        if not client or not client.is_connected():
            logger.warning("⚠️ Client not connected, reconnecting...")
            connect_result = await self.connect_session(phone, session_id)
            if not connect_result['success']:
                return {'success': False, 'error': 'Session not connected'}
            client = connect_result['client']
        
        # Пропускаем инвайт-ссылки
        if 't.me/+' in target or 't.me/joinchat/' in target:
            logger.warning(f"⚠️ Cannot send to invite link")
            return {'success': False, 'error': 'Cannot send to invite links'}
        
        # Очистка
        target_clean = target
        if target_clean.startswith('https://t.me/'):
            target_clean = target_clean.replace('https://t.me/', '')
        if target_clean.startswith('http://t.me/'):
            target_clean = target_clean.replace('http://t.me/', '')
        if target_clean.startswith('@'):
            target_clean = target_clean[1:]
        if '?' in target_clean:
            target_clean = target_clean.split('?')[0]
        
        logger.info(f"🔄 Cleaned target: {target_clean}")
        
        try:
            # Получаем entity
            logger.info(f"🔄 Getting entity...")
            entity = await client.get_entity(target_clean)
            logger.info(f"✅ Entity: {entity.__class__.__name__} (ID: {entity.id})")
            
            # Проверяем permissions
            try:
                logger.info(f"🔄 Checking permissions...")
                permissions = await client.get_permissions(entity)
                logger.info(f"📋 Permissions object: {permissions}")
                logger.info(f"📋 send_messages: {getattr(permissions, 'send_messages', 'N/A')}")
                logger.info(f"📋 is_banned: {getattr(permissions, 'is_banned', 'N/A')}")
                
                # Если забанены
                if hasattr(permissions, 'is_banned') and permissions.is_banned:
                    logger.error(f"❌ USER IS BANNED in this chat")
                    return {'success': False, 'error': 'User is banned'}
                
                # Если нет прав
                if hasattr(permissions, 'send_messages') and not permissions.send_messages:
                    logger.error(f"❌ NO PERMISSION to send messages")
                    return {'success': False, 'error': 'No permission to send messages'}
                
            except Exception as perm_err:
                logger.warning(f"⚠️ Could not check permissions: {perm_err}")
            
            # Отправляем сообщение
            logger.info(f"🔄 Sending message...")
            await client.send_message(entity, message)
            logger.info(f"✅ MESSAGE SENT successfully")
            return {'success': True}
            
        except Exception as send_err:
            error_msg = str(send_err)
            logger.error(f"❌ SEND ERROR: {type(send_err).__name__}: {error_msg}")
            
            if "can't write" in error_msg.lower():
                logger.error(f"❌ REASON: Write forbidden")
            elif "flood" in error_msg.lower():
                logger.error(f"❌ REASON: Flood wait")
            elif "banned" in error_msg.lower():
                logger.error(f"❌ REASON: User banned")
            
            return {'success': False, 'error': error_msg}
            
    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}
    
    finally:
        logger.info(f"=" * 60)
        logger.info(f"🏁 SEND_MESSAGE FINISHED")
        logger.info(f"=" * 60)
    
    async def join_chat(self, session_id: str, phone: str, target: str):
    """Вступление в группу/канал"""
    try:
        logger.info(f"=" * 60)
        logger.info(f"🔄 JOIN_CHAT STARTED")
        logger.info(f"📱 Phone: {phone}")
        logger.info(f"🎯 Target: {target}")
        logger.info(f"=" * 60)
        
        # Получаем клиент
        client = self.sessions.get(session_id)
        if not client or not client.is_connected():
            logger.warning("⚠️ Client not connected, reconnecting...")
            connect_result = await self.connect_session(phone, session_id)
            if not connect_result['success']:
                logger.error("❌ Failed to connect session")
                return {'success': False, 'error': 'Session not connected'}
            client = connect_result['client']
            logger.info("✅ Client reconnected")
        
        original_target = target
        
        # Проверка на приватную ссылку
        is_invite_link = False
        invite_hash = None
        
        if 't.me/+' in target or 't.me/joinchat/' in target:
            is_invite_link = True
            if 't.me/+' in target:
                invite_hash = target.split('t.me/+')[1].split('?')[0].split('/')[0]
            elif 't.me/joinchat/' in target:
                invite_hash = target.split('t.me/joinchat/')[1].split('?')[0].split('/')[0]
            logger.info(f"🔗 INVITE LINK detected: {invite_hash}")
        
        # Вступление через инвайт-ссылку
        if is_invite_link and invite_hash:
            try:
                logger.info(f"🔄 Attempting ImportChatInviteRequest({invite_hash})")
                result = await client(ImportChatInviteRequest(invite_hash))
                logger.info(f"✅ ImportChatInviteRequest SUCCESS: {result}")
                logger.info(f"✅ JOINED via invite: {original_target}")
                return {'success': True, 'joined': True, 'type': 'invite'}
                
            except UserAlreadyParticipantError as e:
                logger.info(f"✅ Already member (invite): {original_target}")
                return {'success': True, 'joined': False, 'already_member': True}
                
            except InviteHashExpiredError as e:
                logger.error(f"❌ Invite expired: {e}")
                return {'success': False, 'error': 'Invite expired', 'skippable': True}
                
            except FloodWaitError as e:
                logger.error(f"❌ Flood wait {e.seconds}s: {e}")
                return {'success': False, 'error': f'Flood wait {e.seconds}s', 'skippable': True}
                
            except Exception as e:
                logger.error(f"❌ ImportChatInviteRequest ERROR: {type(e).__name__}: {e}")
                return {'success': False, 'error': str(e), 'skippable': True}
        
        # Вступление через публичную ссылку/username
        else:
            # Очистка таргета
            target_clean = target
            if target_clean.startswith('https://t.me/'):
                target_clean = target_clean.replace('https://t.me/', '')
            if target_clean.startswith('http://t.me/'):
                target_clean = target_clean.replace('http://t.me/', '')
            if target_clean.startswith('@'):
                target_clean = target_clean[1:]
            if '?' in target_clean:
                target_clean = target_clean.split('?')[0]
            
            logger.info(f"🔄 PUBLIC LINK/USERNAME: {target_clean}")
            
            try:
                # Получаем entity
                logger.info(f"🔄 Attempting client.get_entity({target_clean})")
                entity = await client.get_entity(target_clean)
                logger.info(f"✅ Entity found: {entity.__class__.__name__}")
                logger.info(f"📋 Entity ID: {entity.id}")
                logger.info(f"📋 Entity title: {getattr(entity, 'title', 'N/A')}")
                
                # Проверяем тип
                if isinstance(entity, User):
                    logger.info(f"👤 ENTITY IS USER - skipping join")
                    return {'success': True, 'joined': False, 'is_user': True}
                
                # Проверяем участие
                logger.info(f"🔄 Checking if already member...")
                try:
                    permissions = await client.get_permissions(entity)
                    logger.info(f"📋 Permissions retrieved: {permissions}")
                    
                    if permissions and hasattr(permissions, 'is_admin'):
                        logger.info(f"✅ Already member (has permissions)")
                        return {'success': True, 'joined': False, 'already_member': True}
                except Exception as perm_err:
                    logger.warning(f"⚠️ Could not check permissions: {perm_err}")
                
                # Пытаемся вступить
                logger.info(f"🔄 Attempting JoinChannelRequest")
                await client(JoinChannelRequest(entity))
                logger.info(f"✅ JoinChannelRequest SUCCESS")
                
                # Проверяем что вступили
                await asyncio.sleep(1)
                try:
                    permissions_after = await client.get_permissions(entity)
                    logger.info(f"✅ Permissions after join: {permissions_after}")
                except:
                    pass
                
                logger.info(f"✅ JOINED channel: {original_target}")
                return {'success': True, 'joined': True, 'type': 'public'}
                
            except UserAlreadyParticipantError as e:
                logger.info(f"✅ UserAlreadyParticipantError - already member")
                return {'success': True, 'joined': False, 'already_member': True}
                
            except ChannelPrivateError as e:
                logger.error(f"❌ ChannelPrivateError: {e}")
                return {'success': False, 'error': 'Channel is private', 'skippable': True}
                
            except FloodWaitError as e:
                logger.error(f"❌ FloodWaitError: {e.seconds}s")
                return {'success': False, 'error': f'Flood wait {e.seconds}s', 'skippable': True}
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ ERROR: {type(e).__name__}: {error_msg}")
                
                if 'username' in error_msg.lower() and 'unacceptable' in error_msg.lower():
                    logger.error(f"⚠️ Invalid username format")
                    return {'success': False, 'error': 'Invalid link format', 'skippable': True}
                
                return {'success': False, 'error': error_msg, 'skippable': True}
                
    except Exception as e:
        logger.error(f"❌ FATAL ERROR in join_chat: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e), 'skippable': True}
    
    finally:
        logger.info(f"=" * 60)
        logger.info(f"🏁 JOIN_CHAT FINISHED")
        logger.info(f"=" * 60)
    
    async def send_message(self, session_id: str, phone: str, target: str, message: str):
    """Отправка сообщения"""
    try:
        logger.info(f"=" * 60)
        logger.info(f"📨 SEND_MESSAGE STARTED")
        logger.info(f"🎯 Target: {target}")
        logger.info(f"=" * 60)
        
        client = self.sessions.get(session_id)
        if not client or not client.is_connected():
            logger.warning("⚠️ Client not connected, reconnecting...")
            connect_result = await self.connect_session(phone, session_id)
            if not connect_result['success']:
                return {'success': False, 'error': 'Session not connected'}
            client = connect_result['client']
        
        # Пропускаем инвайт-ссылки
        if 't.me/+' in target or 't.me/joinchat/' in target:
            logger.warning(f"⚠️ Cannot send to invite link")
            return {'success': False, 'error': 'Cannot send to invite links'}
        
        # Очистка
        target_clean = target
        if target_clean.startswith('https://t.me/'):
            target_clean = target_clean.replace('https://t.me/', '')
        if target_clean.startswith('http://t.me/'):
            target_clean = target_clean.replace('http://t.me/', '')
        if target_clean.startswith('@'):
            target_clean = target_clean[1:]
        if '?' in target_clean:
            target_clean = target_clean.split('?')[0]
        
        logger.info(f"🔄 Cleaned target: {target_clean}")
        
        try:
            # Получаем entity
            logger.info(f"🔄 Getting entity...")
            entity = await client.get_entity(target_clean)
            logger.info(f"✅ Entity: {entity.__class__.__name__} (ID: {entity.id})")
            
            # Проверяем permissions
            try:
                logger.info(f"🔄 Checking permissions...")
                permissions = await client.get_permissions(entity)
                logger.info(f"📋 Permissions object: {permissions}")
                logger.info(f"📋 send_messages: {getattr(permissions, 'send_messages', 'N/A')}")
                logger.info(f"📋 is_banned: {getattr(permissions, 'is_banned', 'N/A')}")
                
                # Если забанены
                if hasattr(permissions, 'is_banned') and permissions.is_banned:
                    logger.error(f"❌ USER IS BANNED in this chat")
                    return {'success': False, 'error': 'User is banned'}
                
                # Если нет прав
                if hasattr(permissions, 'send_messages') and not permissions.send_messages:
                    logger.error(f"❌ NO PERMISSION to send messages")
                    return {'success': False, 'error': 'No permission to send messages'}
                
            except Exception as perm_err:
                logger.warning(f"⚠️ Could not check permissions: {perm_err}")
            
            # Отправляем сообщение
            logger.info(f"🔄 Sending message...")
            await client.send_message(entity, message)
            logger.info(f"✅ MESSAGE SENT successfully")
            return {'success': True}
            
        except Exception as send_err:
            error_msg = str(send_err)
            logger.error(f"❌ SEND ERROR: {type(send_err).__name__}: {error_msg}")
            
            if "can't write" in error_msg.lower():
                logger.error(f"❌ REASON: Write forbidden")
            elif "flood" in error_msg.lower():
                logger.error(f"❌ REASON: Flood wait")
            elif "banned" in error_msg.lower():
                logger.error(f"❌ REASON: User banned")
            
            return {'success': False, 'error': error_msg}
            
    except Exception as e:
        logger.error(f"❌ FATAL ERROR: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}
    
    finally:
        logger.info(f"=" * 60)
        logger.info(f"🏁 SEND_MESSAGE FINISHED")
        logger.info(f"=" * 60)
    
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