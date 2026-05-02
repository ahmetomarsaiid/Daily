import os
import logging
import asyncio
import aiohttp
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Fetch environment variables from Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

# --- BOT MEMORY ---
SHOWN_RECOMMENDATIONS = set()

# --- DAILYMOTION API HELPER ---
async def search_dailymotion(query: str, sort_by: str = 'relevance', limit: int = 60) -> list:
    url = "https://api.dailymotion.com/videos"
    params = {
        "fields": "id,title,url,duration,views_total",
        "search": query,
        "sort": sort_by,
        "limit": limit
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("list", [])
                return []
        except Exception as e:
            logger.error(f"API Error: {e}")
            return []

# --- ULTRA-STRICT FILTERING SYSTEM ---
def is_clean_english_dubbed(title: str, strict_dub_check: bool = False) -> bool:
    """Blocks unwanted languages, Asian characters, and enforces English Dubs."""
    title_lower = title.lower()
    
    # 🚫 1. BLOCK ASIAN CHARACTERS (Chinese, Japanese, Korean)
    # If the title has non-English characters, it's usually raw/subbed. Destroy it.
    if re.search(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', title):
        return False

    # 🚫 2. BLACKLIST WORDS
    blacklist = [
        'hindi', 'urdu', 'tamil', 'indo', 'indonesian', 'espanol', 'spanish', 
        'sub', 'subbed', 'subtitle', 'malay', 'arabic', 'telugu', 'korean', 'thai', 'tagalog', 'raw'
    ]
    for bad_word in blacklist:
        if re.search(rf'\b{bad_word}\b', title_lower):
            return False
            
    # 🚫 3. REQUIRE "DUB" FOR RECOMMENDATIONS
    if strict_dub_check:
        if 'dub' not in title_lower and 'eng' not in title_lower:
            return False
            
    return True

def get_movie_base_name(title: str) -> str:
    clean = re.sub(r'[^a-zA-Z\s]', '', title).lower()
    return " ".join(clean.split()[:4])

def filter_videos(videos: list, max_results: int = 5, is_recommendation: bool = False, required_query: str = None) -> list:
    filtered = []
    seen_movie_fingerprints = set()
    
    # If a specific name was requested, we extract words > 2 letters to verify they match
    query_words = []
    if required_query:
        query_words = [w.lower() for w in required_query.split() if len(w) > 2]
    
    for vid in videos:
        vid_id = vid.get('id')
        title = vid.get('title', '')
        title_lower = title.lower()
        
        # 1. STRICT LANGUAGE & CHARACTER CHECK
        if not is_clean_english_dubbed(title, strict_dub_check=is_recommendation):
            continue
            
        # 2. MATCH CHECK (For /dubbed command)
        # Ensure the title actually contains part of the requested movie name!
        if required_query and query_words:
            if not any(w in title_lower for w in query_words):
                continue # The movie name isn't even in the title!
            
        # 3. CHECK HISTORY
        if is_recommendation and vid_id in SHOWN_RECOMMENDATIONS:
            continue
            
        # 4. BLOCK DUPLICATES
        fingerprint = get_movie_base_name(title)
        if fingerprint in seen_movie_fingerprints:
            continue
            
        seen_movie_fingerprints.add(fingerprint)
        filtered.append(vid)
        
        if is_recommendation:
            SHOWN_RECOMMENDATIONS.add(vid_id)
            
        if len(filtered) >= max_results:
            break
            
    return filtered

# --- REAL-TIME STATUS ANIMATION ---
async def update_status(message, context):
    statuses = [
        "⏳ <b>System Status:</b> <i>Connecting to servers...</i>",
        "📡 <b>System Status:</b> <i>Downloading search results...</i>",
        "🛑 <b>System Status:</b> <i>Destroying Subbed/Asian character videos...</i>",
        "✨ <b>System Status:</b> <i>Formatting perfect English Dubs...</i>"
    ]
    for status in statuses:
        try:
            await context.bot.edit_message_text(
                chat_id=message.chat_id,
                message_id=message.message_id,
                text=status,
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.8) 
        except Exception:
            pass 

# --- BEAUTIFUL UI FORMATTER ---
def format_results(videos: list, header: str) -> str:
    if not videos:
        return f"🚫 <b>{header}</b>\n\n<i>No pure English Dubbed results found.</i>"
    
    text = f"🌟 <b>{header}</b> 🌟\n\n"
    for i, vid in enumerate(videos, 1):
        mins, secs = divmod(vid.get('duration', 0), 60)
        views = vid.get('views_total', 0)
        title = vid.get('title', 'Unknown Title')
        url = vid.get('url', '#')
        
        text += f"🎬 <b>{i}. {title}</b>\n"
        text += f"⏳ <code>{mins}m {secs}s</code>   |   👀 <code>{views:,} views</code>\n"
        text += f"▶️ <a href='{url}'><b>CLICK HERE TO WATCH</b></a>\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        
    return text

# --- SECURITY CHECK ---
def is_admin(user_id: int) -> bool:
    if not ADMIN_ID: return True
    return str(user_id) == str(ADMIN_ID)

# --- COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ <i>Access Denied. Admin only.</i>", parse_mode=ParseMode.HTML)
        return

    welcome_text = (
        "🐉 <b>CHINESE DRAMA VIP HUB</b> 🐉\n\n"
        "<i>Welcome, Master. I strictly filter out non-English titles, subs, and Hindi dubs.</i>\n\n"
        "👇 <b>CHOOSE A COMMAND BELOW:</b>\n"
        "🎥 <code>/dubbed [Name]</code> - Search for a specific English Dubbed show.\n"
        "🎲 <code>/recommend</code> - Get 5 guaranteed pure English Dubbed recommendations.\n"
        "🌍 <code>/search [Query]</code> - General open search."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔥 Give Me Fresh Recommendations 🔥", callback_data="btn_recommend")],
        [
            InlineKeyboardButton("❓ Help: Dubbed", callback_data="btn_help_dubbed"),
            InlineKeyboardButton("❓ Help: Search", callback_data="btn_help_search")
        ]
    ]
    await update.message.reply_text(text=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def dubbed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return

    query_raw = " ".join(context.args)
    if not query_raw:
        await update.message.reply_text("⚠️ <b>Missing Name!</b>\nType: <code>/dubbed [movie name]</code>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text("🚀 <i>Initializing strict search...</i>", parse_mode=ParseMode.HTML)
    await update_status(status_msg, context)
    
    # 1. STRICT SEARCH (Require the movie name to actually be in the title)
    search_query = f"{query_raw} english dubbed chinese drama"
    raw_videos = await search_dailymotion(search_query, sort_by='relevance', limit=60)
    strict_videos = filter_videos(raw_videos, max_results=5, is_recommendation=False, required_query=query_raw)
    
    if strict_videos:
        # EXACT MATCH FOUND
        final_text = format_results(strict_videos, f"🔍 English Dubbed: {query_raw.upper()}")
        await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        # 2. EXACT MATCH NOT FOUND - DO A LOOSER SEARCH FOR FALLBACKS
        loose_videos = filter_videos(raw_videos, max_results=5, is_recommendation=False, required_query=None)
        
        if not loose_videos:
            await status_msg.edit_text("🚫 <b>Not Found:</b> This movie isn't available in English Dubbed, and I couldn't find anything similar either.", parse_mode=ParseMode.HTML)
            return
            
        # Store the familiar videos in memory so the buttons can access them
        context.user_data['fallback_videos'] = loose_videos
        context.user_data['fallback_query'] = query_raw
        
        # Ask the user if they want the familiar ones
        keyboard = [
            [InlineKeyboardButton("✅ Yes, show me", callback_data="btn_yes_fallback"),
             InlineKeyboardButton("❌ No", callback_data="btn_no_fallback")]
        ]
        
        ask_text = (
            f"🚫 <b>NOT FOUND:</b> <i>'{query_raw}'</i> isn't currently available in English Dubbed.\n\n"
            "👀 However, I found some <b>familiar/similar videos</b>. Do you need those or not?"
        )
        await status_msg.edit_text(text=ask_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open search: Gives exactly what is searched without strict language filters."""
    if not is_admin(update.effective_user.id): return

    query_raw = " ".join(context.args)
    if not query_raw: return

    status_msg = await update.message.reply_text("🚀 <i>Searching global database...</i>", parse_mode=ParseMode.HTML)
    await update_status(status_msg, context)
    
    raw_videos = await search_dailymotion(query_raw, sort_by='visited', limit=15)
    
    videos = []
    seen = set()
    for vid in raw_videos:
        fp = get_movie_base_name(vid.get('title', ''))
        if fp not in seen:
            seen.add(fp)
            videos.append(vid)
        if len(videos) >= 5: break
            
    final_text = format_results(videos, f"🌍 Global Search: {query_raw}")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def recommend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return

    status_msg = await update.message.reply_text("🚀 <i>Finding pure English Dubbed gems...</i>", parse_mode=ParseMode.HTML)
    await update_status(status_msg, context)
    
    search_query = "chinese drama english dubbed OR donghua english dubbed"
    raw_videos = await search_dailymotion(search_query, sort_by='recent', limit=80)
    
    # Strict filter applied
    videos = filter_videos(raw_videos, max_results=5, is_recommendation=True)
    
    final_text = format_results(videos, "💎 Fresh English Dubbed Recommendations 💎")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --- INLINE BUTTONS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    if query.data == "btn_yes_fallback":
        # User clicked YES to familiar videos
        videos = context.user_data.get('fallback_videos', [])
        q_raw = context.user_data.get('fallback_query', 'Similar Content')
        
        if not videos:
            await query.message.edit_text("⚠️ <i>Session expired. Please search again.</i>", parse_mode=ParseMode.HTML)
            return
            
        final_text = format_results(videos, f"👀 Familiar Videos for '{q_raw}'")
        await query.message.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    elif query.data == "btn_no_fallback":
        # User clicked NO
        await query.message.edit_text("❌ <b>Search Cancelled.</b> Let me know if you need anything else!", parse_mode=ParseMode.HTML)

    elif query.data == "btn_recommend":
        status_msg = await query.message.reply_text("🚀 <i>Finding pure English Dubbed gems...</i>", parse_mode=ParseMode.HTML)
        await update_status(status_msg, context)
        
        search_query = "chinese drama english dubbed OR donghua english dubbed"
        raw_videos = await search_dailymotion(search_query, sort_by='recent', limit=80)
        videos = filter_videos(raw_videos, max_results=5, is_recommendation=True)
        
        final_text = format_results(videos, "💎 Fresh English Dubbed Recommendations 💎")
        await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    elif query.data == "btn_help_dubbed":
        await query.message.reply_text("💡 <b>Dubbed Help:</b>\nType <code>/dubbed Name</code>. I will automatically block Hindi/Subtitles and find the English Dub.", parse_mode=ParseMode.HTML)
    elif query.data == "btn_help_search":
        await query.message.reply_text("💡 <b>Search Help:</b>\nType <code>/search Anything</code>. This searches the whole site without language limits.", parse_mode=ParseMode.HTML)

def main():
    if not BOT_TOKEN: return
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("dubbed", dubbed_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("recommend", recommend_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
