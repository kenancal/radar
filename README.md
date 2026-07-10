# RADAR — Günlük Teknoloji & Girişim & Yatırım Bülteni (arşivli)

Bilgisayarın kapalı olsa bile her gün otomatik çalışır; ABD/Avrupa'daki yeni
startup, yatırım ve yapay zeka haberlerini çeker, **"Türkiye'de hayata
geçirilebilir iş fırsatı"** gözüyle eler/özetler ve sana **kaynak linkleriyle**
mail atar. Ayrıca her bülteni **arşivler**: bir siteden gün gün geçmişe dönüp
bakabilirsin. Bültenler kaybolmaz.

Çalışma yeri: **GitHub Actions** (GitHub bulutu) — senin makinene bağlı değil.

---

## Nasıl çalışır
1. Her sabah 06:30 (İstanbul) Actions tetiklenir.
2. `radar.py` haberleri çeker, LLM ile eler/özetler.
3. Bülteni **mail atar** + `archive/2026-06-10.html` olarak **kaydeder**.
4. `index.html` arşiv tarayıcısını günceller (gün seçici + tüm günlerin listesi).
5. `archive/` ve `index.html` repoya geri commit edilir.
6. GitHub Pages bunları site olarak yayınlar → istediğin güne tıklarsın.

## Dosyalar
```
radar.py                      # ana program (çek + ele + bülten + arşiv + index)
feeds.py                      # takip edilen RSS kaynakları
requirements.txt              # bağımlılıklar
.env.example                  # lokal test için örnek ayar
.github/workflows/radar.yml   # zamanlanmış görev (cron) + arşiv commit
archive/                      # her günün bülteni (otomatik oluşur)
index.html                    # arşiv tarayıcısı (otomatik oluşur)
```

## Kurulum (tek seferlik)

### 1) Repo
Yeni bir GitHub reposu aç ve dosyaları aynı yapıyla koy. `radar.yml` mutlaka
`.github/workflows/` altında olmalı.

### 2) Mail için App Password (Gmail)
Google Hesabı → Güvenlik → 2 adımlı doğrulama açık → **Uygulama Şifreleri** →
16 haneli şifre. Bunu `SMTP_PASS` olarak kullan.

### 3) Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| İsim | Değer |
|------|-------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USER` | `senin@gmail.com` |
| `SMTP_PASS` | 16 haneli app password |
| `MAIL_TO` | bültenin gideceği adres |
| `OPENAI_API_KEY` | `sk-...` (opsiyonel) |
| `OPENAI_MODEL` | `gpt-4o-mini` (opsiyonel) |
| `SITE_URL` | Pages adresin (opsiyonel; mailde arşiv linki çıkar) |

### 4) GitHub Pages'i aç (arşiv sitesi için)
Repo → **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main`,
klasör `/ (root)` → Save. Birkaç dakika sonra siten şu adreste yayında olur:
`https://<kullanıcı-adın>.github.io/<repo-adı>/`
Bu adresi istersen `SITE_URL` secret'ına da ekle.

> Not: İlk bülten çalışana kadar `index.html` / `archive/` boştur; ilk çalıştırmadan
> sonra dolar.

### 5) Test et
Repo → **Actions** → "Radar Günlük Bülten" → **Run workflow**.
Birkaç dakikada mail gelir; Pages adresinde ilk bülten listelenir.

### 6) Saat
`radar.yml` içindeki `cron: '30 3 * * *'` UTC'dir → 06:30 İstanbul. Değiştirmek
istersen UTC'ye göre ayarla.

---

## Lokal test
```bash
pip install -r requirements.txt
cp .env.example .env      # içini doldur
python radar.py           # archive/ ve index.html'i lokalde de üretir
```

## Özelleştirme
- **Kaynaklar:** `feeds.py`
- **Eleme/önceliklendirme:** `radar.py` → `CURATION_SYSTEM_PROMPT` (kendi sektör
  ilgilerini ekleyebilirsin: enerji, termal, IoT, donanım, 3D baskı vb.)
- **Tasarım:** `radar.py` → `build_html_curated` ve `rebuild_index`

## Maliyet
Actions: günde ~1-2 dk (private repo aylık 2000 dk ücretsiz kotada). LLM
(gpt-4o-mini): günde birkaç sent. GitHub Pages: ücretsiz.

---

## Katkıda bulunma

RADAR açık kaynaklı bir projedir. Hata düzeltmeleri, yeni RSS kaynakları, testler, dokümantasyon iyileştirmeleri, bölgesel değerlendirme profilleri ve altyapı geliştirmeleri memnuniyetle karşılanır.

Katkı yapmadan önce [CONTRIBUTING.md](CONTRIBUTING.md) dosyasını inceleyin.

Büyük özellikler veya mimari değişiklikler için önce bir GitHub issue açılması önerilir.

## Güvenlik

API anahtarlarını, SMTP şifrelerini, erişim tokenlarını veya kişisel bilgileri repoya commit etmeyin. Hassas bilgiler GitHub Actions Secrets veya yerel `.env` dosyası üzerinden yönetilmelidir.

## Lisans

Bu proje [MIT License](LICENSE) altında yayımlanmaktadır.
