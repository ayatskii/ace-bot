# database.py
import sqlite3
import logging
from datetime import datetime
from typing import List, Tuple, Optional
import os

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "ace_bot.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create user_words table to store saved vocabulary
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_words (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        word TEXT NOT NULL,
                        definition TEXT,
                        translation TEXT,
                        example TEXT,
                        topic TEXT,
                        saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        UNIQUE(user_id, word)
                    )
                ''')
                
                conn.commit()
                logger.info("✅ Database initialized successfully")
                
        except Exception as e:
            logger.error(f"🔥 Failed to initialize database: {e}")
            raise
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> bool:
        """Add or update user information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO users 
                    (user_id, username, first_name, last_name, last_activity)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                logger.info(f"✅ User {user_id} added/updated in database")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to add user {user_id}: {e}")
            return False
    
    def update_user_activity(self, user_id: int):
        """Update user's last activity timestamp"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = ?
                ''', (user_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"🔥 Failed to update activity for user {user_id}: {e}")
    
    def save_word_to_user_vocabulary(self, user_id: int, word: str, definition: str = None, 
                                   translation: str = None, example: str = None, topic: str = None) -> bool:
        """Save a word to user's personal vocabulary"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_words 
                    (user_id, word, definition, translation, example, topic, saved_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, word.lower().strip(), definition, translation, example, topic))
                conn.commit()
                logger.info(f"✅ Word '{word}' saved to user {user_id}'s vocabulary")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to save word '{word}' for user {user_id}: {e}")
            return False
    
    def get_user_vocabulary(self, user_id: int, limit: int = 50) -> List[Tuple]:
        """Get user's saved vocabulary words"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT word, definition, translation, example, topic, saved_at
                    FROM user_words 
                    WHERE user_id = ? 
                    ORDER BY saved_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                words = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(words)} words for user {user_id}")
                return words
        except Exception as e:
            logger.error(f"🔥 Failed to get vocabulary for user {user_id}: {e}")
            return []
    
    def remove_word_from_user_vocabulary(self, user_id: int, word: str) -> bool:
        """Remove a word from user's vocabulary"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_words 
                    WHERE user_id = ? AND word = ?
                ''', (user_id, word.lower().strip()))
                conn.commit()
                if cursor.rowcount > 0:
                    logger.info(f"✅ Word '{word}' removed from user {user_id}'s vocabulary")
                    return True
                else:
                    logger.warning(f"⚠️ Word '{word}' not found in user {user_id}'s vocabulary")
                    return False
        except Exception as e:
            logger.error(f"🔥 Failed to remove word '{word}' for user {user_id}: {e}")
            return False
    
    def get_user_vocabulary_count(self, user_id: int) -> int:
        """Get the count of words in user's vocabulary"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM user_words WHERE user_id = ?', (user_id,))
                count = cursor.fetchone()[0]
                return count
        except Exception as e:
            logger.error(f"🔥 Failed to get vocabulary count for user {user_id}: {e}")
            return 0
    
    def word_exists_in_user_vocabulary(self, user_id: int, word: str) -> bool:
        """Check if a word already exists in user's vocabulary"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 1 FROM user_words 
                    WHERE user_id = ? AND word = ?
                ''', (user_id, word.lower().strip()))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"🔥 Failed to check word existence for user {user_id}: {e}")
            return False

    def get_user_info(self, user_id: int) -> Optional[Tuple]:
        """Get user information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, created_at, last_activity
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"🔥 Failed to get user info for {user_id}: {e}")
            return None

# Global database instance
db = DatabaseManager()
