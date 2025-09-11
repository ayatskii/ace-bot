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
                self._migrate_writing_evaluations_table(cursor)
                self._migrate_speaking_question_history(cursor)
                
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
                
                # Create writing evaluations table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS writing_evaluations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        task_description TEXT NOT NULL,
                        essay_text TEXT NOT NULL,
                        overall_score REAL NOT NULL,
                        task_response_score REAL,
                        coherence_cohesion_score REAL,
                        lexical_resource_score REAL,
                        grammatical_range_score REAL,
                        evaluation_feedback TEXT NOT NULL,
                        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create user writing statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_writing_stats (
                        user_id INTEGER PRIMARY KEY,
                        total_evaluations INTEGER DEFAULT 0,
                        average_overall_score REAL DEFAULT 0.0,
                        best_overall_score REAL DEFAULT 0.0,
                        average_task_response_score REAL DEFAULT 0.0,
                        average_coherence_cohesion_score REAL DEFAULT 0.0,
                        average_lexical_resource_score REAL DEFAULT 0.0,
                        average_grammatical_range_score REAL DEFAULT 0.0,
                        last_evaluation_date TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create group chats table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_chats (
                        group_id INTEGER PRIMARY KEY,
                        group_title TEXT,
                        group_type TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create group sent words table (for uniqueness tracking)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_sent_words (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER NOT NULL,
                        word TEXT NOT NULL,
                        definition TEXT,
                        translation TEXT,
                        example TEXT,
                        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        sent_by_user_id INTEGER,
                        FOREIGN KEY (group_id) REFERENCES group_chats (group_id),
                        UNIQUE(group_id, word)
                    )
                ''')
                
                # Create group settings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_settings (
                        group_id INTEGER PRIMARY KEY,
                        auto_send_enabled BOOLEAN DEFAULT 0,
                        send_interval_hours INTEGER DEFAULT 24,
                        word_difficulty TEXT DEFAULT 'IELTS Band 7-9 (C1/C2)',
                        last_auto_send TIMESTAMP,
                        FOREIGN KEY (group_id) REFERENCES group_chats (group_id)
                    )
                ''')
                
                # === FLASHCARD SYSTEM TABLES ===
                
                # Create flashcard decks table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS flashcard_decks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        creator_user_id INTEGER NOT NULL,
                        is_public BOOLEAN DEFAULT 0,
                        is_shared BOOLEAN DEFAULT 0,
                        category TEXT DEFAULT 'General',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        card_count INTEGER DEFAULT 0,
                        FOREIGN KEY (creator_user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create flashcards table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS flashcards (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        deck_id INTEGER NOT NULL,
                        front_text TEXT NOT NULL,
                        back_text TEXT NOT NULL,
                        front_image_url TEXT,
                        back_image_url TEXT,
                        front_audio_url TEXT,
                        back_audio_url TEXT,
                        tags TEXT,
                        difficulty INTEGER DEFAULT 1 CHECK (difficulty IN (1, 2, 3, 4, 5)),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id) ON DELETE CASCADE
                    )
                ''')
                
                # Create user progress table (Spaced Repetition SM-2)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_card_progress (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        card_id INTEGER NOT NULL,
                        ease_factor REAL DEFAULT 2.5,
                        interval_days INTEGER DEFAULT 1,
                        due_date DATE NOT NULL,
                        review_count INTEGER DEFAULT 0,
                        streak_count INTEGER DEFAULT 0,
                        last_reviewed TIMESTAMP,
                        last_rating INTEGER,
                        total_time_spent INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (card_id) REFERENCES flashcards (id) ON DELETE CASCADE,
                        UNIQUE(user_id, card_id)
                    )
                ''')
                
                # Create study sessions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        deck_id INTEGER,
                        session_type TEXT DEFAULT 'review' CHECK (session_type IN ('review', 'learn', 'cram')),
                        cards_studied INTEGER DEFAULT 0,
                        cards_correct INTEGER DEFAULT 0,
                        session_duration INTEGER DEFAULT 0,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id)
                    )
                ''')
                
                # Create user deck subscriptions table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_deck_subscriptions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        deck_id INTEGER NOT NULL,
                        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_active BOOLEAN DEFAULT 1,
                        notification_enabled BOOLEAN DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (user_id),
                        FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id) ON DELETE CASCADE,
                        UNIQUE(user_id, deck_id)
                    )
                ''')
                
                # Create user learning statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_learning_stats (
                        user_id INTEGER PRIMARY KEY,
                        total_cards_studied INTEGER DEFAULT 0,
                        total_study_time INTEGER DEFAULT 0,
                        current_streak INTEGER DEFAULT 0,
                        longest_streak INTEGER DEFAULT 0,
                        cards_due_today INTEGER DEFAULT 0,
                        last_study_date DATE,
                        level INTEGER DEFAULT 1,
                        experience_points INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_sessions ON speaking_simulations (user_id, started_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_status ON speaking_simulations (status)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_simulation_parts ON speaking_part_responses (simulation_id, part_number)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_question_history_user_part ON speaking_question_history (user_id, part_number, created_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_writing_evaluations ON writing_evaluations (user_id, evaluated_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_sent_words ON group_sent_words (group_id, sent_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_group_activity ON group_chats (last_activity)')
                
                # Flashcard system indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_flashcards_deck ON flashcards (deck_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_progress_due ON user_card_progress (user_id, due_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_progress_card ON user_card_progress (card_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_study_sessions_user ON study_sessions (user_id, started_at)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_deck_subscriptions ON user_deck_subscriptions (user_id, is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_public_decks ON flashcard_decks (is_public, category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_deck_creator ON flashcard_decks (creator_user_id)')
                
                conn.commit()
                logger.info("✅ Database initialized successfully")
                
        except Exception as e:
            logger.error(f"🔥 Failed to initialize database: {e}")
            raise

    def _migrate_speaking_question_history(self, cursor):
        """Ensure speaking_question_history table exists for uniqueness tracking."""
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS speaking_question_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    part_number INTEGER NOT NULL CHECK (part_number IN (1,2,3)),
                    question_text TEXT NOT NULL,
                    topic TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        except Exception as e:
            logger.error(f"🔥 Failed to ensure speaking_question_history table: {e}")
    
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
    
    def _migrate_writing_evaluations_table(self, cursor):
        """Migrate existing writing_evaluations table to fix structure"""
        try:
            # Check if the table exists and has the correct structure
            cursor.execute("PRAGMA table_info(writing_evaluations)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            logger.info(f"🔍 Writing evaluations table columns: {column_names}")
            
            # If table doesn't exist, it will be created with correct structure
            if not columns:
                logger.info("✅ Writing evaluations table doesn't exist, will be created")
                return
            
            # Check if the table structure is correct
            expected_columns = ['id', 'user_id', 'task_description', 'essay_text', 'overall_score', 
                              'task_response_score', 'coherence_cohesion_score', 'lexical_resource_score', 
                              'grammatical_range_score', 'evaluation_feedback', 'evaluated_at']
            
            if set(column_names) != set(expected_columns):
                logger.warning(f"⚠️ Table structure mismatch. Expected: {expected_columns}, Got: {column_names}")
                logger.info("🔄 Dropping and recreating writing_evaluations table with correct structure")
                
                # Drop the existing table
                cursor.execute("DROP TABLE IF EXISTS writing_evaluations")
                
                # Recreate with correct structure
                cursor.execute('''
                    CREATE TABLE writing_evaluations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        task_description TEXT NOT NULL,
                        essay_text TEXT NOT NULL,
                        overall_score REAL NOT NULL,
                        task_response_score REAL,
                        coherence_cohesion_score REAL,
                        lexical_resource_score REAL,
                        grammatical_range_score REAL,
                        evaluation_feedback TEXT NOT NULL,
                        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Recreate the index
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_writing_evaluations ON writing_evaluations (user_id, evaluated_at)')
                
                logger.info("✅ Writing evaluations table recreated with correct structure")
            else:
                logger.info("✅ Writing evaluations table structure is correct")
                        
        except Exception as e:
            logger.error(f"🔥 Failed to migrate writing_evaluations table: {e}")
    
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

    # === SPEAKING QUESTION HISTORY ===
    def save_question_history(self, user_id: int, part_number: int, question_text: str, topic: str = None) -> bool:
        """Persist generated question to history for deduplication."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO speaking_question_history (user_id, part_number, question_text, topic)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, part_number, question_text.strip(), (topic or '').strip()))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to save question history for user {user_id}, part {part_number}: {e}")
            return False

    def get_recent_questions(self, user_id: int, part_number: int, limit: int = 200) -> List[str]:
        """Fetch recent generated questions for a user and part."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT question_text FROM speaking_question_history
                    WHERE user_id = ? AND part_number = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (user_id, part_number, limit))
                rows = cursor.fetchall()
                return [r[0] for r in rows]
        except Exception as e:
            logger.error(f"🔥 Failed to get recent questions for user {user_id}, part {part_number}: {e}")
            return []

    def get_recent_topics(self, user_id: int, part_number: int, window_days: int = 30) -> List[str]:
        """Fetch distinct topics used recently to avoid repeats across sessions."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT COALESCE(topic, '') FROM speaking_question_history
                    WHERE user_id = ? AND part_number = ?
                      AND datetime(created_at) >= datetime('now', ?)
                ''', (user_id, part_number, f'-{int(window_days)} days'))
                rows = cursor.fetchall()
                return [r[0] for r in rows if r[0]]
        except Exception as e:
            logger.error(f"🔥 Failed to get recent topics for user {user_id}, part {part_number}: {e}")
            return []

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
                # First get the user_id from the simulation
                cursor.execute('SELECT user_id FROM speaking_simulations WHERE session_id = ?', (session_id,))
                user_id_result = cursor.fetchone()
                if not user_id_result:
                    logger.error(f"🔥 Could not find simulation {session_id}")
                    return False
                
                simulation_user_id = user_id_result[0]
                
                # Get current speaking stats
                cursor.execute('SELECT * FROM user_speaking_stats WHERE user_id = ?', (simulation_user_id,))
                current_stats = cursor.fetchone()
                
                if current_stats:
                    # Update existing stats
                    old_total = current_stats[1]  # total_simulations
                    old_completed = current_stats[2]  # completed_simulations
                    old_avg = current_stats[3]  # average_overall_score
                    old_best = current_stats[4]  # best_overall_score
                    
                    new_total = old_total + 1
                    new_completed = old_completed + 1
                    new_avg = (old_avg * old_completed + overall_band) / new_completed
                    new_best = max(old_best, overall_band)
                    
                    cursor.execute('''
                        UPDATE user_speaking_stats 
                        SET total_simulations = ?, completed_simulations = ?, 
                            average_overall_score = ?, best_overall_score = ?,
                            last_simulation_date = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (new_total, new_completed, new_avg, new_best, simulation_user_id))
                else:
                    # Insert new stats record
                    cursor.execute('''
                        INSERT INTO user_speaking_stats 
                        (user_id, total_simulations, completed_simulations, 
                         average_overall_score, best_overall_score, 
                         last_simulation_date, updated_at)
                        VALUES (?, 1, 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ''', (simulation_user_id, overall_band, overall_band))
                
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
                
                # Check if stats exist but seem incorrect (0 simulations but simulations exist)
                if not result or result[0] == 0:
                    # Check if there are actually completed simulations for this user
                    cursor.execute('SELECT COUNT(*) FROM speaking_simulations WHERE user_id = ? AND status = ?', (user_id, 'completed'))
                    actual_count = cursor.fetchone()[0]
                    
                    if actual_count > 0:
                        logger.info(f"🔧 Found {actual_count} completed simulations but 0 in stats for user {user_id}, recalculating...")
                        # Recalculate stats
                        if self.recalculate_speaking_stats(user_id):
                            # Retry getting the stats
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

    def recalculate_speaking_stats(self, user_id: int) -> bool:
        """Recalculate speaking statistics for a user based on their existing simulations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all completed speaking simulations for the user
                cursor.execute('''
                    SELECT overall_band, completed_at
                    FROM speaking_simulations 
                    WHERE user_id = ? AND status = 'completed'
                    ORDER BY completed_at ASC
                ''', (user_id,))
                simulations = cursor.fetchall()
                
                if not simulations:
                    logger.info(f"ℹ️ No completed speaking simulations found for user {user_id}")
                    return True
                
                # Calculate statistics
                total_simulations = len(simulations)
                completed_simulations = total_simulations
                overall_scores = [sim[0] for sim in simulations]
                last_simulation_date = simulations[-1][1]  # Most recent simulation date
                
                # Calculate averages
                avg_overall = sum(overall_scores) / len(overall_scores)
                best_overall = max(overall_scores)
                
                # Update or insert statistics
                cursor.execute('''
                    INSERT OR REPLACE INTO user_speaking_stats 
                    (user_id, total_simulations, completed_simulations, 
                     average_overall_score, best_overall_score, 
                     last_simulation_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, total_simulations, completed_simulations, 
                      avg_overall, best_overall, last_simulation_date))
                
                conn.commit()
                logger.info(f"✅ Recalculated speaking stats for user {user_id}: {completed_simulations} simulations, avg score {avg_overall:.1f}")
                return True
                
        except Exception as e:
            logger.error(f"🔥 Failed to recalculate speaking stats for user {user_id}: {e}")
            return False

    def save_writing_evaluation(self, user_id: int, task_description: str, essay_text: str,
                               overall_score: float, task_response_score: float = None,
                               coherence_cohesion_score: float = None, lexical_resource_score: float = None,
                               grammatical_range_score: float = None, evaluation_feedback: str = "") -> bool:
        """Save a writing evaluation to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Execute the INSERT statement with exact column specification
                cursor.execute('''
                    INSERT INTO writing_evaluations 
                    (user_id, task_description, essay_text, overall_score, task_response_score,
                     coherence_cohesion_score, lexical_resource_score, grammatical_range_score, evaluation_feedback)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, task_description, essay_text, overall_score, task_response_score,
                      coherence_cohesion_score, lexical_resource_score, grammatical_range_score, evaluation_feedback))
                
                # Update user writing statistics
                # First get current stats
                cursor.execute('SELECT * FROM user_writing_stats WHERE user_id = ?', (user_id,))
                current_stats = cursor.fetchone()
                
                if current_stats:
                    # Update existing stats
                    old_total = current_stats[1]  # total_evaluations
                    old_avg_overall = current_stats[2]  # average_overall_score
                    old_best = current_stats[3]  # best_overall_score
                    old_avg_tr = current_stats[4] if current_stats[4] else 0  # average_task_response_score
                    old_avg_cc = current_stats[5] if current_stats[5] else 0  # average_coherence_cohesion_score
                    old_avg_lr = current_stats[6] if current_stats[6] else 0  # average_lexical_resource_score
                    old_avg_gra = current_stats[7] if current_stats[7] else 0  # average_grammatical_range_score
                    
                    new_total = old_total + 1
                    new_avg_overall = (old_avg_overall * old_total + overall_score) / new_total
                    new_best = max(old_best, overall_score)
                    
                    # Calculate new averages for individual scores (only if they exist)
                    new_avg_tr = (old_avg_tr * old_total + (task_response_score or 0)) / new_total if task_response_score else old_avg_tr
                    new_avg_cc = (old_avg_cc * old_total + (coherence_cohesion_score or 0)) / new_total if coherence_cohesion_score else old_avg_cc
                    new_avg_lr = (old_avg_lr * old_total + (lexical_resource_score or 0)) / new_total if lexical_resource_score else old_avg_lr
                    new_avg_gra = (old_avg_gra * old_total + (grammatical_range_score or 0)) / new_total if grammatical_range_score else old_avg_gra
                    
                    cursor.execute('''
                        UPDATE user_writing_stats 
                        SET total_evaluations = ?, average_overall_score = ?, best_overall_score = ?,
                            average_task_response_score = ?, average_coherence_cohesion_score = ?,
                            average_lexical_resource_score = ?, average_grammatical_range_score = ?,
                            last_evaluation_date = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (new_total, new_avg_overall, new_best, new_avg_tr, new_avg_cc, new_avg_lr, new_avg_gra, user_id))
                else:
                    # Insert new stats record
                    cursor.execute('''
                        INSERT INTO user_writing_stats 
                        (user_id, total_evaluations, average_overall_score, best_overall_score,
                         average_task_response_score, average_coherence_cohesion_score,
                         average_lexical_resource_score, average_grammatical_range_score,
                         last_evaluation_date, updated_at)
                        VALUES (?, 1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ''', (user_id, overall_score, overall_score, 
                          task_response_score or 0, coherence_cohesion_score or 0,
                          lexical_resource_score or 0, grammatical_range_score or 0))
                
                conn.commit()
                logger.info(f"✅ Writing evaluation saved for user {user_id} with score {overall_score}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to save writing evaluation for user {user_id}: {e}")
            return False

    def get_user_writing_stats(self, user_id: int) -> dict:
        """Get user's writing statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT total_evaluations, average_overall_score, best_overall_score,
                           average_task_response_score, average_coherence_cohesion_score,
                           average_lexical_resource_score, average_grammatical_range_score,
                           last_evaluation_date
                    FROM user_writing_stats 
                    WHERE user_id = ?
                ''', (user_id,))
                result = cursor.fetchone()
                
                # Check if stats exist but seem incorrect (0 evaluations but evaluations exist)
                if not result or result[0] == 0:
                    # Check if there are actually evaluations for this user
                    cursor.execute('SELECT COUNT(*) FROM writing_evaluations WHERE user_id = ?', (user_id,))
                    actual_count = cursor.fetchone()[0]
                    
                    if actual_count > 0:
                        logger.info(f"🔧 Found {actual_count} evaluations but 0 in stats for user {user_id}, recalculating...")
                        # Recalculate stats
                        if self.recalculate_writing_stats(user_id):
                            # Retry getting the stats
                            cursor.execute('''
                                SELECT total_evaluations, average_overall_score, best_overall_score,
                                       average_task_response_score, average_coherence_cohesion_score,
                                       average_lexical_resource_score, average_grammatical_range_score,
                                       last_evaluation_date
                                FROM user_writing_stats 
                                WHERE user_id = ?
                            ''', (user_id,))
                            result = cursor.fetchone()
                
                if result:
                    return {
                        'total_evaluations': result[0],
                        'average_overall_score': result[1],
                        'best_overall_score': result[2],
                        'average_task_response_score': result[3],
                        'average_coherence_cohesion_score': result[4],
                        'average_lexical_resource_score': result[5],
                        'average_grammatical_range_score': result[6],
                        'last_evaluation_date': result[7]
                    }
                else:
                    return {
                        'total_evaluations': 0,
                        'average_overall_score': 0.0,
                        'best_overall_score': 0.0,
                        'average_task_response_score': 0.0,
                        'average_coherence_cohesion_score': 0.0,
                        'average_lexical_resource_score': 0.0,
                        'average_grammatical_range_score': 0.0,
                        'last_evaluation_date': None
                    }
        except Exception as e:
            logger.error(f"🔥 Failed to get writing stats for user {user_id}: {e}")
            return {
                'total_evaluations': 0,
                'average_overall_score': 0.0,
                'best_overall_score': 0.0,
                'average_task_response_score': 0.0,
                'average_coherence_cohesion_score': 0.0,
                'average_lexical_resource_score': 0.0,
                'average_grammatical_range_score': 0.0,
                'last_evaluation_date': None
            }

    def get_recent_writing_evaluations(self, user_id: int, limit: int = 5) -> List[Tuple]:
        """Get recent writing evaluations for a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT task_description, overall_score, evaluated_at
                    FROM writing_evaluations 
                    WHERE user_id = ? 
                    ORDER BY evaluated_at DESC 
                    LIMIT ?
                ''', (user_id, limit))
                evaluations = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(evaluations)} recent writing evaluations for user {user_id}")
                return evaluations
        except Exception as e:
            logger.error(f"🔥 Failed to get recent writing evaluations for user {user_id}: {e}")
            return []

    def recalculate_writing_stats(self, user_id: int) -> bool:
        """Recalculate writing statistics for a user based on their existing evaluations"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all writing evaluations for the user
                cursor.execute('''
                    SELECT overall_score, task_response_score, coherence_cohesion_score,
                           lexical_resource_score, grammatical_range_score, evaluated_at
                    FROM writing_evaluations 
                    WHERE user_id = ? 
                    ORDER BY evaluated_at ASC
                ''', (user_id,))
                evaluations = cursor.fetchall()
                
                if not evaluations:
                    logger.info(f"ℹ️ No writing evaluations found for user {user_id}")
                    return True
                
                # Calculate statistics
                total_evaluations = len(evaluations)
                overall_scores = [eval[0] for eval in evaluations]
                task_response_scores = [eval[1] for eval in evaluations if eval[1] is not None]
                coherence_scores = [eval[2] for eval in evaluations if eval[2] is not None]
                lexical_scores = [eval[3] for eval in evaluations if eval[3] is not None]
                grammar_scores = [eval[4] for eval in evaluations if eval[4] is not None]
                last_evaluation_date = evaluations[-1][5]  # Most recent evaluation date
                
                # Calculate averages
                avg_overall = sum(overall_scores) / len(overall_scores)
                best_overall = max(overall_scores)
                avg_task_response = sum(task_response_scores) / len(task_response_scores) if task_response_scores else 0.0
                avg_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0.0
                avg_lexical = sum(lexical_scores) / len(lexical_scores) if lexical_scores else 0.0
                avg_grammar = sum(grammar_scores) / len(grammar_scores) if grammar_scores else 0.0
                
                # Update or insert statistics
                cursor.execute('''
                    INSERT OR REPLACE INTO user_writing_stats 
                    (user_id, total_evaluations, average_overall_score, best_overall_score,
                     average_task_response_score, average_coherence_cohesion_score,
                     average_lexical_resource_score, average_grammatical_range_score,
                     last_evaluation_date, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (user_id, total_evaluations, avg_overall, best_overall,
                      avg_task_response, avg_coherence, avg_lexical, avg_grammar, last_evaluation_date))
                
                conn.commit()
                logger.info(f"✅ Recalculated writing stats for user {user_id}: {total_evaluations} evaluations, avg score {avg_overall:.1f}")
                return True
                
        except Exception as e:
            logger.error(f"🔥 Failed to recalculate writing stats for user {user_id}: {e}")
            return False

    # === GROUP CHAT FUNCTIONS ===
    
    def add_group_chat(self, group_id: int, group_title: str, group_type: str) -> bool:
        """Add or update group chat information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO group_chats 
                    (group_id, group_title, group_type, last_activity)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (group_id, group_title, group_type))
                conn.commit()
                logger.info(f"✅ Group {group_id} ({group_title}) added/updated in database")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to add group {group_id}: {e}")
            return False
    
    def get_group_sent_words(self, group_id: int, limit: int = 100) -> List[Tuple]:
        """Get words sent to a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT word, definition, translation, example, sent_at, sent_by_user_id
                    FROM group_sent_words 
                    WHERE group_id = ? 
                    ORDER BY sent_at DESC 
                    LIMIT ?
                ''', (group_id, limit))
                words = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(words)} sent words for group {group_id}")
                return words
        except Exception as e:
            logger.error(f"🔥 Failed to get sent words for group {group_id}: {e}")
            return []
    
    def is_word_sent_to_group(self, group_id: int, word: str) -> bool:
        """Check if a word has already been sent to a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 1 FROM group_sent_words 
                    WHERE group_id = ? AND LOWER(word) = LOWER(?)
                ''', (group_id, word.strip()))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"🔥 Failed to check word existence for group {group_id}: {e}")
            return False
    
    def save_word_to_group(self, group_id: int, word: str, definition: str, 
                          translation: str, example: str, sent_by_user_id: int) -> bool:
        """Save a word as sent to a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO group_sent_words 
                    (group_id, word, definition, translation, example, sent_by_user_id, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (group_id, word.strip().lower(), definition, translation, example, sent_by_user_id))
                
                # Update group last activity
                cursor.execute('''
                    UPDATE group_chats 
                    SET last_activity = CURRENT_TIMESTAMP 
                    WHERE group_id = ?
                ''', (group_id,))
                
                conn.commit()
                logger.info(f"✅ Word '{word}' saved to group {group_id}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to save word '{word}' to group {group_id}: {e}")
            return False
    
    def get_group_settings(self, group_id: int) -> dict:
        """Get settings for a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT auto_send_enabled, send_interval_hours, word_difficulty, last_auto_send
                    FROM group_settings 
                    WHERE group_id = ?
                ''', (group_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'auto_send_enabled': bool(result[0]),
                        'send_interval_hours': result[1],
                        'word_difficulty': result[2],
                        'last_auto_send': result[3]
                    }
                else:
                    # Return default settings if not found
                    return {
                        'auto_send_enabled': False,
                        'send_interval_hours': 24,
                        'word_difficulty': 'IELTS Band 7-9 (C1/C2)',
                        'last_auto_send': None
                    }
        except Exception as e:
            logger.error(f"🔥 Failed to get settings for group {group_id}: {e}")
            return {}
    
    def update_group_settings(self, group_id: int, **settings) -> bool:
        """Update settings for a specific group"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert or update settings
                cursor.execute('''
                    INSERT OR REPLACE INTO group_settings 
                    (group_id, auto_send_enabled, send_interval_hours, word_difficulty, last_auto_send)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    group_id,
                    settings.get('auto_send_enabled', False),
                    settings.get('send_interval_hours', 24),
                    settings.get('word_difficulty', 'IELTS Band 7-9 (C1/C2)'),
                    settings.get('last_auto_send', None)
                ))
                
                conn.commit()
                logger.info(f"✅ Settings updated for group {group_id}")
                return True
        except Exception as e:
            logger.error(f"🔥 Failed to update settings for group {group_id}: {e}")
            return False
    
    def get_group_stats(self, group_id: int = None) -> dict:
        """Get statistics for groups"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if group_id:
                    # Stats for specific group
                    cursor.execute('SELECT COUNT(*) FROM group_sent_words WHERE group_id = ?', (group_id,))
                    word_count = cursor.fetchone()[0]
                    
                    cursor.execute('''
                        SELECT group_title, group_type, added_at, last_activity
                        FROM group_chats WHERE group_id = ?
                    ''', (group_id,))
                    group_info = cursor.fetchone()
                    
                    return {
                        'group_id': group_id,
                        'word_count': word_count,
                        'group_title': group_info[0] if group_info else 'Unknown',
                        'group_type': group_info[1] if group_info else 'Unknown',
                        'added_at': group_info[2] if group_info else None,
                        'last_activity': group_info[3] if group_info else None
                    }
                else:
                    # Global stats
                    cursor.execute('SELECT COUNT(*) FROM group_chats WHERE is_active = 1')
                    total_groups = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM group_sent_words')
                    total_words_sent = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(DISTINCT group_id) FROM group_sent_words')
                    active_groups = cursor.fetchone()[0]
                    
                    return {
                        'total_groups': total_groups,
                        'total_words_sent': total_words_sent,
                        'active_groups': active_groups
                    }
        except Exception as e:
            logger.error(f"🔥 Failed to get group stats: {e}")
            return {}
    
    def get_all_groups(self, limit: int = 50) -> List[Tuple]:
        """Get all groups (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT gc.group_id, gc.group_title, gc.group_type, gc.added_at, gc.last_activity,
                           COUNT(gsw.id) as word_count
                    FROM group_chats gc
                    LEFT JOIN group_sent_words gsw ON gc.group_id = gsw.group_id
                    WHERE gc.is_active = 1
                    GROUP BY gc.group_id
                    ORDER BY gc.last_activity DESC
                    LIMIT ?
                ''', (limit,))
                groups = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(groups)} groups")
                return groups
        except Exception as e:
            logger.error(f"🔥 Failed to get all groups: {e}")
            return []
    
    def clear_group_words(self, group_id: int) -> bool:
        """Clear all words sent to a specific group (admin only)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM group_sent_words WHERE group_id = ?', (group_id,))
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"✅ Cleared {deleted_count} words from group {group_id}")
                    return True
                else:
                    logger.warning(f"⚠️ No words found to clear for group {group_id}")
                    return False
        except Exception as e:
            logger.error(f"🔥 Failed to clear words for group {group_id}: {e}")
            return False
    
    def get_groups_with_auto_send(self) -> List[Tuple]:
        """Get all groups with auto-send enabled"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT gc.group_id, gc.group_title, gs.last_auto_send, gs.send_interval_hours
                    FROM group_chats gc
                    JOIN group_settings gs ON gc.group_id = gs.group_id
                    WHERE gc.is_active = 1 AND gs.auto_send_enabled = 1
                    ORDER BY gc.last_activity DESC
                ''')
                groups = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(groups)} groups with auto-send enabled")
                return groups
        except Exception as e:
            logger.error(f"🔥 Failed to get groups with auto-send: {e}")
            return []

    # === FLASHCARD SYSTEM FUNCTIONS ===
    
    def create_deck(self, user_id: int, name: str, description: str = "", category: str = "General", is_public: bool = False) -> int:
        """Create a new flashcard deck"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO flashcard_decks (name, description, creator_user_id, category, is_public)
                    VALUES (?, ?, ?, ?, ?)
                ''', (name, description, user_id, category, is_public))
                deck_id = cursor.lastrowid
                conn.commit()
                logger.info(f"✅ Created deck '{name}' with ID {deck_id} for user {user_id}")
                return deck_id
        except Exception as e:
            logger.error(f"🔥 Failed to create deck: {e}")
            return None
    
    def create_flashcard(self, deck_id: int, front_text: str, back_text: str, tags: str = "", difficulty: int = 1) -> int:
        """Create a new flashcard"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO flashcards (deck_id, front_text, back_text, tags, difficulty)
                    VALUES (?, ?, ?, ?, ?)
                ''', (deck_id, front_text, back_text, tags, difficulty))
                card_id = cursor.lastrowid
                
                # Update deck card count
                cursor.execute('''
                    UPDATE flashcard_decks 
                    SET card_count = card_count + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (deck_id,))
                
                conn.commit()
                logger.info(f"✅ Created flashcard {card_id} in deck {deck_id}")
                return card_id
        except Exception as e:
            logger.error(f"🔥 Failed to create flashcard: {e}")
            return None
    
    def get_user_decks(self, user_id: int) -> List[Tuple]:
        """Get all decks for a user (created + subscribed)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT d.id, d.name, d.description, d.category, d.card_count, 
                           d.creator_user_id, d.created_at,
                           CASE WHEN d.creator_user_id = ? THEN 'owned' ELSE 'subscribed' END as relation
                    FROM flashcard_decks d
                    LEFT JOIN user_deck_subscriptions s ON d.id = s.deck_id AND s.user_id = ? AND s.is_active = 1
                    WHERE d.creator_user_id = ? OR s.user_id = ?
                    ORDER BY d.updated_at DESC
                ''', (user_id, user_id, user_id, user_id))
                decks = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(decks)} decks for user {user_id}")
                return decks
        except Exception as e:
            logger.error(f"🔥 Failed to get user decks: {e}")
            return []
    
    def get_due_cards(self, user_id: int, limit: int = 20) -> List[Tuple]:
        """Get cards due for review using spaced repetition"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT c.id, c.deck_id, c.front_text, c.back_text, c.tags, c.difficulty,
                           p.ease_factor, p.interval_days, p.review_count, p.streak_count,
                           d.name as deck_name
                    FROM flashcards c
                    JOIN user_card_progress p ON c.id = p.card_id
                    JOIN flashcard_decks d ON c.deck_id = d.id
                    WHERE p.user_id = ? AND p.due_date <= DATE('now')
                    ORDER BY p.due_date ASC, p.ease_factor ASC
                    LIMIT ?
                ''', (user_id, limit))
                cards = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(cards)} due cards for user {user_id}")
                return cards
        except Exception as e:
            logger.error(f"🔥 Failed to get due cards: {e}")
            return []
    
    def get_new_cards(self, user_id: int, limit: int = 10) -> List[Tuple]:
        """Get new cards that haven't been studied yet"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT c.id, c.deck_id, c.front_text, c.back_text, c.tags, c.difficulty,
                           d.name as deck_name
                    FROM flashcards c
                    JOIN flashcard_decks d ON c.deck_id = d.id
                    LEFT JOIN user_card_progress p ON c.id = p.card_id AND p.user_id = ?
                    WHERE p.id IS NULL AND (
                        d.creator_user_id = ? OR 
                        EXISTS (SELECT 1 FROM user_deck_subscriptions s 
                               WHERE s.user_id = ? AND s.deck_id = d.id AND s.is_active = 1)
                    )
                    ORDER BY c.created_at ASC
                    LIMIT ?
                ''', (user_id, user_id, user_id, limit))
                cards = cursor.fetchall()
                logger.info(f"✅ Retrieved {len(cards)} new cards for user {user_id}")
                return cards
        except Exception as e:
            logger.error(f"🔥 Failed to get new cards: {e}")
            return []
    
    def calculate_sm2_algorithm(self, ease_factor: float, interval: int, rating: int) -> Tuple[float, int]:
        """SM-2 Algorithm implementation
        Rating: 1=Again, 2=Hard, 3=Good, 4=Easy
        Returns: (new_ease_factor, new_interval)
        """
        from datetime import timedelta
        
        if rating < 3:  # Again or Hard
            new_interval = 1
            new_ease_factor = max(1.3, ease_factor - 0.2)
        else:
            if interval == 1:
                new_interval = 6
            elif interval == 6:
                new_interval = int(interval * ease_factor)
            else:
                new_interval = int(interval * ease_factor)
            
            # Adjust ease factor based on rating
            new_ease_factor = ease_factor + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
            new_ease_factor = max(1.3, new_ease_factor)  # Minimum ease factor
        
        return new_ease_factor, new_interval
    
    def review_card(self, user_id: int, card_id: int, rating: int, time_spent: int = 0) -> bool:
        """Record card review and update spaced repetition data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get current progress or create new
                cursor.execute('''
                    SELECT ease_factor, interval_days, review_count, streak_count
                    FROM user_card_progress
                    WHERE user_id = ? AND card_id = ?
                ''', (user_id, card_id))
                
                progress = cursor.fetchone()
                
                if progress:
                    ease_factor, interval_days, review_count, streak_count = progress
                else:
                    # New card
                    ease_factor, interval_days, review_count, streak_count = 2.5, 1, 0, 0
                
                # Calculate new values using SM-2
                new_ease_factor, new_interval = self.calculate_sm2_algorithm(ease_factor, interval_days, rating)
                
                # Update streak
                if rating >= 3:  # Good or Easy
                    new_streak = streak_count + 1
                else:
                    new_streak = 0
                
                from datetime import datetime, timedelta
                due_date = (datetime.now() + timedelta(days=new_interval)).date()
                
                # Insert or update progress
                cursor.execute('''
                    INSERT OR REPLACE INTO user_card_progress 
                    (user_id, card_id, ease_factor, interval_days, due_date, 
                     review_count, streak_count, last_reviewed, last_rating, total_time_spent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 
                           COALESCE((SELECT total_time_spent FROM user_card_progress 
                                   WHERE user_id = ? AND card_id = ?), 0) + ?)
                ''', (user_id, card_id, new_ease_factor, new_interval, due_date,
                      review_count + 1, new_streak, rating, user_id, card_id, time_spent))
                
                conn.commit()
                logger.info(f"✅ Updated card {card_id} progress for user {user_id} (rating: {rating}, new interval: {new_interval})")
                return True
                
        except Exception as e:
            logger.error(f"🔥 Failed to review card: {e}")
            return False
    
    def get_study_stats(self, user_id: int) -> dict:
        """Get comprehensive study statistics for user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get or create user stats
                cursor.execute('SELECT * FROM user_learning_stats WHERE user_id = ?', (user_id,))
                stats = cursor.fetchone()
                
                if not stats:
                    # Create default stats
                    cursor.execute('''
                        INSERT INTO user_learning_stats (user_id) VALUES (?)
                    ''', (user_id,))
                    conn.commit()
                    stats = (user_id, 0, 0, 0, 0, 0, None, 1, 0, None, None)
                
                # Get current due cards count
                cursor.execute('''
                    SELECT COUNT(*) FROM user_card_progress 
                    WHERE user_id = ? AND due_date <= DATE('now')
                ''', (user_id,))
                due_cards = cursor.fetchone()[0]
                
                # Get total cards available
                cursor.execute('''
                    SELECT COUNT(*) FROM flashcards c
                    JOIN flashcard_decks d ON c.deck_id = d.id
                    WHERE d.creator_user_id = ? OR EXISTS (
                        SELECT 1 FROM user_deck_subscriptions s 
                        WHERE s.user_id = ? AND s.deck_id = d.id AND s.is_active = 1
                    )
                ''', (user_id, user_id))
                total_cards = cursor.fetchone()[0]
                
                return {
                    'user_id': stats[0],
                    'total_cards_studied': stats[1],
                    'total_study_time': stats[2],
                    'current_streak': stats[3],
                    'longest_streak': stats[4],
                    'cards_due_today': due_cards,
                    'last_study_date': stats[6],
                    'level': stats[7],
                    'experience_points': stats[8],
                    'total_cards_available': total_cards
                }
                
        except Exception as e:
            logger.error(f"🔥 Failed to get study stats: {e}")
            return {}

# Global database instance
db = DatabaseManager()
