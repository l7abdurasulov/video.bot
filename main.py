import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

TOKEN = "8804588411:AAFV2AYGAodwKBBgJ0TCqCgyB.." 8804588411:AAFV2AYGA0dwKBBgJ0TCqCgyBXAscqqOyks"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Foydalanuvchilarning qidiruv natijalarini vaqtincha saqlash uchun lug'at
user_searches = {}

# 1. Start komandasi va rasmga mos to'liq menyu hamda "Guruhga qo'shish" tugmasi
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_name = message.from_user.first_name
    
    text = (
        f"🔥 Assalomu alaykum, {user_name}!\n\n"
        "Bot orqali quyidagilarni yuklab olishingiz mumkin[span_2](start_span)[span_2](end_span)[span_3](start_span)[span_3](end_span):\n\n"
        "• Instagram - post, stories, reels[span_4](start_span)[span_4](end_span)[span_5](start_span)[span_5](end_span);\n"
        "• YouTube - video, shorts, audio[span_6](start_span)[span_6](end_span)[span_7](start_span)[span_7](end_span);\n"
        "• Tik Tok - suv belgisi bo'lmagan video[span_8](start_span)[span_8](end_span)[span_9](start_span)[span_9](end_span);\n"
        "• Facebook - post, reels[span_10](start_span)[span_10](end_span)[span_11](start_span)[span_11](end_span);\n"
        "• Pinterest - rasm, video[span_12](start_span)[span_12](end_span)[span_13](start_span)[span_13](end_span);\n"
        "• Snapchat - rasm, video[span_14](start_span)[span_14](end_span)[span_15](start_span)[span_15](end_span);\n"
        "• Likee - suv belgisi bo'lmagan video[span_16](start_span)[span_16](end_span)[span_17](start_span)[span_17](end_span);\n"
        "• Telegram - stories[span_18](start_span)[span_18](end_span)[span_19](start_span)[span_19](end_span);\n"
        "• Threads - rasm, video[span_20](start_span)[span_20](end_span)[span_21](start_span)[span_21](end_span).\n\n"
        "Shazam funksiya[span_22](start_span)[span_22](end_span)[span_23](start_span)[span_23](end_span):\n"
        "• Qo'shiq nomi yoki ijrochi ismi[span_24](start_span)[span_24](end_span)[span_25](start_span)[span_25](end_span)\n"
        "• Qo'shiq matni[span_26](start_span)[span_26](end_span)[span_27](start_span)[span_27](end_span)\n"
        "• Video / Audio[span_28](start_span)[span_28](end_span)[span_29](start_span)[span_29](end_span)\n\n"
        "🚀 Media yuklashni boshlash uchun uning havolasini yuboring[span_30](start_span)[span_30](end_span)[span_31](start_span)[span_31](end_span).\n"
        "😎 Bot guruhlarda ham ishlay oladi[span_32](start_span)[span_32](end_span)[span_33](start_span)[span_33](end_span)!"
    )
    
    bot_info = await bot.get_me()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ GURUHGA QO'SHISH", url=f"https://t.me/{bot_info.username}?startgroup=true")]
        ]
    )
    
    await message.answer(text, reply_markup=keyboard)

# 2. Havolalar orqali yuklash (URL) - Videodan musiqa ajratish funksiyasi bilan
@dp.message(F.text.startswith("http"))
async def download_content(message: Message):
    url = message.text.strip()
    processing_msg = await message.answer("⏳ Kontent va undagi musiqa yuklab olinmoqda, iltimos kuting...")
    
    file_prefix = f"download_{message.from_user.id}"
    ydl_opts = {
        'outtmpl': f'{file_prefix}_%(id)s.%(ext)s',
        'quiet': True,
        'format': 'best',
        'geo_bypass': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    downloaded_files = []
    try:
        loop = asyncio.get_running_loop()
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info:
                    return [ydl.prepare_filename(entry) for entry in info['entries']]
                else:
                    return [ydl.prepare_filename(info)]

        downloaded_files = await loop.run_in_executor(None, download)

        photos_to_send = []
        for file_path in downloaded_files:
            if os.path.exists(file_path):
                # A) Rasmlar
                if file_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                    photos_to_send.append(InputMediaPhoto(media=FSInputFile(file_path)))
                
                # B) Videolar (va ulardan musiqani alohida ajratib olish)
                elif file_path.endswith(('.mp4', '.mkv', '.mov', '.webm', .avi)): # syntax fix
                    video_file = FSInputFile(file_path)
                    await message.answer_video(video_file, caption="Mana siz so'ragan video! 🚀")
                    
                    # Videodan musiqani (.mp3) ajratib olish
                    audio_path = file_path.rsplit('.', 1)[0] + '.mp3'
                    process = await asyncio.create_subprocess_exec(
                        'ffmpeg', '-i', file_path, '-vn', '-ab', '192k', '-ar', '44100', '-y', audio_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.communicate()

                    # Agar musiqa muvaffaqiyatli ajratilgan bo'lsa, uni ham yuboramiz
                    if os.path.exists(audio_path):
                        audio_file = FSInputFile(audio_path)
                        await message.answer_audio(audio_file, caption="🎵 Videodagi musiqa!")
                        os.remove(audio_path)

                    os.remove(file_path)
                    
                # C) Audiolar / Qo'shiqlar
                elif file_path.endswith(('.mp3', '.m4a', '.opus', '.flac', '.wav', '.aac')):
                    audio_file = FSInputFile(file_path)
                    await message.answer_audio(audio_file, caption="Mana siz so'ragan qo'shiq! 🎵")
                    os.remove(file_path)

        if photos_to_send:
            await message.answer_media_group(photos_to_send)
            for file_path in downloaded_files:
                if os.path.exists(file_path):
                    os.remove(file_path)

        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)

    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await message.answer("❌ Xatolik yuz berdi: Havola yaroqsiz yoki kontent topilmadi.")
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
        
        for file_path in downloaded_files:
            if os.path.exists(file_path):
                os.remove(file_path)

# 3. Matn bo'yicha musiqa qidirish (Shazam uslubi)
@dp.message(~F.text.startswith("http") & ~F.text.startswith("/"))
async def search_music(message: Message):
    query = message.text.strip()
    processing_msg = await message.answer("🔍 Qo'shiqlar qidirilmoqda...")

    ydl_opts = {
        'default_search': 'ytsearch10',
        'quiet': True,
        'extract_flat': True,
    }

    try:
        loop = asyncio.get_running_loop()
        def search():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(query, download=False)

        result = await loop.run_in_executor(None, search)
        entries = result.get('entries', [])

        if not entries:
            await message.answer("❌ Hech qanday qo'shiq topilmadi.")
            await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)
            return

        user_searches[message.from_user.id] = entries

        text = f"🔎 **{query}** bo'yicha topilgan natijalar:\n\n"
        buttons = []
        row = []

        for i, entry in enumerate(entries[:10], 1):
            title = entry.get('title', 'Nomaʼlum qoʻshiq')
            duration = entry.get('duration', 0)
            if duration:
                mins = duration // 60
                secs = duration % 60
                dur_str = f"⏱ {mins}:{secs:02d}"
            else:
                dur_str = ""
                
            text += f"{i}. {title} {dur_str}\n"
            
            row.append(InlineKeyboardButton(text=str(i), callback_data=f"dl_{i-1}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)

    except Exception as e:
        logging.error(f"Qidiruv xatoligi: {e}")
        await message.answer("❌ Qidirishda xatolik yuz berdi.")
        await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)

# 4. Raqamli tugma bosilganda tanlangan qo'shiqni yuklab yuborish
@dp.callback_query(F.data.startswith("dl_"))
async def download_selected_audio(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_searches:
        await callback.answer("⚠️ Qidiruv muddati eskirgan. Iltimos, qo'shiq nomini qaytadan yozing.", show_alert=True)
        return

    index = int(callback.data.split("_")[1])
    entries = user_searches[user_id]

    if index >= len(entries):
        await callback.answer("⚠️ Xatolik yuz berdi.", show_alert=True)
        return

    selected_entry = entries[index]
    video_url = selected_entry.get('url') or f"https://www.youtube.com/watch?v={selected_entry.get('id')}"

    await callback.message.answer("⏳ Tanlangan qo'shiq yuklab olinmoqda, kuting...")
    
    file_prefix = f"audio_{user_id}"
    ydl_opts = {
        'format': 'bestaudio',
        'outtmpl': f'{file_prefix}_%(id)s.%(ext)s',
        'quiet': True,
        'geo_bypass': True,
        'nocheckcertificate': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
    }

    try:
        loop = asyncio.get_running_loop()
        def download_audio():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                return ydl.prepare_filename(info)

        audio_path = await loop.run_in_executor(None, download_audio)

        if os.path.exists(audio_path):
            audio_file = FSInputFile(audio_path)
            await callback.message.answer_audio(audio_file, caption="🎵 Qo'shiq yuklab berildi!")
            os.remove(audio_path)
        else:
            await callback.message.answer("❌ Qo'shiqni yuklab bo'lmadi.")

    except Exception as e:
        logging.error(f"Audio yuklash xatoligi: {e}")
        await callback.message.answer("❌ Qo'shiqni yuklashda xatolik yuz berdi.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
