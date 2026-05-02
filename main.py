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

# --- BOT MEMORY (To prevent recommending the same thing ever again) ---
SHOWN_RECOMMENDATIONS = set()

# --- DAILYMOTION API HELPER ---
async def search_dailymotion(query: str, sort_by: str = 'relevance', limit: int = 60) -> list:
    """Fetches a large batch of videos so we have enough to filter through."""
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
def is_clean_english_dubbed(title: str) -> bool:
    """Returns False if it contains ANY unwanted language or subtitle marker."""
    title_lower = title.lower()
    
    # 🚫 BLACKLIST: If it has any of these words, destroy it.
    blacklist = [
        'hindi', 'urdu', 'tamil', 'indo', 'indonesian', 'espanol', 'spanish', 
        'sub', 'subbed', 'subtitle', 'malay', 'arabic', 'telugu', 'korean', 'thai', 'tagalog'
    ]
    
    for bad_word in blacklist:
        # Check for standalone bad words to avoid accidental filtering
        if re.search(rf'\b{bad_word}\b', title_lower):
            return False
            
    return True

def get_movie_base_name(title: str) -> str:
    """Strips episode numbers and parts to find the core movie name to block duplicates."""
    # Remove numbers and special characters, keep only letters
    clean = re.sub(r'[^a-zA-Z\s]', '', title).lower()
    # Return the first 3-4 words as the "fingerprint" of the movie
    return " ".join(clean.split()[:4])

def filter_videos(videos: list, max_results: int = 5, is_recommendation: bool = False) -> list:
    """Filters out garbage, duplicates, and previously seen recommendations."""
    filtered = []
    seen_movie_fingerprints = set()
    
    for vid in videos:
        vid_id = vid.get('id')
        title = vid.get('title', '')
        
        # 1. STRICT LANGUAGE CHECK (Only English Dubbed, NO Subs, NO Hindi)
        if not is_clean_english_dubbed(title):
            continue
            
        # 2. CHECK HISTORY (Don't recommend things you've already seen)
        if is_recommendation and vid_id in SHOWN_RECOMMENDATIONS:
            continue
            
        # 3. BLOCK DUPLICATES (No "Part 1", "Part 2" in the same list)
        fingerprint = get_movie_base_name(title)
        if fingerprint in seen_movie_fingerprints:
            continue
            
        # Passes all tests! Add it.
        seen_movie_fingerprints.add(fingerprint)
        filtered.append(vid)
        
        # Memorize it if it's a recommendation
        if is_recommendation:
            SHOWN_RECOMMENDATIONS.add(vid_id)
            
        # Stop once we have exactly 5 perfect results
        if len(filtered) >= max_results:
            break
            
    return filtered

# --- REAL-TIME STATUS ANIMATION ---
async def update_status(message, context):
    """Shows the user exactly what the bot is doing in real-time."""
    statuses = [
        "⏳ <b>System Status:</b> <i>Connecting to servers...</i>",
        "📡 <b>System Status:</b> <i>Downloading search results...</i>",
        "🛑 <b>System Status:</b> <i>Destroying Hindi/Subbed videos...</i>",
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
    """Creates a stunning, emoji-rich layout for the final results."""
    if not videos:
        return f"🚫 <b>{header}</b>\n\n<i>No pure English Dubbed results found after destroying all Hindi/Subbed videos. Try another name!</i>"
    
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
    if not ADMIN_ID: 
        return True
    return str(user_id) == str(ADMIN_ID)

# --- COMMANDS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔️ <i>Access Denied. Admin only.</i>", parse_mode=ParseMode.HTML)
        return

    welcome_text = (
        "🐉 <b>CHINESE DRAMA VIP HUB</b> 🐉\n\n"
        "<i>Welcome, Master. I am programmed to hunt down the highest quality English Dubbed Chinese Dramas, automatically destroying any Hindi or Subbed garbage.</i>\n\n"
        "👇 <b>CHOOSE A COMMAND BELOW:</b>\n"
        "🎥 <code>/dubbed [Name]</code> - Strict search for a specific English Dubbed show.\n"
        "🎲 <code>/recommend</code> - Get 5 fresh, pure English Dubbed recommendations.\n"
        "🌍 <code>/search [Query]</code> - General open search for absolutely anything."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔥 Give Me Fresh Recommendations 🔥", callback_data="btn_recommend")],
        [
            InlineKeyboardButton("❓ Help: Dubbed", callback_data="btn_help_dubbed"),
            InlineKeyboardButton("❓ Help: Search", callback_data="btn_help_search")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def dubbed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return

    query_raw = " ".join(context.args)
    if not query_raw:
        await update.message.reply_text("⚠️ <b>Missing Name!</b>\nType: <code>/dubbed [movie name]</code>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text("🚀 <i>Initializing strict search...</i>", parse_mode=ParseMode.HTML)
    await update_status(status_msg, context)
    
    # Strict API query
    search_query = f"{query_raw} english dubbed chinese drama"
    raw_videos = await search_dailymotion(search_query, sort_by='relevance', limit=60)
    
    # Apply strict python filter
    videos = filter_videos(raw_videos, max_results=5, is_recommendation=False)
    
    final_text = format_results(videos, f"🔍 English Dubbed: {query_raw.upper()}")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open search: Does NOT filter out languages. Gives exactly what is searched."""
    if not is_admin(update.effective_user.id): return

    query_raw = " ".join(context.args)
    if not query_raw:
        return

    status_msg = await update.message.reply_text("🚀 <i>Searching global database...</i>", parse_mode=ParseMode.HTML)
    await update_status(status_msg, context)
    
    raw_videos = await search_dailymotion(query_raw, sort_by='visited', limit=15)
    
    # Simple duplicate block, NO language filter for general search
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
    
    # Broad query designed to catch donghua/dramas that are dubbed
    search_query = "chinese drama english dubbed OR donghua english dubbed"
    raw_videos = await search_dailymotion(search_query, sort_by='recent', limit=80)
    
    # Strict filter + History Check
    videos = filter_videos(raw_videos, max_results=5, is_recommendation=True)
    
    final_text = format_results(videos, "💎 Fresh English Dubbed Recommendations 💎")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --- INLINE BUTTONS ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() 
    
    if query.data == "btn_recommend":
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
