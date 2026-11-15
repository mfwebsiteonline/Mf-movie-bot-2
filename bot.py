import os
import re
import math
import asyncio
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait

# ================= CONFIGURATION =================
BOT_NAME = "MF MOVIE BOT 2"
API_ID = 39140696
API_HASH = "64757b9724e7143c5cc554d7a776334b"
BOT_TOKEN = "9132996644:AAGG5YznyacFrvjUXYW14xA8xdKBIW80Wp4"

ADMINS = [7199304293]
LOG_CHANNEL = -1004461624670
FILE_CHANNELS = [-1004345329387]
AUTH_CHANNEL = -1004352245988

DATABASE_URI = "mongodb+srv://risham004:risham0043bot@cluster0.d1h9npz.mongodb.net/?retryWrites=true&w=majority"
DATABASE_NAME = "MF_Movie_Bot_2_DB"

START_PIC = "https://i.ibb.co/Z6kwCvsD/83b9b287-1edf-4390-b0dd-c98179ec8374.jpg"
GRP_LNK = "https://t.me/MFMovieandSeriesRequestGroup"
CHNL_LNK = "https://t.me/mfmainchannel"
PORT = int(os.environ.get("PORT", 8080))
# =================================================

app = Client("MF_MOVIE_BOT_2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB Connection
db_client = AsyncIOMotorClient(DATABASE_URI)
db = db_client[DATABASE_NAME]
files_col = db["files"]
users_col = db["users"]

INVITE_LINK = None
INDEX_CANCEL = False

def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        i += 1
        size /= 1024.0
    return f"{size:.2f} {units[i]}"

async def add_user(user_id, name):
    if not await users_col.find_one({"_id": user_id}):
        await users_col.insert_one({"_id": user_id, "name": name})
        try:
            await app.send_message(
                LOG_CHANNEL,
                f"🆕 **#NewUser in {BOT_NAME}**\n👤 **Name:** {name}\n🆔 **ID:** `{user_id}`"
            )
        except Exception:
            pass

async def is_subscribed(client: Client, user_id: int):
    if not AUTH_CHANNEL or user_id in ADMINS:
        return True
    try:
        member = await client.get_chat_member(AUTH_CHANNEL, user_id)
        if member.status in [enums.ChatMemberStatus.BANNED, enums.ChatMemberStatus.LEFT]:
            return False
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True

async def get_invite_link(client: Client):
    global INVITE_LINK
    if INVITE_LINK:
        return INVITE_LINK
    try:
        chat = await client.get_chat(AUTH_CHANNEL)
        if chat.username:
            INVITE_LINK = f"https://t.me/{chat.username}"
        else:
            link = await client.create_chat_invite_link(AUTH_CHANNEL)
            INVITE_LINK = link.invite_link
        return INVITE_LINK
    except Exception:
        return CHNL_LNK

# ----------------- START & ADMIN COMMANDS -----------------
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    await add_user(user_id, message.from_user.first_name)

    if len(message.command) > 1 and message.command[1].startswith("file_"):
        file_unique_id = message.command[1].split("_", 1)[1]
        
        if not await is_subscribed(client, user_id):
            invite_url = await get_invite_link(client)
            btn = [
                [InlineKeyboardButton("📢 Join Our Main Channel", url=invite_url)],
                [InlineKeyboardButton("🔄 Try Again", callback_data=f"checksub_{file_unique_id}")]
            ]
            return await message.reply_text(
                f"❗ **നിങ്ങൾ ഞങ്ങളുടെ ചാനലിൽ ജോയിൻ ചെയ്തിട്ടില്ല!**\n\n"
                f"**{BOT_NAME}**-ൽ നിന്ന് ഫയലുകൾ ലഭിക്കാൻ താഴെ കാണുന്ന ബട്ടൺ വഴി ചാനലിൽ ജോയിൻ ചെയ്ത ശേഷം **Try Again** ക്ലിക്ക് ചെയ്യുക.",
                reply_markup=InlineKeyboardMarkup(btn)
            )
        
        file_data = await files_col.find_one({"_id": file_unique_id})
        if not file_data:
            return await message.reply_text("❌ ഈ ഫയൽ ഡാറ്റാബേസിൽ കണ്ടെത്താനായില്ല!")
        
        return await client.send_cached_media(
            chat_id=user_id,
            file_id=file_data["file_id"],
            caption=f"🎬 **{file_data['file_name']}**\n📦 **Size:** `{get_size(file_data['file_size'])}`\n\n🤖 **Powered By:** **{BOT_NAME}**\n📢 **Join:** [Movie Request Group]({GRP_LNK})"
        )

    btn = [
        [InlineKeyboardButton("➕ Add Me To Your Group ➕", url=f"https://t.me/{client.me.username}?startgroup=true")],
        [
            InlineKeyboardButton("🎬 Request Group", url=GRP_LNK),
            InlineKeyboardButton("📢 Main Channel", url=CHNL_LNK)
        ],
        [InlineKeyboardButton("📊 Bot Status", callback_data="status_cb")]
    ]
    await message.reply_photo(
        photo=START_PIC,
        caption=f"ഹലോ **{message.from_user.mention}** 👋,\n\n"
                f"ഞാൻ **{BOT_NAME}** ആണ്! 🎬\n\n"
                f"നിങ്ങൾക്ക് ആവശ്യമുള്ള സിനിമകളുടെയോ സീരീസുകളുടെയോ പേര് ഇവിടെയോ ഞങ്ങളുടെ ഗ്രൂപ്പിലോ ടൈപ്പ് ചെയ്ത് അയച്ചാൽ ഉടൻ ഫയൽ ലഭിക്കും.",
        reply_markup=InlineKeyboardMarkup(btn)
    )

@app.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats_cmd(client: Client, message: Message):
    total_files = await files_col.count_documents({})
    total_users = await users_col.count_documents({})
    await message.reply_text(
        f"📊 **{BOT_NAME} - Database Statistics**\n\n"
        f"📁 **Total Files Saved:** `{total_files}`\n"
        f"👥 **Total Users:** `{total_users}`"
    )

@app.on_message(filters.command("deleteall") & filters.user(ADMINS))
async def delete_all_cmd(client: Client, message: Message):
    await files_col.delete_many({})
    await message.reply_text("🗑️ **ഡാറ്റാബേസിലെ എല്ലാ ഫയലുകളും ഡിലീറ്റ് ചെയ്തു!**")

@app.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_cmd(client: Client, message: Message):
    users = users_col.find({})
    b_msg = message.reply_to_message
    sts = await message.reply_text("⏳ **Broadcasting message...**")
    success = 0
    failed = 0
    async for user in users:
        try:
            await b_msg.copy(chat_id=user["_id"])
            success += 1
            await asyncio.sleep(0.05)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await b_msg.copy(chat_id=user["_id"])
            success += 1
        except Exception:
            failed += 1
    await sts.edit_text(f"✅ **Broadcast Completed!**\n\n🟢 **Success:** `{success}`\n🔴 **Failed:** `{failed}`")

# ----------------- AUTO & BULK FILE INDEXING -----------------
async def save_file_to_db(message: Message):
    media = message.document or message.video or message.audio
    if not media:
        return False
    file_name = media.file_name or message.caption or "Unknown_File"
    clean_name = re.sub(r"[@_\-\.\+]", " ", file_name)
    
    file_doc = {
        "_id": media.file_unique_id,
        "file_id": media.file_id,
        "file_name": file_name,
        "search_name": clean_name.lower(),
        "file_size": media.file_size,
        "caption": message.caption or file_name
    }
    try:
        await files_col.update_one({"_id": media.file_unique_id}, {"$set": file_doc}, upsert=True)
        return True
    except Exception:
        return False

@app.on_message(filters.chat(FILE_CHANNELS) & (filters.document | filters.video | filters.audio))
async def auto_save_file(client: Client, message: Message):
    await save_file_to_db(message)

# Forward a channel message to Admin PM to bulk index old files or save single file
@app.on_message(filters.private & filters.user(ADMINS) & (filters.forwarded | filters.document | filters.video | filters.audio))
async def admin_index_handler(client: Client, message: Message):
    if message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        chat_id = message.forward_from_chat.id
        last_msg_id = message.forward_from_message_id
        btn = [
            [InlineKeyboardButton("✅ Start Bulk Indexing", callback_data=f"index_{chat_id}_{last_msg_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="close_data")]
        ]
        return await message.reply_text(
            f"📢 **Channel ID:** `{chat_id}`\n"
            f"🔢 **Total Messages to Scan:** `{last_msg_id}`\n\n"
            f"ഈ ചാനലിലെ പഴയ ഫയലുകൾ എല്ലാം ഡാറ്റാബേസിലേക്ക് സേവ് ചെയ്യണോ?",
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
    if await save_file_to_db(message):
        await message.reply_text(f"✅ **ഫയൽ {BOT_NAME} ഡാറ്റാബേസിലേക്ക് സേവ് ചെയ്തിട്ടുണ്ട്!**", quote=True)

# ----------------- SEARCH & PAGINATION -----------------
@app.on_message(filters.text & (filters.group | filters.private) & ~filters.command(["start", "stats", "deleteall", "broadcast"]))
async def search_files(client: Client, message: Message):
    query = message.text.strip()
    if len(query) < 2 or query.startswith("/"):
        return

    clean_query = re.sub(r"[@_\-\.\+]", " ", query).lower()
    words = clean_query.split()
    regex_pattern = ".*".join(map(re.escape, words))

    cursor = files_col.find({"search_name": {"$regex": regex_pattern, "$options": "i"}})
    results = await cursor.to_list(length=50)

    if not results:
        if message.chat.type == enums.ChatType.PRIVATE:
            await message.reply_text("😕 ഈ പേരിൽ ഫയലുകൾ ഒന്നും കണ്ടെത്തിയില്ല. സ്പെല്ലിംഗ് കറക്റ്റ് ആണോ എന്ന് പരിശോധിക്കുക.")
        return

    await send_results_page(client, message, results, query, page=0)

async def send_results_page(client: Client, message_or_cb, results, query, page=0):
    per_page = 10
    total_pages = math.ceil(len(results) / per_page)
    start_idx = page * per_page
    end_idx = start_idx + per_page
    current_files = results[start_idx:end_idx]

    bot_username = client.me.username
    buttons = []

    for file in current_files:
        size_str = get_size(file["file_size"])
        btn_text = f"[{size_str}] {file['file_name']}"
        buttons.append([InlineKeyboardButton(btn_text, url=f"https://t.me/{bot_username}?start=file_{file['_id']}")])

    nav_btns = []
    if page > 0:
        nav_btns.append(InlineKeyboardButton("⬅️ Back", callback_data=f"page_{page-1}_{query[:25]}"))
    nav_btns.append(InlineKeyboardButton(f"📑 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_btns.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}_{query[:25]}"))

    if len(nav_btns) > 1:
        buttons.append(nav_btns)

    text = (
        f"🤖 **{BOT_NAME}**\n"
        f"🔍 **Search:** `{query}`\n"
        f"📁 **Results:** `{len(results)}`\n\n"
        f"👇 **താഴെ കാണുന്ന ബട്ടണിൽ ക്ലിക്ക് ചെയ്ത് ഫയൽ ഡൗൺലോഡ് ചെയ്യാം:**"
    )

    if isinstance(message_or_cb, Message):
        await message_or_cb.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), quote=True)
    elif isinstance(message_or_cb, CallbackQuery):
        await message_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))

# ----------------- CALLBACK HANDLERS -----------------
@app.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    global INDEX_CANCEL
    data = query.data
    user_id = query.from_user.id

    if data == "noop":
        await query.answer()

    elif data == "close_data":
        await query.message.delete()

    elif data == "cancel_index":
        INDEX_CANCEL = True
        await query.answer("🛑 Indexing സ്റ്റോപ്പ് ചെയ്യുന്നു...", show_alert=True)

    elif data.startswith("index_"):
        _, chat_id_str, last_id_str = data.split("_")
        chat_id = int(chat_id_str)
        last_msg_id = int(last_id_str)
        INDEX_CANCEL = False

        await query.message.edit_text(
            "⏳ **Indexing Started... ദയവായി കാത്തിരിക്കുക.**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel Indexing", callback_data="cancel_index")]])
        )

        saved = 0
        current = 1
        while current <= last_msg_id:
            if INDEX_CANCEL:
                return await query.message.edit_text(f"🛑 **Indexing Cancelled!**\n✅ **Total Saved:** `{saved}`")
            
            batch_ids = list(range(current, min(current + 100, last_msg_id + 1)))
            try:
                messages = await client.get_messages(chat_id, batch_ids)
                for msg in messages:
                    if msg and (msg.document or msg.video or msg.audio):
                        if await save_file_to_db(msg):
                            saved += 1
            except FloodWait as e:
                await asyncio.sleep(e.value)
                continue
            except Exception as e:
                return await query.message.edit_text(f"❌ **Error:** ചാനലിൽ ബോട്ട് Admin ആണെന്ന് ഉറപ്പുവരുത്തുക!\n`{e}`")

            current += 100
            if current % 200 == 1:
                try:
                    await query.message.edit_text(
                        f"🔄 **Indexing in Progress...**\n📊 **Checked:** `{min(current, last_msg_id)}/{last_msg_id}`\n✅ **Saved Files:** `{saved}`",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel", callback_data="cancel_index")]])
                    )
                except Exception:
                    pass

        await query.message.edit_text(f"✅ **Indexing പൂർത്തിയായി!**\n📁 **Total Files Saved:** `{saved}`")

    elif data == "status_cb":
        total_files = await files_col.count_documents({})
        total_users = await users_col.count_documents({})
        await query.answer(f"🤖 {BOT_NAME}\n📁 Total Files: {total_files}\n👥 Total Users: {total_users}", show_alert=True)

    elif data.startswith("checksub_"):
        file_unique_id = data.split("_", 1)[1]
        if not await is_subscribed(client, user_id):
            return await query.answer("❌ നിങ്ങൾ ഇതുവരെ ചാനലിൽ ജോയിൻ ചെയ്തിട്ടില്ല! ജോയിൻ ചെയ്ത ശേഷം ശ്രമിക്കുക.", show_alert=True)
        
        file_data = await files_col.find_one({"_id": file_unique_id})
        if not file_data:
            return await query.answer("❌ ഫയൽ കണ്ടെത്താനായില്ല!", show_alert=True)
        
        await query.message.delete()
        await client.send_cached_media(
            chat_id=user_id,
            file_id=file_data["file_id"],
            caption=f"🎬 **{file_data['file_name']}**\n📦 **Size:** `{get_size(file_data['file_size'])}`\n\n🤖 **Powered By:** **{BOT_NAME}**\n📢 **Join:** [Movie Request Group]({GRP_LNK})"
        )

    elif data.startswith("page_"):
        _, page_str, search_q = data.split("_", 2)
        page = int(page_str)
        clean_query = re.sub(r"[@_\-\.\+]", " ", search_q).lower()
        words = clean_query.split()
        regex_pattern = ".*".join(map(re.escape, words))

        cursor = files_col.find({"search_name": {"$regex": regex_pattern, "$options": "i"}})
        results = await cursor.to_list(length=50)
        if results:
            await send_results_page(client, query, results, search_q, page=page)
        await query.answer()

# ----------------- WEB SERVER FOR RENDER/KOYEB -----------------
async def health_check(request):
    return web.Response(text=f"{BOT_NAME} is Running Alive!")

async def start_services():
    server = web.Application()
    server.router.add_get("/", health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"🌐 Web Server started on Port {PORT}")

    await app.start()
    app.me = await app.get_me()
    print(f"🤖 {BOT_NAME} Started as @{app.me.username}")
    try:
        await app.send_message(LOG_CHANNEL, f"🚀 **{BOT_NAME} Started Successfully!**")
    except Exception as e:
        print(f"Log Channel Warning: {e}")
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
