from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yt_dlp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

load_dotenv()

from recognition import (  # noqa: E402
    ACRCloudRecognizer,
    RecognitionError,
    RecognitionNotConfigured,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("video_bot")


def positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if parsed < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return parsed


MAX_UPLOAD_BYTES = positive_int_env("MAX_UPLOAD_MB", 20) * 1024 * 1024
MAX_DOWNLOAD_BYTES = positive_int_env("MAX_DOWNLOAD_MB", 45) * 1024 * 1024
MAX_DURATION_SECONDS = positive_int_env("MAX_DURATION_MINUTES", 15) * 60
MAX_SEARCH_CHARS = 160
SESSION_TTL_SECONDS = 30 * 60
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
ALLOWED_HOSTS = {
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "facebook.com",
    "fb.watch",
    "pinterest.com",
    "pin.it",
    "threads.net",
    "snapchat.com",
    "t.me",
    "telegram.me",
    "likee.video",
    "reddit.com",
    "redd.it",
    "x.com",
    "twitter.com",
    "capcut.com",
}

dp = Dispatcher()
recognizer = ACRCloudRecognizer()
job_slots = asyncio.Semaphore(3)
user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
search_sessions: dict[str, dict] = {}


class MediaDownloadError(RuntimeError):
    """A safe, user-facing media download failure."""


def is_allowed_media_url(raw_url: str) -> bool:
    if not raw_url or len(raw_url) > 2048:
        return False
    try:
        parsed = urlsplit(raw_url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        return False
    if port not in (None, 443):
        return False
    return any(host == domain or host.endswith("." + domain) for domain in ALLOWED_HOSTS)


def normalize_media_url(raw_url: str) -> str:
    """Normalize public Telegram post aliases to yt-dlp's supported URL shape."""
    parsed = urlsplit(raw_url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if host == "telegram.me" or host.endswith(".telegram.me"):
        parsed = parsed._replace(netloc="t.me")
        host = "t.me"

    parts = [part for part in parsed.path.split("/") if part]
    if host == "t.me" and len(parts) == 3 and parts[0] == "s" and parts[2].isdigit():
        parsed = parsed._replace(path=f"/{parts[1]}/{parts[2]}")
    return urlunsplit(parsed)


def _duration_or_size_filter(info: dict, *, incomplete: bool) -> str | None:
    duration = info.get("duration")
    if duration and duration > MAX_DURATION_SECONDS:
        return "Media exceeds the duration limit"
    size = info.get("filesize") or info.get("filesize_approx")
    if size and size > MAX_DOWNLOAD_BYTES:
        return "Media exceeds the file-size limit"
    return None


def _download_sync(url: str, directory: Path, *, audio_only: bool = False) -> Path:
    options = {
        "format": "bestaudio/best" if audio_only else "best[ext=mp4]/best",
        "outtmpl": str(directory / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "ignoreconfig": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_DOWNLOAD_BYTES,
        "socket_timeout": 20,
        "retries": 1,
        "fragment_retries": 1,
        "restrictfilenames": True,
        "match_filter": _duration_or_size_filter,
    }
    if audio_only:
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ]

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
    except Exception as exc:
        raise MediaDownloadError("Media could not be downloaded") from exc

    if not info or info.get("entries"):
        raise MediaDownloadError("Playlists are not supported")

    allowed_extensions = AUDIO_EXTENSIONS if audio_only else VIDEO_EXTENSIONS
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and path.suffix.lower() in allowed_extensions
        and 0 < path.stat().st_size <= MAX_DOWNLOAD_BYTES
    ]
    if audio_only:
        mp3_candidates = [path for path in candidates if path.suffix.lower() == ".mp3"]
        candidates = mp3_candidates or candidates
    if not candidates:
        raise MediaDownloadError("No supported media file was produced")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _search_youtube_sync(query: str) -> list[dict]:
    options = {
        "default_search": "ytsearch5",
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            result = downloader.extract_info(f"ytsearch5:{query}", download=False) or {}
    except Exception as exc:
        raise MediaDownloadError("Music search failed") from exc

    results = []
    for entry in result.get("entries") or []:
        if not entry:
            continue
        results.append(
            {
                "id": str(entry.get("id") or ""),
                "url": str(entry.get("url") or ""),
                "title": str(entry.get("title") or "Noma’lum"),
                "duration": entry.get("duration"),
            }
        )
    return results


async def _extract_sample(source: Path, destination: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-t",
        "12",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        "-b:a",
        "96k",
        str(destination),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()
    if process.returncode != 0 or not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError("Audio extraction failed")


async def _identify_and_reply(message: Message, source: Path) -> None:
    if not recognizer.configured:
        await message.answer(
            "Qo‘shiqni avtomatik tanish uchun ACRCloud sozlamalari hali kiritilmagan. "
            "ACR_HOST, ACR_ACCESS_KEY va ACR_ACCESS_SECRET qiymatlarini hosting secrets’iga qo‘shing."
        )
        return

    try:
        async with tempfile.TemporaryDirectory(prefix="music-sample-") as temp_dir:
            sample = Path(temp_dir) / "sample.mp3"
            await _extract_sample(source, sample)
            match = await recognizer.identify(sample)
    except RecognitionNotConfigured:
        await message.answer("Musiqa aniqlash xizmati sozlanmagan.")
        return
    except RecognitionError:
        logger.warning("Music identification request failed")
        await message.answer("Musiqani aniqlashda xatolik bo‘ldi. Birozdan keyin qayta urinib ko‘ring.")
        return
    except FileNotFoundError:
        await message.answer("Serverda FFmpeg o‘rnatilmagan. Uni hosting muhitiga o‘rnating.")
        return
    except Exception as exc:
        logger.warning("Audio processing failed (%s)", type(exc).__name__)
        await message.answer("Videodan audioni ajratib bo‘lmadi.")
        return

    if not match:
        await message.answer("Aniq mos qo‘shiq topilmadi. Boshqa parchasini yuborib ko‘ring.")
        return

    title = html.escape(str(match.get("title") or "Noma’lum qo‘shiq"))
    artists = match.get("artists") or []
    artist_text = ", ".join(str(item.get("name", "")) for item in artists if item.get("name"))
    lines = ["🎵 <b>Qo‘shiq topildi</b>", f"<b>{title}</b>"]
    if artist_text:
        lines.append(html.escape(artist_text))
    album = (match.get("album") or {}).get("name")
    if album:
        lines.append(f"Albom: {html.escape(str(album))}")

    spotify_id = (
        ((match.get("external_metadata") or {}).get("spotify") or {})
        .get("track", {})
        .get("id")
    )
    if spotify_id and re.fullmatch(r"[A-Za-z0-9]+", str(spotify_id)):
        lines.append(f'<a href="https://open.spotify.com/track/{spotify_id}">Spotify’da ochish</a>')
    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def _delete_message(message: Message | None) -> None:
    if not message:
        return
    try:
        await message.delete()
    except Exception:
        pass


@dp.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "• Video yoki audio yuboring — undagi qo‘shiqni aniqlashga harakat qilaman.\n"
        "• Qo‘shiq nomi yoki ijrochisini yozing — qidiruv natijalarini chiqaraman.\n"
        "• Public video havolalari: YouTube, Instagram, TikTok, Facebook, Pinterest, "
        "Snapchat Spotlight, Telegram kanal posti, Likee, Reddit va X/Twitter.\n"
        "• CapCut va Threads public sahifalari best-effort: hamma havola ochilavermaydi.\n\n"
        "Faqat yuklab olishga ruxsatingiz bor kontentdan foydalaning. "
        "Private, login talab qiladigan Stories va geo-cheklovlarni bot aylanib o‘tmaydi."
    )


@dp.message(F.video | F.audio | F.voice | F.document)
async def handle_uploaded_media(message: Message) -> None:
    if not message.from_user:
        return

    media = message.video or message.audio or message.voice or message.document
    if not media:
        return

    filename = getattr(media, "file_name", None) or "upload"
    mime_type = getattr(media, "mime_type", None) or ""
    extension = Path(filename).suffix.lower()
    is_video = bool(message.video) or mime_type.startswith("video/") or extension in VIDEO_EXTENSIONS
    is_audio = (
        bool(message.audio or message.voice)
        or mime_type.startswith("audio/")
        or extension in AUDIO_EXTENSIONS
    )
    if not (is_video or is_audio):
        await message.answer("Iltimos, video yoki audio fayl yuboring.")
        return

    if media.file_size and media.file_size > MAX_UPLOAD_BYTES:
        await message.answer(f"Fayl hajmi {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasin.")
        return

    async with job_slots, user_locks[message.from_user.id]:
        status = await message.answer("⏳ Fayl tekshirilmoqda va musiqasi aniqlanmoqda…")
        try:
            remote_file = await message.bot.get_file(media.file_id)
            if remote_file.file_size and remote_file.file_size > MAX_UPLOAD_BYTES:
                await message.answer(
                    f"Fayl hajmi {MAX_UPLOAD_BYTES // (1024 * 1024)} MB dan oshmasin."
                )
                return
            if not remote_file.file_path:
                raise RuntimeError("Telegram did not return a file path")

            suffix = extension if extension else (".mp4" if is_video else ".mp3")
            with tempfile.TemporaryDirectory(prefix="telegram-media-") as temp_dir:
                source = Path(temp_dir) / f"upload{suffix}"
                await message.bot.download_file(remote_file.file_path, destination=source)
                if not source.exists() or source.stat().st_size > MAX_UPLOAD_BYTES:
                    await message.answer("Fayl bo‘sh yoki ruxsat etilgan hajmdan katta.")
                    return
                await _identify_and_reply(message, source)
        except Exception as exc:
            logger.warning("Uploaded media processing failed (%s)", type(exc).__name__)
            await message.answer("Faylni qayta ishlashda xatolik bo‘ldi.")
        finally:
            await _delete_message(status)


async def _send_downloaded_media(message: Message, path: Path) -> None:
    if path.stat().st_size > MAX_DOWNLOAD_BYTES:
        raise MediaDownloadError("Media exceeds the upload size limit")
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        if path.suffix.lower() == ".mp4":
            await message.answer_video(FSInputFile(path), supports_streaming=True)
        else:
            await message.answer_document(FSInputFile(path))
    elif path.suffix.lower() in AUDIO_EXTENSIONS:
        if path.suffix.lower() in {".mp3", ".m4a"}:
            await message.answer_audio(FSInputFile(path))
        else:
            await message.answer_document(FSInputFile(path))
    else:
        raise MediaDownloadError("Unsupported media type")


async def _process_media_url(message: Message, url: str) -> None:
    if not is_allowed_media_url(url):
        await message.answer(
            "Bu domen hozircha qo‘llab-quvvatlanmaydi. "
            "YouTube, Instagram, TikTok, Facebook, Pinterest, Snapchat Spotlight, "
            "Telegram public post, Likee, Reddit yoki X havolasini yuboring."
        )
        return
    url = normalize_media_url(url)
    if not message.from_user:
        return

    async with job_slots, user_locks[message.from_user.id]:
        status = await message.answer("⏳ Havola tekshirilmoqda…")
        try:
            with tempfile.TemporaryDirectory(prefix="social-media-") as temp_dir:
                directory = Path(temp_dir)
                media_path = await asyncio.to_thread(_download_sync, url, directory)
                await _send_downloaded_media(message, media_path)
                await _identify_and_reply(message, media_path)
        except MediaDownloadError:
            await message.answer(
                "Media topilmadi yoki platforma uni botga ochmadi. "
                "Havola public bo‘lsin; private/Stories, login, hajm yoki davomiylik "
                "cheklovlari sababli yuklanmasligi mumkin."
            )
        except Exception as exc:
            logger.warning("URL processing failed (%s)", type(exc).__name__)
            await message.answer("Havolani qayta ishlashda xatolik bo‘ldi.")
        finally:
            await _delete_message(status)


def _prune_search_sessions() -> None:
    now = time.monotonic()
    expired = [
        session_id
        for session_id, session in search_sessions.items()
        if now - session["created_at"] > SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        search_sessions.pop(session_id, None)


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    if not message.text or message.text.startswith("/"):
        return
    query = message.text.strip()
    urls = re.findall(r"https?://[^\s<>]+", query)
    if urls:
        if len(urls) > 1:
            await message.answer("Iltimos, bir xabarda bitta video havolasini yuboring.")
            return
        clean_url = urls[0].rstrip(").,!?;")
        await _process_media_url(message, clean_url)
        return
    if len(query) > MAX_SEARCH_CHARS:
        await message.answer(f"Qidiruv matni {MAX_SEARCH_CHARS} belgidan oshmasin.")
        return
    if not query:
        return
    if not message.from_user:
        return

    status = await message.answer("🔎 Qo‘shiqlar qidirilmoqda…")
    try:
        entries = await asyncio.to_thread(_search_youtube_sync, query)
    except MediaDownloadError:
        await message.answer("Qidiruvda xatolik bo‘ldi. Keyinroq qayta urinib ko‘ring.")
        return
    finally:
        await _delete_message(status)

    if not entries:
        await message.answer("Hech qanday natija topilmadi.")
        return

    _prune_search_sessions()
    session_id = os.urandom(4).hex()
    search_sessions[session_id] = {
        "user_id": message.from_user.id,
        "created_at": time.monotonic(),
        "entries": entries,
    }

    buttons = []
    lines = [f"🔎 <b>{html.escape(query)}</b> bo‘yicha natijalar:"]
    for index, entry in enumerate(entries):
        title = entry["title"]
        duration = entry.get("duration")
        duration_text = ""
        if isinstance(duration, (int, float)) and duration > 0:
            duration_text = f" · {int(duration) // 60}:{int(duration) % 60:02d}"
        lines.append(f"{index + 1}. {html.escape(title)}{duration_text}")
        button_title = title if len(title) <= 45 else title[:42] + "…"
        buttons.append(
            [InlineKeyboardButton(
                text=f"⬇️ {index + 1}. {button_title}",
                callback_data=f"music:{session_id}:{index}",
            )]
        )

    lines.append(
        "\nFaqat yuklab olish huquqingiz bor audio materialni tanlang."
    )
    await message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("music:"))
async def download_selected_music(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.message.answer("Qidiruv natijasi eskirgan. Qayta qidiring.")
        return
    _, session_id, index_text = parts
    session = search_sessions.get(session_id)
    if not session or session["user_id"] != callback.from_user.id:
        await callback.message.answer("Qidiruv natijasi eskirgan. Qayta qidiring.")
        return
    try:
        index = int(index_text)
        entry = session["entries"][index]
    except (ValueError, IndexError):
        await callback.message.answer("Tanlangan natija topilmadi.")
        return

    video_id = entry.get("id", "")
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        candidate_url = f"https://www.youtube.com/watch?v={video_id}"
    else:
        candidate_url = entry.get("url", "")
    if not is_allowed_media_url(candidate_url):
        await callback.message.answer("Tanlangan natijaning havolasi yaroqsiz.")
        return

    status = await callback.message.answer("⏳ Tanlangan audio yuklanmoqda…")
    try:
        async with job_slots, user_locks[callback.from_user.id]:
            with tempfile.TemporaryDirectory(prefix="music-search-") as temp_dir:
                audio_path = await asyncio.to_thread(
                    _download_sync,
                    candidate_url,
                    Path(temp_dir),
                    audio_only=True,
                )
                title = entry["title"][:64]
                await callback.message.answer_audio(
                    FSInputFile(audio_path),
                    title=title,
                )
    except MediaDownloadError:
        await callback.message.answer(
            "Audioni yuklab bo‘lmadi. Faqat yuklashga ruxsatingiz bo‘lgan kontentdan foydalaning."
        )
    except Exception as exc:
        logger.warning("Selected audio download failed (%s)", type(exc).__name__)
        await callback.message.answer("Audioni yuborishda xatolik bo‘ldi.")
    finally:
        await _delete_message(status)


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Set BOT_TOKEN in the hosting environment")
    bot = Bot(token=token)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
