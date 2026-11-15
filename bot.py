import os
import time
import asyncio
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, idle
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIGURATION =================
API_ID = int(os.environ.get("API_ID", 39140696))
API_HASH = os.environ.get("API_HASH", "64757b9724e7143c5cc554d7a776334b")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

ADMINS = [7199304293]  # നിങ്ങളുടെ അഡ്മിൻ ID
DATABASE_URI = os.environ.get(
    "DATABASE_URI",
    "mongodb+srv://risham004:risham0043bot@cluster0.d1h9npz.mongodb.net/?retryWrites=true&w=majority"
)
DATABASE_NAME = "MF_Personal_Queue_Renamer"
PORT = int(os.environ.get("PORT", 8080))
# =================================================

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN നൽകിയിട്ടില്ല! Render Environment-ൽ BOT_TOKEN ചേർക്കുക.")
    exit(1)

app = Client(
    "Queue_Renamer_Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# MongoDB Connection
db_client = AsyncIOMotorClient(DATABASE_URI)
db = db_client[DATABASE_NAME]
users_col = db["admin_data"]

# Queue & State management per user
USER_QUEUES = {}
USER_STATES = {}

# Aiohttp Web Server for Render Port 8080
async def health_check(request):
    return web.Response(text="Queue Renamer Bot is Running Alive!")

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"🌐 Web Server started on Port {PORT}")

def get_readable_time(seconds):
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = ''
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f'{int(period_value)}{period_name} '
    return result.strip()

async def progress_for_pyrogram(current, total, ud_type, message, start):
    now = time.time()
    diff = now - start
    if round(diff % 5.0) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        
        progress_str = "[{0}{1}] \n📁 Progress: {2}%\n".format(
            ''.join(["█" for i in range(int(percentage / 10))]),
            ''.join(["░" for i in range(10 - int(percentage / 10))]),
            round(percentage, 2)
        )
        
        tmp = f"{progress_str}" \
              f"📊 Done: {human_readable_size(current)} / {human_readable_size(total)}\n" \
              f"⚡ Speed: {human_readable_size(speed)}/s\n" \
              f"⏱️ ETA: {get_readable_time(time_to_completion)}"
        try:
            await message.edit_text(text=f"📥 **{ud_type}**\n\n{tmp}")
        except Exception:
            pass

def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"

# ----------------- QUEUE PROCESSOR -----------------
async def process_next_in_queue(client: Client, user_id: int, chat_id: int):
    if user_id in USER_STATES and USER_STATES[user_id].get("step") == "waiting_type":
        return

    queue = USER_QUEUES.get(user_id, [])
    if not queue:
        USER_STATES.pop(user_id, None)
        await client.send_message(chat_id, "🎉 **ക്യൂവിലുള്ള എല്ലാ ഫയലുകളും വിജയകരമായി പ്രോസസ്സ് ചെയ്ത് കഴിഞ്ഞു!**")
        return

    next_msg = queue.pop(0)
    orig_name = getattr(next_msg.document or next_msg.video, "file_name", "Unknown_File")
    
    USER_STATES[user_id] = {
        "current_msg": next_msg,
        "filename": None,
        "step": "waiting_name",
        "chat_id": chat_id
    }

    await client.send_message(
        chat_id,
        f"📁 **ലഭിച്ച ഫയൽ:** `{orig_name}`\n"
        f"🔢 **ക്യൂവിൽ ബാക്കിയുള്ളത്:** `{len(queue)}` ഫയലുകൾ\n\n"
        f"📝 **ഈ ഫയലിനുള്ള പുതിയ പേര് (Extension ഉൾപ്പെടെ - ഉദാ: `Movie.mkv`) അയച്ചുതരുക:**"
    )

# ----------------- COMMANDS & HANDLERS -----------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("⛔ ഇത് റീഷാമിന്റെ പെഴ്സണൽ ബോട്ട് ആണ്!")
    
    await message.reply_text(
        "👋 **ഹലോ റീഷാം, വെൽക്കം!**\n\n"
        "ഞാൻ നിങ്ങളുടെ **Queue Batch Renamer & Rethumbnail Bot** ആണ് 🛠️\n\n"
        "📌 **ഉപയോഗിക്കുന്ന വിധം:**\n"
        "1️⃣ ഫോട്ടോ അയച്ചാൽ തമ്പ്നെയിൽ സേവ് ആകും.\n"
        "2️⃣ എത്ര ഫയലുകൾ വേണമെങ്കിലും ഒന്നിച്ച് ഫോർവേഡ് ചെയ്യുക.\n"
        "3️⃣ ഓരോ ഫയലിനും പേര് നൽകി Document ആണോ Video ആണോ എന്ന് തിരഞ്ഞെടുക്കുക!\n\n"
        "🗑️ തമ്പ്നെയിൽ മാറ്റാൻ `/delthumb` അടിക്കുക."
    )

@app.on_message(filters.command("delthumb") & filters.private)
async def delete_thumb(client: Client, message: Message):
    if message.from_user.id not in ADMINS:
        return
    await users_col.update_one({"_id": message.from_user.id}, {"$unset": {"thumb": ""}}, upsert=True)
    await message.reply_text("🗑️ **കസ്റ്റം തമ്പ്നെയിൽ ഡിലീറ്റ് ചെയ്തിരിക്കുന്നു!**")

@app.on_message(filters.photo & filters.private)
async def save_thumbnail(client: Client, message: Message):
    if message.from_user.id not in ADMINS:
        return
    thumb_id = message.photo.file_id
    await users_col.update_one({"_id": message.from_user.id}, {"$set": {"thumb": thumb_id}}, upsert=True)
    await message.reply_text("✅ **കസ്റ്റം തമ്പ്നെയിൽ വിജയകരമായി സേവ് ചെയ്തു!**")

@app.on_message((filters.document | filters.video) & filters.private)
async def receive_files(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        return
    
    if user_id not in USER_QUEUES:
        USER_QUEUES[user_id] = []
    
    USER_QUEUES[user_id].append(message)
    queue_len = len(USER_QUEUES[user_id])

    if user_id not in USER_STATES:
        await process_next_in_queue(client, user_id, message.chat.id)
    else:
        await message.reply_text(f"📌 ഫയൽ ക്യൂവിലേക്ക് ചേർത്തു! (Position: {queue_len})", quote=True)

@app.on_message(filters.text & filters.private & ~filters.command(["start", "delthumb"]))
async def handle_text_input(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        return
    
    state = USER_STATES.get(user_id)
    if not state or state.get("step") != "waiting_name":
        return

    new_filename = message.text.strip()
    if "." not in new_filename:
        return await message.reply_text("⚠️ ഫയൽ നാമത്തിൽ Extension (ഉദാ: `.mkv` അല്ലെങ്കിൽ `.mp4`) ഉൾപ്പെടുത്താൻ മറക്കരുത്!")

    state["filename"] = new_filename
    state["step"] = "waiting_type"

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📄 Send as Document", callback_data="type_document"),
            InlineKeyboardButton("🎬 Send as Video", callback_data="type_video")
        ]
    ])
    await message.reply_text(
        f"🏷️ **പുതിയ പേര്:** `{new_filename}`\n\n"
        f"ഇത് ഏത് ഫോർമാറ്റിലാണ് അയക്കേണ്ടത് എന്ന് തിരഞ്ഞെടുക്കുക:",
        reply_markup=markup
    )

@app.on_callback_query(filters.regex("^type_"))
async def process_file_type(client, callback):
    user_id = callback.from_user.id
    if user_id not in ADMINS:
        return await callback.answer("⛔ Permitted only for admin!", show_alert=True)

    state = USER_STATES.get(user_id)
    if not state or state.get("step") != "waiting_type":
        return await callback.answer("⌛ സെഷൻ എക്സ്പയർ ആയിരിക്കുന്നു!", show_alert=True)

    send_type = callback.data.split("_")[1]
    orig_msg = state["current_msg"]
    new_filename = state["filename"]
    chat_id = state["chat_id"]

    await callback.message.delete()
    status_msg = await client.send_message(chat_id, "⏳ **ഫയൽ ഡൗൺലോഡ് ചെയ്യാൻ തുടങ്ങുന്നു...**")
    start_time = time.time()

    downloads_dir = "downloads"
    os.makedirs(downloads_dir, exist_ok=True)

    try:
        file_path = await client.download_media(
            orig_msg,
            file_name=os.path.join(downloads_dir, new_filename),
            progress=progress_for_pyrogram,
            progress_args=("Downloading File...", status_msg, start_time)
        )

        await status_msg.edit_text("📥 **ഡൗൺലോഡ് പൂർത്തിയായി! തമ്പ്നെയിൽ സെറ്റ് ചെയ്യുന്നു...**")

        user_data = await users_col.find_one({"_id": user_id})
        thumb_path = None
        if user_data and "thumb" in user_data:
            thumb_path = await client.download_media(user_data["thumb"])

        await status_msg.edit_text("📤 **Telegram-ലേക്ക് അപ്‌ലോഡ് ചെയ്യുന്നു...**")
        up_start_time = time.time()

        if send_type == "video":
            await client.send_video(
                chat_id=chat_id,
                video=file_path,
                caption=f"🎬 <b>{new_filename}</b>",
                thumb=thumb_path,
                progress=progress_for_pyrogram,
                progress_args=("Uploading File...", status_msg, up_start_time)
            )
        else:
            await client.send_document(
                chat_id=chat_id,
                document=file_path,
                caption=f"📁 <b>{new_filename}</b>",
                thumb=thumb_path,
                progress=progress_for_pyrogram,
                progress_args=("Uploading File...", status_msg, up_start_time)
            )

        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ **എറർ സംഭവിച്ചു:**\n`{e}`")
    
    finally:
        try:
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            if 'thumb_path' in locals() and thumb_path and os.path.exists(thumb_path):
                os.remove(thumb_path)
        except Exception:
            pass

    USER_STATES.pop(user_id, None)
    await process_next_in_queue(client, user_id, chat_id)

# ----------------- MAIN STARTUP -----------------
async def main():
    await start_web_server()
    await app.start()
    me = await app.get_me()
    print(f"🤖 Queue Renamer Bot Started Successfully as @{me.username}")
    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
