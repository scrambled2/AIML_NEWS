import feedparser
import asyncio
import aiohttp
import time
import logging
import random
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# List of common user agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
]

class FeedReader:
    def __init__(self, database, config):
        """Initialize feed reader with database and config objects."""
        self.db = database
        self.config = config
        self.polling = False
        self.session = None
        self.retry_delays = [1, 2, 5, 10, 30]  # Seconds to wait between retries
    async def start_polling(self):
        """Start polling feeds at their configured intervals."""
        if self.polling:
            logger.warning("Feed polling already in progress")
            return
        
        self.polling = True
        self.feed_tasks = {}  # Track polling tasks by feed_id
        
        try:
            # Initial poll of all feeds
            await self.poll_all_feeds()
            
            # Then set up individual polling tasks for each feed
            feeds = self.db.get_feeds(enabled_only=True)
            for feed in feeds:
                self._schedule_feed_polling(feed)
            
            # Keep the polling loop alive
            while self.polling:
                await asyncio.sleep(10)  # Just a heartbeat check
                
        except asyncio.CancelledError:
            logger.info("Feed polling task cancelled")
            self.polling = False
        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            self.polling = False
            raise
    
    def _schedule_feed_polling(self, feed):
        """Schedule a feed to be polled at its configured interval."""
        feed_id = feed['id']
        interval = feed.get('polling_interval', 30)  # Default to 30 minutes
        
        # Cancel existing task if there is one
        if feed_id in self.feed_tasks and not self.feed_tasks[feed_id].done():
            self.feed_tasks[feed_id].cancel()
        
        # Create new polling task
        self.feed_tasks[feed_id] = asyncio.create_task(self._poll_feed_periodically(feed, interval))
        logger.info(f"Scheduled feed '{feed['name']}' to poll every {interval} minutes")
    
    async def _poll_feed_periodically(self, feed, interval_minutes):
        """Poll a feed periodically at the specified interval."""
        feed_id = feed['id']
        feed_name = feed['name']
        
        try:
            while self.polling:
                # Poll the feed
                await self.poll_feed(feed)
                
                # Wait for the configured interval
                logger.info(f"Feed '{feed_name}' next poll in {interval_minutes} minutes")
                await asyncio.sleep(interval_minutes * 60)
                
                # Get the latest feed config in case interval was changed
                try:
                    updated_feed = self.db.get_feed_by_id(feed_id)
                    if updated_feed and updated_feed.get('is_enabled', True):
                        # Update the interval if it changed
                        new_interval = updated_feed.get('polling_interval', 30)
                        if new_interval != interval_minutes:
                            logger.info(f"Feed '{feed_name}' polling interval changed: {interval_minutes} -> {new_interval} minutes")
                            interval_minutes = new_interval
                    else:
                        # Feed was disabled or deleted, stop polling
                        logger.info(f"Feed '{feed_name}' was disabled or deleted, stopping polling")
                        break
                except Exception as e:
                    logger.error(f"Error getting updated feed config for '{feed_name}': {e}")
        
        except asyncio.CancelledError:
            logger.info(f"Feed polling task for '{feed_name}' cancelled")
        except Exception as e:
            logger.error(f"Error in periodic polling for feed '{feed_name}': {e}")
            # Reschedule with backoff
            backoff_minutes = min(interval_minutes * 2, 120)  # Max 2 hours backoff
            logger.info(f"Rescheduling feed '{feed_name}' with backoff: {backoff_minutes} minutes")
            if self.polling:
                # Create a new task with backoff
                self.feed_tasks[feed_id] = asyncio.create_task(self._poll_feed_periodically(feed, backoff_minutes))
    
    def stop_polling(self):
        """Stop the polling loop and cancel all feed polling tasks."""
        self.polling = False
        
        # Cancel all feed polling tasks
        for feed_id, task in self.feed_tasks.items():
            if not task.done():
                task.cancel()
        
        self.feed_tasks = {}
        logger.info("Feed polling stopped")
    
    async def poll_all_feeds(self):
        """Poll all enabled feeds for new content."""
        try:
            feeds = self.db.get_feeds(enabled_only=True)
            if not feeds:
                logger.info("No enabled feeds found")
                return
            
            # Create shared session for all requests
            if self.session is None or self.session.closed:
                timeout = aiohttp.ClientTimeout(total=60)  # 60 seconds timeout
                self.session = aiohttp.ClientSession(timeout=timeout)
            
            # Process feeds concurrently with a limit
            max_concurrent = self.config.get('max_concurrent_feeds', 5)
            tasks = []
            
            for feed in feeds:
                if len(tasks) >= max_concurrent:
                    # Wait for some tasks to complete before adding more
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(pending)  # Convert set back to list
                    # Handle any exceptions
                    for task in done:
                        try:
                            await task
                        except Exception as e:
                            logger.error(f"Feed polling task error: {e}")
                
                # Add new task
                task = asyncio.create_task(self.poll_feed(feed))
                tasks.append(task)
            
            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error in poll_all_feeds: {e}")
            raise
    
    async def poll_feed(self, feed):
        """Poll a single feed for new items."""
        feed_id = feed['id']
        feed_url = feed['url']
        feed_name = feed['name']
        last_guid = feed['last_polled_item_guid']
        
        logger.info(f"Polling feed: {feed_name} ({feed_url})")
        
        try:
            # Parse the feed
            feed_data = await self._fetch_and_parse_feed_with_retry(feed_url)
            
            if not feed_data or not feed_data.entries:
                logger.warning(f"No entries found for feed: {feed_name}")
                self.db.increment_feed_error(feed_id)
                return
            
            # Process entries (newest first)
            entries = sorted(feed_data.entries, key=lambda e: self._get_published_date(e), reverse=True)
            new_items_count = 0
            latest_guid = None
            
            for entry in entries:
                guid = entry.get('id', entry.get('link', ''))
                
                # Stop if we've reached the last processed item
                if guid == last_guid:
                    break
                
                # Set the latest guid on first iteration
                if latest_guid is None:
                    latest_guid = guid
                
                # Process the new entry
                await self._process_entry(feed_id, entry)
                new_items_count += 1
                
                # Add a small delay between processing entries to be nice to servers
                await asyncio.sleep(0.5)
            
            # Update feed status with latest guid
            if latest_guid:
                self.db.update_feed_poll_status(feed_id, latest_guid)
            
            logger.info(f"Processed {new_items_count} new items from feed: {feed_name}")
            
        except Exception as e:
            logger.error(f"Error polling feed {feed_name}: {e}")
            self.db.increment_feed_error(feed_id)
    
    async def _fetch_and_parse_feed_with_retry(self, feed_url):
        """Fetch and parse a feed from its URL with retries."""
        for attempt, delay in enumerate(self.retry_delays):
            try:
                return await self._fetch_and_parse_feed(feed_url)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {feed_url}: {e}")
                if attempt < len(self.retry_delays) - 1:
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed for {feed_url}")
                    raise
    
    async def _fetch_and_parse_feed(self, feed_url):
        """Fetch and parse a feed from its URL."""
        try:
            # Select a random user agent
            user_agent = random.choice(USER_AGENTS)
            
            headers = {
                'User-Agent': user_agent,
                'Accept': 'application/rss+xml, application/xml, text/xml, application/atom+xml, text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
                'TE': 'Trailers',
            }
            
            async with self.session.get(feed_url, headers=headers, allow_redirects=True) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch feed: {feed_url}, status: {response.status}")
                    return None
                
                content = await response.text()
                
                # Special handling for different feed types or platforms
                if 'openai.com' in feed_url and response.status == 403:
                    # Try alternative OpenAI feed URL
                    alternative_url = 'https://openai.com/news/rss.xml'
                    if feed_url != alternative_url:
                        logger.info(f"Trying alternative OpenAI feed URL: {alternative_url}")
                        return await self._fetch_and_parse_feed(alternative_url)
                
                # Parse with feedparser
                feed_data = feedparser.parse(content)
                
                if feed_data.bozo and feed_data.get('bozo_exception') is not None:
                    logger.warning(f"Feed parsing error for {feed_url}: {feed_data.bozo_exception}")
                    # Try to continue anyway if there are entries
                    if not feed_data.entries:
                        raise Exception(f"No entries found in feed with parsing error: {feed_data.bozo_exception}")
                
                return feed_data
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching feed: {feed_url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching feed {feed_url}: {e}")
            return None
    
    async def _process_entry(self, feed_id, entry):
        """Process a single feed entry."""
        guid = entry.get('id', entry.get('link', ''))
        link = entry.get('link', '')
        title = entry.get('title', 'No Title')
        published_date = self._get_published_date(entry)
        
        # Add basic article info to database
        article_id = self.db.add_article(
            feed_id=feed_id,
            guid=guid,
            link=link,
            title=title,
            published_date=published_date,
            status="pending_content"
        )
        
        if article_id is None:
            # Article already exists
            return
        
        # Extract content
        content = await self._extract_content_with_retry(entry, link)
        
        if content:
            # Update with content
            status = "pending_llm" if self.config.get('store_content_level') != 'none' else "processed"
            self.db.execute(
                "UPDATE articles SET raw_content = ?, processing_status = ? WHERE id = ?",
                (content, status, article_id)
            )
            logger.info(f"Updated article content for: {title}")
        else:
            # If we couldn't extract content, mark as error
            self.db.execute(
                "UPDATE articles SET processing_status = 'content_extraction_failed' WHERE id = ?",
                (article_id,)
            )
            logger.warning(f"Failed to extract content for: {title}")
    
    async def _extract_content_with_retry(self, entry, link):
        """Extract content with retries."""
        for attempt, delay in enumerate(self.retry_delays[:3]):  # Use fewer retries for content extraction
            try:
                content = await self._extract_content(entry, link)
                if content and len(content) > 200:  # Ensure we got meaningful content
                    return content
                # If content is too short, we'll retry with a different method
                logger.warning(f"Extracted content too short ({len(content) if content else 0} chars), retrying with different method")
            except Exception as e:
                logger.warning(f"Content extraction attempt {attempt + 1} failed for {link}: {e}")
            
            if attempt < 2:  # Don't sleep after the last attempt
                await asyncio.sleep(delay)
        
        # Fall back to just using the feed summary if we couldn't extract full content
        summary = entry.get('summary', '')
        if summary and len(summary) > 100:
            logger.info(f"Using feed summary as fallback for {link}")
            return summary
        
        return entry.get('content', [{}])[0].get('value', '')
    
    async def _extract_content(self, entry, link):
        """Extract content from a feed entry or its linked page."""
        # First try to get content from the feed itself
        content = entry.get('content', [{}])[0].get('value', '')
        if not content:
            content = entry.get('summary', '')
        
        # If content is too short, try to fetch the full article
        if len(content) < 500 and link:
            try:
                content = await self._fetch_article_content(link)
            except Exception as e:
                logger.error(f"Error fetching article content from {link}: {e}")
                # If we can't fetch the article, use what we have from the feed
        
        return content
    
    async def _fetch_article_content(self, url):
        """Fetch and extract the main content from an article URL."""
        try:
            # Select a random user agent for this request
            user_agent = random.choice(USER_AGENTS)
            
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0',
                'Referer': 'https://www.google.com/',  # Pretend we came from Google
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1',
                'TE': 'Trailers',
            }
            
            # Add some randomization to seem more human-like
            if random.random() > 0.5:
                headers['DNT'] = '1'
            
            # Parse domain for special handling
            domain = urlparse(url).netloc
            
            # Special handling for known problematic sites
            if 'machinelearningmastery.com' in domain:
                headers['Referer'] = 'https://machinelearningmastery.com/'
                # Add some cookies that might help
                headers['Cookie'] = 'wordpress_gdpr_allowed_services=a:1:{i:0;s:9:"wordpress";}; _ga=GA1.2.123456789.1620000000'
            elif 'openai.com' in domain:
                headers['Referer'] = 'https://openai.com/'
            
            await asyncio.sleep(random.uniform(1.0, 2.0))  # Random delay before request
            
            async with self.session.get(url, headers=headers, allow_redirects=True, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch article: {url}, status: {response.status}")
                    return ""
                
                html = await response.text()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove script, style, and navigation elements
                for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                    element.decompose()
                
                # Extract main content using multiple strategies
                main_content = self._extract_content_from_html(soup, url)
                
                # Clean up the text
                main_content = re.sub(r'\s+', ' ', main_content).strip()
                
                return main_content
                
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            return ""
    
    def _extract_content_from_html(self, soup, url):
        """Extract content using multiple strategies."""
        domain = urlparse(url).netloc
        
        # Strategy 1: Look for common content containers
        content_selectors = [
            'article', '.article', '.post', '.content', 'main', '#content', '#main',
            '.post-content', '.entry-content', '.article-content', '.post-body',
            '[itemprop="articleBody"]', '.blog-post', '.blog-content'
        ]
        
        # Add domain-specific selectors
        if 'machinelearningmastery.com' in domain:
            content_selectors.extend(['.entry', '.post-content', '.entry-content'])
        elif 'openai.com' in domain:
            content_selectors.extend(['.post-content', '.research-paper'])
        elif 'ai.googleblog.com' in domain:
            content_selectors.extend(['.post-body', '.post'])
        elif 'arxiv.org' in domain:
            content_selectors.extend(['#abs', '.abstract'])
        
        # Try all selectors
        for selector in content_selectors:
            content_candidates = soup.select(selector)
            if content_candidates:
                # Use the largest content container
                main_content = max(content_candidates, key=lambda x: len(x.get_text())).get_text()
                if len(main_content) > 200:  # Only use if it has substantial content
                    return main_content
        
        # Strategy 2: Look for largest <p> tag collection
        paragraphs = soup.find_all('p')
        if paragraphs:
            # Get text from all paragraphs
            p_text = ' '.join(p.get_text() for p in paragraphs)
            if len(p_text) > 200:
                return p_text
        
        # Strategy 3: Fall back to body text
        body_text = soup.body.get_text() if soup.body else ""
        
        # If body text is very large, try to extract only the middle portion
        if len(body_text) > 10000:
            start = len(body_text) // 4
            end = 3 * len(body_text) // 4
            return body_text[start:end]
        
        return body_text
    
    def _get_published_date(self, entry):
        """Extract and format the published date from a feed entry."""
        # Try different date fields
        for date_field in ['published_parsed', 'updated_parsed', 'created_parsed']:
            date_tuple = entry.get(date_field)
            if date_tuple:
                return time.strftime('%Y-%m-%dT%H:%M:%SZ', date_tuple)
        
        # If no parsed date found, try string fields
        for date_field in ['published', 'updated', 'created']:
            date_str = entry.get(date_field)
            if date_str:
                try:
                    # Try different date formats
                    for date_format in [
                        '%a, %d %b %Y %H:%M:%S %z',
                        '%a, %d %b %Y %H:%M:%S %Z',
                        '%Y-%m-%dT%H:%M:%SZ',
                        '%Y-%m-%dT%H:%M:%S%z',
                        '%Y-%m-%dT%H:%M:%S.%f%z',
                        '%Y-%m-%d %H:%M:%S',
                        '%d %b %Y %H:%M:%S %z',
                        '%d %b %Y'
                    ]:
                        try:
                            dt = datetime.strptime(date_str, date_format)
                            return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                        except ValueError:
                            continue
                except (ValueError, TypeError):
                    pass
        
        # Default to current time
        return datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("HTTP session closed")