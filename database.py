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
                        is_active BOOLEAN DEFAULT 1,
                        is_blocked BOOLEAN DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        blocked_at TIMESTAMP,
                        blocked_by INTEGER
                    )
                ''')
                
                # Add missing columns if they don't exist (migration)
                self._migrate_users_table(cursor)
                
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
    
    def _migrate_users_table(self, cursor):
        """Migrate existing users table to add new admin columns"""
        try:
            # Check if columns exist by trying to select them
            try:
                cursor.execute("SELECT is_active FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
                logger.info("✅ Added is_active column to users table")
            
            try:
                cursor.execute("SELECT is_blocked FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
                logger.info("✅ Added is_blocked column to users table")
            
            try:
                cursor.execute("SELECT blocked_at FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN blocked_at TIMESTAMP")
                logger.info("✅ Added blocked_at column to users table")
            
            try:
                cursor.execute("SELECT blocked_by FROM users LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE users ADD COLUMN blocked_by INTEGER")
                logger.info("✅ Added blocked_by column to users table")
                
        except Exception as e:
            logger.error(f"🔥 Failed to migrate users table: {e}")
    
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
                    SELECT user_id, username, first_name, last_name, is_active, is_blocked, 
                           created_at, last_activity, blocked_at, blocked_by
                    FROM users WHERE user_id = ?
                ''', (user_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"🔥 Failed to get user info for {user_id}: {e}")
            return None

    # === ADMIN FUNCTIONS ===
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Tuple]:
        """Get all users with pagination (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, first_name, last_name, is_active, is_blocked,
                           created_at, last_activity
                    FROM users 
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                users = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(users)} users (limit: {limit}, offset: {offset})")
                return users
        except Exception as e:
            logger.error(f"🔥 Failed to get all users: {e}")
            return []
    
    def get_user_stats(self) -> dict:
        """Get user statistics (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total users
                cursor.execute('SELECT COUNT(*) FROM users')
                total_users = cursor.fetchone()[0]
                
                # Active users
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1 AND is_blocked = 0')
                active_users = cursor.fetchone()[0]
                
                # Blocked users
                cursor.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
                blocked_users = cursor.fetchone()[0]
                
                # Users with saved words
                cursor.execute('SELECT COUNT(DISTINCT user_id) FROM user_words')
                users_with_words = cursor.fetchone()[0]
                
                # Total saved words
                cursor.execute('SELECT COUNT(*) FROM user_words')
                total_words = cursor.fetchone()[0]
                
                # New users today
                cursor.execute('''
                    SELECT COUNT(*) FROM users 
                    WHERE DATE(created_at) = DATE('now')
                ''')
                new_users_today = cursor.fetchone()[0]
                
                return {
                    'total_users': total_users,
                    'active_users': active_users,
                    'blocked_users': blocked_users,
                    'users_with_words': users_with_words,
                    'total_words': total_words,
                    'new_users_today': new_users_today
                }
        except Exception as e:
            logger.error(f"🔥 Failed to get user stats: {e}")
            return {}
    
    def block_user(self, user_id: int, admin_id: int) -> bool:
        """Block a user (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET is_blocked = 1, blocked_at = CURRENT_TIMESTAMP, blocked_by = ?
                    WHERE user_id = ?
                ''', (admin_id, user_id))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"✅ User {user_id} blocked by admin {admin_id}")
                    return True
                else:
                    logger.warning(f"⚠️ User {user_id} not found for blocking")
                    return False
        except Exception as e:
            logger.error(f"🔥 Failed to block user {user_id}: {e}")
            return False
    
    def unblock_user(self, user_id: int) -> bool:
        """Unblock a user (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET is_blocked = 0, blocked_at = NULL, blocked_by = NULL
                    WHERE user_id = ?
                ''', (user_id,))
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(f"✅ User {user_id} unblocked")
                    return True
                else:
                    logger.warning(f"⚠️ User {user_id} not found for unblocking")
                    return False
        except Exception as e:
            logger.error(f"🔥 Failed to unblock user {user_id}: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user and all their data (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete user's words first
                cursor.execute('DELETE FROM user_words WHERE user_id = ?', (user_id,))
                words_deleted = cursor.rowcount
                
                # Delete user
                cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
                user_deleted = cursor.rowcount
                
                conn.commit()
                
                if user_deleted > 0:
                    logger.info(f"✅ User {user_id} deleted with {words_deleted} words")
                    return True
                else:
                    logger.warning(f"⚠️ User {user_id} not found for deletion")
                    return False
        except Exception as e:
            logger.error(f"🔥 Failed to delete user {user_id}: {e}")
            return False
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Check if a user is blocked"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else False
        except Exception as e:
            logger.error(f"🔥 Failed to check if user {user_id} is blocked: {e}")
            return False
    
    def search_users(self, query: str) -> List[Tuple]:
        """Search users by username, first_name, or user_id (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Try to search by user_id if query is numeric
                if query.isdigit():
                    cursor.execute('''
                        SELECT user_id, username, first_name, last_name, is_active, is_blocked,
                               created_at, last_activity
                        FROM users 
                        WHERE user_id = ? OR username LIKE ? OR first_name LIKE ?
                        ORDER BY created_at DESC
                    ''', (int(query), f'%{query}%', f'%{query}%'))
                else:
                    cursor.execute('''
                        SELECT user_id, username, first_name, last_name, is_active, is_blocked,
                               created_at, last_activity
                        FROM users 
                        WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
                        ORDER BY created_at DESC
                    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
                
                users = cursor.fetchall()
                logger.info(f"✅ Found {len(users)} users matching '{query}'")
                return users
        except Exception as e:
            logger.error(f"🔥 Failed to search users with query '{query}': {e}")
            return []

# Global database instance
db = DatabaseManager()
