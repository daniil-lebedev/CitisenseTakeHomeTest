# Citisense Event Popularity Extraction Tool

A UK-focused event popularity analysis tool that extracts data from multiple sources to gauge event interest and activity.

## Features

- **UK-Focused Search**: Prioritizes UK locations, subreddits, and events
- **Multi-Source Data**: Combines Eventbrite, Reddit, and Google Trends
- **High Relevance Filtering**: Only returns content with 90+ relevance scores
- **Date-Specific Analysis**: Searches for activity on specific dates
- **Structured Output**: Clean JSON results with detailed event/post data

## Sources

- **Eventbrite**: UK events and activities (web scraping)
- **Reddit**: UK subreddits (API integration)
- **Google Trends**: Search popularity data

## Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables in `.env`:
```
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_app_name
```

## Usage

```bash
python main.py --keyword "EVENT_NAME" --date "YYYY-MM-DD"
```

### Examples

```bash
# Music festivals
python main.py --keyword "Glastonbury Festival" --date "2025-06-25"

# Sports events
python main.py --keyword "Premier League" --date "2025-11-02"

# Seasonal events
python main.py --keyword "Christmas Markets" --date "2025-12-15"

# Tech events
python main.py --keyword "London Tech Week" --date "2025-06-10"
```

## Output

Results are saved to `Results/` folder as timestamped JSON files containing:

- **Summary**: Event counts and trend scores
- **Detailed Data**: Full event listings and Reddit posts
- **Metadata**: Search duration, sources, relevance thresholds

## Requirements

- Python 3.7+
- Reddit API credentials (optional but recommended)
- Internet connection for web scraping and API calls

## UK Focus

The tool specifically targets:
- UK Eventbrite locations (eventbrite.co.uk)
- UK subreddits (r/london, r/manchester, r/AskUK, etc.)
- UK-relevant content and discussions
- British cultural events and activities