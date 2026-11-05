# Video va musiqa Telegram boti

Aiogram 3 asosidagi bot. Telegram’dan yuborilgan video/audio ichidagi qo‘shiqni ACRCloud orqali aniqlaydi, matn bo‘yicha YouTube natijalarini qidiradi va ruxsat berilgan public media havolalarini qayta ishlaydi.

## Imkoniyatlar

- Telegram’dan yuborilgan audio yoki videodan 12 soniyalik namuna ajratib, qo‘shiq nomi va ijrochini topish.
- Qo‘shiq nomi yoki ijrochi bo‘yicha YouTube qidiruvi.
- Ruxsat etilgan HTTPS havolalardagi public media fayllarni yuklab, Telegram’ga yuborish.
- Fayl hajmi, davomiyligi, playlist va havola hosti bo‘yicha cheklovlar.
- Har bir ish uchun vaqtinchalik katalog; fayllar ish tugagach o‘chiriladi.

Bot faqat siz yuklashga va qayta tarqatishga huquqingiz bo‘lgan kontentda ishlatilishi kerak. U login/cookie talab qiladigan private kontentni yoki geo-cheklovlarni aylanib o‘tmaydi.

## Kerakli narsalar

- Python 3.11+
- FFmpeg (`ffmpeg` buyrug‘i shell’da ishlashi kerak)
- Telegram bot tokeni
- Qo‘shiq tanish uchun ACRCloud loyihasi va uning host, access key, access secret qiymatlari

## O‘rnatish

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` ichiga qiymatlarni kiriting. `BOT_TOKEN` va ACRCloud kalitlarini GitHub’ga commit qilmang; production’da hosting platformasining Secrets/Environment Variables bo‘limidan kiriting. Eski token ommaviy repozitoriyda bo‘lgan bo‘lsa, BotFather’da bekor qiling va yangisini ishlating.

ACRCloud’da loyiha ochib, host’ni loyihangiz hududiga mos kiriting (masalan, `identify-eu-west-1.acrcloud.com`). Qo‘shiqni tanish xizmati sozlanmagan bo‘lsa, bot qidiruvni ishlatadi, ammo audio identifikatsiyasi ishlamaydi.

## Ishga tushirish

```bash
python main.py
```

Bot long polling rejimida ishlaydi. Hosting’da uni doimiy background worker sifatida ishga tushiring. FFmpeg hosting muhitiga alohida o‘rnatilishi kerak.

Docker bilan ishga tushirish uchun:

```bash
docker build -t video-music-bot .
docker run --env-file .env video-music-bot
```

## Muhit o‘zgaruvchilari

| O‘zgaruvchi | Majburiy | Standart | Maqsad |
|---|---:|---:|---|
| `BOT_TOKEN` | Ha | — | Telegram bot tokeni |
| `ACR_HOST` | Musiqa tanish uchun | — | ACRCloud loyiha hosti, protokolsiz |
| `ACR_ACCESS_KEY` | Musiqa tanish uchun | — | ACRCloud access key |
| `ACR_ACCESS_SECRET` | Musiqa tanish uchun | — | ACRCloud access secret |
| `MAX_UPLOAD_MB` | Yo‘q | `20` | Telegram’dan olinadigan fayl chegarasi |
| `MAX_DOWNLOAD_MB` | Yo‘q | `45` | Havoladan olinadigan va yuboriladigan fayl chegarasi |
| `MAX_DURATION_MINUTES` | Yo‘q | `15` | Havola mediasining maksimal davomiyligi |
| `LOG_LEVEL` | Yo‘q | `INFO` | Log darajasi |

## Sinov

```bash
python -m compileall -q .
```

ACRCloud API’si ishlashi uchun haqiqiy loyiha sozlamalari va internet aloqasi kerak.
