import os
import json
import argparse
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Union, Any

import requests
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Environment variables loaded from .env file")
except ImportError:
    logger.info("dotenv not available, using os.getenv directly")

# Optional libs for Reddit & Google Trends
try:
    from pytrends.request import TrendReq
except Exception:
    TrendReq = None

# Reddit API
try:
    import praw
except Exception:
    praw = None

def fetch_eventbrite_count(keyword: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """
    Scrape Eventbrite search results and return detailed event data with relevance scores.
    """
    logger.info(f"Starting Eventbrite search for keyword: '{keyword}' (UK-focused)")
    if start_date and end_date:
        logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    return fetch_eventbrite_scrape(keyword)

def fetch_eventbrite_scrape(keyword: str) -> Dict[str, Any]:
    """
    Scrape Eventbrite search results since the API was deprecated in 2019.
    """
    q = keyword.replace(" ", "+")
    # UK-focused Eventbrite URLs
    urls = [
        f"https://www.eventbrite.co.uk/d/united-kingdom/{q}/",
        f"https://www.eventbrite.co.uk/search?q={q}&location=United+Kingdom"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    # Try multiple URLs until one works
    for i, url in enumerate(urls, 1):
        logger.info(f"Attempt {i}: Fetching URL: {url}")
        
        try:
            r = requests.get(url, timeout=20, headers=headers)
            logger.info(f"HTTP Status: {r.status_code}")
            
            if r.status_code == 404:
                logger.info(f"URL {i} returned 404, trying next...")
                continue
                
            r.raise_for_status()
            
            soup = BeautifulSoup(r.text, "html.parser")
            logger.info(f"Page parsed, HTML length: {len(r.text)} characters")
            
            # Try multiple selectors for event cards
            selectors = [
                "[data-testid='search-result-event-card']",
                ".search-event-card-wrapper",
                ".eds-event-card-content__primary-content", 
                ".search-main-content__events-list-item",
                "[data-spec='search-result']",
                ".search-results-panel-content article",
                ".event-card",
                "[class*='event-card']",
                ".discover-search-desktop-card",
                ".eds-card-content"
            ]
            
            logger.info(f"Trying {len(selectors)} different CSS selectors...")
            
            for j, selector in enumerate(selectors, 1):
                cards = soup.select(selector)
                logger.info(f"{j}. Selector '{selector}': {len(cards)} matches")
                if cards:
                    logger.info(f"Found {len(cards)} events using selector: {selector}")
                    
                    # Extract detailed event information
                    events = []
                    for k, card in enumerate(cards):
                        try:
                            # Extract event details
                            title_elem = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) or card.find(attrs={'class': lambda x: x and 'title' in str(x).lower()})
                            title = title_elem.get_text(strip=True) if title_elem else card.get_text(strip=True)[:100]
                            
                            # Look for date/time information
                            date_elem = card.find(attrs={'class': lambda x: x and any(word in str(x).lower() for word in ['date', 'time', 'when'])})
                            date_text = date_elem.get_text(strip=True) if date_elem else ""
                            
                            # Look for location information
                            location_elem = card.find(attrs={'class': lambda x: x and any(word in str(x).lower() for word in ['location', 'venue', 'where'])})
                            location = location_elem.get_text(strip=True) if location_elem else ""
                            
                            # Look for event link
                            link_elem = card.find('a', href=True)
                            link = link_elem['href'] if link_elem else ""
                            if link and not link.startswith('http'):
                                link = f"https://www.eventbrite.com{link}"
                            
                            # Calculate relevance score
                            relevance_score = calculate_relevance_score(title, keyword)
                            
                            event_data = {
                                "title": title[:200],  # Limit title length
                                "date_text": date_text[:100],
                                "location": location[:100],
                                "link": link,
                                "relevance_score": relevance_score,
                                "source": "eventbrite_scrape"
                            }
                            events.append(event_data)
                            
                            # Log first few events
                            if k < 3:
                                logger.info(f"Event {k+1}: {title[:100]}...")
                                
                        except Exception as e:
                            logger.warning(f"Error parsing event {k+1}: {e}")
                            continue
                    
                    # Filter events by high relevance (90+)
                    high_relevance_events = [e for e in events if e['relevance_score'] >= 90]
                    logger.info(f"Filtered to {len(high_relevance_events)} high-relevance events (90+ score) from {len(events)} total")
                    
                    return {
                        "count": len(high_relevance_events),
                        "events": high_relevance_events,
                        "source": "eventbrite_scrape",
                        "selector_used": selector,
                        "total_events_found": len(events),
                        "relevance_threshold": 90
                    }
            
            # If no specific selectors work, look for any links to events
            logger.info("Trying fallback: looking for event links (/e/ pattern)")
            event_links = soup.find_all("a", href=lambda x: x and "/e/" in x)
            if event_links:
                logger.info(f"Found {len(event_links)} event links")
                
                events = []
                for k, link in enumerate(event_links):
                    try:
                        href = link.get('href', '')
                        if not href.startswith('http'):
                            href = f"https://www.eventbrite.com{href}"
                        
                        title = link.get_text(strip=True) or f"Event {k+1}"
                        relevance_score = calculate_relevance_score(title, keyword)
                        
                        event_data = {
                            "title": title[:200],
                            "date_text": "",
                            "location": "",
                            "link": href,
                            "relevance_score": relevance_score,
                            "source": "eventbrite_links"
                        }
                        events.append(event_data)
                        
                        if k < 3:
                            logger.info(f"Link {k+1}: {title[:50]}... -> {href}")
                            
                    except Exception as e:
                        logger.warning(f"Error parsing link {k+1}: {e}")
                        continue
                
                # Filter events by high relevance (90+)
                high_relevance_events = [e for e in events if e['relevance_score'] >= 90]
                logger.info(f"   Filtered to {len(high_relevance_events)} high-relevance events (90+ score) from {len(events)} total")
                
                return {
                    "count": len(high_relevance_events),
                    "events": high_relevance_events,
                    "source": "eventbrite_links",
                    "total_events_found": len(events),
                    "relevance_threshold": 90
                }
            
            logger.info(f"No events found with URL {i}, trying next...")
            
        except Exception as e:
            logger.error(f"Error with URL {i}: {e}")
            continue
    
    logger.warning("No events found with any URL or method")
    return {
        "count": 0,
        "events": [],
        "source": "eventbrite_scrape",
        "error": "No events found"
    }



def calculate_relevance_score(title: str, keyword: str) -> int:
    """Calculate relevance score based on keyword matching and context."""
    title_lower = title.lower()
    keyword_lower = keyword.lower()
    
    score = 0
    
    # Exact keyword match
    if keyword_lower in title_lower:
        score += 100
    
    # Individual word matches
    for word in keyword_lower.split():
        if word in title_lower:
            score += 35
    
    # Event-related bonus
    event_terms = ['festival', 'event', 'celebration', 'party', 'concert', 'show', 'tour', 'live', 'performance']
    if any(term in title_lower for term in event_terms):
        score += 20
    
    return max(0, min(score, 100))

def fetch_reddit_mentions(keyword: str, start_ts: int, end_ts: int) -> Union[Dict[str, Any], int]:
    """
    Use Reddit API and scraping to get Reddit mentions:
    1. Reddit API via praw (most reliable but limited)
    2. Reddit search scraping (fallback)
    Returns total mentions found between start_ts and end_ts.
    Note: Pushshift API now requires moderator access, so we don't use it.
    """
    
    start_date = datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d %H:%M:%S')
    end_date = datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Starting Reddit search for keyword: '{keyword}' (UK-prioritized)")
    logger.info(f"Date range: {start_date} to {end_date} (timestamps: {start_ts} - {end_ts})")
    
    # Try Reddit API first (most reliable)
    reddit_client_id = os.getenv("REDDIT_CLIENT_ID")
    reddit_client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    reddit_user_agent = os.getenv("REDDIT_USER_AGENT")
    
    logger.info(f"Reddit credentials: ID={reddit_client_id[:10] + '...' if reddit_client_id else 'None'}, Secret={'***' if reddit_client_secret else 'None'}, Agent={reddit_user_agent}")
    
    if reddit_client_id and reddit_client_secret and praw:
        logger.info("Attempting Reddit API connection...")
        try:
            reddit = praw.Reddit(
                client_id=reddit_client_id,
                client_secret=reddit_client_secret,
                user_agent=reddit_user_agent
            )
            
            logger.info(f"Reddit API connected, read-only mode: {reddit.read_only}")
            
            # Search UK-specific subreddits only
            uk_subreddits = "unitedkingdom+uk+london+manchester+birmingham+glasgow+edinburgh+liverpool+bristol+leeds+casualuk+britishproblems+askuk"
            
            logger.info("Searching UK subreddits only...")
            submissions = list(reddit.subreddit(uk_subreddits).search(keyword, limit=1000, sort="new"))
            logger.info(f"Found {len(submissions)} total submissions")
            
            # Print ALL submissions found (first 20)
            logger.info("ALL Reddit submissions found:")
            for i, sub in enumerate(submissions[:20]):
                created = datetime.fromtimestamp(sub.created_utc).strftime('%Y-%m-%d %H:%M:%S')
                title = sub.title[:100] + "..." if len(sub.title) > 100 else sub.title
                logger.info(f"      {i+1}. [{created}] {title} (r/{sub.subreddit}) - Score: {sub.score}")
            
            if len(submissions) > 20:
                logger.info(f"... and {len(submissions) - 20} more submissions")
            
            # Filter by date range
            filtered_count = 0
            in_range_submissions = []
            for submission in submissions:
                if start_ts <= submission.created_utc <= end_ts:
                    filtered_count += 1
                    in_range_submissions.append(submission)
            
            logger.info(f"{filtered_count} submissions within date range ({start_date} to {end_date})")
            
            # Create detailed post data
            posts_to_return = in_range_submissions if in_range_submissions else submissions[:10]
            
            detailed_posts = []
            for sub in posts_to_return:
                # Calculate relevance score
                relevance_score = calculate_relevance_score(sub.title, keyword)
                
                detailed_posts.append({
                    "title": sub.title,
                    "subreddit": str(sub.subreddit),
                    "author": str(sub.author) if sub.author else "[deleted]",
                    "score": sub.score,
                    "num_comments": sub.num_comments,
                    "created_utc": sub.created_utc,
                    "created_date": datetime.fromtimestamp(sub.created_utc).strftime('%Y-%m-%d %H:%M:%S'),
                    "url": f"https://reddit.com{sub.permalink}",
                    "relevance_score": relevance_score,
                    "in_date_range": start_ts <= sub.created_utc <= end_ts
                })
            
            # If no posts in target date range, return empty result
            if filtered_count == 0:
                logger.info("No posts found in target date range")
                logger.info("Returning empty result (only posts within specified date range are included)")
                
                return {
                    "count": 0,
                    "posts": [],
                    "in_date_range": 0,
                    "source": "reddit_api",
                    "total_posts_found": len(detailed_posts),
                    "relevance_threshold": 90
                }
            
            # Log submissions in date range
            if in_range_submissions:
                logger.info("   Submissions within target date range:")
                for i, post in enumerate(detailed_posts[:10]):
                    if post['in_date_range']:
                        logger.info(f"      {i+1}. [{post['created_date']}] {post['title'][:100]}... (r/{post['subreddit']}) - Score: {post['score']}, Relevance: {post['relevance_score']}")
            
            # Filter posts by high relevance (90+) AND within date range
            posts_in_range = [p for p in detailed_posts if p['in_date_range']]
            high_relevance_posts_in_range = [p for p in posts_in_range if p['relevance_score'] >= 90]
            
            logger.info(f"Filtered to {len(high_relevance_posts_in_range)} high-relevance posts (90+ score) within date range from {len(detailed_posts)} total")
            
            return {
                "count": len(high_relevance_posts_in_range),
                "posts": high_relevance_posts_in_range,
                "in_date_range": len(high_relevance_posts_in_range),
                "source": "reddit_api",
                "total_posts_found": len(detailed_posts),
                "posts_in_date_range": len(posts_in_range),
                "relevance_threshold": 90
            }
            
        except Exception as e:
            logger.error(f"Reddit API failed: {e}")
    else:
        logger.info("Reddit API credentials not available or praw not installed")
    
    # No Reddit API available
    logger.info("   Reddit API credentials not available")
    return {"count": 0, "posts": [], "in_date_range": 0, "source": "no_api"}



def fetch_google_trends_score(keyword: str, start_date: datetime, end_date: datetime) -> Optional[Union[Dict[str, Any], int]]:
    """
    Uses pytrends to get interest_over_time and returns a normalized 0-100 score for the date range (max over range).
    If pytrends not available, returns None.
    """
    logger.info(f"Starting Google Trends search for keyword: '{keyword}'")
    logger.info(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if TrendReq is None:
        logger.warning("   pytrends not available")
        return None
    
    try:
        pytrends = TrendReq(hl="en-UK", tz=0)
        timeframe = f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"
        logger.info(f"Building payload with timeframe: {timeframe}")
        
        pytrends.build_payload([keyword], timeframe=timeframe)
        logger.info("Fetching interest over time data...")
        
        df = pytrends.interest_over_time()
        logger.info(f"Retrieved dataframe with {len(df)} rows")
        
        if df.empty:
            logger.warning("No data returned from Google Trends")
            return
        
        # Log some sample data points
        if len(df) > 0:
            logger.info(f"   Sample data points:")
            for i, (date, row) in enumerate(df.head(3).iterrows()):
                score = row[keyword] if keyword in row else 0
                logger.info(f"{i+1}. {date.strftime('%Y-%m-%d')}: {score}")
        
        # Extract detailed trend data
        max_score = int(df[keyword].max())
        avg_score = int(df[keyword].mean())
        min_score = int(df[keyword].min())
        
        # Get all daily data points
        daily_data = []
        for date, row in df.iterrows():
            daily_data.append({
                "date": date.strftime('%Y-%m-%d'),
                "score": int(row[keyword])
            })
        
        # Calculate trend direction (comparing first and last values)
        if len(daily_data) >= 2:
            trend_direction = "increasing" if daily_data[-1]["score"] > daily_data[0]["score"] else "decreasing"
            if daily_data[-1]["score"] == daily_data[0]["score"]:
                trend_direction = "stable"
        else:
            trend_direction = "unknown"
        
        logger.info(f"Google Trends scores - Max: {max_score}, Average: {avg_score}, Trend: {trend_direction}")
        
        return {
            "max_score": max_score,
            "avg_score": avg_score,
            "min_score": min_score,
            "trend_direction": trend_direction,
            "total_days": len(daily_data),
            "timeframe": timeframe,
            "daily_data": daily_data
        }
        
    except Exception as e:
        logger.error(f"Google Trends error: {e}")
        return None

def iso_to_unix(dt_iso: str) -> int:
    dt = datetime.fromisoformat(dt_iso)
    return int(dt.timestamp())

def create_output_filename(keyword: str, current_time: datetime) -> str:
    """
    Create output filename in format: {search_name}_{date_time}_search_output.json
    """
    # Clean keyword for filename (remove spaces, special chars)
    search_name = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).rstrip()
    search_name = search_name.replace(' ', '_').lower()
    
    # Format datetime as YYYYMMDD_HHMMSS
    date_time = current_time.strftime("%Y%m%d_%H%M%S")
    
    return f"{search_name}_{date_time}_search_output.json"

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract event popularity signals from multiple sources")
    parser.add_argument("--keyword", required=True, help="Search keyword (e.g., 'Taylor Swift')")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD (single date) or start_date,end_date")
    parser.add_argument("--eventbrite_token", default=os.getenv("EVENTBRITE_TOKEN"), help="Eventbrite API token (deprecated)")
    parser.add_argument("--out", default=None, help="Custom output JSON file (optional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create Results directory if it doesn't exist
    results_dir = "Results"
    os.makedirs(results_dir, exist_ok=True)
    
    # Generate output filename if not provided
    current_time = datetime.now()
    if args.out is None:
        filename = create_output_filename(args.keyword, current_time)
        output_path = os.path.join(results_dir, filename)
    else:
        output_path = args.out

    logger.info("=" * 80)
    logger.info("CITISENSE EVENT POPULARITY EXTRACTION")
    logger.info("=" * 80)
    logger.info(f"Keyword: '{args.keyword}'")
    logger.info(f"Date input: {args.date}")
    logger.info(f"Output file: {output_path}")

    # parse date input
    if "," in args.date:
        start = datetime.fromisoformat(args.date.split(",")[0])
        end = datetime.fromisoformat(args.date.split(",")[1])
        logger.info(f"Parsed date range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    else:
        start = datetime.fromisoformat(args.date)
        end = start + timedelta(days=1)
        logger.info(f"Parsed single date: {start.strftime('%Y-%m-%d')} (24-hour window)")

    logger.info("\n" + "=" * 80)

    # Eventbrite
    logger.info("EVENTBRITE EXTRACTION")
    logger.info("-" * 40)
    try:
        eb_data = fetch_eventbrite_count(args.keyword, start_date=start, end_date=end, token=args.eventbrite_token)
        if isinstance(eb_data, dict):
            eb_count = eb_data['count']
            logger.info(f"Eventbrite result: {eb_count} events")
        else:
            eb_count = eb_data
            eb_data = {"count": eb_count, "events": [], "source": "eventbrite_scrape"}
            logger.info(f"Eventbrite result: {eb_count} events")
    except Exception as e:
        logger.error(f"Eventbrite fetch error: {e}")
        eb_count = None
        eb_data = {"count": 0, "events": [], "error": str(e)}

    logger.info("\n" + "=" * 80)

    # Reddit mentions
    logger.info("REDDIT EXTRACTION")
    logger.info("-" * 40)
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    try:
        reddit_data = fetch_reddit_mentions(args.keyword, start_ts, end_ts)
        if isinstance(reddit_data, dict):
            reddit_count = reddit_data['count']
            logger.info(f"Reddit result: {reddit_count} posts ({reddit_data['in_date_range']} in date range)")
        else:
            reddit_count = reddit_data
            logger.info(f"Reddit result: {reddit_count} mentions")
    except Exception as e:
        logger.error(f"Reddit fetch error: {e}")
        reddit_data = {"count": 0, "posts": [], "error": str(e)}
        reddit_count = 0

    logger.info("\n" + "=" * 80)

    # Google Trends
    logger.info("GOOGLE TRENDS EXTRACTION")
    logger.info("-" * 40)
    try:
        gt_raw = fetch_google_trends_score(args.keyword, start, end)
        if isinstance(gt_raw, dict):
            gt_data = gt_raw
            logger.info(f"Google Trends result: Max {gt_data['max_score']}, Avg {gt_data['avg_score']}, Trend: {gt_data['trend_direction']}")
        elif gt_raw is not None:
            # Handle simple numeric score
            gt_data = {
                "max_score": gt_raw,
                "avg_score": gt_raw,
                "trend_direction": "stable",
                "data_type": "simple_score"
            }
            logger.info(f"Google Trends result: {gt_raw} (simple score)")
        else:
            gt_data = None
            logger.info("Google Trends result: No data available")
    except Exception as e:
        logger.error(f"Google Trends error: {e}")
        gt_data = {"error": str(e), "max_score": None}

    logger.info("\n" + "=" * 80)
    logger.info("FINAL RESULTS")
    logger.info("-" * 40)

    out = {
        "keyword": args.keyword,
        "summary": {
            "eventbrite_events": eb_count,
            "reddit_mentions": reddit_count,
            "google_trends_score": gt_data.get("max_score") if isinstance(gt_data, dict) else gt_data
        },
        "detailed_data": {
            "eventbrite": eb_data,
            "reddit": reddit_data,
            "google_trends": gt_data
        },
        "date": start.strftime("%Y-%m-%d"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "search_metadata": {
            "search_duration_seconds": (datetime.now() - current_time).total_seconds(),
            "date_range": f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}",
            "sources_attempted": ["eventbrite", "reddit", "google_trends"],
            "sources_successful": [
                source for source, result in [
                    ("eventbrite", eb_count is not None),
                    ("reddit", reddit_count is not None), 
                    ("google_trends", gt_data is not None)
                ] if result
            ]
        }
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved results to: {output_path}")
    logger.info("Final JSON output:")
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()