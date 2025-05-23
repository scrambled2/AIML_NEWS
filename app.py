import os
import asyncio
import logging
import signal
import sys
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from threading import Thread

# Create application directory if it doesn't exist
os.makedirs('instance', exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("instance/aiml_news.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import our modules
from config import Config
from database import Database
from feed_reader import FeedReader
from llm_processor import LLMProcessor
# Import the new ArXiv extractor
from arxiv_extractor import ArXivExtractor

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For flash messages

# Initialize configuration
config = Config()

# Initialize database
db = Database(config.database_path)

# Initialize feed reader and LLM processor with proper error handling
try:
    feed_reader = FeedReader(db, config)
    logger.info("Feed reader initialized")
except Exception as e:
    logger.error(f"Error initializing feed reader: {e}")
    raise

try:
    llm_processor = LLMProcessor(db, config)
    logger.info("LLM processor initialized")
except Exception as e:
    logger.error(f"Error initializing LLM processor: {e}")
    # Create a dummy LLM processor that doesn't do anything
    class DummyLLMProcessor:
        async def start_processing(self):
            logger.info("Dummy LLM processor - no processing will be done")
        def stop_processing(self):
            pass
    llm_processor = DummyLLMProcessor()

# Initialize ArXiv extractor after the existing initializations
try:
    arxiv_extractor = ArXivExtractor(db, config)
    logger.info("ArXiv extractor initialized")
except Exception as e:
    logger.error(f"Error initializing ArXiv extractor: {e}")
    # Create a dummy extractor
    class DummyArXivExtractor:
        async def start_extraction(self):
            logger.info("Dummy ArXiv extractor - no extraction will be done")
        async def close(self):
            pass
    arxiv_extractor = DummyArXivExtractor()

# Initialize asyncio loop and tasks
loop = asyncio.new_event_loop()
feed_poller_task = None
llm_processor_task = None
arxiv_extractor_task = None

def start_background_tasks():
    """Start background tasks for feed polling, LLM processing, and ArXiv extraction."""
    global feed_poller_task, llm_processor_task, arxiv_extractor_task

    try:
        # Create tasks
        feed_poller_task = loop.create_task(feed_reader.start_polling())
        llm_processor_task = loop.create_task(llm_processor.start_processing())
        arxiv_extractor_task = loop.create_task(arxiv_extractor.start_extraction())

        logger.info("Background tasks started")
    except Exception as e:
        logger.error(f"Error starting background tasks: {e}")

def run_async_loop():
    """Run the asyncio event loop in a separate thread."""
    asyncio.set_event_loop(loop)
    start_background_tasks()

    try:
        loop.run_forever()
    except Exception as e:
        logger.error(f"Error in asyncio loop: {e}")

# Start asyncio loop in a separate thread
async_thread = Thread(target=run_async_loop, daemon=True)
async_thread.start()

# Handle graceful shutdown
def shutdown_handler(signum, frame):
    """Handle shutdown signals by stopping tasks and closing connections."""
    logger.info(f"Received signal {signum}, shutting down...")

    # Cancel tasks
    if feed_poller_task:
        feed_poller_task.cancel()
    if llm_processor_task:
        llm_processor_task.cancel()
    if arxiv_extractor_task:
        arxiv_extractor_task.cancel()

    # Close sessions
    if not loop.is_closed():
        loop.call_soon_threadsafe(lambda: loop.create_task(feed_reader.close()))
        loop.call_soon_threadsafe(lambda: loop.create_task(arxiv_extractor.close()))

    # Close database connection
    db.close()

    # Stop the event loop
    loop.call_soon_threadsafe(loop.stop)

    logger.info("Shutdown complete")

    # Only exit if this was called as a signal handler
    if signum in (signal.SIGINT, signal.SIGTERM):
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

# Add default feeds if none exist
try:
    # Check if there are any feeds
    feeds = db.get_feeds(enabled_only=False)
    if not feeds:
        logger.info("No feeds found. Adding default feeds.")

        # Default feeds
        default_feeds = [
            {
                "name": "Microsoft Research Blog",
                "url": "https://www.microsoft.com/en-us/research/feed/"
            }
        ]

        # Add each feed
        for i, feed in enumerate(default_feeds):
            feed_id = db.add_feed(feed["url"], feed["name"])
            # Update additional properties with higher default
            db.update_feed(feed_id, polling_interval=30, max_articles=5000, display_order=i+1)

        logger.info(f"Added {len(default_feeds)} default feeds")
except Exception as e:
    logger.error(f"Error adding default feeds: {e}")

# Flask routes
@app.route('/')
def index():
    """Main page - side panel view with articles."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 5), 100)

    offset = (page - 1) * per_page
    feed_id = request.args.get('feed_id', None, type=int)
    keyword = request.args.get('keyword', None)
    sort_by = request.args.get('sort_by', 'date_desc')

    # Check if request is from mobile (used for initial side panel visibility)
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent

    try:
        articles = db.get_articles(limit=per_page, offset=offset, feed_id=feed_id, keyword=keyword, sort_by=sort_by)
        feeds = db.get_feeds(enabled_only=False)

        # Count query for pagination
        count_query = "SELECT COUNT(*) FROM articles a"
        params = []

        where_clauses = []
        if feed_id:
            where_clauses.append("a.feed_id = ?")
            params.append(feed_id)

        if keyword:
            keyword_clause = """
                (
                    a.id IN (
                        SELECT article_id
                        FROM article_keywords
                        WHERE keyword_id IN (
                            SELECT id
                            FROM keywords
                            WHERE keyword_text LIKE ?
                        )
                    )
                    OR a.title LIKE ?
                    OR a.summary LIKE ?
                    OR a.raw_content LIKE ?
                )
            """
            where_clauses.append(keyword_clause)

            keyword_pattern = f"%{keyword}%"
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern, keyword_pattern])

        if where_clauses:
            count_query += " WHERE " + " AND ".join(where_clauses)

        cursor = db.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        total_pages = (total_count + per_page - 1) // per_page

        return render_template(
            'index.html',
            articles=articles,
            feeds=feeds,
            current_page=page,
            total_pages=total_pages,
            selected_feed_id=feed_id,
            selected_keyword=keyword,
            sort_by=sort_by,
            per_page=per_page,
            is_mobile=is_mobile
        )
    except Exception as e:
        logger.error(f"Error in index route: {e}")
        flash(f"An error occurred: {str(e)}", "error")
        return render_template('index.html',
                              articles=[], feeds=[], current_page=1, total_pages=1, sort_by='date_desc')

@app.route('/article/<int:article_id>')
def article(article_id):
    """Article detail page."""
    try:
        article = db.get_article_by_id(article_id)
        if not article:
            flash('Article not found', 'error')
            return redirect(url_for('index'))

        # Parse keywords string if it exists
        keywords = []
        if article.get('keywords'):
            keywords = [k.strip() for k in article['keywords'].split(',')]

        return render_template('article.html', article=article, keywords=keywords)
    except Exception as e:
        logger.error(f"Error in article route: {e}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/search')
def search():
    """Search articles."""
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))

    try:
        page = request.args.get('page', 1, type=int)

        # Get per_page from query parameter or default to 20
        per_page = request.args.get('per_page', 20, type=int)
        # Validate per_page to avoid unreasonable values
        per_page = min(max(per_page, 5), 100)  # Between 5 and 100

        offset = (page - 1) * per_page

        # Search articles
        results = db.search_articles(query, limit=per_page, offset=offset)

        # Count total results for pagination
        # Use same query structure for consistency
        count_query = """
            SELECT COUNT(*) FROM (
                SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?
                UNION
                SELECT id FROM articles WHERE title LIKE ? OR summary LIKE ? OR raw_content LIKE ?
                UNION
                SELECT article_id FROM article_keywords
                JOIN keywords ON article_keywords.keyword_id = keywords.id
                WHERE keyword_text LIKE ?
            )
        """
        pattern = f"%{query}%"
        cursor = db.execute(count_query, (query, pattern, pattern, pattern, pattern))
        total_count = cursor.fetchone()[0]
        total_pages = (total_count + per_page - 1) // per_page

        return render_template(
            'search.html',
            query=query,
            results=results,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page
        )
    except Exception as e:
        logger.error(f"Error in search route: {e}")
        flash(f"An error occurred during search: {str(e)}", "error")
        return redirect(url_for('index'))

# Helper function for date formatting (moved to top-level)
def format_date(date_str):
    """Format ISO date string to readable format."""
    if not date_str:
        return "N/A"
    try:
        # Handle potential timezone 'Z' by replacing it for ISO parsing
        if isinstance(date_str, str) and date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(date_str)
        return dt.strftime('%B %d, %Y %H:%M')
    except Exception:
        return str(date_str) # Return original if parsing fails

@app.route('/api/article/<int:article_id>')
def api_article(article_id):
    """API endpoint to get article data with ArXiv information."""
    try:
        # Updated query to include new fields
        cursor = db.execute(
            """SELECT a.*, f.name as feed_name,
                      GROUP_CONCAT(k.keyword_text) as keywords
               FROM articles a
               JOIN feeds f ON a.feed_id = f.id
               LEFT JOIN article_keywords ak ON a.id = ak.article_id
               LEFT JOIN keywords k ON ak.keyword_id = k.id
               WHERE a.id = ?
               GROUP BY a.id""",
            (article_id,)
        )

        article_data = cursor.fetchone()
        if not article_data:
            return jsonify({"error": "Article not found"}), 404

        # Convert to dictionary
        article_dict = dict(article_data)

        # Parse keywords string if it exists
        keywords = []
        if article_dict.get('keywords'):
            keywords = [k.strip() for k in article_dict['keywords'].split(',')]

        # Format dates for JSON
        date_fields = ['published_date', 'fetched_date', 'llm_processed_date',
                      'full_content_extracted_date', 'deep_summary_date']

        for field in date_fields:
            if article_dict.get(field):
                article_dict[f'{field}_formatted'] = format_date(article_dict[field])

        # Add ArXiv status information
        arxiv_info = {
            'is_arxiv': bool(article_dict.get('arxiv_id')),
            'arxiv_id': article_dict.get('arxiv_id'),
            'has_full_content': article_dict.get('full_content_status') == 'extracted',
            'full_content_status': article_dict.get('full_content_status', 'not_applicable'),
            'has_deep_summary': article_dict.get('deep_summary_status') == 'completed',
            'deep_summary_status': article_dict.get('deep_summary_status', 'not_requested'),
        }

        return jsonify({
            "article": article_dict,
            "keywords": keywords,
            "arxiv_info": arxiv_info
        })

    except Exception as e:
        logger.error(f"Error in API article route: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/feeds')
def feeds():
    """Feed management page."""
    try:
        all_feeds = db.get_feeds(enabled_only=False, include_article_counts=True)
        return render_template('feeds.html', feeds=all_feeds)
    except Exception as e:
        logger.error(f"Error in feeds route: {e}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/feeds/update-max-articles/<int:feed_id>', methods=['POST'])
def update_max_articles(feed_id):
    """Update max articles for a feed via AJAX."""
    try:
        max_articles = int(request.form.get('max_articles', 100))

        # Validate the input (allow up to 50,000 articles)
        if max_articles < 10 or max_articles > 50000:
            return jsonify({'success': False, 'error': 'Max articles must be between 10 and 50,000'}), 400

        # Update the feed
        if db.update_feed(feed_id=feed_id, max_articles=max_articles):
            return jsonify({'success': True, 'max_articles': max_articles})
        else:
            return jsonify({'success': False, 'error': 'Feed not found or no changes made'}), 404
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid number format'}), 400
    except Exception as e:
        logger.error(f"Error updating max articles: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/feeds/add', methods=['POST'])
def add_feed():
    """Add a new feed."""
    url = request.form.get('url', '').strip()
    name = request.form.get('name', '').strip()

    if not url:
        flash('Feed URL is required', 'error')
        return redirect(url_for('feeds'))

    try:
        if not name:
            # Extract domain as name if not provided
            try:
                from urllib.parse import urlparse
                parsed_url = urlparse(url)
                name = parsed_url.netloc
            except:
                name = url

        # Add feed to database
        feed_id = db.add_feed(url, name)

        if feed_id:
            flash(f'Feed "{name}" added successfully', 'success')
        else:
            flash('Feed already exists or could not be added', 'error')
    except Exception as e:
        logger.error(f"Error adding feed: {e}")
        flash(f"An error occurred: {str(e)}", "error")

    return redirect(url_for('feeds'))

@app.route('/feeds/edit/<int:feed_id>', methods=['GET', 'POST'])
def edit_feed(feed_id):
    """Edit a feed."""
    try:
        # Get the feed
        feed = db.get_feed_by_id(feed_id)

        if not feed:
            flash('Feed not found', 'error')
            return redirect(url_for('feeds'))

        if request.method == 'POST':
            # Update feed details
            name = request.form.get('name', '').strip()
            url = request.form.get('url', '').strip()
            is_enabled = request.form.get('is_enabled') == 'on'
            polling_interval = int(request.form.get('polling_interval', 30))
            max_articles = int(request.form.get('max_articles', 100))

            # Validate inputs
            if polling_interval < 5 or polling_interval > 1440:
                flash('Polling interval must be between 5 and 1440 minutes', 'error')
                return render_template('edit_feed.html', feed=feed)

            if max_articles < 10 or max_articles > 50000:
                flash('Maximum articles must be between 10 and 50,000', 'error')
                return render_template('edit_feed.html', feed=feed)

            if db.update_feed(
                feed_id=feed_id,
                name=name,
                url=url,
                is_enabled=is_enabled,
                polling_interval=polling_interval,
                max_articles=max_articles
            ):
                flash('Feed updated successfully', 'success')
            else:
                flash('No changes made to feed', 'info')

            return redirect(url_for('feeds'))

        return render_template('edit_feed.html', feed=feed)
    except Exception as e:
        logger.error(f"Error editing feed: {e}")
        flash(f'Error editing feed: {str(e)}', 'error')
        return redirect(url_for('feeds'))

@app.route('/feeds/delete/<int:feed_id>', methods=['POST'])
def delete_feed(feed_id):
    """Delete a feed and all its articles."""
    try:
        if db.delete_feed(feed_id):
            flash('Feed and all its articles deleted successfully', 'success')
        else:
            flash('Error deleting feed', 'error')
    except Exception as e:
        logger.error(f"Error deleting feed: {e}")
        flash(f'Error deleting feed: {str(e)}', 'error')

    return redirect(url_for('feeds'))

@app.route('/article/delete/<int:article_id>', methods=['POST'])
def delete_article(article_id):
    """Delete a specific article."""
    try:
        if db.delete_article(article_id):
            flash('Article deleted successfully', 'success')
        else:
            flash('Error deleting article', 'error')
    except Exception as e:
        logger.error(f"Error deleting article: {e}")
        flash(f'Error deleting article: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/feeds/toggle/<int:feed_id>', methods=['POST'])
def toggle_feed_status(feed_id):
    """Toggle feed enabled/disabled status."""
    try:
        if db.toggle_feed(feed_id):
            flash('Feed status toggled successfully', 'success')
        else:
            flash('Error toggling feed status', 'error')
    except Exception as e:
        logger.error(f"Error toggling feed: {e}")
        flash(f'Error toggling feed: {str(e)}', 'error')

    return redirect(url_for('feeds'))

@app.route('/feeds/export', methods=['GET'])
def export_feeds():
    """Export feeds to JSON."""
    try:
        feeds_json = db.export_feeds_to_json()

        # Convert to JSON and create a response
        response = app.response_class(
            response=json.dumps(feeds_json, indent=2),
            status=200,
            mimetype='application/json'
        )

        # Set headers for file download
        response.headers["Content-Disposition"] = "attachment; filename=feeds_export.json"

        return response
    except Exception as e:
        logger.error(f"Error exporting feeds: {e}")
        flash(f'Error exporting feeds: {str(e)}', 'error')
        return redirect(url_for('feeds'))

@app.route('/feeds/import', methods=['GET', 'POST'])
def import_feeds():
    """Import feeds from JSON."""
    if request.method == 'POST':
        try:
            # Check if file was uploaded
            if 'file' not in request.files:
                flash('No file part', 'error')
                return redirect(request.url)

            file = request.files['file']

            # Check if file was selected
            if file.filename == '':
                flash('No selected file', 'error')
                return redirect(request.url)

            # Check file type
            if not file.filename.endswith('.json'):
                flash('Only JSON files are allowed', 'error')
                return redirect(request.url)

            # Read and parse the file
            try:
                json_data = json.load(file)
            except json.JSONDecodeError:
                flash('Invalid JSON file', 'error')
                return redirect(request.url)

            # Get overwrite option
            overwrite = request.form.get('overwrite') == 'on'

            # Import feeds
            result = db.import_feeds_from_json(json_data, overwrite)

            # Show results
            flash(f"Import complete: {result['added']} added, {result['updated']} updated, "
                  f"{result['skipped']} skipped, {result['errors']} errors", 'success')

            return redirect(url_for('feeds'))
        except Exception as e:
            logger.error(f"Error importing feeds: {e}")
            flash(f'Error importing feeds: {str(e)}', 'error')
            return redirect(url_for('feeds'))

    return render_template('import_feeds.html')

@app.route('/poll-now', methods=['POST'])
def poll_now():
    """Manually trigger feed polling."""
    try:
        # Schedule polling in the event loop
        loop.call_soon_threadsafe(lambda: loop.create_task(feed_reader.poll_all_feeds()))
        flash('Feed polling started', 'success')
    except Exception as e:
        logger.error(f"Error starting manual polling: {e}")
        flash(f'Error starting polling: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/process-pending', methods=['POST'])
def process_pending():
    """Manually process pending articles with LLM."""
    try:
        # Schedule LLM processing
        loop.call_soon_threadsafe(lambda: loop.create_task(llm_processor.start_processing()))
        flash('LLM processing started', 'success')
    except Exception as e:
        logger.error(f"Error starting LLM processing: {e}")
        flash(f'Error starting LLM processing: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/extract-arxiv', methods=['POST'])
def extract_arxiv():
    """Manually trigger ArXiv content extraction."""
    try:
        # Get batch size and continuous mode from form
        batch_size = request.form.get('batch_size', '100')
        continuous = request.form.get('continuous') == 'true'

        # Convert batch size to integer with fallback
        try:
            batch_size = int(batch_size)
        except ValueError:
            batch_size = 100

        # Limit batch size to reasonable values
        batch_size = max(10, min(batch_size, 1000))

        # Start extraction with parameters
        loop.call_soon_threadsafe(
            lambda: loop.create_task(
                arxiv_extractor.start_extraction(batch_size=batch_size, continuous=continuous)
            )
        )

        if continuous:
            flash(f'ArXiv content extraction started in continuous mode with batch size {batch_size}', 'success')
        else:
            flash(f'ArXiv content extraction started for up to {batch_size} articles', 'success')

    except Exception as e:
        logger.error(f"Error starting ArXiv extraction: {e}")
        flash(f'Error starting ArXiv extraction: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/admin/clean-keywords', methods=['POST'])
def clean_keywords():
    """Clean up orphaned keywords."""
    try:
        count = db.clean_orphaned_keywords()
        flash(f'Successfully cleaned {count} orphaned keywords', 'success')
    except Exception as e:
        logger.error(f"Error cleaning keywords: {e}")
        flash(f'Error cleaning keywords: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Gracefully shut down the application."""
    # Call the shutdown handler
    shutdown_handler(signal.SIGTERM, None)
    return "Server shutting down..."

@app.route('/favorites')
def favorites():
    """Favorites page with side-panel interface."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(max(per_page, 5), 100)

    offset = (page - 1) * per_page
    tag_filter = request.args.get('tag_filter', None)
    sort_by = request.args.get('sort_by', 'date_desc')

    # Check if request is from mobile
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent

    try:
        favorites = db.get_favorites(limit=per_page, offset=offset, tag_filter=tag_filter, sort_by=sort_by)
        all_tags = db.get_favorite_tags()

        # Get total count for pagination
        total_count = db.get_favorites_count(tag_filter=tag_filter)
        total_pages = (total_count + per_page - 1) // per_page

        return render_template(
            'favorites.html',
            favorites=favorites,
            all_tags=all_tags,
            current_page=page,
            total_pages=total_pages,
            selected_tag=tag_filter,
            sort_by=sort_by,
            per_page=per_page,
            is_mobile=is_mobile,
            total_count=total_count
        )
    except Exception as e:
        logger.error(f"Error in favorites route: {e}")
        flash(f"An error occurred: {str(e)}", "error")
        return render_template('favorites.html',
                              favorites=[], all_tags=[], current_page=1, total_pages=1,
                              sort_by='date_desc', total_count=0)

@app.route('/api/favorite/<int:article_id>', methods=['POST'])
def api_add_favorite(article_id):
    """Add article to favorites via AJAX."""
    try:
        data = request.get_json() or {}
        notes = data.get('notes', '').strip()
        tags = data.get('tags', '').strip()

        success = db.add_favorite(article_id, notes, tags)

        if success:
            return jsonify({'success': True, 'message': 'Article added to favorites'})
        else:
            return jsonify({'success': False, 'error': 'Failed to add to favorites'}), 500
    except Exception as e:
        logger.error(f"Error adding favorite: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorite/<int:article_id>', methods=['DELETE'])
def api_remove_favorite(article_id):
    """Remove article from favorites via AJAX."""
    try:
        success = db.remove_favorite(article_id)

        if success:
            return jsonify({'success': True, 'message': 'Article removed from favorites'})
        else:
            return jsonify({'success': False, 'error': 'Article not in favorites'}), 404
    except Exception as e:
        logger.error(f"Error removing favorite: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorite/<int:article_id>', methods=['PUT'])
def api_update_favorite(article_id):
    """Update favorite notes and tags via AJAX."""
    try:
        data = request.get_json() or {}
        notes = data.get('notes', '').strip()
        tags = data.get('tags', '').strip()

        success = db.update_favorite(article_id, notes, tags)

        if success:
            return jsonify({'success': True, 'message': 'Favorite updated'})
        else:
            return jsonify({'success': False, 'error': 'Favorite not found'}), 404
    except Exception as e:
        logger.error(f"Error updating favorite: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorite/<int:article_id>/status')
def api_favorite_status(article_id):
    """Get favorite status for an article."""
    try:
        is_fav = db.is_favorite(article_id)

        if is_fav:
            # Get favorite details
            cursor = db.execute(
                "SELECT notes, tags, added_date FROM favorites WHERE article_id = ?",
                (article_id,)
            )
            result = cursor.fetchone()

            return jsonify({
                'is_favorite': True,
                'notes': result[0] if result else '',
                'tags': result[1] if result else '',
                'added_date': result[2] if result else ''
            })
        else:
            return jsonify({'is_favorite': False})
    except Exception as e:
        logger.error(f"Error getting favorite status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/favorites/tags')
def api_favorite_tags():
    """Get all favorite tags for autocomplete."""
    try:
        tags = db.get_favorite_tags()
        return jsonify({'tags': tags})
    except Exception as e:
        logger.error(f"Error getting favorite tags: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/arxiv-feed-breakdown')
def api_arxiv_feed_breakdown():
    """Get ArXiv article breakdown by feed."""
    try:
        breakdown = db.get_feed_arxiv_breakdown()
        return jsonify(breakdown)
    except Exception as e:
        logger.error(f"Error getting ArXiv feed breakdown: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/arxiv-stats')
def api_arxiv_stats():
    """Get ArXiv processing statistics."""
    try:
        stats = db.get_arxiv_statistics()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting ArXiv stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/arxiv-processing-status')
def api_arxiv_processing_status():
    """Get current ArXiv processing status."""
    try:
        # Get pending extraction count
        cursor = db.execute(
            """SELECT COUNT(*) FROM articles
               WHERE arxiv_id IS NOT NULL
               AND full_content_status = 'pending'"""
        )
        pending_extraction = cursor.fetchone()[0]

        # Get currently processing count (estimate based on recent activity)
        cursor = db.execute(
            """SELECT COUNT(*) FROM articles
               WHERE full_content_extracted_date > datetime('now', '-5 minutes')
               OR deep_summary_date > datetime('now', '-5 minutes')"""
        )
        currently_processing = cursor.fetchone()[0]

        return jsonify({
            'pending_extraction': pending_extraction,
            'currently_processing': currently_processing
        })
    except Exception as e:
        logger.error(f"Error getting ArXiv processing status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/article/<int:article_id>/request-deep-summary', methods=['POST'])
def api_request_deep_summary(article_id):
    """Request deep summary generation for an article."""
    try:
        # Check if article has full content
        cursor = db.execute(
            "SELECT full_content_status, deep_summary_status FROM articles WHERE id = ?",
            (article_id,)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({'success': False, 'error': 'Article not found'}), 404

        full_content_status, deep_summary_status = result

        if full_content_status != 'extracted':
            return jsonify({'success': False, 'error': 'Article does not have full content extracted'}), 400

        if deep_summary_status == 'pending':
            return jsonify({'success': False, 'error': 'Deep summary already pending'}), 400

        # Request deep summary
        success = db.request_deep_summary(article_id)

        if success:
            # Trigger processing
            loop.call_soon_threadsafe(
                lambda: loop.create_task(
                    llm_processor.generate_deep_summary_for_article(article_id)
                )
            )
            return jsonify({'success': True, 'message': 'Deep summary requested'})
        else:
            return jsonify({'success': False, 'error': 'Failed to request deep summary'}), 500

    except Exception as e:
        logger.error(f"Error requesting deep summary: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/article/<int:article_id>/extract-arxiv', methods=['POST'])
def api_extract_arxiv_content(article_id):
    """Manually extract ArXiv content for a specific article."""
    try:
        # Get the article
        cursor = db.execute(
            "SELECT id, title, link, guid FROM articles WHERE id = ?",
            (article_id,)
        )
        article = cursor.fetchone()

        if not article:
            return jsonify({'success': False, 'error': 'Article not found'}), 404

        # Check if it's an ArXiv article
        link = article[2] or ''
        guid = article[3] or ''

        if 'arxiv.org' not in link.lower() and 'arxiv.org' not in guid.lower():
            return jsonify({'success': False, 'error': 'Not an ArXiv article'}), 400

        # Trigger extraction for this specific article
        article_dict = {
            'id': article[0],
            'title': article[1],
            'link': article[2],
            'guid': article[3]
        }

        loop.call_soon_threadsafe(
            lambda: loop.create_task(
                arxiv_extractor.process_article(article_dict)
            )
        )

        return jsonify({'success': True, 'message': 'ArXiv extraction started'})

    except Exception as e:
        logger.error(f"Error extracting ArXiv content: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.context_processor
def utility_processor():
    """Add utility functions to template context."""
    # Add current year for copyright footer
    now = datetime.now()

    return dict(format_date=format_date, now=now)

if __name__ == '__main__':
    logger.info("Starting AI/ML News Aggregator")
    app.run(debug=True, use_reloader=False)  # use_reloader=False to avoid duplicate background tasks