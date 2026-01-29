#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Scheduler module for automatic mailings
"""

import logging
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

class MailingScheduler:
    def __init__(self, db, userbot_manager, bot):
        """Инициализация планировщика"""
        self.db = db
        self.userbot_manager = userbot_manager
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        logger.info("📅 MailingScheduler initialized")
    
    def start(self):
        """Запуск планировщика"""
        try:
            self.scheduler.start()
            self.load_scheduled_mailings()
            logger.info("✅ Scheduler started")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
    
    def stop(self):
        """Остановка планировщика"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                logger.info("⏹ Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def load_scheduled_mailings(self):
        """Загрузить все активные запланированные рассылки"""
        try:
            mailings = self.db.get_active_scheduled_mailings()
            
            for mailing in mailings:
                self.add_job(mailing)
            
            logger.info(f"✅ Loaded {len(mailings)} scheduled mailings")
        except Exception as e:
            logger.error(f"Error loading scheduled mailings: {e}")
    
    def add_job(self, mailing_data: dict):
        """Добавить задачу в планировщик"""
        try:
            job_id = f"mailing_{mailing_data['id']}"
            schedule_type = mailing_data.get('schedule_type', 'once')
            schedule_time = mailing_data.get('schedule_time')
            
            # Удаляем старую задачу если есть
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
            
            if schedule_type == 'once':
                # Разовая рассылка
                run_date = datetime.fromisoformat(schedule_time)
                trigger = DateTrigger(run_date=run_date)
                
            elif schedule_type == 'daily':
                # Ежедневная рассылка
                hour, minute = schedule_time.split(':')
                trigger = CronTrigger(hour=int(hour), minute=int(minute))
                
            elif schedule_type == 'hourly':
                # Каждый час
                trigger = CronTrigger(minute=0)
                
            else:
                logger.warning(f"Unknown schedule type: {schedule_type}")
                return
            
            # Добавляем задачу
            self.scheduler.add_job(
                self.execute_mailing,
                trigger=trigger,
                id=job_id,
                args=[mailing_data],
                replace_existing=True
            )
            
            logger.info(f"✅ Job added: {job_id} ({schedule_type})")
            
        except Exception as e:
            logger.error(f"Error adding job: {e}")
    
    async def execute_mailing(self, mailing_data: dict):
        """Выполнить запланированную рассылку"""
        try:
            user_id = mailing_data['user_id']
            targets = mailing_data.get('targets', [])
            account_ids = mailing_data.get('account_ids', [])
            
            logger.info(f"🚀 Executing scheduled mailing #{mailing_data['id']}")
            
            # Получаем аккаунты
            accounts = []
            for acc_id in account_ids:
                account = self.db.get_account(acc_id)
                if account and account['is_active']:
                    accounts.append(account)
            
            if not accounts:
                logger.warning(f"No active accounts for mailing #{mailing_data['id']}")
                return
            
            # Распределяем таргеты
            targets_per_account = len(targets) // len(accounts)
            remainder = len(targets) % len(accounts)
            
            total_sent = 0
            total_errors = 0
            
            start_idx = 0
            for idx, account in enumerate(accounts):
                end_idx = start_idx + targets_per_account + (1 if idx < remainder else 0)
                account_targets = targets[start_idx:end_idx]
                start_idx = end_idx
                
                if not account_targets:
                    continue
                
                # Выполняем рассылку
                sent, errors = await self._run_account_mailing(
                    account, account_targets, mailing_data
                )
                
                total_sent += sent
                total_errors += errors
                
                await asyncio.sleep(10)
            
            # Обновляем время последнего запуска
            self.db.update_scheduled_mailing_run(mailing_data['id'])
            
            # Сохраняем в историю
            message_text = mailing_data.get('message_text') or '[Медиа]'
            self.db.add_mailing(user_id, message_text, total_sent, total_errors)
            
            # Уведомляем пользователя
            await self.bot.send_message(
                chat_id=user_id,
                text=f"✅ *Запланированная рассылка выполнена!*\n\n"
                     f"📨 Отправлено: {total_sent}\n"
                     f"❌ Ошибок: {total_errors}",
                parse_mode='Markdown'
            )
            
            logger.info(f"✅ Mailing #{mailing_data['id']} completed: {total_sent} sent, {total_errors} errors")
            
            # Если разовая рассылка - деактивируем
            if mailing_data.get('schedule_type') == 'once':
                self.db.delete_scheduled_mailing(mailing_data['id'])
                self.remove_job(mailing_data['id'])
            
        except Exception as e:
            logger.error(f"Error executing mailing: {e}")
    
    async def _run_account_mailing(self, account: dict, targets: list, mailing_data: dict):
        """Рассылка с одного аккаунта"""
        session_id = account['session_id']
        phone = account['phone_number']
        
        connect_result = await self.userbot_manager.connect_session(phone, session_id)
        if not connect_result['success']:
            return 0, len(targets)
        
        sent = 0
        errors = 0
        
        # Фаза 1: Вступление
        for target in targets:
            try:
                await self.userbot_manager.join_chat(session_id, phone, target)
                await asyncio.sleep(2)
            except:
                pass
        
        await asyncio.sleep(10)
        
        # Фаза 2: Отправка
        for target in targets:
            try:
                message_text = mailing_data.get('message_text')
                
                if message_text:
                    result = await self.userbot_manager.send_message(
                        session_id, phone, target, message_text
                    )
                    
                    if result.get('success'):
                        sent += 1
                    else:
                        errors += 1
                else:
                    errors += 1
                
                await asyncio.sleep(5)
                
            except Exception as e:
                errors += 1
                logger.error(f"Error sending to {target}: {e}")
        
        return sent, errors
    
    def remove_job(self, schedule_id: int):
        """Удалить задачу"""
        try:
            job_id = f"mailing_{schedule_id}"
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"🗑 Job {job_id} removed")
        except Exception as e:
            logger.error(f"Error removing job: {e}")