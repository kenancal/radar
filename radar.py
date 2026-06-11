# radar.py
# RADAR - Gunluk teknoloji & girisim & yatirim radari (Webrazzi tarzi kartli surum).
#
# Akis:
#   1) feeds.py'deki RSS kaynaklarindan son ~30 saatin haberlerini ceker (gorselleriyle).
#   2) Bir LLM (Gemini ucretsiz ya da OpenAI) ile haberleri "Turkiye'de hayata
#      gecirilebilir is firsati" gozuyle eler, siralar ve TURKCE ozetler.
#   3) Kartli, okunakli bir HTML bulten olusturur (kategori + baslik + ozet + kaynak + gorsel).
#   4) Bulteni mail atar VE archive/<tarih>.html olarak kaydeder.
#   5) index.html arsiv tarayicisini gunceller (gun gun secim).
#
# LLM anahtari:
#   GEMINI_API_KEY  (ucretsiz; aistudio.google.com/app/apikey)  -> oncelikli
#   ya da OPENAI_API_KEY
#   Ikisi de yoksa: ham basliklar (cevirisiz) gonderilir.
#
# Ortam degiskenleri:
#   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO   (zorunlu)
#   GEMINI_API_KEY ya da OPENAI_API_KEY                   (Turkce kurasyon icin)
#   LLM_MODEL    (ops. - Gemini'de gemini-2.5-flash, OpenAI'de gpt-4o-mini)
#   SITE_URL     (ops. - GitHub Pages adresi; mailde arsiv linki cikar)
#   LOOKBACK_HOURS (ops, 30), MAX_ITEMS_TO_LLM (ops, 60)

import os
import re
import json
import glob
import html
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate

import feedparser
from dateutil import parser as dateparser

from feeds import FEEDS

USER_AGENT = "RadarBot/1.0 (+daily tech briefing)"
TZ_OFFSET = dt.timedelta(hours=3)        # Europe/Istanbul, UTC+3
ARCHIVE_DIR = "archive"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

# Renkler
EMERALD = "#00A86B"
NAVY    = "#10243a"
INK     = "#5f6b76"
MUTED   = "#9aa6ad"
EYEBROW = "#8893a0"
GOLD    = "#f0b429"
LINE    = "#e6eaec"
PAGE_BG = "#eceff2"
CARD    = "#ffffff"
SANS    = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

SIGNAL_COLOR = {"Yuksek": EMERALD, "Yüksek": EMERALD, "Orta": "#d98a16",
                "Dusuk": MUTED, "Düsuk": MUTED, "Düşük": MUTED}

# Karar etiketi renkleri: (yazi, arka plan)
KARAR_COLOR = {
    "Kesinlikle denenmeli": ("#0a7d4f", "#e3f7ee"),
    "Denenebilir":          ("#0a7d4f", "#eafaf2"),
    "Potansiyel vaat ediyor": ("#1769a8", "#e7f1fb"),
    "Potansiyel vaad ediyor": ("#1769a8", "#e7f1fb"),
    "Araştırılmalı":        ("#a76a08", "#fdf3e0"),
    "Arastirilmali":        ("#a76a08", "#fdf3e0"),
    "Türkiye'de zaten var": ("#6b7680", "#eef1f3"),
    "Turkiye'de zaten var": ("#6b7680", "#eef1f3"),
}

TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _load_dotenv():
    if not os.path.exists(".env"):
        return
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def tr_long_date(d: dt.date) -> str:
    return f"{d.day} {TR_MONTHS[d.month]} {d.year}, {TR_DAYS[d.weekday()]}"


def _clip(text, n=130):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= n else text[:n].rstrip() + "…"


# ----------------------------- 1) Haberleri cek (gorselleriyle) -----------------------------

def _extract_image(entry):
    for key in ("media_content", "media_thumbnail"):
        val = entry.get(key)
        if isinstance(val, list):
            for m in val:
                u = m.get("url")
                if u and u.startswith("http"):
                    return u
    for l in entry.get("links", []):
        if l.get("rel") == "enclosure" and str(l.get("type", "")).startswith("image") and l.get("href"):
            return l["href"]
    blob = ""
    if entry.get("content"):
        try:
            blob = entry["content"][0].get("value", "")
        except Exception:
            pass
    blob += entry.get("summary", "") or entry.get("description", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob)
    if m and m.group(1).startswith("http"):
        return m.group(1)
    return None


def fetch_entries(lookback_hours: int):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    seen_urls, seen_titles, items = set(), set(), []

    for source_name, url in FEEDS:
        try:
            parsed = feedparser.parse(url, agent=USER_AGENT)
        except Exception as e:
            print(f"[uyari] feed okunamadi: {source_name} -> {e}")
            continue

        for entry in parsed.entries:
            link = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not link or not title:
                continue

            published = None
            for key in ("published", "updated", "created"):
                if entry.get(key):
                    try:
                        published = dateparser.parse(entry[key]); break
                    except Exception:
                        pass
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            if published is not None and published < cutoff:
                continue

            norm_title = re.sub(r"\s+", " ", title.lower())
            if link in seen_urls or norm_title in seen_titles:
                continue
            seen_urls.add(link); seen_titles.add(norm_title)

            summary = entry.get("summary", "") or entry.get("description", "")
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = html.unescape(re.sub(r"\s+", " ", summary)).strip()[:400]

            items.append({
                "source": source_name, "title": html.unescape(title),
                "url": link, "summary": summary, "published": published,
                "image": _extract_image(entry),
            })

    items.sort(key=lambda x: x["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
               reverse=True)
    print(f"[bilgi] {len(items)} benzersiz haber toplandi.")
    return items


# ----------------------------- 2) LLM kurasyon (Gemini ucretsiz / OpenAI) -----------------------------

CURATION_SYSTEM_PROMPT = """Sen deneyimli bir teknoloji ve girisim analistisin.
Gorevin: gunluk haber akisindan, IS FIRSATI sinyali tasiyan haberleri secmek, siralamak,
TURKCE ozetlemek ve Turkiye acisindan DEGERLENDIRMEK. Tum ciktilar akici Turkce olmali.

Kapsam:
- Yabanci (ABD/Avrupa) yeni startuplar, yatirimlar, satin almalar, yapay zeka gelismeleri.
- AYRICA Turkiye'de kurulan startuplar ve Turkiye'deki yatirim turlari/anlasmalar (Webrazzi,
  Google Haber TR kaynaklari). Bunlari da MUTLAKA degerlendir, atlamadan dahil et.

Salt magazin, borsa dedikodusu ve net is sinyali olmayan haberleri ELE. En guclu 8-14 maddeyi sec.

Her madde icin Turkiye degerlendirmesi yap:
- uygulanabilirlik_puani: 0-10 tam sayi. Is modelinin/teknolojinin Turkiye'de hayata
  gecirilmesinin ne kadar kolay/uygulanabilir oldugu (kaynak, regulasyon, altyapi, sermaye).
- tutma_olasiligi_puani: 0-10 tam sayi. Boyle bir girisimin Turkiye pazarinda tutma,
  buyume ve para kazanma olasiligi (talep, odeme aliskanligi, rekabet).
- karar: su SECENEKLERDEN BIRI (aynen yaz):
  "Kesinlikle denenmeli" | "Denenebilir" | "Arastirilmali" | "Potansiyel vaat ediyor" | "Turkiye'de zaten var"
  (Turkiye'de bu is zaten yapiliyorsa "Turkiye'de zaten var" de.)
- turkiye_acisi: Turkiye'de nasil uyarlanabilir / hangi spesifik firsati acar, 1-2 cumle.
- yatirim_firsati: yatirim acisindan kisa not (fonlanabilir mi, hangi asama/tutar mantikli,
  kim ilgilenir), 1 cumle.

SADECE su semada gecerli bir JSON dondur, baska metin yazma:
{
  "gun_ozeti": "2-3 cumlede gunun ana temasi",
  "maddeler": [
    {
      "kategori": "Startup | Yatirim | Yapay Zeka | Trend",
      "baslik": "haberin Turkce, net basligi",
      "kaynak": "kaynak adi",
      "url": "verilen orijinal url'yi AYNEN kullan",
      "ozet_tr": "1-2 cumle Turkce ozet",
      "uygulanabilirlik_puani": 0,
      "tutma_olasiligi_puani": 0,
      "karar": "Denenebilir",
      "turkiye_acisi": "...",
      "yatirim_firsati": "...",
      "sinyal": "Yuksek | Orta | Dusuk"
    }
  ]
}"""


def _llm_client_and_model():
    try:
        from openai import OpenAI
    except Exception as e:
        print(f"[uyari] openai paketi yuklenemedi: {e}")
        return None, None, None
    gem = os.environ.get("GEMINI_API_KEY")
    if gem:
        model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
        return OpenAI(api_key=gem, base_url=GEMINI_BASE), model, "gemini"
    oa = os.environ.get("OPENAI_API_KEY")
    if oa:
        model = os.environ.get("LLM_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
        return OpenAI(api_key=oa), model, "openai"
    return None, None, None


def _parse_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*", "", raw).strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e != -1:
        raw = raw[s:e + 1]
    return json.loads(raw)


def curate_with_llm(items):
    client, model, provider = _llm_client_and_model()
    if client is None:
        print("[bilgi] LLM anahtari yok (GEMINI_API_KEY/OPENAI_API_KEY) -> ham liste gonderilecek.")
        return None

    url_to_image = {it["url"]: it.get("image") for it in items}
    payload = [{"source": it["source"], "title": it["title"], "url": it["url"],
                "summary": it["summary"]} for it in items]
    messages = [
        {"role": "system", "content": CURATION_SYSTEM_PROMPT},
        {"role": "user", "content": "Bugunun haber akisi (JSON):\n\n"
         + json.dumps(payload, ensure_ascii=False)},
    ]

    raw = None
    for use_rf in (True, False):     # once json_object dene; desteklenmezse formatsiz dene
        try:
            kwargs = dict(model=model, temperature=0.4, messages=messages)
            if use_rf:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content
            break
        except Exception as e:
            print(f"[uyari] LLM denemesi (response_format={use_rf}) hata: {e}")
    if not raw:
        return None

    try:
        data = _parse_json(raw)
    except Exception as e:
        print(f"[uyari] JSON cozulemedi: {e}")
        return None

    maddeler = data.get("maddeler") or []
    if not maddeler:
        print("[uyari] LLM bos sonuc dondu.")
        return None
    for m in maddeler:
        m["_image"] = url_to_image.get(m.get("url", ""))
    print(f"[bilgi] LLM ({provider}/{model}) {len(maddeler)} madde secti.")
    return data


# ----------------------------- 3) Kartli HTML bulten -----------------------------

def _shell(date_long: str, intro_html: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RADAR · {html.escape(date_long)}</title></head>
<body style="margin:0;padding:0;background:{PAGE_BG};">
<div style="max-width:640px;margin:0 auto;padding:20px 14px 44px;font-family:{SANS};">
  <!--TOPBAR-->
  {intro_html}
  {body_html}
  <div style="text-align:center;font-size:12px;color:{MUTED};margin-top:24px;line-height:1.6;">
    RADAR · Her başlık orijinal kaynağa link verir.
  </div>
</div></body></html>"""


def _intro_card(date_long: str, ozet: str) -> str:
    ozet_html = (f'<div style="font-size:14px;color:{INK};line-height:1.65;">{html.escape(ozet)}</div>'
                 if ozet else
                 f'<div style="font-size:14px;color:{INK};line-height:1.65;">'
                 f'Günün öne çıkan teknoloji, girişim ve yatırım gelişmelerini aşağıda bulabilirsin. '
                 f'Her başlık kaynağa link verir; detay için tıkla.</div>')
    return (f'<div style="background:{CARD};border-radius:14px;padding:22px 24px;margin-bottom:16px;'
            f'box-shadow:0 1px 2px rgba(16,36,58,.05);">'
            f'<div style="font-size:19px;font-weight:800;color:{NAVY};margin-bottom:10px;">'
            f'<span style="color:{EMERALD};">●</span> RADAR · Güncel Haberler · '
            f'<span style="color:{INK};font-weight:600;">{html.escape(date_long)}</span></div>'
            f'{ozet_html}</div>')


def _verdict_badge(karar):
    if not karar:
        return ""
    fg, bg = KARAR_COLOR.get(karar, ("#a76a08", "#fdf3e0"))
    return (f'<span style="display:inline-block;background:{bg};color:{fg};font-size:12px;'
            f'font-weight:700;padding:4px 11px;border-radius:20px;margin:0 6px 6px 0;'
            f'white-space:nowrap;">{html.escape(karar)}</span>')


def _score_pill(label, val):
    try:
        v = int(round(float(val)))
    except (TypeError, ValueError):
        return ""
    col = EMERALD if v >= 7 else ("#d98a16" if v >= 4 else "#c0492b")
    return (f'<span style="display:inline-block;background:#f3f5f6;color:#48535d;font-size:12px;'
            f'font-weight:600;padding:3px 10px;border-radius:20px;margin:0 6px 6px 0;white-space:nowrap;">'
            f'<span style="color:{col};">●</span> {html.escape(label)} <b style="color:{NAVY};">{v}</b>/10</span>')


def _card(m) -> str:
    url = html.escape(m.get("url") or "#")
    kategori = m.get("kategori") or "Trend"
    baslik = m.get("baslik") or ""
    ozet = m.get("ozet_tr") or ""
    turkiye = m.get("turkiye_acisi")
    yatirim = m.get("yatirim_firsati")
    kaynak = m.get("kaynak") or ""
    sinyal = m.get("sinyal")
    karar = m.get("karar")
    uyg = m.get("uygulanabilirlik_puani")
    tutma = m.get("tutma_olasiligi_puani")
    image = m.get("_image")
    sig_col = SIGNAL_COLOR.get(sinyal, "#d98a16")

    eyebrow = (f'<div style="margin:0 0 9px;">'
               f'<span style="display:inline-block;width:20px;height:3px;background:{GOLD};'
               f'border-radius:2px;vertical-align:middle;margin-right:8px;"></span>'
               f'<span style="font-size:11px;font-weight:700;letter-spacing:1.2px;color:{EYEBROW};'
               f'text-transform:uppercase;vertical-align:middle;">{html.escape(kategori)}</span></div>')
    headline = (f'<a href="{url}" style="display:block;font-size:18px;font-weight:700;color:{NAVY};'
                f'text-decoration:none;line-height:1.35;margin:0 0 10px;">{html.escape(baslik)}</a>')
    teaser = (f'<div style="font-size:14px;color:{INK};line-height:1.55;margin:0 0 11px;">{html.escape(_clip(ozet))}</div>'
              if ozet else "")

    assess = ""
    badges = _verdict_badge(karar) + _score_pill("Uygulanabilirlik", uyg) + _score_pill("Türkiye’de tutma", tutma)
    if badges:
        assess = f'<div style="margin:0 0 11px;">{badges}</div>'

    tr_line = (f'<div style="font-size:13px;color:{EMERALD};line-height:1.5;margin:0 0 8px;">'
               f'<b>Türkiye fırsatı</b> · {html.escape(turkiye)}</div>' if turkiye else "")
    yat_line = (f'<div style="font-size:13px;color:{INK};line-height:1.5;margin:0 0 12px;">'
                f'<b style="color:{NAVY};">Yatırım fırsatı</b> · {html.escape(yatirim)}</div>' if yatirim else "")
    source = (f'<div style="font-size:12px;color:{MUTED};">'
              f'{html.escape(kaynak)} &nbsp;·&nbsp; '
              f'<a href="{url}" style="color:{EMERALD};text-decoration:none;font-weight:700;">Kaynağa git →</a>'
              + (f' &nbsp;·&nbsp; <span style="color:{sig_col};font-weight:700;">● {html.escape(sinyal)}</span>'
                 if sinyal else "") + '</div>')

    text_pad = "padding-right:16px;" if image else ""
    img_td = ""
    if image:
        img_td = (f'<td valign="top" width="156" align="right">'
                  f'<img src="{html.escape(image)}" width="150" '
                  f'style="width:150px;height:auto;max-height:120px;border-radius:10px;display:block;border:0;object-fit:cover;"></td>')

    return (f'<div style="background:{CARD};border-radius:14px;padding:18px 20px;margin-bottom:14px;'
            f'box-shadow:0 1px 2px rgba(16,36,58,.05);">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;"><tr>'
            f'<td valign="top" style="{text_pad}">{eyebrow}{headline}{teaser}{assess}{tr_line}{yat_line}{source}</td>'
            f'{img_td}</tr></table></div>')


def build_html_curated(data, date_long) -> str:
    intro = _intro_card(date_long, data.get("gun_ozeti", ""))
    cards = "".join(_card(m) for m in data["maddeler"])
    return _shell(date_long, intro, cards)


def build_html_raw(items, date_long) -> str:
    intro = _intro_card(
        date_long,
        "Not: Türkçe özet/değerlendirme için LLM anahtarı bulunamadı, ham başlıklar listeleniyor. "
        "GEMINI_API_KEY ekleyince bültenler Türkçe ve puanlı gelecek.")
    cards = "".join(_card({
        "kategori": it["source"], "baslik": it["title"], "url": it["url"],
        "ozet_tr": it["summary"], "kaynak": it["source"], "_image": it.get("image"),
    }) for it in items[:40])
    return _shell(date_long, intro, cards)


# ----------------------------- 4) Arsiv + index -----------------------------

def save_archive(html_full: str, date_iso: str) -> str:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    back = (f'<div style="margin-bottom:14px;"><a href="../index.html" '
            f'style="font-size:13px;color:{MUTED};text-decoration:none;">← Tüm bültenler</a></div>')
    page = html_full.replace("<!--TOPBAR-->", back, 1)
    path = os.path.join(ARCHIVE_DIR, f"{date_iso}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[bilgi] Arsiv yazildi -> {path}")
    return path


def rebuild_index():
    files = sorted(glob.glob(os.path.join(ARCHIVE_DIR, "*.html")), reverse=True)
    dates = []
    for fp in files:
        name = os.path.splitext(os.path.basename(fp))[0]
        try:
            dates.append((name, dt.date.fromisoformat(name)))
        except ValueError:
            continue

    options = "\n".join(f'        <option value="{iso}">{html.escape(tr_long_date(d))}</option>'
                        for iso, d in dates)
    cards = "\n".join(
        f'''      <a class="day" href="archive/{iso}.html">
        <span class="day-date">{html.escape(tr_long_date(d))}</span>
        <span class="day-go">Bülteni aç →</span></a>''' for iso, d in dates)
    latest = (f'<p class="sub">En son bülten: <a href="archive/{dates[0][0]}.html">'
              f'{html.escape(tr_long_date(dates[0][1]))}</a></p>' if dates else "")

    css = """
    :root{--emerald:#00A86B;--navy:#10243a;--ink:#5f6b76;--muted:#9aa6ad;--line:#e6eaec;--bg:#eceff2;--card:#fff;}
    *{box-sizing:border-box;}
    body{margin:0;background:var(--bg);color:var(--ink);
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}
    .wrap{max-width:640px;margin:0 auto;padding:34px 16px 60px;}
    .brand{font-size:26px;font-weight:800;color:var(--navy);}
    .brand .dot{color:var(--emerald);}
    .tag{font-size:13px;color:var(--muted);margin:4px 0 0;}
    .sub{font-size:14px;margin:10px 0 0;color:var(--navy);}
    .sub a{color:var(--emerald);text-decoration:none;font-weight:700;}
    .picker{margin:24px 0 28px;padding:18px 20px;background:var(--navy);border-radius:14px;}
    .picker label{display:block;color:#cfe6da;font-size:13px;margin-bottom:8px;}
    .picker select{width:100%;padding:12px 14px;border-radius:10px;border:none;font-size:15px;
      font-family:inherit;color:var(--navy);background:#fff;}
    .list h2{font-size:13px;color:var(--muted);font-weight:700;text-transform:uppercase;
      letter-spacing:1px;margin:0 0 12px;}
    .day{display:flex;justify-content:space-between;align-items:center;text-decoration:none;
      background:var(--card);border-radius:12px;padding:16px 20px;margin-bottom:10px;
      box-shadow:0 1px 2px rgba(16,36,58,.05);}
    .day-date{font-size:16px;color:var(--navy);font-weight:700;}
    .day-go{font-size:13px;color:var(--emerald);font-weight:700;}
    .empty{color:var(--muted);font-size:15px;}
    .foot{margin-top:34px;text-align:center;font-size:12px;color:var(--muted);}
    """
    body_list = (f'<div class="list"><h2>Tüm bültenler</h2>{cards}</div>' if dates
                 else '<p class="empty">Henüz bülten yok. İlk bülten geldiğinde burada listelenecek.</p>')

    page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RADAR · Arşiv</title><style>{css}</style></head>
<body><div class="wrap">
  <div class="brand"><span class="dot">●</span> RADAR</div>
  <p class="tag">Günlük teknoloji &amp; girişim &amp; yatırım bülteni — arşiv</p>
  {latest}
  <div class="picker"><label for="day">Bir güne git</label>
    <select id="day" onchange="if(this.value)location.href='archive/'+this.value+'.html';">
        <option value="">— tarih seç —</option>
{options}
    </select></div>
  {body_list}
  <div class="foot">Otomatik olarak her gün güncellenir. RADAR.</div>
</div></body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[bilgi] index.html guncellendi ({len(dates)} bulten).")


# ----------------------------- 5) Mail -----------------------------

def send_email(subject: str, html_body: str):
    host = os.environ["SMTP_HOST"]; port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]; password = os.environ["SMTP_PASS"]
    mail_to = os.environ["MAIL_TO"]

    site = os.environ.get("SITE_URL", "").strip()
    topbar = (f'<div style="margin-bottom:14px;"><a href="{html.escape(site)}" '
              f'style="font-size:13px;color:{MUTED};text-decoration:none;">↗ Arşivde tüm bültenler</a></div>'
              if site else "")
    body = html_body.replace("<!--TOPBAR-->", topbar, 1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject; msg["From"] = user; msg["To"] = mail_to
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText("RADAR bulteni HTML formatindadir.", "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port) as s:
            s.login(user, password); s.sendmail(user, mail_to.split(","), msg.as_string())
    else:
        with smtplib.SMTP(host, port) as s:
            s.starttls(); s.login(user, password); s.sendmail(user, mail_to.split(","), msg.as_string())
    print(f"[bilgi] Mail gonderildi -> {mail_to}")


# ----------------------------- main -----------------------------

def main():
    _load_dotenv()
    lookback = int(os.environ.get("LOOKBACK_HOURS", "30"))
    max_items = int(os.environ.get("MAX_ITEMS_TO_LLM", "60"))

    now_local = dt.datetime.now(dt.timezone.utc) + TZ_OFFSET
    date_iso = now_local.strftime("%Y-%m-%d")
    date_long = tr_long_date(now_local.date())

    items = fetch_entries(lookback)
    if not items:
        print("[bilgi] Yeni haber yok; index yine de guncelleniyor.")
        rebuild_index(); return

    data = curate_with_llm(items[:max_items])
    if data:
        html_body = build_html_curated(data, date_long)
        subject = f"RADAR · {date_long} · {len(data['maddeler'])} fırsat sinyali"
    else:
        html_body = build_html_raw(items, date_long)
        subject = f"RADAR · {date_long} · {min(len(items),40)} başlık"

    save_archive(html_body, date_iso)
    rebuild_index()
    try:
        send_email(subject, html_body)
    except Exception as e:
        print(f"[uyari] Mail gonderilemedi ({e}); arsiv yine de kaydedildi.")


if __name__ == "__main__":
    main()
