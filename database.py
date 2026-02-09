#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='bot_data.db'):
        try:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self._create_tables()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")
            raise
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                subscription_plan TEXT DEFAULT 'trial',
                subscription_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                phone TEXT NOT NULL,
                account_name TEXT,
                session_string TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mailings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_ids TEXT,
                target_list TEXT,
                message TEXT,
                status TEXT DEFAULT 'pending',
                sent_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
        logger.info("✅ Database tables created/updated")
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM users WHERE user_id = ?", (user_id,))
            exists = cursor.fetchone()
            
            if exists:
                cursor.execute("""
                    UPDATE users 
                    SET username = ?, first_name = ?, last_name = ?, last_active = ?
                    WHERE user_id = ?
                """, (username, first_name, last_name, datetime.now(), user_id))
            else:
                cursor.execute("""
                    INSERT INTO users (user_id, username, first_name, last_name, subscription_plan, subscription_end)
                    VALUES (?, ?, ?, ?, 'trial', datetime('now', '+7 days'))
                """, (user_id, username, first_name, last_name))
            
            self.conn.commit()
            logger.info(f"✅ User {user_id} added/updated")
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            self.conn.rollback()
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def add_log(self, user_id: int, action: str, details: str = None):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO logs (user_id, action, details, timestamp)
                VALUES (?, ?, ?, ?)
            """, (user_id, action, details, datetime.now()))
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error adding log: {e}")
    
    def get_user_accounts(self, user_id: int) -> List[Dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM accounts WHERE user_id = ? AND is_active = 1", (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
    
    def get_user_mailings(self, user_id: int, limit: int = 10) -> List[Dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM mailings 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting mailings: {e}")
            return []
    
    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("✅ Database closed")