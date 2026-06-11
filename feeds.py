# feeds.py
# RADAR icin takip edilen RSS kaynaklari.
# Yeni kaynak eklemek icin sadece bu listeyi duzenle: (kaynak_adi, rss_url)
# Calismayan bir feed olursa radar.py onu sessizce atlar, digerleri etkilenmez.

FEEDS = [
    # --- Startup & Girisimcilik & Yatirim ---
    ("TechCrunch",            "https://techcrunch.com/feed/"),
    ("TechCrunch Startups",   "https://techcrunch.com/category/startups/feed/"),
    ("TechCrunch Venture",    "https://techcrunch.com/category/venture/feed/"),
    ("Crunchbase News",       "https://news.crunchbase.com/feed/"),
    ("VentureBeat",           "https://venturebeat.com/feed/"),
    ("a16z",                  "https://a16z.com/feed/"),

    # --- Yapay Zeka ---
    ("TechCrunch AI",         "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI",        "https://venturebeat.com/category/ai/feed/"),
    ("The Verge",             "https://www.theverge.com/rss/index.xml"),
    ("MIT Tech Review",       "https://www.technologyreview.com/feed/"),

    # --- Erken sinyal / urun lansmanlari ---
    ("Hacker News (front)",   "https://hnrss.org/frontpage?points=150"),
    ("Hacker News (Show HN)", "https://hnrss.org/show"),
    ("Product Hunt",          "https://www.producthunt.com/feed"),
]
