# feeds.py
# RADAR icin takip edilen RSS kaynaklari: (kaynak_adi, rss_url)
# Calismayan bir feed sessizce atlanir; istedigini ekle/cikar.

FEEDS = [
    # --- TURKIYE: girisim & yatirim ---
    ("Google Haber TR — Girişim/Yatırım",
     "https://news.google.com/rss/search?q=startup%20yat%C4%B1r%C4%B1m%20giri%C5%9Fim%20when%3A2d&hl=tr&gl=TR&ceid=TR:tr"),
    ("Google Haber TR — Yatırım Turu",
     "https://news.google.com/rss/search?q=giri%C5%9Fim%20%22yat%C4%B1r%C4%B1m%20turu%22%20when%3A3d&hl=tr&gl=TR&ceid=TR:tr"),

    # --- Startup & Girisimcilik & Yatirim (yabanci) ---
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
