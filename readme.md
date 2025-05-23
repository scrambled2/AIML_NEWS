# AI/ML News Aggregator

A sophisticated RSS feed aggregator specifically designed for AI and Machine Learning news. This application automatically polls RSS feeds, extracts content, generates AI-powered summaries and keywords, and presents everything in a modern, responsive web interface with side-panel article viewing. Features advanced ArXiv integration with full paper content extraction and comprehensive analysis capabilities.

## 🚀 Key Features

### Core Functionality
- **RSS Feed Management**: Add, edit, enable/disable RSS feeds with individual polling intervals
- **Automated Content Extraction**: Fetches full article content beyond RSS summaries
- **AI-Powered Processing**: Uses OpenAI GPT models to generate article summaries and extract keywords
- **ArXiv Integration**: Full paper content extraction from ArXiv HTML format with API fallback
- **Deep Analysis**: Comprehensive LLM analysis of full research papers with structured breakdowns
- **Intelligent Search**: Full-text search across titles, summaries, content, and keywords
- **Advanced Filtering**: Filter by source, keywords, and sort by date, title, or source
- **Side-Panel Interface**: Click any article to view its content without leaving the page
- **Favorites System**: Save articles with personal notes and tags for later reference

### ArXiv Advanced Features
- **Full Paper Extraction**: Downloads complete research papers from ArXiv HTML format (Dec 2023+)
- **Smart Content Detection**: Automatically identifies ArXiv papers and extracts paper IDs
- **Dual Processing**: Full HTML content for recent papers, enhanced abstracts for older ones
- **Bulk Processing**: Continuous processing mode for large backlogs with configurable batch sizes
- **Processing Dashboard**: Visual statistics showing extraction and analysis progress with real-time updates
- **Deep Research Analysis**: Comprehensive LLM analysis including methodology, results, significance
- **Content Type Detection**: Distinguishes between full papers and abstract-only content
- **Front-End Controls**: Interactive processing controls with batch size selection and monitoring

### User Interface
- **Modern Design**: Clean, responsive Bootstrap-based interface with dark mode support
- **Processing Status Indicators**: Visual badges showing ArXiv extraction and analysis status
- **Interactive Controls**: Dropdown processing controls with configurable batch sizes and modes
- **Real-time Updates**: AJAX-powered interface updates without page reloads
- **Mobile Responsive**: Optimized layouts for desktop, tablet, and mobile devices
- **Statistics Dashboard**: Comprehensive processing metrics with live progress bars and monitoring
- **Pagination**: Efficient browsing of large article collections

### Data Management
- **SQLite Database**: Lightweight, serverless database with full-text search capabilities
- **ArXiv Status Tracking**: Monitors extraction and analysis progress for each paper
- **Caching System**: LLM response caching to reduce API costs and improve performance
- **Data Export/Import**: Backup and restore feed configurations as JSON
- **Article Limits**: Configurable per-feed article retention (10-50,000 articles)
- **Favorites Management**: Personal article collections with notes and tagging

### Background Processing
- **Concurrent Feed Polling**: Configurable concurrent feed processing
- **ArXiv Content Extraction**: Automatic full paper content extraction from HTML
- **LLM Processing Pipeline**: Regular summaries and deep analysis generation
- **Retry Logic**: Robust error handling with exponential backoff
- **User Agent Rotation**: Multiple user agents to avoid blocking
- **Rate Limiting**: Respectful polling with configurable intervals
- **Graceful Shutdown**: Clean termination of background tasks

## 📋 Requirements

### System Requirements
- **Python**: 3.8 or higher
- **Operating System**: Windows, macOS, or Linux
- **Memory**: Minimum 2GB RAM (8GB+ recommended for large article volumes)
- **Storage**: 1GB+ free space (scales with article volume)

### Python Dependencies
- **Flask**: Web framework and routing
- **feedparser**: RSS/Atom feed parsing
- **aiohttp**: Asynchronous HTTP client for feed fetching
- **beautifulsoup4**: HTML parsing and content extraction
- **openai**: OpenAI API client for LLM processing
- **python-dotenv**: Environment variable management
- **sqlite3**: Database (built into Python)

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd aiml-news-aggregator
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux  
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create a `.env` file in the project root:
```env
# OpenAI API Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Database Configuration
DATABASE_PATH=instance/aiml_news.db

# Optional: Logging Level
LOG_LEVEL=INFO
```

### 5. Configuration File
The `config.json` file contains application settings:
```json
{
    "polling_interval_minutes": 30,
    "max_concurrent_feeds": 5,
    "store_content_level": "summary_only",
    "openai_model": "gpt-4o-mini",
    "summary_max_tokens": 150
}
```

## 🚀 Quick Start

### 1. Start the Application
```bash
python app.py
```

The application will start on `http://localhost:5000`

### 2. Initial Setup
- The app creates a default Microsoft Research feed on first run
- Navigate to **Manage Feeds** to add more RSS sources
- Add ArXiv feeds for enhanced functionality:
  - `http://export.arxiv.org/rss/cs.AI` (AI papers)
  - `http://export.arxiv.org/rss/cs.LG` (Machine Learning papers)
  - `http://export.arxiv.org/rss/cs.CL` (Computational Linguistics)

### 3. Basic Usage
- **Browse Articles**: Main page shows recent articles in a side-panel layout
- **View Article**: Click any article title to view full content in the side panel
- **Filter Content**: Use the filters to narrow down articles by source or keywords
- **Search**: Use the search bar to find specific articles across all content
- **Process ArXiv**: Use dropdown controls to configure and start ArXiv extraction
  - **Batch Processing**: Select 50-500 articles per batch
  - **Continuous Mode**: Process entire backlog automatically
  - **Monitor Progress**: Real-time dashboard updates during processing
- **Generate Analysis**: Click **"Generate Deep Analysis"** on ArXiv papers for comprehensive breakdowns

## ⚙️ Configuration

### Application Settings (`config.json`)

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| `polling_interval_minutes` | Global default polling interval | 30 | 5-1440 |
| `max_concurrent_feeds` | Maximum feeds processed simultaneously | 5 | 1-20 |
| `store_content_level` | Content storage level | "summary_only" | "none", "summary_only", "full" |
| `openai_model` | OpenAI model for processing | "gpt-4o-mini" | Any OpenAI model |
| `summary_max_tokens` | Maximum tokens for summaries | 150 | 50-500 |

### Feed-Level Settings

Each feed can be configured individually:
- **Polling Interval**: 5-1440 minutes (overrides global setting)
- **Maximum Articles**: 10-50,000 articles to retain
- **Enable/Disable**: Toggle feed processing
- **Display Order**: Control feed ordering in lists

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for LLM processing | Yes* |
| `DATABASE_PATH` | SQLite database file path | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | No |

*Required only if using AI features (summaries/keywords/deep analysis)

## 🎓 ArXiv Integration

### Automatic Detection
The system automatically identifies ArXiv papers from RSS feeds and tracks their processing status with visual indicators:
- 🎓 **ArXiv** - Identified as ArXiv paper
- 📄 **Full** - Full content extracted
- 🧠 **Deep** - Deep analysis completed
- ⏰ **Processing** - Currently being processed

### Content Extraction
- **HTML Format**: Extracts full paper content from ArXiv's HTML format (papers after Dec 2023)
- **API Fallback**: Uses ArXiv API for enhanced abstracts on older papers
- **Smart Processing**: Automatically detects content type and adjusts processing accordingly
- **Bulk Processing**: Configurable batch sizes (50-500 articles) with continuous processing mode

### Processing Controls
- **Interactive Dashboard**: Front-end controls for batch size selection and processing modes
- **Single Batch Mode**: Process specific number of articles (50, 100, 200, 500)
- **Continuous Mode**: Process entire backlog automatically with progress monitoring
- **Real-Time Status**: Live updates showing pending articles and processing progress
- **Quick Actions**: One-click buttons for common processing tasks

### Deep Analysis Features
- **Structured Analysis**: Comprehensive breakdowns including methodology, results, significance
- **Technical Keywords**: Extraction of key technical terms and concepts
- **Research Context**: Analysis of limitations, future work, and field impact
- **Content Indicators**: Clear labels showing analysis quality (full paper vs abstract)

### Processing Workflow
1. **RSS Polling** → New ArXiv articles detected automatically
2. **Content Extraction** → Full papers downloaded from HTML or API (configurable batch processing)
3. **LLM Processing** → Summaries and deep analysis generated
4. **Status Tracking** → Visual indicators updated in real-time with progress monitoring
5. **Bulk Processing** → Continuous processing mode handles large backlogs efficiently

## 🏗️ Architecture

### Application Structure
```
aiml-news-aggregator/
├── app.py                 # Main Flask application
├── config.py             # Configuration management
├── database.py           # Database operations
├── feed_reader.py        # RSS feed processing
├── llm_processor.py      # AI/LLM integration
├── arxiv_extractor.py    # ArXiv content extraction
├── requirements.txt      # Python dependencies
├── config.json          # Application configuration
├── .env                 # Environment variables
├── static/              # Static web assets
│   ├── css/            # Stylesheets
│   └── js/             # JavaScript files
├── templates/           # HTML templates
└── instance/           # Runtime data
    ├── aiml_news.db    # SQLite database
    ├── aiml_news.log   # Application logs
    └── llm_cache/      # LLM response cache
```

### Core Components

#### 1. Flask Application (`app.py`)
- **Web Routes**: Handles all HTTP requests and responses
- **Background Tasks**: Manages asynchronous feed polling, ArXiv extraction, and LLM processing
- **Error Handling**: Comprehensive error handling and logging
- **Statistics API**: Provides real-time processing metrics

#### 2. Database Layer (`database.py`)
- **SQLite Integration**: Thread-safe database operations
- **ArXiv Tracking**: Specialized tables for ArXiv processing status
- **Full-Text Search**: FTS5 virtual tables for fast searching
- **Favorites System**: Personal article collections with notes and tags

#### 3. Feed Processing (`feed_reader.py`)
- **Async HTTP**: Concurrent feed fetching with aiohttp
- **Content Extraction**: BeautifulSoup-based article content extraction
- **Error Recovery**: Retry logic with exponential backoff
- **Rate Limiting**: Respectful crawling with delays

#### 4. ArXiv Extractor (`arxiv_extractor.py`)
- **HTML Parsing**: Extracts full paper content from ArXiv HTML format
- **Pattern Matching**: Identifies ArXiv papers from various URL formats
- **Content Analysis**: Distinguishes between full papers and abstracts
- **API Integration**: Fallback to ArXiv API for older papers

#### 5. LLM Integration (`llm_processor.py`)
- **OpenAI Integration**: Async OpenAI API client
- **Dual Processing**: Regular summaries and comprehensive deep analysis
- **Content-Aware**: Adjusts prompts based on content type (full paper vs abstract)
- **Response Caching**: MD5-based response caching to reduce costs

### Database Schema

#### Core Tables
- **feeds**: RSS feed configurations and metadata
- **articles**: Article content and processing status
- **keywords**: Extracted keyword dictionary
- **article_keywords**: Many-to-many relationship between articles and keywords
- **favorites**: User-saved articles with notes and tags
- **articles_fts**: Full-text search virtual table

#### ArXiv Extensions
- **arxiv_id**: ArXiv paper identifier
- **full_content_status**: Tracks content extraction progress
- **full_content**: Complete paper text
- **deep_summary_status**: Tracks analysis progress
- **deep_summary**: Comprehensive LLM analysis

## 🔌 API Endpoints

### Web Routes
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main article listing with side panel and ArXiv dashboard |
| `/article/<id>` | GET | Full article detail page |
| `/search` | GET | Search results page |
| `/favorites` | GET | Favorite articles management |
| `/feeds` | GET | Feed management interface with ArXiv breakdown |
| `/feeds/add` | POST | Add new RSS feed |
| `/feeds/edit/<id>` | GET/POST | Edit feed settings |
| `/feeds/delete/<id>` | POST | Delete feed and articles |
| `/feeds/export` | GET | Export feeds as JSON |
| `/feeds/import` | POST | Import feeds from JSON |

### API Routes
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/article/<id>` | GET | Article data with ArXiv information as JSON |
| `/api/arxiv-stats` | GET | ArXiv processing statistics with real-time metrics |
| `/api/arxiv-feed-breakdown` | GET | ArXiv content breakdown by feed |
| `/api/arxiv-processing-status` | GET | Current processing status and backlog information |
| `/api/favorite/<id>` | POST/PUT/DELETE | Favorites management |
| `/api/article/<id>/extract-arxiv` | POST | Manual ArXiv content extraction |
| `/api/article/<id>/request-deep-summary` | POST | Request deep analysis |

### Control Routes
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/poll-now` | POST | Trigger immediate feed polling |
| `/process-pending` | POST | Start LLM processing |
| `/extract-arxiv` | POST | Start ArXiv content extraction with configurable options |
| `/admin/clean-keywords` | POST | Remove orphaned keywords |
| `/shutdown` | POST | Graceful application shutdown |

## 🎨 User Interface

### Main Interface
- **Article List**: Left panel with article cards showing titles, summaries, and ArXiv status
- **Side Panel**: Right panel for viewing full article content and ArXiv analysis
- **ArXiv Dashboard**: Processing statistics with progress bars, live metrics, and processing controls
- **Interactive Controls**: Dropdown menus for batch processing configuration and monitoring
- **Filter Bar**: Source, keyword, sorting, and pagination controls

### ArXiv Features
- **Status Indicators**: Visual badges showing extraction and analysis progress
- **Content Type Labels**: Clear indicators for full papers vs enhanced abstracts
- **Processing Controls**: Interactive dropdown with batch size selection and processing modes
- **Progress Tracking**: Real-time updates during processing with detailed progress bars
- **Bulk Processing**: Continuous mode for handling large backlogs efficiently

### Feed Management
- **Feed List**: Table view with ArXiv content breakdown
- **Processing Metrics**: Visual progress bars for extraction and analysis rates
- **Quick Actions**: Enable/disable, edit, delete, and view articles per feed
- **Statistics**: Comprehensive breakdown of ArXiv content by feed

### Favorites System
- **Personal Collections**: Save articles with custom notes and tags
- **Tag Management**: Organize favorites with searchable tags
- **Notes System**: Add personal thoughts and annotations
- **Filter and Sort**: Advanced filtering by tags and notes

## 🔍 Search and Filtering

### Search Capabilities
- **Full-Text Search**: Searches across article titles, summaries, and content
- **Keyword Search**: Matches AI-extracted keywords
- **ArXiv Content**: Searches full paper content when available
- **Favorites Search**: Dedicated search within saved articles

### Filtering Options
- **Source Filter**: Show articles from specific feeds
- **Keyword Filter**: Filter by extracted keywords
- **ArXiv Status**: Filter by extraction and analysis status
- **Content Type**: Filter by full papers vs abstracts
- **Date Range**: Sort by publication date
- **Processing Status**: Filter by LLM processing status

## 🔧 Development and Maintenance

### Development Setup
```bash
# Install development dependencies
pip install -r requirements.txt

# Run in development mode
python app.py

# Enable debug mode
export FLASK_ENV=development  # Unix
set FLASK_ENV=development     # Windows
```

### Monitoring and Health Checks
- **Application Logs**: Stored in `instance/aiml_news.log`
- **Processing Metrics**: Real-time statistics via API endpoints
- **Database Health**: SQLite integrity and performance monitoring
- **ArXiv Processing**: Extraction and analysis success rates

### Regular Maintenance
- **Clean Keywords**: Use "Clean Orphaned Keywords" button monthly
- **Database Optimization**: Consider VACUUM operations for large databases
- **Log Rotation**: Archive or delete old log files
- **Cache Management**: LLM response cache cleanup
- **Backup Strategy**: Regular backup of database and configuration files

### Performance Optimization
- **ArXiv Processing**: Adjust concurrent extraction limits
- **LLM Batch Size**: Configure processing batch sizes
- **Database Indexing**: Optimize queries for large datasets
- **Caching Strategy**: Monitor cache hit rates and storage usage

## 🐛 Troubleshooting

### Common Issues

#### ArXiv Processing Issues
- **No Content Extracted**: Check if papers are from Dec 2023 or later for HTML format
- **Extraction Failures**: Monitor logs for rate limiting or network issues; adjust batch sizes if needed
- **Status Not Updating**: Refresh dashboard or check background tasks; use continuous monitoring
- **Large Backlog Processing**: Use continuous mode with appropriate batch sizes (100-200 articles)
- **Processing Stuck**: Check pending queue in dashboard and restart with smaller batch sizes

#### LLM Processing Issues
- **Deep Analysis Failures**: Verify OpenAI API key and model availability
- **Processing Stuck**: Check pending queue and restart LLM processing
- **Poor Analysis Quality**: Adjust model parameters or content extraction

#### Database Issues
- **Database Locked**: Ensure only one instance is running
- **Large Database Size**: Consider article retention limits and cleanup
- **Search Performance**: Rebuild FTS indexes if queries are slow

#### General Performance
- **High Memory Usage**: Reduce concurrent processing limits
- **Slow Response**: Check database query performance and indexing
- **Network Issues**: Verify feed URLs and API connectivity

### Log Analysis
```bash
# Monitor application logs
tail -f instance/aiml_news.log

# Check for ArXiv extraction issues
grep "ArXiv" instance/aiml_news.log

# Monitor LLM processing
grep "LLM" instance/aiml_news.log
```

## 📊 Statistics and Metrics

### Processing Dashboard
The main page displays comprehensive ArXiv processing statistics with real-time updates:
- **Total ArXiv Papers**: Count of identified research papers
- **Full Content Extracted**: Papers with complete content and extraction progress
- **Full Papers vs Abstracts**: Content quality breakdown with visual indicators
- **Deep Analysis Completed**: Papers with comprehensive analysis and completion rates
- **Processing Queue**: Real-time pending extractions and analysis counts
- **Recent Activity**: New papers added this week
- **Live Monitoring**: Automatic updates during processing operations
- **Interactive Controls**: Dropdown menus for configuring batch processing options

### Feed Performance
The feeds page shows detailed breakdown by source:
- **ArXiv Content Ratio**: Percentage of ArXiv papers per feed
- **Extraction Rates**: Success rates for content extraction
- **Analysis Coverage**: Percentage with deep analysis
- **Processing Efficiency**: Visual progress indicators

## 🔒 Security and Privacy

### Data Protection
- **Local Storage**: All data stored locally in SQLite database
- **API Security**: OpenAI API key stored in environment variables
- **Content Privacy**: No external data sharing except API calls
- **User Control**: Complete control over data retention and deletion

### Best Practices
- **Environment Variables**: Keep API keys out of version control
- **Regular Updates**: Update dependencies for security patches
- **Access Control**: Run behind reverse proxy for public deployments
- **Data Backup**: Regular backups of configuration and database

## 🚀 Advanced Usage

### Bulk Processing
- **Mass Extraction**: Process all ArXiv papers with configurable batch sizes (50-500 articles)
- **Continuous Mode**: Automatic processing of entire backlog until completion
- **Batch Analysis**: Generate deep analysis for multiple papers with progress monitoring
- **Real-time Monitoring**: Live statistics and progress tracking during bulk operations

### Research Workflow
- **Paper Discovery**: RSS feeds provide continuous research updates
- **Content Analysis**: Deep LLM analysis provides structured insights
- **Knowledge Management**: Favorites system for personal research collections
- **Search and Filter**: Advanced filtering for research topics

### Integration Possibilities
- **API Access**: JSON endpoints for external integration
- **Data Export**: Export favorites and statistics for external analysis
- **Custom Feeds**: Add specialized ArXiv subject feeds
- **Notification Systems**: Monitor processing status programmatically

## 🤝 Contributing

### Development Guidelines
1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature-name`
3. **Make** changes with appropriate tests
4. **Commit** with clear messages
5. **Submit** a pull request

### Areas for Contribution
- **ArXiv Integration**: Enhanced content extraction and analysis
- **LLM Features**: Additional analysis types and models
- **User Interface**: Improved visualization and interaction
- **Performance**: Optimization and scaling improvements
- **Documentation**: Enhanced guides and examples

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **ArXiv**: For providing open access to research papers and HTML format
- **OpenAI**: For providing the GPT API for content analysis
- **Bootstrap**: For the responsive UI framework
- **SQLite**: For the lightweight database solution
- **Python Community**: For the excellent libraries and ecosystem

---

*AI/ML News Aggregator - Advanced RSS aggregation with ArXiv integration and comprehensive research paper analysis*

*Version: 2.0.0 with ArXiv Integration*
*Last Updated: January 2025*