# arxiv_extractor.py - Clean version with bulk processing

import asyncio
import aiohttp
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ArXivExtractor:
    def __init__(self, database, config):
        """Initialize ArXiv extractor with database and config."""
        self.db = database
        self.config = config
        self.session = None
        self.base_url = "http://export.arxiv.org/api/query"
        
    async def start_extraction(self, batch_size=100, continuous=False):
        """Start extracting ArXiv content for applicable articles."""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        if continuous:
            return await self.start_bulk_extraction(batch_size)
        else:
            return await self.start_single_batch(batch_size)
    
    async def start_single_batch(self, batch_size=100):
        """Process a single batch of ArXiv articles."""
        try:
            articles = self.db.get_articles_for_arxiv_extraction(limit=batch_size)
            
            if not articles:
                logger.info("No articles found for ArXiv extraction")
                return 0
            
            logger.info(f"Processing {len(articles)} articles for ArXiv content (batch size: {batch_size})")
            
            processed = 0
            for article in articles:
                try:
                    await self.process_article(article)
                    processed += 1
                    # Configurable delay
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error processing article {article['id']}: {e}")
            
            logger.info(f"Completed batch processing: {processed} articles processed")
            return processed
                    
        except Exception as e:
            logger.error(f"Error in ArXiv extraction: {e}")
            return 0

    async def start_bulk_extraction(self, batch_size=100, delay_between_articles=0.3, delay_between_batches=2):
        """Process ALL pending ArXiv articles until complete."""
        if not self.session or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        total_processed = 0
        batch_count = 0
        
        try:
            logger.info(f"Starting bulk ArXiv extraction with batch_size={batch_size}, delays={delay_between_articles}s/{delay_between_batches}s")
            
            while True:
                batch_count += 1
                
                # Get next batch
                articles = self.db.get_articles_for_arxiv_extraction(limit=batch_size)
                
                if not articles:
                    logger.info(f"Bulk ArXiv extraction complete! Processed {total_processed} total articles in {batch_count-1} batches")
                    break
                
                logger.info(f"Processing batch #{batch_count} of {len(articles)} articles (total processed so far: {total_processed})")
                
                # Process this batch
                batch_processed = 0
                for article in articles:
                    try:
                        await self.process_article(article)
                        total_processed += 1
                        batch_processed += 1
                        
                        # Log progress every 50 articles
                        if total_processed % 50 == 0:
                            logger.info(f"Progress: {total_processed} articles processed")
                        
                        # Configurable delay between articles
                        await asyncio.sleep(delay_between_articles)
                    except Exception as e:
                        logger.error(f"Error processing article {article['id']}: {e}")
                
                logger.info(f"Batch #{batch_count} complete: {batch_processed} articles processed")
                
                # Brief pause between batches to be respectful
                if batch_processed > 0:  # Only pause if we actually processed something
                    await asyncio.sleep(delay_between_batches)
                    
        except Exception as e:
            logger.error(f"Error in bulk ArXiv extraction after {total_processed} articles: {e}")
            
        return total_processed
    
    async def process_article(self, article):
        """Process a single article for ArXiv content."""
        article_id = article['id']
        link = article.get('link', '')
        guid = article.get('guid', '')
        
        # Extract ArXiv ID from URL or GUID
        arxiv_id = self.extract_arxiv_id(link) or self.extract_arxiv_id(guid)
        
        if not arxiv_id:
            # Not an ArXiv article, mark as not applicable
            self.db.update_article_arxiv_status(article_id, status='not_applicable')
            return
        
        logger.info(f"Found ArXiv ID {arxiv_id} for article {article_id}")
        
        # Update with ArXiv ID and pending status
        self.db.update_article_arxiv_status(article_id, arxiv_id=arxiv_id, status='pending')
        
        try:
            # Fetch full content from ArXiv HTML or API
            full_content = await self.fetch_arxiv_content(arxiv_id)
            
            if full_content:
                # Update article with full content
                self.db.update_article_full_content(article_id, full_content, status='extracted')
                logger.info(f"Successfully extracted ArXiv content for article {article_id}")
            else:
                self.db.update_article_arxiv_status(article_id, arxiv_id=arxiv_id, status='failed')
                logger.warning(f"Failed to extract ArXiv content for article {article_id}")
                
        except Exception as e:
            logger.error(f"Error fetching ArXiv content for {arxiv_id}: {e}")
            self.db.update_article_arxiv_status(article_id, arxiv_id=arxiv_id, status='failed')
    
    def extract_arxiv_id(self, url):
        """Extract ArXiv ID from URL or GUID."""
        if not url:
            return None
            
        patterns = [
            # Standard ArXiv URLs
            r'arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)',
            r'arxiv\.org/abs/([a-z-]+/[0-9]{7}v?[0-9]*)',
            r'arxiv\.org/pdf/([0-9]{4}\.[0-9]{4,5})',
            r'arxiv\.org/pdf/([a-z-]+/[0-9]{7})',
            
            # OAI GUID format (like oai:arXiv.org:2502.13767v3)
            r'oai:arXiv\.org:([0-9]{4}\.[0-9]{4,5}v?[0-9]*)',
            r'oai:arXiv\.org:([a-z-]+/[0-9]{7}v?[0-9]*)',
            
            # Case variations
            r'arXiv\.org/abs/([0-9]{4}\.[0-9]{4,5}v?[0-9]*)',
            r'arXiv\.org/abs/([a-z-]+/[0-9]{7}v?[0-9]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                arxiv_id = match.group(1)
                # Remove version number if present
                arxiv_id = re.sub(r'v[0-9]+$', '', arxiv_id)
                return arxiv_id
        
        return None
    
    async def fetch_arxiv_content(self, arxiv_id):
        """Fetch full content from ArXiv HTML or API fallback."""
        try:
            # First try to get full HTML content (for papers after Dec 2023)
            html_content = await self.fetch_arxiv_html(arxiv_id)
            if html_content:
                logger.info(f"Successfully fetched HTML content for {arxiv_id}")
                return html_content
            
            # Fallback to API for metadata (older papers or failed HTML)
            logger.info(f"HTML not available for {arxiv_id}, falling back to API")
            return await self.fetch_arxiv_api(arxiv_id)
                
        except Exception as e:
            logger.error(f"Error fetching ArXiv content for {arxiv_id}: {e}")
            return None
    
    async def fetch_arxiv_html(self, arxiv_id):
        """Fetch full paper content from ArXiv HTML format."""
        try:
            # Construct HTML URL
            html_url = f"https://arxiv.org/html/{arxiv_id}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            async with self.session.get(html_url, headers=headers) as response:
                if response.status == 404:
                    logger.info(f"HTML not available for {arxiv_id} (404)")
                    return None
                elif response.status != 200:
                    logger.warning(f"HTML fetch failed for {arxiv_id}, status: {response.status}")
                    return None
                
                html_content = await response.text()
                
                # Parse HTML content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extract paper content
                return self.extract_content_from_html(soup, arxiv_id)
                
        except Exception as e:
            logger.error(f"Error fetching HTML for {arxiv_id}: {e}")
            return None
    
    def extract_content_from_html(self, soup, arxiv_id):
        """Extract and format content from ArXiv HTML."""
        try:
            content_parts = []
            
            # Try to find the main content area
            main_content = soup.find('main') or soup.find('article') or soup.find('body')
            
            if not main_content:
                logger.warning(f"Could not find main content area for {arxiv_id}")
                return None
            
            # Remove unwanted elements
            for element in main_content.find_all(['nav', 'header', 'footer', 'aside', 'script', 'style']):
                element.decompose()
            
            # Extract title
            title_elem = main_content.find('h1') or soup.find('title')
            if title_elem:
                title = title_elem.get_text().strip()
                content_parts.append(f"Title: {title}")
            
            # Add ArXiv metadata
            content_parts.append(f"ArXiv ID: {arxiv_id}")
            content_parts.append(f"ArXiv URL: https://arxiv.org/abs/{arxiv_id}")
            content_parts.append(f"HTML URL: https://arxiv.org/html/{arxiv_id}")
            
            # Extract all paragraph text
            paragraphs = main_content.find_all('p')
            if paragraphs:
                paper_text = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if text and len(text) > 20:
                        paper_text.append(text)
                
                if paper_text:
                    content_parts.append(f"\nFull Text:\n" + '\n\n'.join(paper_text))
            
            full_content = '\n'.join(content_parts)
            
            # Validate we got substantial content
            if len(full_content) < 500:
                logger.warning(f"HTML content too short for {arxiv_id}: {len(full_content)} chars")
                return None
            
            logger.info(f"Extracted {len(full_content)} characters from HTML for {arxiv_id}")
            return full_content
            
        except Exception as e:
            logger.error(f"Error extracting HTML content for {arxiv_id}: {e}")
            return None
    
    async def fetch_arxiv_api(self, arxiv_id):
        """Fetch content from ArXiv API (fallback method)."""
        try:
            # Construct API URL
            url = f"{self.base_url}?id_list={quote(arxiv_id)}&max_results=1"
            
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"ArXiv API returned status {response.status} for {arxiv_id}")
                    return None
                
                xml_content = await response.text()
                
                # Parse XML response
                root = ET.fromstring(xml_content)
                
                # Find the entry
                namespace = {'atom': 'http://www.w3.org/2005/Atom'}
                entries = root.findall('atom:entry', namespace)
                
                if not entries:
                    logger.warning(f"No entry found for ArXiv ID {arxiv_id}")
                    return None
                
                entry = entries[0]
                
                # Extract information
                title = self.get_text_from_element(entry.find('atom:title', namespace))
                summary = self.get_text_from_element(entry.find('atom:summary', namespace))
                
                # Get authors
                authors = []
                for author in entry.findall('atom:author', namespace):
                    name = self.get_text_from_element(author.find('atom:name', namespace))
                    if name:
                        authors.append(name)
                
                # Construct content (API fallback version)
                content_parts = []
                
                if title:
                    content_parts.append(f"Title: {title}")
                
                if authors:
                    content_parts.append(f"Authors: {', '.join(authors)}")
                
                content_parts.append(f"ArXiv ID: {arxiv_id}")
                content_parts.append(f"ArXiv URL: https://arxiv.org/abs/{arxiv_id}")
                
                if summary:
                    content_parts.append(f"\nAbstract:\n{summary}")
                
                return '\n'.join(content_parts)
                
        except Exception as e:
            logger.error(f"Error fetching ArXiv API content for {arxiv_id}: {e}")
            return None
    
    def get_text_from_element(self, element):
        """Safely extract text from XML element."""
        if element is not None:
            return element.text.strip() if element.text else ''
        return ''
    
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("ArXiv extractor session closed")