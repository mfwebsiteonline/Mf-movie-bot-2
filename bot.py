import os
import re
import math
import time
import uuid
import threading
import urllib.parse
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ================= CONFIGURATION =================
BOT_NAME = "MF MOVIE BOT 2"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9132996644:AAGG5YznyacFrvjUXYW14xA8xdKBIW80Wp4").strip()

ADMINS = [7199304293]
LOG_CHANNEL = -1004461624670
FILE_CHANNELS = [-1004396180197, -1004345329387]
AUTH_CHANNEL = -1004352245988

DATABASE_URI = os.environ.get(
    "DATABASE_URI",
    "mongodb+srv://risham004:risham0043bot@cluster0.d1h9npz.mongodb.net/?retryWrites=true&w=majority"
)
DATABASE_NAME = os.environ.get("DATABASE_NAME", "MF_Movie_Bot_2_DB")

START_PIC = "https://i.ibb.co/Z6kwCvsD/83b9b287-1edf-4390-b0dd-c98179ec8374.jpg"
GRP_LNK = "https://t.me/MFMovieandSeriesRequestGroup"
CHNL_LNK = "https://t.me/mfmainchannel"
PORT = int(os.environ.get("PORT", 8080))

# Auto Delete Time in Seconds (300s = 5 Minutes)
AUTO_DELETE_TIME = 300

# Filter Categories
LANGUAGES = [
    ("Malayalam", "mal"), ("Tamil", "tam"), ("Hindi", "hin"),
    ("English", "eng"), ("Telugu", "tel"), ("Kannada", "kan")
]
QUALITIES = ["360p", "480p", "720p", "1080p", "1440p", "2160p", "4K", "HDRip", "WEB-DL"]
YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"]
SEASONS = ["S01", "S02", "S03", "S04", "S05", "Season 1", "Season 2", "Season 3"]
# =================================================

BOT_START_TIME = time.time()
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
BOT_USERNAME = ""

# MongoDB Connection
mongo_client = MongoClient(DATABASE_URI, serverSelectionTimeoutMS=5000)
db = mongo_client[DATABASE_NAME]
files_col = db["files"]
users_col = db["users"]
groups_col = db["groups"]

def init_db_indexes():
    try:
        files_col.create_index("file_name")
        files_col.create_index("search_name")
    except Exception:
        pass

threading.Thread(target=init_db_indexes, daemon=True).start()

# In-memory caches & states
SEARCH_CACHE = {}
KNOWN_USERS = set()
KNOWN_GROUPS = set()
CACHED_INVITE_LINK = None
INDEX_CANCEL = False

# Flask Web Server for Render
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return f"{BOT_NAME} is Running Fast & Alive!"

def run_web():
    web_app.run(host="0.0.0.0", port=PORT)

# ----------------- HELPER FUNCTIONS -----------------
def send_typing(chat_id, action="typing"):
    try:
        bot.send_chat_action(chat_id, action)
    except Exception:
        pass

def get_size(size):
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"

def get_uptime():
    seconds = int(time.time() - BOT_START_TIME)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)

def auto_delete_message(chat_id, message_id, delay=AUTO_DELETE_TIME):
    if delay <= 0:
        return
    def _delete():
        time.sleep(delay)
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    threading.Thread(target=_delete, daemon=True).start()

def track_user_or_group_async(chat_type, chat_id, user_id, name, title=None):
    def _worker():
        try:
            if chat_type == "private":
                if user_id not in KNOWN_USERS:
                    KNOWN_USERS.add(user_id)
                    if not users_col.find_one({"_id": user_id}):
                        users_col.insert_one({"_id": user_id, "name": name, "joined_at": time.time()})
                        try:
                            bot.send_message(
                                LOG_CHANNEL,
                                f"🆕 <b>#NewUser in {BOT_NAME}</b>\n👤 <b>Name:</b> {name}\n🆔 <b>ID:</b> <code>{user_id}</code>"
                            )
                        except Exception:
                            pass
            else:
                if chat_id not in KNOWN_GROUPS:
                    KNOWN_GROUPS.add(chat_id)
                    if not groups_col.find_one({"_id": chat_id}):
                        groups_col.insert_one({"_id": chat_id, "title": title or "Group", "added_at": time.time()})
                        try:
                            bot.send_message(
                                LOG_CHANNEL,
                                f"👥 <b>#NewGroup in {BOT_NAME}</b>\n🏷️ <b>Title:</b> {title}\n🆔 <b>ID:</b> <code>{chat_id}</code>"
                            )
                        except Exception:
                            pass
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()

def is_subscribed(user_id):
    if not AUTH_CHANNEL or user_id in ADMINS:
        return True
    try:
        member = bot.get_chat_member(AUTH_CHANNEL, user_id)
        if member.status in ["left", "kicked"]:
            return False
        return True
    except Exception:
        return True

def get_invite_link():
    global CACHED_INVITE_LINK
    if CACHED_INVITE_LINK:
        return CACHED_INVITE_LINK
    try:
        chat = bot.get_chat(AUTH_CHANNEL)
        if chat.username:
            CACHED_INVITE_LINK = f"https://t.me/{chat.username}"
        elif chat.invite_link:
            CACHED_INVITE_LINK = chat.invite_link
        else:
            CACHED_INVITE_LINK = bot.export_chat_invite_link(AUTH_CHANNEL)
        return CACHED_INVITE_LINK
    except Exception:
        return CHNL_LNK

def save_file_to_db(message):
    media = message.document or message.video or message.audio
    if not media:
        return False, None
    
    # Extract file name from document/video name OR caption
    raw_file_name = getattr(media, "file_name", None)
    caption_text = message.caption or ""
    
    if raw_file_name:
        file_name = raw_file_name
    elif caption_text:
        file_name = caption_text.split("\n")[0][:80]
    else:
        file_name = f"Movie_File_{media.file_unique_id[:6]}"

    clean_name = re.sub(r"[@_\-\.\+\[\]\(\)\{\}\:\;\'\"\,\!]", " ", str(file_name))
    caption_clean = re.sub(r"[@_\-\.\+\[\]\(\)\{\}\:\;\'\"\,\!]", " ", str(caption_text))
    
    file_doc = {
        "_id": media.file_unique_id,
        "file_id": media.file_id,
        "file_name": file_name,
        "search_name": f"{clean_name} {caption_clean}".lower().strip(),
        "file_size": getattr(media, "file_size", 0),
        "file_type": message.content_type,
        "caption": caption_text or file_name
    }
    try:
        files_col.update_one({"_id": media.file_unique_id}, {"$set": file_doc}, upsert=True)
        return True, file_name
    except Exception as e:
        print(f"DB Save Error: {e}")
        return False, None

def send_file_to_user(chat_id, file_data):
    send_typing(chat_id, "upload_document")
    f_name = file_data.get("file_name", "Movie_File")
    f_size = get_size(file_data.get("file_size", 0))
    f_id = file_data.get("file_id") or file_data.get("_id")

    caption = (
        f"🎬 <b>File Name:</b> <code>{f_name}</code>\n"
        f"📦 <b>File Size:</b> <code>{f_size}</code>\n\n"
        f"🤖 <b>Uploaded By:</b> <a href='{CHNL_LNK}'>{BOT_NAME}</a>\n"
        f"📢 <b>Request Group:</b> <a href='{GRP_LNK}'>Join Here</a>"
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🎬 Request Group", url=GRP_LNK),
        InlineKeyboardButton("📢 Main Channel", url=CHNL_LNK)
    )
    f_type = file_data.get("file_type", "document")
    try:
        if f_type == "video":
            bot.send_video(chat_id, f_id, caption=caption, reply_markup=markup)
        elif f_type == "audio":
            bot.send_audio(chat_id, f_id, caption=caption, reply_markup=markup)
        else:
            bot.send_document(chat_id, f_id, caption=caption, reply_markup=markup)
        return True
    except Exception:
        try:
            bot.send_document(chat_id, f_id, caption=caption, reply_markup=markup)
            return True
        except Exception:
            try:
                bot.send_video(chat_id, f_id, caption=caption, reply_markup=markup)
                return True
            except Exception:
                return False

def get_all_file_collections():
    cols = [files_col]
    try:
        for db_name in mongo_client.list_database_names():
            if db_name in ["admin", "local", "config"]:
                continue
            curr_db = mongo_client[db_name]
            for col_name in curr_db.list_collection_names():
                if col_name in ["users", "groups", "chats", "banned", "admin_data"]:
                    continue
                c = curr_db[col_name]
                if c.full_name != files_col.full_name:
                    cols.append(c)
    except Exception:
        pass
    return cols

def query_db_files(search_text):
    clean_query = re.sub(r"[@_\-\.\+\[\]\(\)\{\}\:\;\'\"\,\!]", " ", search_text).lower().strip()
    words = [w for w in clean_query.split() if len(w) > 0]
    if not words:
        return []
    
    # Match each word anywhere in the file_name, search_name, or caption
    and_conditions = []
    for w in words:
        esc = re.escape(w)
        and_conditions.append({
            "$or": [
                {"search_name": {"$regex": esc, "$options": "i"}},
                {"file_name": {"$regex": esc, "$options": "i"}},
                {"caption": {"$regex": esc, "$options": "i"}}
            ]
        })
    query_filter = {"$and": and_conditions}

    results = []
    seen_ids = set()

    for col in get_all_file_collections():
        try:
            cursor = col.find(query_filter).limit(60)
            for doc in cursor:
                if "file_name" not in doc and "caption" not in doc:
                    continue
                uid = str(doc.get("_id"))
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    if "file_name" not in doc:
                        doc["file_name"] = str(doc.get("caption", "Movie_File"))[:60]
                    if "search_name" not in doc:
                        fn = str(doc.get("file_name", ""))
                        cp = str(doc.get("caption", ""))
                        doc["search_name"] = re.sub(r"[@_\-\.\+\[\]\(\)]", " ", f"{fn} {cp}").lower()
                    if "file_id" not in doc:
                        doc["file_id"] = doc["_id"]
                    results.append(doc)
                if len(results) >= 60:
                    break
        except Exception:
            continue
        if len(results) >= 60:
            break

    return results

def find_file_by_id(file_unique_id):
    for col in get_all_file_collections():
        try:
            doc = col.find_one({"_id": file_unique_id})
            if doc:
                if "file_id" not in doc:
                    doc["file_id"] = doc["_id"]
                return doc
        except Exception:
            continue
    return None

def generate_full_status_text():
    total_files = 0
    total_media_size = 0
    for col in get_all_file_collections():
        try:
            sample = col.find_one()
            if sample and ("file_name" in sample or "file_size" in sample):
                total_files += col.count_documents({})
                pipeline = [{"$group": {"_id": None, "sz": {"$sum": "$file_size"}}}]
                agg = list(col.aggregate(pipeline))
                if agg:
                    total_media_size += agg[0].get("sz", 0) or 0
        except Exception:
            pass

    total_users = users_col.count_documents({})
    total_groups = groups_col.count_documents({})

    try:
        db_stats = db.command("dbstats")
        data_size = db_stats.get("dataSize", 0)
        storage_size = db_stats.get("storageSize", 0)
        index_size = db_stats.get("indexSize", 0)
        total_db_used = storage_size + index_size
        free_db_space = max(0, (512 * 1024 * 1024) - total_db_used)
        collections_count = db_stats.get("collections", 0)
    except Exception:
        data_size = storage_size = index_size = total_db_used = free_db_space = collections_count = 0

    return (
        f"📊 <b>{BOT_NAME} - FULL ADMIN & DB STATUS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot System Status:</b>\n"
        f"├ 🟢 <b>Status:</b> Online (Fast Mode)\n"
        f"├ ⏱️ <b>Uptime:</b> <code>{get_uptime()}</code>\n"
        f"├ 👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"└ 💬 <b>Total Groups:</b> <code>{total_groups}</code>\n\n"
        f"📁 <b>Indexed Media Details:</b>\n"
        f"├ 📢 <b>DB Channel:</b> <code>-1004396180197</code>\n"
        f"├ 🎬 <b>Total Files:</b> <code>{total_files}</code>\n"
        f"└ 📦 <b>Total Media Size:</b> <code>{get_size(total_media_size)}</code>\n\n"
        f"🗄️ <b>MongoDB Database Details:</b>\n"
        f"├ 🏷️ <b>Active DB:</b> <code>{DATABASE_NAME}</code>\n"
        f"├ 📂 <b>Collections:</b> <code>{collections_count}</code>\n"
        f"├ 📝 <b>Data Size:</b> <code>{get_size(data_size)}</code>\n"
        f"├ 🗂️ <b>Storage Size:</b> <code>{get_size(storage_size)}</code>\n"
        f"├ 🔍 <b>Index Size:</b> <code>{get_size(index_size)}</code>\n"
        f"├ 💾 <b>Used DB Space:</b> <code>{get_size(total_db_used)} / 512 MB</code>\n"
        f"└ 🆓 <b>Free DB Space:</b> <code>{get_size(free_db_space)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

# ----------------- START & ADMIN COMMANDS -----------------
@bot.message_handler(commands=["start"])
def start_cmd(message):
    send_typing(message.chat.id)
    user_id = message.from_user.id
    track_user_or_group_async(
        message.chat.type, message.chat.id, user_id,
        message.from_user.first_name, getattr(message.chat, "title", None)
    )

    args = message.text.split()
    if len(args) > 1:
        param = args[1]
        
        if param.startswith("all_"):
            parts = param.split("_")
            sid = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 0

            if not is_subscribed(user_id):
                invite_url = get_invite_link()
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url))
                markup.add(InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{BOT_USERNAME}?start={param}"))
                return bot.send_message(
                    message.chat.id,
                    f"❗ <b>Access Denied!</b>\n\n"
                    f"You must join our main channel to download files from <b>{BOT_NAME}</b>.\n"
                    f"Click the button below to join, then tap <b>Try Again</b>.",
                    reply_markup=markup
                )

            session = SEARCH_CACHE.get(sid)
            if not session:
                return bot.send_message(message.chat.id, "⌛ Search session expired. Please type the movie name again.")
            
            results = session["filtered"]
            files_to_send = results[page * 10 : (page + 1) * 10]
            bot.send_message(message.chat.id, f"📥 <b>Sending {len(files_to_send)} files...</b>")
            for f in files_to_send:
                send_file_to_user(message.chat.id, f)
                time.sleep(0.25)
            return

        if param.startswith("file_"):
            file_unique_id = param.split("_", 1)[1]
            
            if not is_subscribed(user_id):
                invite_url = get_invite_link()
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url))
                markup.add(InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_{file_unique_id}"))
                return bot.send_message(
                    message.chat.id,
                    f"❗ <b>Access Denied!</b>\n\n"
                    f"You must join our main channel to get files from <b>{BOT_NAME}</b>.\n"
                    f"Join using the button below and click <b>Try Again</b>.",
                    reply_markup=markup
                )
            
            file_data = find_file_by_id(file_unique_id)
            if not file_data:
                return bot.send_message(message.chat.id, "❌ File not found in the database!")
            
            return send_file_to_user(message.chat.id, file_data)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ Add Me To Your Group ➕", url=f"https://t.me/{BOT_USERNAME}?startgroup=true"))
    markup.row(
        InlineKeyboardButton("🎬 Request Group", url=GRP_LNK),
        InlineKeyboardButton("📢 Main Channel", url=CHNL_LNK)
    )
    markup.row(
        InlineKeyboardButton("🛠️ Help & Commands", callback_data="help_cb"),
        InlineKeyboardButton("ℹ️ About Bot", callback_data="about_cb")
    )
    if user_id in ADMINS:
        markup.add(InlineKeyboardButton("📊 Admin Full DB Status", callback_data="full_status_cb"))

    caption_text = (
        f"Hello <b>{message.from_user.first_name}</b> 👋,\n\n"
        f"Welcome to <b>{BOT_NAME}</b>! 🎬\n\n"
        f"✨ <b>Bot Features:</b>\n"
        f"• <b>Direct PM Search:</b> Just send any movie or series name here to get instant download buttons.\n"
        f"• <b>Group Auto-Filter:</b> Add me to your group to provide instant movie results.\n"
        f"• <b>Smart Filters:</b> Filter files by Language, Quality, Year, and Season.\n\n"
        f"👇 <b>Type any movie or series name below to start searching!</b>"
    )
    try:
        bot.send_photo(message.chat.id, photo=START_PIC, caption=caption_text, reply_markup=markup)
    except Exception:
        bot.send_message(message.chat.id, caption_text, reply_markup=markup)

@bot.message_handler(commands=["index"])
def index_cmd(message):
    send_typing(message.chat.id)
    if message.from_user.id not in ADMINS:
        return bot.reply_to(message, "⛔ This command is restricted to Admins only!")
    
    bot.reply_to(
        message,
        "🗂️ <b>How to Bulk Index Channel Files:</b>\n\n"
        "1️⃣ Make sure this bot is <b>Admin</b> in your File Database Channel (<code>-1004396180197</code>).\n"
        "2️⃣ <b>Forward the last message/file</b> from your File Channel directly to this bot.\n"
        "3️⃣ Click the <b>✅ Start Bulk Indexing</b> button that appears!\n\n"
        "💡 <i>Note: Any new file posted in your DB channel is also indexed automatically!</i>"
    )

@bot.message_handler(commands=["status", "stats", "db"])
def status_cmd(message):
    send_typing(message.chat.id)
    if message.from_user.id not in ADMINS:
        return bot.reply_to(message, "⛔ This command is restricted to Admins only!")
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_status"))
    bot.reply_to(message, generate_full_status_text(), reply_markup=markup)

@bot.message_handler(commands=["deleteall"])
def delete_all_cmd(message):
    send_typing(message.chat.id)
    if message.from_user.id not in ADMINS:
        return
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Yes, Delete All", callback_data="confirm_delall"),
        InlineKeyboardButton("❌ Cancel", callback_data="close_msg")
    )
    bot.reply_to(message, "⚠️ <b>Are you sure you want to delete ALL indexed files from the database?</b>", reply_markup=markup)

@bot.message_handler(commands=["broadcast"])
def broadcast_cmd(message):
    send_typing(message.chat.id)
    if message.from_user.id not in ADMINS:
        return
    if not message.reply_to_message:
        return bot.reply_to(message, "ℹ️ Please reply to a message with <code>/broadcast</code> to send it to all users.")
    
    users = list(users_col.find({}))
    sts = bot.reply_to(message, f"⏳ <b>Broadcasting message to {len(users)} users...</b>")
    success = 0
    failed = 0
    for user in users:
        try:
            bot.copy_message(user["_id"], message.chat.id, message.reply_to_message.message_id)
            success += 1
            time.sleep(0.05)
        except Exception:
            failed += 1
    bot.edit_message_text(
        f"✅ <b>Broadcast Completed!</b>\n\n🟢 <b>Success:</b> <code>{success}</code>\n🔴 <b>Failed:</b> <code>{failed}</code>",
        chat_id=sts.chat.id,
        message_id=sts.message_id
    )

# ----------------- AUTO CHANNEL & BULK INDEXING -----------------
@bot.channel_post_handler(content_types=["document", "video", "audio"])
def channel_file_save(message):
    # Automatically index from ANY channel where bot is admin
    ok, fname = save_file_to_db(message)
    if ok:
        print(f"✅ Auto-Indexed from Channel ({message.chat.id}): {fname}")
        for admin_id in ADMINS:
            try:
                bot.send_message(
                    admin_id,
                    f"✅ <b>New File Auto-Indexed!</b>\n"
                    f"🎬 <b>File:</b> <code>{fname}</code>\n"
                    f"📢 <b>Channel:</b> {message.chat.title or message.chat.id}"
                )
            except Exception:
                pass

@bot.edited_channel_post_handler(content_types=["document", "video", "audio"])
def edited_channel_file_save(message):
    save_file_to_db(message)

@bot.message_handler(content_types=["document", "video", "audio", "text"], func=lambda m: m.forward_from_chat is not None)
def handle_forwarded_channel_msg(message):
    if not message.from_user or message.from_user.id not in ADMINS:
        return
    if message.forward_from_chat.type == "channel":
        send_typing(message.chat.id)
        # Also save this single file immediately if it contains media
        save_file_to_db(message)
        
        chat_id = message.forward_from_chat.id
        chat_title = message.forward_from_chat.title or str(chat_id)
        last_msg_id = message.forward_from_message_id

        if not last_msg_id:
            return bot.reply_to(message, "✅ File saved! (Note: Forward from a channel where bot is Admin to bulk index old files).")

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ Start Bulk Indexing", callback_data=f"startidx_{chat_id}_{last_msg_id}"))
        markup.add(InlineKeyboardButton("❌ Cancel", callback_data="close_msg"))

        bot.reply_to(
            message,
            f"🗂️ <b>Channel Detected for Bulk Indexing!</b>\n\n"
            f"📢 <b>Channel Name:</b> {chat_title}\n"
            f"🆔 <b>Channel ID:</b> <code>{chat_id}</code>\n"
            f"🔢 <b>Messages to Scan:</b> <code>1 to {last_msg_id}</code>\n\n"
            f"Do you want to scan and index all files from this channel into the database?",
            reply_markup=markup
        )

@bot.message_handler(content_types=["document", "video", "audio"])
def pm_or_group_file_save(message):
    if message.from_user and message.from_user.id in ADMINS:
        send_typing(message.chat.id)
        ok, fname = save_file_to_db(message)
        if ok and message.chat.type == "private":
            bot.reply_to(message, f"✅ <b>File Successfully Saved to Database!</b>\n🎬 <code>{fname}</code>")

def run_bulk_index(chat_id, last_msg_id, status_msg):
    global INDEX_CANCEL
    INDEX_CANCEL = False
    saved = 0
    checked = 0
    failed = 0

    for msg_id in range(last_msg_id, 0, -1):
        if INDEX_CANCEL:
            try:
                bot.edit_message_text(
                    f"🛑 <b>Bulk Indexing Cancelled!</b>\n\n"
                    f"📊 <b>Messages Scanned:</b> <code>{checked}</code>\n"
                    f"✅ <b>Files Indexed:</b> <code>{saved}</code>",
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id
                )
            except Exception:
                pass
            return

        checked += 1
        try:
            # Forward message to LOG_CHANNEL temporarily to inspect media via Bot API
            fwd = bot.forward_message(LOG_CHANNEL, chat_id, msg_id, disable_notification=True)
            if fwd and (fwd.document or fwd.video or fwd.audio):
                ok, _ = save_file_to_db(fwd)
                if ok:
                    saved += 1
            try:
                bot.delete_message(LOG_CHANNEL, fwd.message_id)
            except Exception:
                pass
            time.sleep(0.15)
        except Exception as e:
            err_str = str(e).lower()
            if "retry after" in err_str:
                wait_sec = int(re.findall(r"\d+", err_str)[-1]) if re.findall(r"\d+", err_str) else 5
                time.sleep(wait_sec + 1)
            else:
                failed += 1

        if checked % 20 == 0 or checked == last_msg_id:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🛑 Stop Indexing", callback_data="cancel_index"))
            try:
                bot.edit_message_text(
                    f"🔄 <b>Bulk Indexing in Progress...</b>\n\n"
                    f"📢 <b>Channel ID:</b> <code>{chat_id}</code>\n"
                    f"🔍 <b>Scanned:</b> <code>{checked} / {last_msg_id}</code>\n"
                    f"✅ <b>Files Saved:</b> <code>{saved}</code>\n"
                    f"⏭️ <b>Skipped (Non-media/Deleted):</b> <code>{failed}</code>",
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=markup
                )
            except Exception:
                pass

    try:
        bot.edit_message_text(
            f"✅ <b>Bulk Indexing Completed Successfully!</b>\n\n"
            f"📊 <b>Total Messages Scanned:</b> <code>{checked}</code>\n"
            f"🎬 <b>Total Files Indexed:</b> <code>{saved}</code>",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
    except Exception:
        pass

# ----------------- FAST SEARCH & ADVANCED FILTER ENGINE -----------------
@bot.message_handler(content_types=["text"])
def handle_search(message):
    if not message.text or message.text.startswith("/"):
        return

    # Show "typing..." status immediately
    send_typing(message.chat.id, "typing")

    track_user_or_group_async(
        message.chat.type, message.chat.id, message.from_user.id,
        message.from_user.first_name, getattr(message.chat, "title", None)
    )

    query = re.sub(r"@\w+", "", message.text).strip()
    if len(query) < 2:
        return

    results = query_db_files(query)

    if not results:
        google_url = f"https://www.google.com/search?q={urllib.parse.quote(query + ' movie')}"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔍 Check Spelling on Google", url=google_url))
        markup.add(InlineKeyboardButton("🎬 Request in Group", url=GRP_LNK))
        
        reply_msg = bot.reply_to(
            message,
            f"😕 Sorry <b>{message.from_user.first_name}</b>, no files found for <code>{query}</code>!\n\n"
            f"• Please check the spelling on Google using the button below.\n"
            f"• Make sure files are indexed in the database using <code>/index</code>.",
            reply_markup=markup
        )
        if message.chat.type != "private":
            auto_delete_message(reply_msg.chat.id, reply_msg.message_id, 45)
        return

    sid = uuid.uuid4().hex[:8]
    if len(SEARCH_CACHE) > 500:
        SEARCH_CACHE.clear()

    SEARCH_CACHE[sid] = {
        "query": query,
        "all_results": results,
        "filtered": results,
        "filter_label": "All Files",
        "user_id": message.from_user.id
    }

    sent_msg = render_filter_page(message, sid, page=0, is_edit=False)
    if sent_msg and message.chat.type != "private":
        auto_delete_message(sent_msg.chat.id, sent_msg.message_id, AUTO_DELETE_TIME)

def render_filter_page(message_or_call, sid, page=0, is_edit=False):
    session = SEARCH_CACHE.get(sid)
    if not session:
        if is_edit:
            bot.answer_callback_query(message_or_call.id, "⌛ Session Expired! Please search again.", show_alert=True)
        return None

    results = session["filtered"]
    query = session["query"]
    filter_label = session["filter_label"]

    per_page = 10
    total_pages = max(1, math.ceil(len(results) / per_page))
    page = max(0, min(page, total_pages - 1))
    start_idx = page * per_page
    current_files = results[start_idx : start_idx + per_page]

    markup = InlineKeyboardMarkup()

    markup.add(
        InlineKeyboardButton(
            f"📤 Send All Files ({len(current_files)}) 📤",
            callback_data=f"sendall_{sid}_{page}"
        )
    )

    markup.row(
        InlineKeyboardButton("🌐 Language", callback_data=f"menu_lang_{sid}"),
        InlineKeyboardButton("🎞️ Quality", callback_data=f"menu_qual_{sid}"),
        InlineKeyboardButton("📅 Year", callback_data=f"menu_year_{sid}")
    )
    if filter_label != "All Files":
        markup.row(
            InlineKeyboardButton("📺 Seasons", callback_data=f"menu_seas_{sid}"),
            InlineKeyboardButton("🔄 Reset Filter", callback_data=f"flt_reset_all_{sid}")
        )
    else:
        markup.add(InlineKeyboardButton("📺 Seasons / Episodes", callback_data=f"menu_seas_{sid}"))

    for idx, file in enumerate(current_files):
        size_str = get_size(file.get("file_size", 0))
        btn_text = f"🎬 [{size_str}] {file.get('file_name', 'Movie')}"
        markup.add(InlineKeyboardButton(btn_text[:60], callback_data=f"fidx_{sid}_{start_idx + idx}"))

    nav_btns = []
    if page > 0:
        nav_btns.append(InlineKeyboardButton("⬅️ Back", callback_data=f"pg_{sid}_{page-1}"))
    nav_btns.append(InlineKeyboardButton(f"📑 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"pg_{sid}_{page+1}"))

    if len(nav_btns) > 1:
        markup.row(*nav_btns)

    markup.add(InlineKeyboardButton("❌ Close Menu", callback_data="close_msg"))

    text = (
        f"🤖 <b>{BOT_NAME}</b>\n"
        f"🎬 <b>Search Query:</b> <code>{query}</code>\n"
        f"🏷️ <b>Filter Applied:</b> <code>{filter_label}</code>\n"
        f"📁 <b>Total Files Found:</b> <code>{len(results)}</code>\n"
        f"⏳ <i>Auto-Delete in 5 Minutes</i>\n\n"
        f"👇 <b>Click on any file button below to download instantly:</b>"
    )

    if is_edit:
        try:
            return bot.edit_message_text(
                text,
                chat_id=message_or_call.message.chat.id,
                message_id=message_or_call.message.message_id,
                reply_markup=markup
            )
        except Exception:
            return None
    else:
        return bot.reply_to(message_or_call, text, reply_markup=markup)

# ----------------- CALLBACK HANDLERS -----------------
@bot.callback_query_handler(func=lambda call: True)
def cb_handler(call):
    global INDEX_CANCEL
    data = call.data
    user_id = call.from_user.id

    if data == "noop":
        bot.answer_callback_query(call.id)

    elif data == "close_msg":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

    elif data == "cancel_index":
        if user_id not in ADMINS:
            return bot.answer_callback_query(call.id, "⛔ Admin Only!", show_alert=True)
        INDEX_CANCEL = True
        bot.answer_callback_query(call.id, "🛑 Stopping bulk index...", show_alert=True)

    elif data.startswith("startidx_"):
        if user_id not in ADMINS:
            return bot.answer_callback_query(call.id, "⛔ Admin Only!", show_alert=True)
        _, chat_id_str, last_id_str = data.split("_")
        chat_id = int(chat_id_str)
        last_msg_id = int(last_id_str)

        bot.answer_callback_query(call.id, "🚀 Bulk Indexing Started!")
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🛑 Stop Indexing", callback_data="cancel_index"))
        status_msg = bot.edit_message_text(
            f"⏳ <b>Starting Bulk Indexing for Channel <code>{chat_id}</code>...</b>\n"
            f"<i>Please make sure the bot is Admin in both the File Channel and Log Channel (<code>{LOG_CHANNEL}</code>).</i>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        threading.Thread(target=run_bulk_index, args=(chat_id, last_msg_id, status_msg), daemon=True).start()

    elif data == "help_cb":
        help_txt = (
            f"🛠️ <b>{BOT_NAME} - Help & Commands</b>\n\n"
            f"1️⃣ <b>Direct PM Search:</b> Send any movie/series name here to get instant files.\n"
            f"2️⃣ <b>Group Auto-Filter:</b> Add the bot as Admin in your group to search movies there.\n"
            f"3️⃣ <b>Auto & Bulk Indexing:</b>\n"
            f"• New files posted in DB Channel (<code>-1004396180197</code>) are saved automatically.\n"
            f"• Forward the last message from your DB Channel to the bot to bulk index old files.\n\n"
            f"4️⃣ <b>Admin Commands:</b>\n"
            f"• <code>/index</code> - Instructions to bulk index channel files\n"
            f"• <code>/status</code> or <code>/db</code> - Full Database & Bot Status\n"
            f"• <code>/broadcast</code> - Reply to a message to broadcast to all users\n"
            f"• <code>/deleteall</code> - Clear all indexed files"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Close", callback_data="close_msg"))
        bot.send_message(call.message.chat.id, help_txt, reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif data == "about_cb":
        about_txt = (
            f"ℹ️ <b>About {BOT_NAME}</b>\n\n"
            f"🤖 <b>Bot Name:</b> {BOT_NAME}\n"
            f"⚡ <b>Engine:</b> Multi-Threaded Auto-Filter v4.0\n"
            f"🗄️ <b>Database:</b> MongoDB Cloud\n"
            f"📢 <b>Main Channel:</b> <a href='{CHNL_LNK}'>Click Here</a>\n"
            f"🎬 <b>Request Group:</b> <a href='{GRP_LNK}'>Click Here</a>"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("❌ Close", callback_data="close_msg"))
        bot.send_message(call.message.chat.id, about_txt, reply_markup=markup)
        bot.answer_callback_query(call.id)

    elif data == "confirm_delall":
        if user_id not in ADMINS:
            return bot.answer_callback_query(call.id, "⛔ Admin Only!", show_alert=True)
        files_col.delete_many({})
        bot.edit_message_text(
            "🗑️ <b>All files have been successfully deleted from the database!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

    elif data in ["full_status_cb", "refresh_status"]:
        if user_id not in ADMINS:
            return bot.answer_callback_query(call.id, "⛔ Admin Only!", show_alert=True)
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_status"),
            InlineKeyboardButton("❌ Close", callback_data="close_msg")
        )
        try:
            if data == "refresh_status":
                bot.edit_message_text(
                    generate_full_status_text(),
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                bot.answer_callback_query(call.id, "✅ Status Refreshed!")
            else:
                bot.send_message(call.message.chat.id, generate_full_status_text(), reply_markup=markup)
                bot.answer_callback_query(call.id)
        except Exception:
            bot.answer_callback_query(call.id, "✅ Already Up-to-date!")

    elif data.startswith("menu_"):
        _, mtype, sid = data.split("_", 2)
        session = SEARCH_CACHE.get(sid)
        if not session:
            return bot.answer_callback_query(call.id, "⌛ Session Expired! Please search again.", show_alert=True)

        markup = InlineKeyboardMarkup()
        if mtype == "lang":
            btns = [InlineKeyboardButton(f"🌐 {name}", callback_data=f"flt_lang_{code}_{sid}") for name, code in LANGUAGES]
            for i in range(0, len(btns), 2):
                markup.row(*btns[i:i+2])
            title = "🌐 <b>Select your preferred Language:</b>"
        elif mtype == "qual":
            btns = [InlineKeyboardButton(f"🎞️ {q}", callback_data=f"flt_qual_{q.lower()}_{sid}") for q in QUALITIES]
            for i in range(0, len(btns), 3):
                markup.row(*btns[i:i+3])
            title = "🎞️ <b>Select your preferred Video Quality:</b>"
        elif mtype == "year":
            btns = [InlineKeyboardButton(f"📅 {y}", callback_data=f"flt_year_{y}_{sid}") for y in YEARS]
            for i in range(0, len(btns), 3):
                markup.row(*btns[i:i+3])
            title = "📅 <b>Select Release Year:</b>"
        elif mtype == "seas":
            btns = [InlineKeyboardButton(f"📺 {s}", callback_data=f"flt_seas_{s.lower()}_{sid}") for s in SEASONS]
            for i in range(0, len(btns), 2):
                markup.row(*btns[i:i+2])
            title = "📺 <b>Select Season:</b>"

        markup.add(InlineKeyboardButton("⬅️ Back to Files", callback_data=f"pg_{sid}_0"))
        bot.edit_message_text(
            f"🎬 <b>Search Query:</b> <code>{session['query']}</code>\n\n{title}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)

    elif data.startswith("flt_"):
        _, ftype, fval, sid = data.split("_", 3)
        session = SEARCH_CACHE.get(sid)
        if not session:
            return bot.answer_callback_query(call.id, "⌛ Session Expired! Please search again.", show_alert=True)

        if ftype == "reset":
            session["filtered"] = session["all_results"]
            session["filter_label"] = "All Files"
            bot.answer_callback_query(call.id, "🔄 Filter Reset!")
            return render_filter_page(call, sid, page=0, is_edit=True)

        matched = []
        for f in session["all_results"]:
            sname = f.get("search_name", "")
            if ftype == "lang":
                full_name = next((name.lower() for name, code in LANGUAGES if code == fval), fval)
                if fval in sname or full_name in sname:
                    matched.append(f)
            else:
                if fval in sname:
                    matched.append(f)

        if not matched:
            return bot.answer_callback_query(
                call.id,
                f"😕 No files found matching '{fval.upper()}'!",
                show_alert=True
            )

        session["filtered"] = matched
        session["filter_label"] = fval.upper()
        bot.answer_callback_query(call.id, f"✅ Found {len(matched)} files for {fval.upper()}!")
        render_filter_page(call, sid, page=0, is_edit=True)

    elif data.startswith("pg_"):
        _, sid, page_str = data.split("_", 2)
        render_filter_page(call, sid, page=int(page_str), is_edit=True)
        bot.answer_callback_query(call.id)

    elif data.startswith("sendall_"):
        _, sid, page_str = data.split("_", 2)
        page = int(page_str)
        session = SEARCH_CACHE.get(sid)
        if not session:
            return bot.answer_callback_query(call.id, "⌛ Session Expired!", show_alert=True)

        if not is_subscribed(user_id):
            invite_url = get_invite_link()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url))
            markup.add(InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{BOT_USERNAME}?start=all_{sid}_{page}"))
            bot.answer_callback_query(call.id, "❗ Please join our channel first!", show_alert=True)
            return bot.send_message(
                call.message.chat.id,
                f"❗ <b>Hello {call.from_user.first_name}, you haven't joined our main channel yet!</b>\n\n"
                f"Please join our channel using the button below and click <b>Try Again</b>.",
                reply_markup=markup
            )

        files_to_send = session["filtered"][page * 10 : (page + 1) * 10]
        bot.answer_callback_query(call.id, f"📥 Sending {len(files_to_send)} files...")
        for f in files_to_send:
            if not send_file_to_user(user_id, f):
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📥 Click Here to Get All Files in PM", url=f"https://t.me/{BOT_USERNAME}?start=all_{sid}_{page}"))
                return bot.send_message(
                    call.message.chat.id,
                    f"👋 <b>{call.from_user.first_name}</b>, click the button below and press <b>Start</b> to receive all files in your PM:",
                    reply_markup=markup
                )
            time.sleep(0.25)

    elif data.startswith("fidx_"):
        _, sid, idx_str = data.split("_", 2)
        idx = int(idx_str)
        session = SEARCH_CACHE.get(sid)
        if not session or idx >= len(session["filtered"]):
            return bot.answer_callback_query(call.id, "⌛ Session Expired! Please search again.", show_alert=True)

        file_data = session["filtered"][idx]
        file_unique_id = str(file_data.get("_id"))

        if not is_subscribed(user_id):
            invite_url = get_invite_link()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url))
            markup.add(InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_{sid}_{idx}"))
            bot.answer_callback_query(call.id, "❗ Please join our channel first!", show_alert=True)
            return bot.send_message(
                call.message.chat.id,
                f"❗ <b>Hello {call.from_user.first_name}, you haven't joined our main channel yet!</b>\n\n"
                f"Please join using the button below and tap <b>Try Again</b> to get your file instantly.",
                reply_markup=markup
            )

        if call.message.chat.type == "private":
            bot.answer_callback_query(call.id, "📥 Sending your file...")
            send_file_to_user(user_id, file_data)
        else:
            if send_file_to_user(user_id, file_data):
                bot.answer_callback_query(call.id, "✅ File has been sent to your PM (Inbox)!", show_alert=True)
            else:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📥 Click Here to Download in PM", url=f"https://t.me/{BOT_USERNAME}?start=file_{file_unique_id}"))
                bot.answer_callback_query(call.id, "👉 Click the button below to start the bot!", show_alert=True)
                msg = bot.send_message(
                    call.message.chat.id,
                    f"👋 <b>{call.from_user.first_name}</b>, click the button below to receive the file directly in your PM:",
                    reply_markup=markup
                )
                auto_delete_message(msg.chat.id, msg.message_id, 60)

    elif data.startswith("checksub_"):
        parts = data.split("_")
        if not is_subscribed(user_id):
            return bot.answer_callback_query(
                call.id,
                "❌ You still haven't joined the channel! Please join first and try again.",
                show_alert=True
            )
        
        file_data = None
        if len(parts) == 3:
            sid, idx_str = parts[1], parts[2]
            session = SEARCH_CACHE.get(sid)
            if session and int(idx_str) < len(session["filtered"]):
                file_data = session["filtered"][int(idx_str)]
        if not file_data:
            file_data = find_file_by_id(parts[-1])

        if not file_data:
            return bot.answer_callback_query(call.id, "❌ File not found!", show_alert=True)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.answer_callback_query(call.id, "✅ Sending your file...")
        if not send_file_to_user(user_id, file_data):
            send_file_to_user(call.message.chat.id, file_data)

# ----------------- START BOT & WEB SERVER -----------------
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print(f"🌐 Web Server started on Port {PORT}")

    bot.remove_webhook()
    me = bot.get_me()
    BOT_USERNAME = me.username
    print(f"🤖 {BOT_NAME} Started Fast & Ready as @{BOT_USERNAME}")
    
    # Explicitly enable channel_post so DB channel uploads are ALWAYS captured!
    bot.infinity_polling(
        timeout=20,
        long_polling_timeout=10,
        skip_pending=True,
        allowed_updates=["message", "edited_message", "channel_post", "edited_channel_post", "callback_query"]
    )
