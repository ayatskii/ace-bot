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
                self._migrate_speaking_simulations_table(cursor)
                
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
                
                # Create speaking simulation sessions table
                cursor.execute('''
                            CREATE TABLE IF NOT EXISTS speaking_simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id TEXT UNIQUE NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            total_score REAL,
            overall_band REAL,
            status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed', 'abandoned', 'paused')),
            time_spent_seconds INTEGER DEFAULT 0,
            complete_feedback TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
                ''')
                
                # Create individual part responses table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS speaking_part_responses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        simulation_id INTEGER NOT NULL,
                        part_number INTEGER NOT NULL CHECK (part_number IN (1, 2, 3)),
                        question_prompt TEXT NOT NULL,
                        user_transcription TEXT,
                        individual_score REAL,
                        fluency_score REAL,
                        vocabulary_score REAL,
                        grammar_score REAL,
                        pronunciation_score REAL,
                        evaluation_text TEXT,
                        recording_duration_seconds INTEGER,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (simulation_id) REFERENCES speaking_simulations (id),
                        UNIQUE(simulation_id, part_number)
                    )
                ''')
                
                # Create user speaking statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_speaking_stats (
                        user_id INTEGER PRIMARY KEY,
                        total_simulations INTEGER DEFAULT 0,
                        completed_simulations INTEGER DEFAULT 0,
                        average_overall_score REAL DEFAULT 0.0,
                        best_overall_score REAL DEFAULT 0.0,
                        total_practice_time_minutes INTEGER DEFAULT 0,
                        last_simulation_date TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions ON speaking_simulations (user_id, started_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_status ON speaking_simulations (status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_simulation_parts ON speaking_part_responses (simulation_id, part_number)')
                
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
    
    def _migrate_speaking_simulations_table(self, cursor):
        """Migrate existing speaking_simulations table to add new columns"""
        try:
            # Check if complete_feedback column exists
            try:
                cursor.execute("SELECT complete_feedback FROM speaking_simulations LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                cursor.execute("ALTER TABLE speaking_simulations ADD COLUMN complete_feedback TEXT")
                logger.info("✅ Added complete_feedback column to speaking_simulations table")
                
        except Exception as e:
            logger.error(f"🔥 Failed to migrate speaking_simulations table: {e}")
    
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
                result = cursor.fetchone()
                count = result[0] if result and result[0] is not None else 0
                return int(count)
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.warning(f"⚠️ user_words table doesn't exist yet for user {user_id}")
                return 0
            else:
                logger.error(f"🔥 Database error getting vocabulary count for user {user_id}: {e}")
                return 0
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
                result = cursor.fetchone()
                if result:
                    logger.info(f"✅ Retrieved user info for {user_id}: {len(result)} fields")
                    return result
                else:
                    logger.warning(f"⚠️ User {user_id} not found in database")
                    return None
        except Exception as e:
            logger.error(f"🔥 Failed to get user info for {user_id}: {e}")
            # Return basic info if database query fails
            return (user_id, None, None, None, 1, 0, None, None, None, None)

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

    def create_speaking_simulation(self, user_id: int) -> str:
        """Create new speaking simulation session"""
        try:
            import time
            session_id = f"sim_{user_id}_{int(time.time())}"
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO speaking_simulations (user_id, session_id, started_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, session_id))
                conn.commit()
                logger.info(f"✅ Created speaking simulation session {session_id} for user {user_id}")
                return session_id
        except Exception as e:
            logger.error(f"🔥 Failed to create speaking simulation for user {user_id}: {e}")
            return None

    def save_part_response(self, simulation_id: str, part_number: int, 
                          prompt: str, transcription: str, scores: dict, evaluation: str) -> bool:
        """Save individual part response with detailed scores"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO speaking_part_responses 
                    (simulation_id, part_number, question_prompt, user_transcription, 
                     individual_score, fluency_score, vocabulary_score, grammar_score, 
                     pronunciation_score, evaluation_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (simulation_id, part_number, prompt, transcription,
                      scores.get('overall', 0), scores.get('fluency', 0),
                      scores.get('vocabulary', 0), scores.get('grammar', 0),
                      scores.get('pronunciation', 0), evaluation))
                conn.commit()
                logger.info(f"✅ Saved part {part_number} response for simulation {simulation_id}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to save part {part_number} response: {e}")
            return False

    def complete_simulation(self, session_id: str, total_score: float, overall_band: float, 
                           complete_feedback: str = None) -> bool:
        """Mark simulation as completed with final scores and save complete feedback"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE speaking_simulations 
                    SET completed_at = CURRENT_TIMESTAMP, 
                        total_score = ?, 
                        overall_band = ?,
                        status = 'completed',
                        complete_feedback = ?
                    WHERE session_id = ?
                ''', (total_score, overall_band, complete_feedback, session_id))
                
                # Update user statistics
                cursor.execute('''
                    INSERT OR REPLACE INTO user_speaking_stats 
                    (user_id, total_simulations, completed_simulations, 
                     average_overall_score, best_overall_score, 
                     last_simulation_date, updated_at)
                    SELECT 
                        s.user_id,
                        COALESCE(stats.total_simulations, 0) + 1,
                        COALESCE(stats.completed_simulations, 0) + 1,
                        (COALESCE(stats.average_overall_score * stats.completed_simulations, 0) + ?) / 
                        (COALESCE(stats.completed_simulations, 0) + 1),
                        CASE 
                            WHEN ? > COALESCE(stats.best_overall_score, 0) THEN ?
                            ELSE COALESCE(stats.best_overall_score, 0)
                        END,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    FROM speaking_simulations s
                    LEFT JOIN user_speaking_stats stats ON s.user_id = stats.user_id
                    WHERE s.session_id = ?
                ''', (overall_band, overall_band, overall_band, session_id))
                
                conn.commit()
                logger.info(f"✅ Completed simulation {session_id} with score {overall_band}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to complete simulation {session_id}: {e}")
            return False



    def get_simulation_details(self, session_id: str) -> dict:
        """Get detailed information about a specific simulation"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Get simulation info
                cursor.execute('''
                    SELECT user_id, started_at, completed_at, total_score, overall_band, status, complete_feedback
                    FROM speaking_simulations WHERE session_id = ?
                ''', (session_id,))
                sim_data = cursor.fetchone()
                
                if not sim_data:
                    return None
                
                # Get part responses
                cursor.execute('''
                    SELECT part_number, question_prompt, user_transcription, 
                           individual_score, evaluation_text, recorded_at
                    FROM speaking_part_responses 
                    WHERE simulation_id = ? 
                    ORDER BY part_number
                ''', (session_id,))
                parts_data = cursor.fetchall()
                
                return {
                    'simulation': sim_data,
                    'parts': parts_data
                }
        except Exception as e:
            logger.error(f"🔥 Failed to get simulation details for {session_id}: {e}")
            return None



    def abandon_simulation(self, session_id: str) -> bool:
        """Mark simulation as abandoned"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE speaking_simulations 
                    SET status = 'abandoned', completed_at = CURRENT_TIMESTAMP
                    WHERE session_id = ?
                ''', (session_id,))
                conn.commit()
                logger.info(f"✅ Abandoned simulation {session_id}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to abandon simulation {session_id}: {e}")
            return False

    def get_user_speaking_stats(self, user_id: int) -> dict:
        """Get user's speaking statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT total_simulations, completed_simulations, average_overall_score,
                           best_overall_score, total_practice_time_minutes, last_simulation_date
                    FROM user_speaking_stats 
                    WHERE user_id = ?
                ''', (user_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'total_simulations': result[0],
                        'completed_simulations': result[1],
                        'average_overall_score': result[2],
                        'best_overall_score': result[3],
                        'total_practice_time_minutes': result[4],
                        'last_simulation_date': result[5]
                    }
                else:
                    return {
                        'total_simulations': 0,
                        'completed_simulations': 0,
                        'average_overall_score': 0.0,
                        'best_overall_score': 0.0,
                        'total_practice_time_minutes': 0,
                        'last_simulation_date': None
                    }
        except Exception as e:
            logger.error(f"🔥 Failed to get speaking stats for user {user_id}: {e}")
            return {
                'total_simulations': 0,
                'completed_simulations': 0,
                'average_overall_score': 0.0,
                'best_overall_score': 0.0,
                'total_practice_time_minutes': 0,
                'last_simulation_date': None
            }

# Global database instance
db = DatabaseManager()
