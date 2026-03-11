RSS_FEEDS = {
    "#tech": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
    ],
    "#ai": [
        "https://venturebeat.com/category/ai/feed/",
        "https://feeds.technologyreview.com/the_download.rss",
    ],
    "#privacy": [
        "https://www.eff.org/rss/updates.xml",
        "https://www.wired.com/feed/category/security/latest/rss",
    ],
    "#software": [
        "https://hnrss.org/frontpage",
        "https://www.infoq.com/feed/",
    ],
    "#techcompanies": [
        "https://feeds.reuters.com/reuters/technologyNews",
        "https://feeds.bloomberg.com/technology/news.rss",
    ],
    "#hardware": [
        "https://www.anandtech.com/rss/",
        "https://www.tomshardware.com/feeds/all",
    ],
}

POSTS_PER_RUN_MIN = 3
POSTS_PER_RUN_MAX = 10
MAX_STORED_IDS = 1000  # keep posted_ids.json from growing forever

GEMINI_MODEL = "gemini-2.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

POSTED_IDS_FILE = "posted_ids.json"
