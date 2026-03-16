import asyncio
import json
import logging
import random

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

from database import Database

logger = logging.getLogger(__name__)


class MailingEngine:
    def __init__(self, db: Database):
        self.db = db

    async def start_mailing(self, mailing_id: int) -> dict:
        mailing = self.db.get_mailing(mailing_id)
        if not mailing:
            raise ValueError(f'Mailing {mailing_id} not found')

        account = self.db.get_account(mailing['account_id'])
        if not account:
            raise ValueError(f"Account {mailing['account_id']} not found")

        recipients = json.loads(mailing['recipients']) if mailing['recipients'] else []

        client = TelegramClient(
            StringSession(account['session_string']),
            account['api_id'],
            account['api_hash'],
        )

        sent = 0
        failed = 0

        await client.connect()
        self.db.update_mailing_status(mailing_id, 'running', sent, failed)

        try:
            for recipient in recipients:
                try:
                    await client.send_message(recipient, mailing['message'])
                    sent += 1
                    self.db.increment_messages_counters(mailing['user_id'], 1)
                    self.db.update_mailing_status(mailing_id, 'running', sent, failed)
                    await asyncio.sleep(random.randint(2, 5))
                except FloodWaitError as exc:
                    logger.warning('Flood wait: %s seconds', exc.seconds)
                    await asyncio.sleep(exc.seconds)
                except Exception as exc:
                    failed += 1
                    self.db.update_mailing_status(mailing_id, 'running', sent, failed)
                    logger.error('Send failed to %s: %s', recipient, exc)

            self.db.update_mailing_status(mailing_id, 'completed', sent, failed)
            return {'sent': sent, 'failed': failed}
        except Exception:
            self.db.update_mailing_status(mailing_id, 'failed', sent, failed)
            raise
        finally:
            await client.disconnect()
