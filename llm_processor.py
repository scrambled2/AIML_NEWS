import os
import json
import asyncio
import logging
import time
from datetime import datetime
import hashlib

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LLMProcessor:
    def __init__(self, database, config):
        """Initialize the LLM processor with database and config objects."""
        self.db = database
        self.config = config
        self.api_key = config.api_key
        self.model = config.get('openai_model', 'gpt-4o')
        self.summary_max_tokens = config.get('summary_max_tokens', 150)

        # Create cache directory
        self.cache_dir = os.path.join('instance', 'llm_cache')
        os.makedirs(self.cache_dir, exist_ok=True)

        # Initialize OpenAI client - with proper error handling
        # Import OpenAI here to handle import errors gracefully
        try:
            from openai import AsyncOpenAI

            if self.api_key:
                os.environ["OPENAI_API_KEY"] = self.api_key  # Set environment variable
                try:
                    self.client = AsyncOpenAI()  # Use environment variable for authentication
                    logger.info("OpenAI client initialized successfully")
                except Exception as e:
                    logger.error(f"Error initializing OpenAI client: {e}")
                    self.client = None
            else:
                logger.warning("No API key provided, LLM processing will be disabled")
                self.client = None

        except ImportError as e:
            logger.error(f"Failed to import OpenAI: {e}")
            logger.info("Try installing with: pip install openai>=1.0.0")
            self.client = None

        # Processing state
        self.processing = False

    async def start_processing(self):
        """Start processing articles that need LLM processing."""
        if not self.api_key or not self.client:
            logger.error("OpenAI API key not set or client initialization failed. LLM processing disabled.")
            return

        if self.processing:
            logger.warning("LLM processing already in progress")
            return

        self.processing = True

        try:
            while self.processing:
                # Process regular articles (existing functionality)
                cursor = self.db.execute(
                    "SELECT id, title, raw_content FROM articles WHERE processing_status = 'pending_llm' LIMIT 5"
                )
                regular_articles = cursor.fetchall()

                # Process deep summaries
                deep_summary_articles = self.db.get_articles_for_deep_summary(limit=5)

                if not regular_articles and not deep_summary_articles:
                    logger.info("No pending articles for LLM processing")
                    await asyncio.sleep(60)
                    continue

                # Process regular articles
                if regular_articles:
                    tasks = []
                    for article in regular_articles:
                        task = asyncio.create_task(self.process_article(article))
                        tasks.append(task)

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"Error in regular LLM processing: {result}")

                # Process deep summaries
                if deep_summary_articles:
                    tasks = []
                    for article in deep_summary_articles:
                        task = asyncio.create_task(self.process_deep_summary(article))
                        tasks.append(task)

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            logger.error(f"Error in deep summary processing: {result}")

                # Brief pause to avoid tight loop
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            logger.info("LLM processing task cancelled")
            self.processing = False
        except Exception as e:
            logger.error(f"Error in LLM processing loop: {e}")
            self.processing = False
            raise

    def stop_processing(self):
        """Stop the LLM processing loop."""
        self.processing = False
        logger.info("LLM processing stopped")

    async def process_article(self, article):
        """Process a single article with LLM for summary and keywords."""
        if not self.client:
            logger.error("OpenAI client not available, cannot process article")
            return

        article_id = article['id']
        title = article['title']
        content = article['raw_content']

        if not content or len(content) < 100:
            logger.warning(f"Article content too short for processing: {article_id}")
            self.db.execute(
                "UPDATE articles SET processing_status = 'insufficient_content' WHERE id = ?",
                (article_id,)
            )
            return

        try:
            # Generate summary
            summary = await self._generate_summary(title, content)

            # Extract keywords
            keywords = await self._extract_keywords(title, content)

            # Update article with summary
            self.db.update_article_summary(article_id, summary, self.model)

            # Add keywords
            if keywords:
                self.db.add_keywords_to_article(article_id, keywords)

            logger.info(f"Successfully processed article: {title}")

        except Exception as e:
            logger.error(f"Error processing article {article_id}: {e}")
            self.db.execute(
                "UPDATE articles SET processing_status = 'llm_error' WHERE id = ?",
                (article_id,)
            )
            raise

    async def _generate_summary(self, title, content):
        """Generate a summary of the article content using LLM."""
        if not self.client:
            return "LLM processing unavailable"

        # Prepare text for summarization
        text_to_summarize = f"Title: {title}\n\nContent: {self._truncate_text(content, 6000)}"

        # Check cache first
        cache_key = self._get_cache_key(text_to_summarize, "summary")
        cached_result = self._check_cache(cache_key)
        if cached_result:
            logger.info("Using cached summary")
            return cached_result

        # Create prompt for summarization
        prompt = f"Summarize the following text, focusing on its key findings or announcements related to AI/ML, in approximately 3-5 sentences:\n\n{text_to_summarize}"

        # Call OpenAI API
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes AI and machine learning content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.summary_max_tokens,
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()

            # Cache the result
            self._cache_result(cache_key, summary)

            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            # Implement exponential backoff retry logic here if needed
            return f"Error generating summary: {str(e)[:100]}..."

    async def _extract_keywords(self, title, content):
        """Extract keywords from the article content using LLM."""
        if not self.client:
            return ["LLM unavailable"]

        # Prepare text for keyword extraction
        text_for_keywords = f"Title: {title}\n\nContent: {self._truncate_text(content, 4000)}"

        # Check cache first
        cache_key = self._get_cache_key(text_for_keywords, "keywords")
        cached_result = self._check_cache(cache_key)
        if cached_result:
            logger.info("Using cached keywords")
            return cached_result.split(', ')

        # Create prompt for keyword extraction
        prompt = f"Extract the 5 most important keywords or phrases from the following text related to AI/ML. Return only a comma-separated list of keywords:\n\n{text_for_keywords}"

        # Call OpenAI API
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that extracts keywords from AI and machine learning content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )

            keywords_text = response.choices[0].message.content.strip()

            # Clean up the response and extract keywords
            keywords = [k.strip() for k in keywords_text.split(',')]
            keywords = [k for k in keywords if k]

            # Cache the result
            self._cache_result(cache_key, ', '.join(keywords))

            return keywords

        except Exception as e:
            logger.error(f"Error extracting keywords: {e}")
            # Implement exponential backoff retry logic here if needed
            return ["Error extracting keywords"]

    def _truncate_text(self, text, max_tokens):
        """Truncate text to approximately max_tokens to fit within model context."""
        # Rough approximation: 1 token ≈ 4 characters for English text
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."

    def _get_cache_key(self, text, operation):
        """Generate a cache key for the given text and operation."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{operation}_{self.model}_{text_hash}.json"

    def _check_cache(self, cache_key):
        """Check if result is in cache."""
        cache_path = os.path.join(self.cache_dir, cache_key)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                    # Check if cache is still valid (e.g., not expired)
                    return cache_data.get('result')
            except Exception as e:
                logger.error(f"Error reading cache: {e}")
        return None

    def _cache_result(self, cache_key, result):
        """Cache the result for future use."""
        cache_path = os.path.join(self.cache_dir, cache_key)
        try:
            with open(cache_path, 'w') as f:
                json.dump({
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Error writing to cache: {e}")

    async def process_deep_summary(self, article):
        """Process a single article for deep summary generation."""
        article_id = article['id']
        title = article['title']
        full_content = article['full_content']

        if not full_content or len(full_content) < 200:
            logger.warning(f"Full content too short for deep summary: {article_id}")
            self.db.update_deep_summary(article_id, "Content too short for detailed analysis", status='failed')
            return

        try:
            # Generate deep summary
            deep_summary = await self._generate_deep_summary(title, full_content)

            # Update article with deep summary
            self.db.update_deep_summary(article_id, deep_summary, status='completed')

            logger.info(f"Successfully generated deep summary for article: {title}")

        except Exception as e:
            logger.error(f"Error processing deep summary for article {article_id}: {e}")
            self.db.update_deep_summary(article_id, f"Error: {str(e)[:100]}", status='failed')
            raise

    async def _generate_deep_summary(self, title, full_content):
        """Generate a comprehensive summary from full article content."""
        if not self.client:
            return "LLM processing unavailable"

        # Prepare text for deep summarization - use more content for HTML papers
        # Check if this looks like full HTML content vs just abstract
        is_full_paper = len(full_content) > 2000 and any(section in full_content.lower() for section in ['introduction', 'methodology', 'results', 'conclusion', 'references'])

        if is_full_paper:
            # For full papers, use more content but still truncate if very long
            text_to_summarize = f"Title: {title}\n\nFull Paper Content: {self._truncate_text(full_content, 16000)}"
            prompt_type = "full_paper"
        else:
            # For abstracts/metadata, use existing approach
            text_to_summarize = f"Title: {title}\n\nContent: {self._truncate_text(full_content, 12000)}"
            prompt_type = "abstract"

        # Check cache first
        cache_key = self._get_cache_key(text_to_summarize, f"deep_summary_{prompt_type}")
        cached_result = self._check_cache(cache_key)
        if cached_result:
            logger.info("Using cached deep summary")
            return cached_result

        # Create appropriate prompt based on content type
        if prompt_type == "full_paper":
            prompt = f"""Please provide a comprehensive analysis of this research paper. Structure your analysis with these sections:

**🎯 Main Contribution**
What is the primary contribution, innovation, or finding of this work?

**🔬 Methodology**
What approaches, methods, or techniques were used? Include key algorithms, datasets, or experimental setup.

**📊 Key Results**
What were the most important quantitative and qualitative results? Include specific metrics, comparisons, or findings.

**💡 Significance**
Why is this work important to the field? What problems does it solve or advance?

**⚠️ Limitations**
What are the acknowledged limitations, assumptions, or areas for improvement?

**🔮 Future Work**
What future research directions or applications are suggested?

**🏷️ Technical Keywords**
List 5-7 key technical terms or concepts that researchers would search for.

Paper to analyze:
{text_to_summarize}

Provide a thorough but concise analysis that would help researchers quickly understand the paper's value and relevance."""
        else:
            prompt = f"""Please provide a comprehensive analysis and summary of this research paper/article. Include:

1. **Main Contribution**: What is the primary contribution or finding?
2. **Methodology**: What approach or methods were used?
3. **Key Results**: What were the most important results or findings?
4. **Significance**: Why is this work important to the AI/ML field?
5. **Limitations**: What are the acknowledged limitations or areas for improvement?
6. **Future Work**: What future research directions are suggested?

Article to analyze:
{text_to_summarize}

Please structure your response clearly with the above sections and provide a thorough but concise analysis."""

        # Call OpenAI API with higher token limit for deep summary
        try:
            max_tokens = 1000 if prompt_type == "full_paper" else 800

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert AI researcher who provides comprehensive analysis of technical papers and articles. Provide structured, detailed summaries that help researchers understand the key contributions and significance of the work. Use clear formatting with headers and bullet points where appropriate."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.3
            )

            deep_summary = response.choices[0].message.content.strip()

            # Add content type indicator
            content_indicator = "\n\n---\n*Analysis based on full paper content*" if prompt_type == "full_paper" else "\n\n---\n*Analysis based on abstract and metadata*"
            deep_summary += content_indicator

            # Cache the result
            self._cache_result(cache_key, deep_summary)

            return deep_summary

        except Exception as e:
            logger.error(f"Error generating deep summary: {e}")
            return f"Error generating deep summary: {str(e)[:100]}..."

    async def generate_deep_summary_for_article(self, article_id):
        """Manually trigger deep summary generation for a specific article."""
        if not self.client:
            logger.error("OpenAI client not available")
            return False

        try:
            # Get article with full content
            cursor = self.db.execute(
                "SELECT id, title, full_content FROM articles WHERE id = ? AND full_content IS NOT NULL",
                (article_id,)
            )
            article = cursor.fetchone()

            if not article:
                logger.error(f"Article {article_id} not found or has no full content")
                return False

            # Mark as pending
            self.db.request_deep_summary(article_id)

            # Process immediately
            await self.process_deep_summary(dict(article))

            return True

        except Exception as e:
            logger.error(f"Error generating deep summary for article {article_id}: {e}")
            return False