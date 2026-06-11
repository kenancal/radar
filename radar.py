# radar.py
# RADAR - Gunluk teknoloji & girisim & yatirim radari (arsivli surum).
#
# Ne yapar:
#   1) feeds.py'deki RSS kaynaklarindan son ~30 saatin haberlerini ceker.
#   2) Bir LLM ile haberleri "Turkiye'de hayata gecirilebilir is firsati" gozuyle
#      eler, siralar ve Turkce ozetler (her madde kaynak linkiyle birlikte).
#   3) Okunakli bir HTML bulten olusturur.
#   4) Bulteni hem mail atar HEM DE archive/<tarih>.html olarak kaydeder.
#   5) index.html arsiv tarayicisini yeniden olusturur (gun gun secim).
#
# GitHub Actions her gun calistiginda archive/ + index.html repoya commit edilir,
# GitHub Pages ile site olarak yayinlanir. Boylece hicbir bulten kaybolmaz.
#
# Calistirma (lokal test):
#   pip install -r requirements.txt
#   python radar.py
#
# Ortam degiskenleri:
#   SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO   (zorunlu - mail icin)
#   OPENAI_API_KEY                                        (opsiyonel - LLM kurasyonu)
#   OPENAI_MODEL                                          (opsiyonel - varsayilan gpt-4o-mini)
#   SITE_URL                                              (opsiyonel - GitHub Pages adresi; mailde arsiv linki cikar)
#   LOOKBACK_HOURS                                        (opsiyonel - varsayilan 30)
#   MAX_ITEMS_TO_LLM                                      (opsiyonel - varsayilan 60)

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

# Renk & tipografi kimligi
EMERALD = "#00A86B"
NAVY    = "#0F2233"
INK     = "#21323d"
MUTED   = "#7b8893"
LINE    = "#e7ebed"
BG      = "#f5f7f8"
CARD    = "#ffffff"
SERIF   = "Georgia, 'Times New Roman', serif"
SANS    = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

SIGNAL_COLOR = {
    "Yuksek": "#00A86B", "Yüksek": "#00A86B",
    "Orta": "#d98a16",  "Düsuk": "#9aa6ad", "Dusuk": "#9aa6ad", "Düşük": "#9aa6ad",
}

TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _load_dotenv():
    """Lokal testte .env varsa oku (GitHub Actions'ta gerek yok, zararsiz)."""
    if not os.path.exists(".env"):
        return
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())


def tr_long_date(d: dt.date) -> str:
    return f"{d.day} {TR_MONTHS[d.month]} {d.year}, {TR_DAYS[d.weekday()]}"


# ----------------------------- 1) Haberleri cek -----------------------------

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
            })

    items.sort(key=lambda x: x["published"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
               reverse=True)
    print(f"[bilgi] {len(items)} benzersiz haber toplandi.")
    return items


# ----------------------------- 2) LLM ile kurasyon -----------------------------

CURATION_SYSTEM_PROMPT = """Sen deneyimli bir teknoloji ve girisim analistisin.
Gorevin: gunluk haber akisindan, Turkiye'de hayata gecirilebilecek IS FIRSATI sinyali
tasiyan haberleri secmek, siralamak ve Turkce ozetlemek.

Oncelik sirasi:
1. ABD/Avrupa'da yeni kurulan, yatirim alan veya hizla buyuyen startuplar (is modeli Turkiye'ye uyarlanabilir mi?)
2. Yeni yatirim turlari, fonlar, satin almalar (paranin nereye aktigi)
3. Yapay zeka urun/altyapi gelismeleri ve bunlarin acabilecegi yeni pazarlar
4. Teknoloji ve tuketici ihtiyaclarinin yon degistirdigine dair sinyaller

Eleme: salt magazinsel/borsa dedikodusu, ayni haberin tekrari ve net is sinyali olmayan
genel haberleri ELE. En guclu 8-14 maddeyi sec.

Cikti: SADECE su semada gecerli bir JSON nesnesi dondur, baska hicbir sey yazma:
{
  "gun_ozeti": "2-3 cumlede gunun ana temasi ve dikkat ceken trend",
  "maddeler": [
    {
      "kategori": "Startup | Yatirim | Yapay Zeka | Trend",
      "baslik": "haberin Turkce, net basligi",
      "kaynak": "kaynak adi",
      "url": "orijinal link (verilen url'yi aynen kullan)",
      "ozet_tr": "1-2 cumle Turkce ozet",
      "neden_onemli": "neden dikkat edilmeli, 1 cumle",
      "turkiye_acisi": "Turkiye'de nasil uyarlanabilir / hangi firsati acar, 1 cumle",
      "sinyal": "Yuksek | Orta | Dusuk"
    }
  ]
}
url alanini MUTLAKA sana verilen orijinal link ile doldur, uydurma."""


def curate_with_llm(items, model):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("[bilgi] OPENAI_API_KEY yok -> LLM kurasyonu atlandi, ham liste gonderilecek.")
        return None
    try:
        from openai import OpenAI
    except Exception as e:
        print(f"[uyari] openai paketi yuklenemedi: {e}")
        return None

    payload = [{"source": it["source"], "title": it["title"], "url": it["url"],
                "summary": it["summary"]} for it in items]
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model, temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CURATION_SYSTEM_PROMPT},
                {"role": "user", "content": "Bugunun haber akisi (JSON listesi):\n\n"
                 + json.dumps(payload, ensure_ascii=False)},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
        if not data.get("maddeler"):
            print("[uyari] LLM bos sonuc dondu, ham listeye dusulecek."); return None
        print(f"[bilgi] LLM {len(data['maddeler'])} madde secti.")
        return data
    except Exception as e:
        print(f"[uyari] LLM kurasyonu basarisiz: {e} -> ham liste gonderilecek.")
        return None


# ----------------------------- 3) HTML bulten (okunakli) -----------------------------

def _shell(date_long: str, intro_html: str, body_html: str, top_bar_html: str = "") -> str:
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RADAR · {html.escape(date_long)}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<div style="max-width:620px;margin:0 auto;padding:22px 18px 40px;font-family:{SANS};color:{INK};">
  {top_bar_html}
  <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">
    <span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:{EMERALD};"></span>
    <span style="font-family:{SERIF};font-size:26px;font-weight:700;letter-spacing:.5px;color:{NAVY};">RADAR</span>
  </div>
  <div style="font-size:13px;color:{MUTED};margin-bottom:20px;border-bottom:1px solid {LINE};padding-bottom:16px;">
    Günlük teknoloji &amp; girişim &amp; yatırım bülteni &middot; {html.escape(date_long)}</div>
  {intro_html}
  {body_html}
  <div style="margin-top:30px;padding-top:16px;border-top:1px solid {LINE};font-size:12px;color:{MUTED};line-height:1.6;">
    Her başlık orijinal kaynağa link verir. Kaynak listesi <code>feeds.py</code> içinden düzenlenebilir.
  </div>
</div></body></html>"""


def _intro_block(text: str) -> str:
    return (f'<div style="background:{NAVY};color:#e9f4ee;border-radius:16px;'
            f'padding:18px 20px;margin-bottom:22px;font-family:{SERIF};font-size:16px;'
            f'line-height:1.6;">'
            f'<span style="color:{EMERALD};font-weight:700;">Günün özeti.</span> '
            f'{html.escape(text)}</div>')


def build_html_curated(data, date_long) -> str:
    intro = _intro_block(data["gun_ozeti"]) if data.get("gun_ozeti") else ""
    cards = []
    for m in data["maddeler"]:
        sig = m.get("sinyal", "Orta")
        sig_col = SIGNAL_COLOR.get(sig, "#d98a16")
        url = html.escape(m.get("url", "#"))
        cards.append(f"""
<article style="background:{CARD};border:1px solid {LINE};border-radius:16px;padding:20px 22px;margin-bottom:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <span style="display:inline-block;background:#eafaf2;color:{EMERALD};font-size:11px;font-weight:700;
                 text-transform:uppercase;letter-spacing:.6px;padding:4px 10px;border-radius:20px;">{html.escape(m.get('kategori','Trend'))}</span>
    <span style="font-size:11px;font-weight:700;color:{sig_col};">● Sinyal: {html.escape(sig)}</span>
  </div>
  <a href="{url}" style="display:block;font-family:{SERIF};font-size:19px;font-weight:700;color:{NAVY};
     text-decoration:none;line-height:1.35;margin-bottom:10px;">{html.escape(m.get('baslik',''))}</a>
  <p style="font-size:15px;color:{INK};margin:0 0 12px;line-height:1.65;">{html.escape(m.get('ozet_tr',''))}</p>
  <p style="font-size:14px;color:{INK};margin:0 0 6px;line-height:1.6;">
     <span style="color:{MUTED};font-weight:700;">Neden önemli</span> &nbsp; {html.escape(m.get('neden_onemli',''))}</p>
  <p style="font-size:14px;color:{INK};margin:0 0 14px;line-height:1.6;">
     <span style="color:{EMERALD};font-weight:700;">Türkiye açısı</span> &nbsp; {html.escape(m.get('turkiye_acisi',''))}</p>
  <a href="{url}" style="font-size:13px;color:{EMERALD};text-decoration:none;font-weight:700;">Kaynağa git →</a>
  <span style="font-size:12px;color:{MUTED};margin-left:8px;">{html.escape(m.get('kaynak',''))}</span>
</article>""")
    return _shell(date_long, intro, "".join(cards))


def build_html_raw(items, date_long) -> str:
    intro = (f'<div style="background:#fff6e6;border:1px solid #f0d8a8;border-radius:16px;'
             f'padding:14px 18px;margin-bottom:22px;font-size:13px;color:#7a5a12;line-height:1.6;">'
             f'LLM kurasyonu yapılmadı (anahtar yok ya da hata). Aşağıda toplanan ham başlıklar var.</div>')
    cards = []
    for it in items[:40]:
        url = html.escape(it["url"])
        cards.append(f"""
<article style="background:{CARD};border:1px solid {LINE};border-radius:14px;padding:16px 18px;margin-bottom:10px;">
  <a href="{url}" style="font-family:{SERIF};font-size:17px;font-weight:700;color:{NAVY};text-decoration:none;line-height:1.4;">{html.escape(it['title'])}</a>
  <p style="font-size:14px;color:{INK};margin:8px 0 12px;line-height:1.6;">{html.escape(it['summary'][:220])}</p>
  <a href="{url}" style="font-size:13px;color:{EMERALD};text-decoration:none;font-weight:700;">Kaynağa git →</a>
  <span style="font-size:12px;color:{MUTED};margin-left:8px;">{html.escape(it['source'])}</span>
</article>""")
    return _shell(date_long, intro, "".join(cards))


# ----------------------------- 4) Arsiv + index -----------------------------

def save_archive(html_full: str, date_iso: str) -> str:
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    # Arsiv sayfasinin en ustune "arsive don" cubugu ekle
    back_bar = (f'<div style="margin-bottom:16px;">'
                f'<a href="../index.html" style="font-size:13px;color:{MUTED};text-decoration:none;">← Tüm bültenler</a></div>')
    page = html_full.replace('<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">',
                             back_bar + '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">', 1)
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
            d = dt.date.fromisoformat(name)
            dates.append((name, d))
        except ValueError:
            continue

    options = "\n".join(
        f'        <option value="{iso}">{html.escape(tr_long_date(d))}</option>'
        for iso, d in dates)
    cards = "\n".join(
        f'''      <a class="day" href="archive/{iso}.html">
        <span class="day-date">{html.escape(tr_long_date(d))}</span>
        <span class="day-go">Bülteni aç →</span>
      </a>''' for iso, d in dates)

    latest_note = ""
    if dates:
        latest_note = (f'<p class="sub">En son bülten: '
                       f'<a href="archive/{dates[0][0]}.html">{html.escape(tr_long_date(dates[0][1]))}</a></p>')

    css = """
    :root { --emerald:#00A86B; --navy:#0F2233; --ink:#21323d; --muted:#7b8893; --line:#e7ebed; --bg:#f5f7f8; --card:#fff; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink);
           font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; }
    .wrap { max-width:620px; margin:0 auto; padding:36px 18px 60px; }
    .brand { display:flex; align-items:baseline; gap:10px; }
    .dot { width:11px; height:11px; border-radius:50%; background:var(--emerald); display:inline-block; }
    .logo { font-family:Georgia,'Times New Roman',serif; font-size:28px; font-weight:700; color:var(--navy); letter-spacing:.5px; }
    .tag { font-size:13px; color:var(--muted); margin:4px 0 0; }
    .sub { font-size:14px; color:var(--ink); margin:10px 0 0; }
    .sub a { color:var(--emerald); text-decoration:none; font-weight:600; }
    .picker { margin:26px 0 30px; padding:18px 20px; background:var(--navy); border-radius:16px; }
    .picker label { display:block; color:#cfe6da; font-size:13px; margin-bottom:8px; }
    .picker select { width:100%; padding:12px 14px; border-radius:10px; border:none; font-size:15px;
                     font-family:inherit; color:var(--navy); background:#fff; }
    .list h2 { font-family:Georgia,serif; font-size:15px; color:var(--muted); font-weight:700;
               text-transform:uppercase; letter-spacing:.6px; margin:0 0 12px; }
    .day { display:flex; justify-content:space-between; align-items:center; text-decoration:none;
           background:var(--card); border:1px solid var(--line); border-radius:14px;
           padding:16px 20px; margin-bottom:10px; }
    .day:hover { border-color:var(--emerald); }
    .day-date { font-family:Georgia,serif; font-size:17px; color:var(--navy); font-weight:700; }
    .day-go { font-size:13px; color:var(--emerald); font-weight:700; }
    .empty { color:var(--muted); font-size:15px; }
    .foot { margin-top:36px; padding-top:16px; border-top:1px solid var(--line); font-size:12px; color:var(--muted); }
    """

    body_list = (f'<div class="list"><h2>Tüm bültenler</h2>{cards}</div>'
                 if dates else '<p class="empty">Henüz bülten yok. İlk bülten geldiğinde burada listelenecek.</p>')

    page = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RADAR · Arşiv</title>
<style>{css}</style></head>
<body><div class="wrap">
  <div class="brand"><span class="dot"></span><span class="logo">RADAR</span></div>
  <p class="tag">Günlük teknoloji &amp; girişim &amp; yatırım bülteni — arşiv</p>
  {latest_note}
  <div class="picker">
    <label for="day">Bir güne git</label>
    <select id="day" onchange="if(this.value)location.href='archive/'+this.value+'.html';">
        <option value="">— tarih seç —</option>
{options}
    </select>
  </div>
  {body_list}
  <div class="foot">Otomatik olarak her gün güncellenir. RADAR.</div>
</div></body></html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[bilgi] index.html guncellendi ({len(dates)} bulten listelendi).")


# ----------------------------- 5) Mail gonder -----------------------------

def send_email(subject: str, html_body: str, date_long: str):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_to = os.environ["MAIL_TO"]

    site_url = os.environ.get("SITE_URL", "").strip()
    body = html_body
    if site_url:
        bar = (f'<div style="margin-bottom:16px;"><a href="{html.escape(site_url)}" '
               f'style="font-size:13px;color:{MUTED};text-decoration:none;">↗ Arşivde tüm bültenler</a></div>')
        body = body.replace('<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">',
                            bar + '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:2px;">', 1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = mail_to
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText("RADAR bulteni HTML formatindadir.", "plain", "utf-8"))
    msg.attach(MIMEText(body, "html", "utf-8"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.sendmail(user, mail_to.split(","), msg.as_string())
    else:
        with smtplib.SMTP(host, port) as server:
            server.starttls(); server.login(user, password)
            server.sendmail(user, mail_to.split(","), msg.as_string())
    print(f"[bilgi] Mail gonderildi -> {mail_to}")


# ----------------------------- main -----------------------------

def main():
    _load_dotenv()
    lookback = int(os.environ.get("LOOKBACK_HOURS", "30"))
    max_items = int(os.environ.get("MAX_ITEMS_TO_LLM", "60"))
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    now_local = (dt.datetime.now(dt.timezone.utc) + TZ_OFFSET)
    date_iso = now_local.strftime("%Y-%m-%d")
    date_long = tr_long_date(now_local.date())

    items = fetch_entries(lookback)
    if not items:
        print("[bilgi] Yeni haber yok; index yine de guncelleniyor.")
        rebuild_index()
        return

    data = curate_with_llm(items[:max_items], model)
    if data:
        html_body = build_html_curated(data, date_long)
        subject = f"RADAR · {date_long} · {len(data['maddeler'])} fırsat sinyali"
    else:
        html_body = build_html_raw(items, date_long)
        subject = f"RADAR · {date_long} · {min(len(items),40)} başlık"

    # Once arsivle (kalici kayit), sonra index, en son mail.
    save_archive(html_body, date_iso)
    rebuild_index()

    try:
        send_email(subject, html_body, date_long)
    except Exception as e:
        print(f"[uyari] Mail gonderilemedi ({e}); arsiv yine de kaydedildi.")


if __name__ == "__main__":
    main()
