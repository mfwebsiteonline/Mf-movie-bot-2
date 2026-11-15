import os
import re
import math
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient

# ================= CONFIGURATION =================
BOT_NAME = "MF MOVIE BOT 2"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

ADMINS = [7199304293]
LOG_CHANNEL = -1004461624670
FILE_CHANNELS = [-1004345329387]
AUTH_CHANNEL = -1004352245988

DATABASE_URI = os.environ.get(
    "DATABASE_URI",
    "mongodb+srv://risham004:risham0043bot@cluster0.d1h9npz.mongodb.net/?retryWrites=true&w=majority"
)
DATABASE_NAME = "MF_Movie_Bot_2_DB"

START_PIC = "https://i.ibb.co/Z6kwCvsD/83b9b287-1edf-4390-b0dd-c98179ec8374.jpg"
GRP_LNK = "https://t.me/MFMovieandSeriesRequestGroup"
CHNL_LNK = "https://t.me/mfmainchannel"
PORT = int(os.environ.get("PORT", 8080))
# =================================================

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN കാണുന്നില്ല! Render Environment-ൽ BOT_TOKEN നൽകുക.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# MongoDB Connection
mongo_client = MongoClient(DATABASE_URI)
db = mongo_client[DATABASE_NAME]
files_col = db["files"]
users_col = db["users"]

# Flask Web Server for Render
web_app = Flask(__name__)

@web_app.route("/")
def home():
    return f"{BOT_NAME} is Running Alive!"

def run_web():
    web_app.run(host="0.0.0.0", port=PORT)

# ----------------- HELPER FUNCTIONS -----------------
def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"

def add_user(user_id, name):
    try:
        if not users_col.find_one({"_id": user_id}):
            users_col.insert_one({"_id": user_id, "name": name})
            bot.send_message(
                LOG_CHANNEL,
                f"🆕 <b>#NewUser in {BOT_NAME}</b>\n👤 <b>Name:</b> {name}\n🆔 <b>ID:</b> <code>{user_id}</code>"
            )
    except Exception as e:
        print(f"Log error: {e}")

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
    try:
        chat = bot.get_chat(AUTH_CHANNEL)
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
        return bot.export_chat_invite_link(AUTH_CHANNEL)
    except Exception:
        return CHNL_LNK

def save_file_to_db(message):
    media = message.document or message.video or message.audio
    if not media:
        return False
    
    file_name = getattr(media, "file_name", None) or message.caption or "Movie_File"
    clean_name = re.sub(r"[@_\-\.\+]", " ", file_name)
    
    file_doc = {
        "_id": media.file_unique_id,
        "file_id": media.file_id,
        "file_name": file_name,
        "search_name": clean_name.lower(),
        "file_size": media.file_size,
        "file_type": message.content_type
    }
    try:
        files_col.update_one({"_id": media.file_unique_id}, {"$set": file_doc}, upsert=True)
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False

def send_file_to_user(chat_id, file_data):
    caption = (
        f"🎬 <b>{file_data['file_name']}</b>\n"
        f"📦 <b>Size:</b> <code>{get_size(file_data['file_size'])}</code>\n\n"
        f"🤖 <b>Powered By:</b> <b>{BOT_NAME}</b>\n"
        f"📢 <b>Join:</b> <a href='{GRP_LNK}'>Movie Request Group</a>"
    )
    f_type = file_data.get("file_type", "document")
    try:
        if f_type == "video":
            bot.send_video(chat_id, file_data["file_id"], caption=caption)
        elif f_type == "audio":
            bot.send_audio(chat_id, file_data["file_id"], caption=caption)
        else:
            bot.send_document(chat_id, file_data["file_id"], caption=caption)
    except Exception:
        bot.send_document(chat_id, file_data["file_id"], caption=caption)

# ----------------- START & ADMIN COMMANDS -----------------
@bot.message_handler(commands=["start"])
def start_cmd(message):
    if message.chat.type != "private":
        return
    
    user_id = message.from_user.id
    add_user(user_id, message.from_user.first_name)

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("file_"):
        file_unique_id = args[1].split("_", 1)[1]
        
        if not is_subscribed(user_id):
            invite_url = get_invite_link()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url))
            markup.add(InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_{file_unique_id}"))
            return bot.send_message(
                user_id,
                f"❗ <b>നിങ്ങൾ ഞങ്ങളുടെ ചാനലിൽ ജോയിൻ ചെയ്തിട്ടില്ല!</b>\n\n"
                f"<b>{BOT_NAME}</b>-ൽ നിന്ന് ഫയലുകൾ ലഭിക്കാൻ താഴെ കാണുന്ന ബട്ടൺ വഴി ചാനലിൽ ജോയിൻ ചെയ്ത ശേഷം <b>Try Again</b> ക്ലിക്ക് ചെയ്യുക.",
                reply_markup=markup
            )
        
        file_data = files_col.find_one({"_id": file_unique_id})
        if not file_data:
            return bot.send_message(user_id, "❌ ഈ ഫയൽ ഡാറ്റാബേസിൽ കണ്ടെത്താനായില്ല!")
        
        return send_file_to_user(user_id, file_data)

    bot_username = bot.get_me().username
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ Add Me To Your Group ➕", url=f"https://t.me/{bot_username}?startgroup=true"))
    markup.row(
        InlineKeyboardButton("🎬 Request Group", url=GRP_LNK),
        InlineKeyboardButton("📢 Main Channel", url=CHNL_LNK)
    )
    markup.add(InlineKeyboardButton("📊 Bot Status", callback_data="status_cb"))

    bot.send_photo(
        user_id,
        photo=START_PIC,
        caption=(
            f"ഹലോ <b>{message.from_user.first_name}</b> 👋,\n\n"
            f"ഞാൻ <b>{BOT_NAME}</b> ആണ്! 🎬\n\n"
            f"നിങ്ങൾക്ക് ആവശ്യമുള്ള സിനിമകളുടെയോ സീരീസുകളുടെയോ പേര് ഇവിടെയോ ഞങ്ങളുടെ ഗ്രൂപ്പിലോ ടൈപ്പ് ചെയ്ത് അയച്ചാൽ ഉടൻ ഫയൽ ലഭിക്കും."
        ),
        reply_markup=markup
    )

@bot.message_handler(commands=["stats"])
def stats_cmd(message):
    if message.from_user.id not in ADMINS:
        return
    total_files = files_col.count_documents({})
    total_users = users_col.count_documents({})
    bot.reply_to(
        message,
        f"📊 <b>{BOT_NAME} - Statistics</b>\n\n"
        f"📁 <b>Total Files:</b> <code>{total_files}</code>\n"
        f"👥 <b>Total Users:</b> <code>{total_users}</code>"
    )

@bot.message_handler(commands=["deleteall"])
def delete_all_cmd(message):
    if message.from_user.id not in ADMINS:
        return
    files_col.delete_many({})
    bot.reply_to(message, "🗑️ <b>ഡാറ്റാബേസിലെ എല്ലാ ഫയലുകളും ഡിലീറ്റ് ചെയ്തു!</b>")

# ----------------- AUTO CHANNEL & ADMIN FILE SAVING -----------------
@bot.channel_post_handler(content_types=["document", "video", "audio"])
def channel_file_save(message):
    if message.chat.id in FILE_CHANNELS:
        save_file_to_db(message)

@bot.message_handler(content_types=["document", "video", "audio"])
def admin_pm_file_save(message):
    if message.chat.type == "private" and message.from_user.id in ADMINS:
        if save_file_to_db(message):
            bot.reply_to(message, f"✅ <b>ഫയൽ {BOT_NAME} ഡാറ്റാബേസിലേക്ക് സേവ് ചെയ്തിട്ടുണ്ട്!</b>")

# ----------------- SEARCH & PAGINATION -----------------
@bot.message_handler(func=lambda m: m.text and not m.text.startswith("/"), content_types=["text"])
def search_files(message):
    query = message.text.strip()
    if len(query) < 2:
        return

    clean_query = re.sub(r"[@_\-\.\+]", " ", query).lower()
    words = clean_query.split()
    regex_pattern = ".*".join(map(re.escape, words))

    results = list(files_col.find({"search_name": {"$regex": regex_pattern, "$options": "i"}}).limit(50))

    if not results:
        if message.chat.type == "private":
            bot.reply_to(message, "😕 ഈ പേരിൽ ഫയലുകൾ ഒന്നും കണ്ടെത്തിയില്ല. സ്പെല്ലിംഗ് കറക്റ്റ് ആണോ എന്ന് പരിശോധിക്കുക.")
        return

    send_results_page(message, results, query, page=0)

def send_results_page(message_or_call, results, query, page=0, is_edit=False):
    per_page = 10
    total_pages = math.ceil(len(results) / per_page)
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_files = results[start_idx:end_idx]

    bot_username = bot.get_me().username
    markup = InlineKeyboardMarkup()

    for file in current_files:
        size_str = get_size(file["file_size"])
        btn_text = f"[{size_str}] {file['file_name']}"
        markup.add(InlineKeyboardButton(btn_text, url=f"https://t.me/{bot_username}?start=file_{file['_id']}"))

    nav_btns = []
    if page > 0:
        nav_btns.append(InlineKeyboardButton("⬅️ Back", callback_data=f"page_{page-1}_{query[:25]}"))
    nav_btns.append(InlineKeyboardButton(f"📑 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}_{query[:25]}"))

    if len(nav_btns) > 1:
        markup.row(*nav_btns)

    text = (
        f"🤖 <b>{BOT_NAME}</b>\n"
        f"🔍 <b>Search:</b> <code>{query}</code>\n"
        f"📁 <b>Results:</b> <code>{len(results)}</code>\n\n"
        f"👇 <b>താഴെ കാണുന്ന ബട്ടണിൽ ക്ലിക്ക് ചെയ്ത് ഫയൽ ഡൗൺലോഡ് ചെയ്യാം:</b>"
    )

    if is_edit:
        bot.edit_message_text(
            text,
            chat_id=message_or_call.message.chat.id,
            message_id=message_or_call.message.message_id,
            reply_markup=markup
        )
    else:
        bot.reply_to(message_or_call, text, reply_markup=markup)

# ----------------- CALLBACK HANDLERS -----------------
@bot.callback_query_handler(func=lambda call: True)
def cb_handler(call):
    data = call.data
    user_id = call.from_user.id

    if data == "noop":
        bot.answer_callback_query(call.id)

    elif data == "status_cb":
        total_files = files_col.count_documents({})
        total_users = users_col.count_documents({})
        bot.answer_callback_query(
            call.id,
            f"🤖 {BOT_NAME}\n📁 Total Files: {total_files}\n👥 Total Users: {total_users}",
            show_alert=True
        )

    elif data.startswith("checksub_"):
        file_unique_id = data.split("_", 1)[1]
        if not is_subscribed(user_id):
            return bot.answer_callback_query(
                call.id,
                "❌ നിങ്ങൾ ഇതുവരെ ചാനലിൽ ജോയിൻ ചെയ്തിട്ടില്ല! ജോയിൻ ചെയ്ത ശേഷം ശ്രമിക്കുക.",
                show_alert=True
            )
        
        file_data = files_col.find_one({"_id": file_unique_id})
        if not file_data:
            return bot.answer_callback_query(call.id, "❌ ഫയൽ കണ്ടെത്താനായില്ല!", show_alert=True)
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        send_file_to_user(user_id, file_data)

    elif data.startswith("page_"):
        _, page_str, search_q = data.split("_", 2)
        page = int(page_str)
        clean_query = re.sub(r"[@_\-\.\+]", " ", search_q).lower()
        words = clean_query.split()
        regex_pattern = ".*".join(map(re.escape, words))

        results = list(files_col.find({"search_name": {"$regex": regex_pattern, "$options": "i"}}).limit(50))
        if results:
            send_results_page(call, results, search_q, page=page, is_edit=True)
        bot.answer_callback_query(call.id)

# ----------------- START BOT & WEB SERVER -----------------
if __name__ == "__main__":
    # Start Flask server in background thread for Render Port 8080
    threading.Thread(target=run_web, daemon=True).start()
    print(f"🌐 Web Server started on Port {PORT}")

    # Remove any old webhooks and start polling
    bot.remove_webhook()
    me = bot.get_me()
    print(f"🤖 {BOT_NAME} Started Successfully as @{me.username}")
    
    try:
        bot.send_message(LOG_CHANNEL, f"🚀 <b>{BOT_NAME} Started Successfully!</b>")
    except Exception as e:
        print(f"Log Channel Notice: {e}")

    bot.infinity_polling(skip_pending=True)
