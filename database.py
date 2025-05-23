import sqlite3
import os
import json
import threading
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path):
        """Initialize database connection and create tables if they don't exist."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.db_path = db_path
        self._local = threading.local()  # Thread-local storage for connections
        self._lock = threading.Lock()    # Lock for thread-safe operations

        # Initialize the database in the main thread
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        try:
            self.create_tables(conn)
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def _get_connection(self):
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            try:
                self._local.conn = sqlite3.connect(self.db_path)
                self._local.conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            except sqlite3.Error as e:
                logger.error(f"Database connection error: {e}")
                raise
        return self._local.conn

    def close(self):
        """Close all database connections."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
            logger.info("Database connection closed")

    def create_tables(self, conn):
        """Create necessary tables if they don't exist."""
        try:
            cursor = conn.cursor()

            # Feeds table with extended fields
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                last_polled_item_guid TEXT,
                last_successful_poll_timestamp DATETIME,
                error_count INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                polling_interval INTEGER DEFAULT 30,
                max_articles INTEGER DEFAULT 100,
                created_at DATETIME,
                last_modified DATETIME,
                display_order INTEGER DEFAULT 0
            )
            ''')

            # Articles table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER,
                guid TEXT UNIQUE,
                link TEXT NOT NULL,
                title TEXT,
                published_date DATETIME,
                fetched_date DATETIME,
                raw_content TEXT,
                summary TEXT,
                llm_model_used TEXT,
                llm_processed_date DATETIME,
                processing_status TEXT,
                FOREIGN KEY (feed_id) REFERENCES feeds (id)
            )
            ''')

            # Keywords table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword_text TEXT UNIQUE NOT NULL
            )
            ''')

            # Article-Keywords junction table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS article_keywords (
                article_id INTEGER,
                keyword_id INTEGER,
                PRIMARY KEY (article_id, keyword_id),
                FOREIGN KEY (article_id) REFERENCES articles (id),
                FOREIGN KEY (keyword_id) REFERENCES keywords (id)
            )
            ''')

            # Add favorites table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                tags TEXT,
                UNIQUE(article_id),
                FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
            )
            ''')

            # Create FTS5 virtual table for full-text search
            cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title,
                summary,
                raw_content,
                content=articles,
                content_rowid=id
            )
            ''')

            # Create triggers to keep FTS table in sync
            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, summary, raw_content)
                VALUES (new.id, new.title, new.summary, new.raw_content);
            END;
            ''')

            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, summary, raw_content)
                VALUES('delete', old.id, old.title, old.summary, old.raw_content);
            END;
            ''')

            cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, summary, raw_content)
                VALUES('delete', old.id, old.title, old.summary, old.raw_content);
                INSERT INTO articles_fts(rowid, title, summary, raw_content)
                VALUES (new.id, new.title, new.summary, new.raw_content);
            END;
            ''')

            # Check if columns exist and add them if needed
            cursor.execute("PRAGMA table_info(feeds)")
            columns = {col[1] for col in cursor.fetchall()}

            # Add new columns if they don't exist - without defaults
            if 'polling_interval' not in columns:
                cursor.execute("ALTER TABLE feeds ADD COLUMN polling_interval INTEGER")
                cursor.execute("UPDATE feeds SET polling_interval = 30 WHERE polling_interval IS NULL")

            if 'max_articles' not in columns:
                cursor.execute("ALTER TABLE feeds ADD COLUMN max_articles INTEGER")
                cursor.execute("UPDATE feeds SET max_articles = 100 WHERE max_articles IS NULL")

            if 'created_at' not in columns:
                cursor.execute("ALTER TABLE feeds ADD COLUMN created_at DATETIME")
                cursor.execute("UPDATE feeds SET created_at = datetime('now') WHERE created_at IS NULL")

            if 'last_modified' not in columns:
                cursor.execute("ALTER TABLE feeds ADD COLUMN last_modified DATETIME")
                cursor.execute("UPDATE feeds SET last_modified = datetime('now') WHERE last_modified IS NULL")

            if 'display_order' not in columns:
                cursor.execute("ALTER TABLE feeds ADD COLUMN display_order INTEGER")
                cursor.execute("UPDATE feeds SET display_order = id WHERE display_order IS NULL")

            # Check if new columns exist and add them if needed
            cursor.execute("PRAGMA table_info(articles)")
            columns = {col[1] for col in cursor.fetchall()}

            # Add ArXiv-related columns
            if 'arxiv_id' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN arxiv_id TEXT")

            if 'full_content_status' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN full_content_status TEXT DEFAULT 'not_applicable'")
                # Possible values: 'not_applicable', 'pending', 'extracted', 'failed', 'unavailable'

            if 'full_content' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN full_content TEXT")

            if 'full_content_extracted_date' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN full_content_extracted_date DATETIME")

            if 'deep_summary_status' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN deep_summary_status TEXT DEFAULT 'not_requested'")
                # Possible values: 'not_requested', 'pending', 'completed', 'failed'

            if 'deep_summary' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN deep_summary TEXT")

            if 'deep_summary_date' not in columns:
                cursor.execute("ALTER TABLE articles ADD COLUMN deep_summary_date DATETIME")

            conn.commit()
            logger.info("Database tables created and upgraded successfully")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error creating/upgrading tables: {e}")
            raise

    def add_feed(self, url, name):
        """Add a new feed to the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # First check if feed already exists
            cursor.execute("SELECT id FROM feeds WHERE url = ?", (url,))
            existing = cursor.fetchone()
            if existing:
                logger.info(f"Feed already exists: {url}")
                return existing[0]

            # Insert the feed with current timestamp
            cursor.execute(
                """
                INSERT INTO feeds
                (url, name, is_enabled, polling_interval, max_articles, created_at, last_modified)
                VALUES (?, ?, 1, 30, 100, datetime('now'), datetime('now'))
                """,
                (url, name)
            )
            conn.commit()
            feed_id = cursor.lastrowid
            logger.info(f"Added feed: {name} ({url})")
            return feed_id
        except sqlite3.IntegrityError:
            logger.warning(f"Feed already exists: {url}")
            cursor.execute("SELECT id FROM feeds WHERE url = ?", (url,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error adding feed: {e}")
            raise

    def get_feeds(self, enabled_only=True, include_article_counts=False):
        """Get all feeds from the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if include_article_counts:
                # Include article counts in the query
                query = """
                SELECT f.*,
                       COALESCE(article_counts.count, 0) as article_count
                FROM feeds f
                LEFT JOIN (
                    SELECT feed_id, COUNT(*) as count
                    FROM articles
                    GROUP BY feed_id
                ) article_counts ON f.id = article_counts.feed_id
                """
            else:
                query = "SELECT * FROM feeds"

            if enabled_only:
                query += " WHERE f.is_enabled = 1" if include_article_counts else " WHERE is_enabled = 1"

            query += " ORDER BY f.display_order, f.id" if include_article_counts else " ORDER BY display_order, id"

            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting feeds: {e}")
            raise

    def update_feed_poll_status(self, feed_id, last_guid, timestamp=None):
        """Update feed's last polled item and timestamp."""
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE feeds SET last_polled_item_guid = ?, last_successful_poll_timestamp = ?, error_count = 0, last_modified = datetime('now') WHERE id = ?",
                (last_guid, timestamp, feed_id)
            )
            conn.commit()
            logger.info(f"Updated feed poll status for feed_id: {feed_id}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating feed poll status: {e}")
            raise

    def increment_feed_error(self, feed_id):
        """Increment error count for a feed."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE feeds SET error_count = error_count + 1, last_modified = datetime('now') WHERE id = ?",
                (feed_id,)
            )
            conn.commit()
            logger.warning(f"Incremented error count for feed_id: {feed_id}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error incrementing feed error count: {e}")
            raise

    def add_article(self, feed_id, guid, link, title, published_date, raw_content=None, status="pending_llm"):
        """Add a new article to the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Check if article already exists
            cursor.execute("SELECT id FROM articles WHERE guid = ?", (guid,))
            existing = cursor.fetchone()
            if existing:
                return existing[0]

            cursor.execute(
                """
                INSERT INTO articles
                (feed_id, guid, link, title, published_date, fetched_date, raw_content, processing_status)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?)
                """,
                (feed_id, guid, link, title, published_date, raw_content, status)
            )
            conn.commit()
            article_id = cursor.lastrowid
            logger.info(f"Added article: {title} from feed: {feed_id}")
            return article_id
        except sqlite3.IntegrityError:
            logger.debug(f"Article already exists: {guid}")
            cursor.execute("SELECT id FROM articles WHERE guid = ?", (guid,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error adding article: {e}")
            raise

    def update_article_summary(self, article_id, summary, model_used):
        """Update article with summary from LLM."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE articles
                SET summary = ?, llm_model_used = ?, llm_processed_date = datetime('now'), processing_status = 'processed'
                WHERE id = ?
                """,
                (summary, model_used, article_id)
            )
            conn.commit()
            logger.info(f"Updated article summary for article_id: {article_id}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating article summary: {e}")
            raise

    def add_keywords_to_article(self, article_id, keywords):
        """Add keywords to an article."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            for keyword in keywords:
                # First try to get existing keyword
                cursor.execute("SELECT id FROM keywords WHERE keyword_text = ?", (keyword,))
                result = cursor.fetchone()

                if result:
                    keyword_id = result['id']
                else:
                    # Create new keyword
                    cursor.execute("INSERT INTO keywords (keyword_text) VALUES (?)", (keyword,))
                    keyword_id = cursor.lastrowid

                # Associate keyword with article
                cursor.execute(
                    "INSERT OR IGNORE INTO article_keywords (article_id, keyword_id) VALUES (?, ?)",
                    (article_id, keyword_id)
                )

            conn.commit()
            logger.info(f"Added keywords to article_id: {article_id}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error adding keywords to article: {e}")
            raise

    def get_articles(self, limit=50, offset=0, feed_id=None, keyword=None, sort_by='date_desc'):
            """Get articles with optional filtering and sorting."""
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                # Base query without filters
                base_query = """
                    SELECT a.*, f.name as feed_name,
                        GROUP_CONCAT(k.keyword_text) as keywords
                    FROM articles a
                    JOIN feeds f ON a.feed_id = f.id
                    LEFT JOIN article_keywords ak ON a.id = ak.article_id
                    LEFT JOIN keywords k ON ak.keyword_id = k.id
                """

                where_clauses = []
                params = []

                # Add feed filter if specified
                if feed_id:
                    where_clauses.append("a.feed_id = ?")
                    params.append(feed_id)

                # Add keyword filter if specified
                if keyword:
                    # This is the enhanced part - search across all text fields
                    keyword_clause = """
                        (
                            -- Search in LLM-extracted keywords
                            a.id IN (
                                SELECT article_id
                                FROM article_keywords
                                WHERE keyword_id IN (
                                    SELECT id
                                    FROM keywords
                                    WHERE keyword_text LIKE ?
                                )
                            )
                            -- Search in title
                            OR a.title LIKE ?
                            -- Search in summary
                            OR a.summary LIKE ?
                            -- Search in raw content
                            OR a.raw_content LIKE ?
                        )
                    """
                    where_clauses.append(keyword_clause)

                    # Add wildcard pattern for SQL LIKE
                    keyword_pattern = f"%{keyword}%"
                    params.extend([keyword_pattern, keyword_pattern, keyword_pattern, keyword_pattern])

                # Construct the full query
                query = base_query
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)

                query += " GROUP BY a.id"

                # Add sorting
                if sort_by == 'date_asc':
                    query += " ORDER BY a.published_date ASC"
                elif sort_by == 'date_desc':
                    query += " ORDER BY a.published_date DESC"
                elif sort_by == 'title_asc':
                    query += " ORDER BY a.title ASC"
                elif sort_by == 'title_desc':
                    query += " ORDER BY a.title DESC"
                elif sort_by == 'feed_asc':
                    query += " ORDER BY f.name ASC"
                elif sort_by == 'feed_desc':
                    query += " ORDER BY f.name DESC"
                else:
                    # Default to date descending
                    query += " ORDER BY a.published_date DESC"

                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                # Execute the query
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                logger.error(f"Error getting articles: {e}")
                raise

    def get_article_by_id(self, article_id):
        """Get a specific article by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.*, f.name as feed_name,
                       GROUP_CONCAT(k.keyword_text) as keywords
                FROM articles a
                JOIN feeds f ON a.feed_id = f.id
                LEFT JOIN article_keywords ak ON a.id = ak.article_id
                LEFT JOIN keywords k ON ak.keyword_id = k.id
                WHERE a.id = ?
                GROUP BY a.id
                """,
                (article_id,)
            )
            result = cursor.fetchone()
            return dict(result) if result else None
        except sqlite3.Error as e:
            logger.error(f"Error getting article by ID: {e}")
            raise

    def search_articles(self, query, limit=50, offset=0):
        """Search articles using full-text search and LIKE patterns for comprehensive results."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Use FTS for main search but also include LIKE patterns for better coverage
            search_query = """
                SELECT a.*, f.name as feed_name,
                       GROUP_CONCAT(k.keyword_text) as keywords,
                       snippet(articles_fts, 0, '<b>', '</b>', '...', 10) as title_snippet,
                       snippet(articles_fts, 1, '<b>', '</b>', '...', 10) as summary_snippet
                FROM (
                    -- First get results from FTS virtual table
                    SELECT rowid FROM articles_fts
                    WHERE articles_fts MATCH ?

                    UNION

                    -- Then get results from LIKE patterns in original tables (for fields that might not be in FTS)
                    SELECT id FROM articles
                    WHERE title LIKE ? OR summary LIKE ? OR raw_content LIKE ?

                    UNION

                    -- Also include keyword matches
                    SELECT article_id FROM article_keywords
                    JOIN keywords ON article_keywords.keyword_id = keywords.id
                    WHERE keyword_text LIKE ?
                ) as matches
                JOIN articles a ON matches.rowid = a.id
                JOIN feeds f ON a.feed_id = f.id
                LEFT JOIN article_keywords ak ON a.id = ak.article_id
                LEFT JOIN keywords k ON ak.keyword_id = k.id
                GROUP BY a.id
                ORDER BY a.published_date DESC
                LIMIT ? OFFSET ?
            """

            # Prepare parameters
            pattern = f"%{query}%"
            cursor.execute(search_query, (query, pattern, pattern, pattern, pattern, limit, offset))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error searching articles: {e}")
            raise

    def execute(self, query, params=()):
        """Execute a custom query."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor
        except sqlite3.Error as e:
            logger.error(f"Error executing query: {e}")
            raise

    def update_feed(self, feed_id, name=None, url=None, is_enabled=None, polling_interval=None, max_articles=None, display_order=None):
        """Update feed details."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Build the SET part of the SQL query
            set_clauses = []
            params = []

            if name is not None:
                set_clauses.append("name = ?")
                params.append(name)

            if url is not None:
                set_clauses.append("url = ?")
                params.append(url)

            if is_enabled is not None:
                set_clauses.append("is_enabled = ?")
                params.append(1 if is_enabled else 0)

            if polling_interval is not None:
                set_clauses.append("polling_interval = ?")
                params.append(polling_interval)

            if max_articles is not None:
                set_clauses.append("max_articles = ?")
                params.append(max_articles)

            if display_order is not None:
                set_clauses.append("display_order = ?")
                params.append(display_order)

            # Only update if there's something to update
            if set_clauses:
                # Always update last_modified timestamp
                set_clauses.append("last_modified = datetime('now')")

                # Build and execute the SQL query
                query = f"UPDATE feeds SET {', '.join(set_clauses)} WHERE id = ?"
                params.append(feed_id)

                cursor.execute(query, params)
                conn.commit()

                if cursor.rowcount > 0:
                    logger.info(f"Updated feed ID {feed_id}")
                    return True
                else:
                    logger.warning(f"Feed ID {feed_id} not found or no changes made")
                    return False

            return False
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating feed: {e}")
            raise

    def toggle_feed(self, feed_id, enabled=None):
        """Toggle or set the enabled state of a feed."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            if enabled is None:
                # Toggle current state
                cursor.execute(
                    "UPDATE feeds SET is_enabled = NOT is_enabled, last_modified = datetime('now') WHERE id = ?",
                    (feed_id,)
                )
            else:
                # Set to specified state
                cursor.execute(
                    "UPDATE feeds SET is_enabled = ?, last_modified = datetime('now') WHERE id = ?",
                    (1 if enabled else 0, feed_id)
                )

            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error toggling feed: {e}")
            raise

    def reorder_feeds(self, order_mapping):
        """Update display order of feeds.

        Args:
            order_mapping: Dictionary mapping feed IDs to their new display order
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            for feed_id, order in order_mapping.items():
                cursor.execute(
                    "UPDATE feeds SET display_order = ?, last_modified = datetime('now') WHERE id = ?",
                    (order, feed_id)
                )

            conn.commit()
            logger.info(f"Reordered {len(order_mapping)} feeds")
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error reordering feeds: {e}")
            raise

    def get_feed_by_id(self, feed_id):
        """Get detailed information about a specific feed."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,))
            feed = cursor.fetchone()

            if feed:
                # Get article count for this feed
                cursor.execute("SELECT COUNT(*) FROM articles WHERE feed_id = ?", (feed_id,))
                article_count = cursor.fetchone()[0]

                # Convert to dict and add article count
                feed_dict = dict(feed)
                feed_dict['article_count'] = article_count

                return feed_dict

            return None
        except sqlite3.Error as e:
            logger.error(f"Error getting feed by ID: {e}")
            raise

    def export_feeds_to_json(self):
        """Export all feeds to a JSON format."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get all feeds, ordered by display order
            cursor.execute(
                "SELECT id, name, url, is_enabled, polling_interval, max_articles, display_order FROM feeds ORDER BY display_order"
            )

            feeds = []
            for row in cursor.fetchall():
                feeds.append({
                    "id": row[0],
                    "name": row[1],
                    "url": row[2],
                    "enabled": bool(row[3]),
                    "polling_interval": row[4],
                    "max_articles": row[5],
                    "display_order": row[6]
                })

            return {"feeds": feeds}
        except sqlite3.Error as e:
            logger.error(f"Error exporting feeds: {e}")
            raise

    def import_feeds_from_json(self, json_data, overwrite=False):
        """Import feeds from JSON data.

        Args:
            json_data: Dictionary containing feed data
            overwrite: If True, will replace existing feeds with same URL

        Returns:
            Dictionary with counts of added, updated, and skipped feeds
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            result = {
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0
            }

            # Get existing feed URLs
            cursor.execute("SELECT id, url FROM feeds")
            existing_feeds = {row[1]: row[0] for row in cursor.fetchall()}

            # Process each feed in the JSON data
            for feed in json_data.get("feeds", []):
                try:
                    url = feed.get("url")
                    if not url:
                        result["errors"] += 1
                        continue

                    name = feed.get("name", url.split("/")[-1])
                    enabled = feed.get("enabled", True)
                    polling_interval = feed.get("polling_interval", 30)
                    max_articles = feed.get("max_articles", 100)
                    display_order = feed.get("display_order", 0)

                    if url in existing_feeds:
                        # Feed exists
                        if overwrite:
                            # Update existing feed
                            feed_id = existing_feeds[url]
                            cursor.execute(
                                """
                                UPDATE feeds
                                SET name = ?, is_enabled = ?, polling_interval = ?,
                                    max_articles = ?, display_order = ?, last_modified = datetime('now')
                                WHERE id = ?
                                """,
                                (name, 1 if enabled else 0, polling_interval, max_articles, display_order, feed_id)
                            )
                            result["updated"] += 1
                        else:
                            # Skip
                            result["skipped"] += 1
                    else:
                        # Add new feed
                        cursor.execute(
                            """
                            INSERT INTO feeds
                            (url, name, is_enabled, polling_interval, max_articles, display_order, created_at, last_modified)
                            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                            """,
                            (url, name, 1 if enabled else 0, polling_interval, max_articles, display_order)
                        )
                        result["added"] += 1
                except Exception as e:
                    logger.error(f"Error processing feed {feed.get('name', 'unknown')}: {e}")
                    result["errors"] += 1

            conn.commit()
            return result
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error importing feeds: {e}")
            raise

    def delete_article(self, article_id):
        """Delete an article and its associated data."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")

            # Delete from article_keywords junction table
            cursor.execute("DELETE FROM article_keywords WHERE article_id = ?", (article_id,))

            # Delete from articles_fts virtual table
            cursor.execute("DELETE FROM articles_fts WHERE rowid = ?", (article_id,))

            # Delete from articles table
            cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))

            # Commit transaction
            conn.commit()
            logger.info(f"Deleted article ID: {article_id}")
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error deleting article {article_id}: {e}")
            return False

    def delete_feed(self, feed_id):
        """Delete a feed and all its associated articles."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Begin transaction
            cursor.execute("BEGIN TRANSACTION")

            # Get all article IDs for this feed
            cursor.execute("SELECT id FROM articles WHERE feed_id = ?", (feed_id,))
            article_ids = [row[0] for row in cursor.fetchall()]

            # Delete article keywords
            cursor.execute("DELETE FROM article_keywords WHERE article_id IN (SELECT id FROM articles WHERE feed_id = ?)", (feed_id,))

            # Delete from FTS
            for article_id in article_ids:
                cursor.execute("DELETE FROM articles_fts WHERE rowid = ?", (article_id,))

            # Delete articles
            cursor.execute("DELETE FROM articles WHERE feed_id = ?", (feed_id,))

            # Delete feed
            cursor.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))

            # Commit transaction
            conn.commit()
            logger.info(f"Deleted feed ID: {feed_id} and {len(article_ids)} associated articles")
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error deleting feed {feed_id}: {e}")
            return False

    def clean_orphaned_keywords(self):
        """Clean up keywords that are not associated with any articles."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Delete keywords not associated with any article
            cursor.execute("""
                DELETE FROM keywords
                WHERE id NOT IN (
                    SELECT DISTINCT keyword_id FROM article_keywords
                )
            """)

            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned up {deleted_count} orphaned keywords")
            return deleted_count
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error cleaning orphaned keywords: {e}")
            return 0

    def add_favorite(self, article_id, notes=None, tags=None):
        """Add an article to favorites."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO favorites (article_id, notes, tags, added_date) VALUES (?, ?, ?, datetime('now'))",
                (article_id, notes, tags)
            )
            conn.commit()
            logger.info(f"Added article {article_id} to favorites")
            return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error adding favorite: {e}")
            return False

    def remove_favorite(self, article_id):
        """Remove an article from favorites."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM favorites WHERE article_id = ?", (article_id,))
            conn.commit()
            removed = cursor.rowcount > 0
            if removed:
                logger.info(f"Removed article {article_id} from favorites")
            return removed
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error removing favorite: {e}")
            return False

    def update_favorite(self, article_id, notes=None, tags=None):
        """Update favorite notes and tags."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE favorites SET notes = ?, tags = ? WHERE article_id = ?",
                (notes, tags, article_id)
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated favorite for article {article_id}")
            return updated
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating favorite: {e}")
            return False

    def get_favorites(self, limit=50, offset=0, tag_filter=None, sort_by='date_desc'):
        """Get favorited articles with optional filtering and sorting."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = """
                SELECT a.*, f.name as feed_name,
                       fav.added_date as favorited_date,
                       fav.notes as favorite_notes,
                       fav.tags as favorite_tags,
                       GROUP_CONCAT(k.keyword_text) as keywords
                FROM favorites fav
                JOIN articles a ON fav.article_id = a.id
                JOIN feeds f ON a.feed_id = f.id
                LEFT JOIN article_keywords ak ON a.id = ak.article_id
                LEFT JOIN keywords k ON ak.keyword_id = k.id
            """

            params = []

            # Add tag filter if specified
            if tag_filter:
                query += " WHERE fav.tags LIKE ?"
                params.append(f"%{tag_filter}%")

            query += " GROUP BY a.id"

            # Add sorting
            if sort_by == 'date_desc':
                query += " ORDER BY fav.added_date DESC"
            elif sort_by == 'date_asc':
                query += " ORDER BY fav.added_date ASC"
            elif sort_by == 'title_asc':
                query += " ORDER BY a.title ASC"
            elif sort_by == 'title_desc':
                query += " ORDER BY a.title DESC"
            elif sort_by == 'published_desc':
                query += " ORDER BY a.published_date DESC"
            else:
                query += " ORDER BY fav.added_date DESC"

            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting favorites: {e}")
            return []

    def is_favorite(self, article_id):
        """Check if an article is favorited."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM favorites WHERE article_id = ?", (article_id,))
            return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Error checking favorite status: {e}")
            return False

    def get_favorite_tags(self):
        """Get all unique tags from favorites."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT tags FROM favorites WHERE tags IS NOT NULL AND tags != ''")

            # Parse comma-separated tags
            all_tags = set()
            for row in cursor.fetchall():
                if row[0]:
                    tags = [tag.strip() for tag in row[0].split(',') if tag.strip()]
                    all_tags.update(tags)

            return sorted(list(all_tags))
        except sqlite3.Error as e:
            logger.error(f"Error getting favorite tags: {e}")
            return []

    def get_favorites_count(self, tag_filter=None):
        """Get total count of favorites for pagination."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = "SELECT COUNT(*) FROM favorites"
            params = []

            if tag_filter:
                query += " WHERE tags LIKE ?"
                params.append(f"%{tag_filter}%")

            cursor.execute(query, params)
            return cursor.fetchone()[0]
        except sqlite3.Error as e:
            logger.error(f"Error getting favorites count: {e}")
            return 0

    def update_article_arxiv_status(self, article_id, arxiv_id=None, status='pending'):
        """Update article with ArXiv ID and extraction status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE articles SET arxiv_id = ?, full_content_status = ? WHERE id = ?",
                (arxiv_id, status, article_id)
            )
            conn.commit()
            logger.info(f"Updated ArXiv status for article {article_id}: {status}")
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating ArXiv status: {e}")
            return False

    def update_article_full_content(self, article_id, full_content, status='extracted'):
        """Update article with extracted full content."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE articles
                   SET full_content = ?, full_content_status = ?, full_content_extracted_date = datetime('now')
                   WHERE id = ?""",
                (full_content, status, article_id)
            )
            conn.commit()
            logger.info(f"Updated full content for article {article_id}")
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating full content: {e}")
            return False

    def update_deep_summary(self, article_id, deep_summary, status='completed'):
        """Update article with deep summary from full content."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE articles
                   SET deep_summary = ?, deep_summary_status = ?, deep_summary_date = datetime('now')
                   WHERE id = ?""",
                (deep_summary, status, article_id)
            )
            conn.commit()
            logger.info(f"Updated deep summary for article {article_id}")
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error updating deep summary: {e}")
            return False

    def get_articles_for_arxiv_extraction(self, limit=10):
        """Get articles that could have ArXiv content extracted."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # More comprehensive ArXiv detection
            cursor.execute(
                """SELECT id, title, link, guid
                   FROM articles
                   WHERE (
                       link LIKE '%arxiv.org%'
                       OR guid LIKE '%arxiv.org%'
                       OR link LIKE '%arXiv.org%'
                       OR guid LIKE '%arXiv.org%'
                   )
                   AND (
                       full_content_status = 'not_applicable'
                       OR full_content_status IS NULL
                       OR arxiv_id IS NULL
                   )
                   ORDER BY published_date DESC
                   LIMIT ?""",
                (limit,)
            )
            results = [dict(row) for row in cursor.fetchall()]
            logger.info(f"Found {len(results)} articles for ArXiv extraction")
            return results
        except sqlite3.Error as e:
            logger.error(f"Error getting articles for ArXiv extraction: {e}")
            return []

    def get_articles_for_deep_summary(self, limit=10):
        """Get articles that have full content but need deep summary."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, title, full_content
                   FROM articles
                   WHERE full_content_status = 'extracted'
                   AND full_content IS NOT NULL
                   AND deep_summary_status = 'pending'
                   ORDER BY full_content_extracted_date DESC
                   LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting articles for deep summary: {e}")
            return []

    def request_deep_summary(self, article_id):
        """Mark an article as requesting deep summary processing."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE articles SET deep_summary_status = 'pending' WHERE id = ?",
                (article_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error requesting deep summary: {e}")
            return False

    def extract_arxiv_id_from_url(self, url):
        """Extract ArXiv ID from URL or GUID."""
        import re

        # ArXiv URL patterns
        patterns = [
            r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5})',  # New format
            r'arxiv\.org/abs/([a-z-]+/[0-9]{7})',     # Old format
            r'arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,5})', # PDF links
            r'arxiv\.org/pdf/([a-z-]+/[0-9]{7})',     # Old PDF format
        ]

        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def get_feed_arxiv_breakdown(self):
        """Get breakdown of ArXiv articles by feed."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get ArXiv article counts by feed
            cursor.execute("""
                SELECT f.id, f.name,
                       COUNT(a.id) as total_arxiv,
                       SUM(CASE WHEN a.full_content_status = 'extracted' THEN 1 ELSE 0 END) as extracted,
                       SUM(CASE WHEN a.deep_summary_status = 'completed' THEN 1 ELSE 0 END) as analyzed
                FROM feeds f
                JOIN articles a ON f.id = a.feed_id
                WHERE a.arxiv_id IS NOT NULL
                GROUP BY f.id
                ORDER BY total_arxiv DESC
            """)

            feeds = []
            for row in cursor.fetchall():
                feed_dict = {
                    "id": row[0],
                    "name": row[1],
                    "total_arxiv": row[2],
                    "extracted": row[3],
                    "analyzed": row[4],
                    "extraction_percentage": round((row[3] / row[2]) * 100) if row[2] > 0 else 0,
                    "analysis_percentage": round((row[4] / row[3]) * 100) if row[3] > 0 else 0
                }
                feeds.append(feed_dict)

            return {
                "feeds": feeds,
                "total_feeds_with_arxiv": len(feeds)
            }

        except sqlite3.Error as e:
            logger.error(f"Error getting ArXiv feed breakdown: {e}")
            return {
                "error": str(e),
                "feeds": [],
                "total_feeds_with_arxiv": 0
            }

    def get_arxiv_statistics(self):
        """Get statistics about ArXiv articles and processing."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get total ArXiv articles
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE arxiv_id IS NOT NULL
            """)
            total_arxiv = cursor.fetchone()[0]

            # Get counts by extraction status
            cursor.execute("""
                SELECT full_content_status, COUNT(*)
                FROM articles
                WHERE arxiv_id IS NOT NULL
                GROUP BY full_content_status
            """)
            extraction_status = {row[0]: row[1] for row in cursor.fetchall()}

            # Format extraction status for UI
            extraction = {
                "extracted": extraction_status.get("extracted", 0),
                "pending": extraction_status.get("pending", 0),
                "failed": extraction_status.get("failed", 0),
                "unavailable": extraction_status.get("unavailable", 0),
                "not_applicable": extraction_status.get("not_applicable", 0)
            }

            # Get deep summary stats
            cursor.execute("""
                SELECT deep_summary_status, COUNT(*)
                FROM articles
                WHERE arxiv_id IS NOT NULL
                GROUP BY deep_summary_status
            """)
            summary_status = {row[0]: row[1] for row in cursor.fetchall()}

            # Format deep summary status for UI
            deep_summary = {
                "completed": summary_status.get("completed", 0),
                "pending": summary_status.get("pending", 0),
                "failed": summary_status.get("failed", 0),
                "not_requested": summary_status.get("not_requested", 0)
            }

            # Get content type statistics
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE arxiv_id IS NOT NULL
                AND full_content_status = 'extracted'
                AND length(full_content) > 10000
            """)
            full_papers = cursor.fetchone()[0]

            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE arxiv_id IS NOT NULL
                AND full_content_status = 'extracted'
                AND length(full_content) <= 10000
            """)
            abstracts_plus = cursor.fetchone()[0]

            # Get recent ArXiv articles (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) FROM articles
                WHERE arxiv_id IS NOT NULL
                AND published_date > datetime('now', '-7 days')
            """)
            recent_arxiv = cursor.fetchone()[0]

            # Get most recent extractions
            cursor.execute("""
                SELECT id, title, arxiv_id, full_content_extracted_date
                FROM articles
                WHERE full_content_status = 'extracted'
                ORDER BY full_content_extracted_date DESC
                LIMIT 5
            """)
            recent_extractions = [dict(row) for row in cursor.fetchall()]

            return {
                "total_arxiv": total_arxiv,
                "recent_arxiv": recent_arxiv,
                "extraction": extraction,
                "deep_summary": deep_summary,
                "content_types": {
                    "full_papers": full_papers,
                    "abstracts_plus": abstracts_plus
                },
                "recent_extractions": recent_extractions
            }

        except sqlite3.Error as e:
            logger.error(f"Error getting ArXiv statistics: {e}")
            return {
                "error": str(e),
                "total_arxiv": 0,
                "recent_arxiv": 0,
                "extraction": {
                    "extracted": 0,
                    "pending": 0,
                    "failed": 0,
                    "unavailable": 0,
                    "not_applicable": 0
                },
                "deep_summary": {
                    "completed": 0,
                    "pending": 0,
                    "failed": 0,
                    "not_requested": 0
                },
                "content_types": {
                    "full_papers": 0,
                    "abstracts_plus": 0
                },
                "recent_extractions": []
            }