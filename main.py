import os
import logging
import asyncio
import aiohttp
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

# --- DAILYMOTION API HELPER ---
async def search_dailymotion(query: str, sort_by: str = 'relevance', limit: int = 5) -> list:
    """
    Connects to the Dailymotion API to fetch videos based on the query.
    """
    url = "https://api.dailymotion.com/videos"
    params = {
        "fields": "title,url,duration,views_total,thumbnail_360_url",
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
                else:
                    logger.error(f"Dailymotion API Error: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Connection Error: {e}")
            return []

# --- REAL-TIME PROGRESS ANIMATION ---
async def update_search_progress(message, context):
    """
    Provides real-time feedback to the user by editing the message 
    with different search statuses.
    """
    statuses = [
        "â³ <i>Initializing secure connection...</i>",
        "ð¡ <i>Querying Dailymotion servers...</i>",
        "ð <i>Scanning for requested content...</i>",
        "ð¥ <i>Extracting and formatting video links...</i>"
    ]
    
    for status in statuses:
        try:
            await context.bot.edit_message_text(
                chat_id=message.chat_id,
                message_id=message.message_id,
                text=status,
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.7) # Slight delay to show the animation
        except Exception:
            pass # Ignore if message hasn't changed

# --- FORMATTING RESULTS ---
def format_results(videos: list, header: str) -> str:
    """Formats the JSON response into a beautiful Telegram message."""
    if not videos:
        return f"ð« <b>{header}</b>\n\n<i>No results found for your request. Try different keywords!</i>"
    
    text = f"â¨ <b>{header}</b> â¨\n\n"
    for i, vid in enumerate(videos, 1):
        mins, secs = divmod(vid.get('duration', 0), 60)
        views = vid.get('views_total', 0)
        title = vid.get('title', 'Unknown Title')
        url = vid.get('url', '#')
        
        text += f"ð¬ <b>{i}. {title}</b>\n"
        text += f"â± <code>{mins}m {secs}s</code> | ð <code>{views:,} views</code>\n"
        text += f"ð <a href='{url}'>Watch Video Now</a>\n"
        text += "ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸ã°ï¸\n"
        
    return text

# --- SECURITY CHECK ---
def is_admin(user_id: int) -> bool:
    """Checks if the user is the authorized admin."""
    if not ADMIN_ID: # If no admin ID is set in Railway, allow everyone
        return True
    return str(user_id) == str(ADMIN_ID)

# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a beautiful menu when the bot is started."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("âï¸ <i>Access Denied. You are not the authorized administrator.</i>", parse_mode=ParseMode.HTML)
        return

    welcome_text = (
        "ð <b>Welcome to your Personal Cinema Bot!</b>\n\n"
        "I am ready to fetch the best Chinese dubbed dramas and movies for you.\n\n"
        "ð <b>Select an option below or type a command:</b>\n"
        "ð¹ <code>/dubbed [name]</code> - Search Chinese dubbed videos\n"
        "ð¹ <code>/search [query]</code> - Get top 5 popular general results\n"
        "ð¹ <code>/recommend</code> - Get latest Chinese dubbed martial arts/superpower"
    )
    
    keyboard = [
        [InlineKeyboardButton("ð Get Recommendations", callback_data="btn_recommend")],
        [
            InlineKeyboardButton("ð¬ How to use Dubbed", callback_data="btn_help_dubbed"),
            InlineKeyboardButton("ð How to Search", callback_data="btn_help_search")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def dubbed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Searches specifically for Chinese dubbed content."""
    if not is_admin(update.effective_user.id):
        return

    query_raw = " ".join(context.args)
    if not query_raw:
        await update.message.reply_text("â ï¸ <b>Error:</b> Please provide a movie name!\n<i>Example:</i> <code>/dubbed the legend of shen li</code>", parse_mode=ParseMode.HTML)
        return

    # Create the specific search phrase
    search_query = f"{query_raw} chinese dubbed"
    
    # Send initial message to edit later
    status_msg = await update.message.reply_text("ð <i>Starting search engine...</i>", parse_mode=ParseMode.HTML)
    
    # Show real-time progress
    await update_search_progress(status_msg, context)
    
    # Fetch data
    videos = await search_dailymotion(search_query, sort_by='relevance', limit=5)
    
    # Format and send final results
    final_text = format_results(videos, f"Chinese Dubbed Results for '{query_raw}'")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """General search returning top 5 most popular/visited results."""
    if not is_admin(update.effective_user.id):
        return

    query_raw = " ".join(context.args)
    if not query_raw:
        await update.message.reply_text("â ï¸ <b>Error:</b> Please provide a search term!\n<i>Example:</i> <code>/search funny cats</code>", parse_mode=ParseMode.HTML)
        return

    status_msg = await update.message.reply_text("ð <i>Starting search engine...</i>", parse_mode=ParseMode.HTML)
    await update_search_progress(status_msg, context)
    
    # Fetch data sorting by 'visited' (most popular)
    videos = await search_dailymotion(query_raw, sort_by='visited', limit=5)
    
    final_text = format_results(videos, f"Top Popular Results for '{query_raw}'")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def recommend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches the latest Chinese dubbed martial arts/superpower content."""
    if not is_admin(update.effective_user.id):
        return

    status_msg = await update.message.reply_text("ð <i>Curating recommendations...</i>", parse_mode=ParseMode.HTML)
    await update_search_progress(status_msg, context)
    
    # Specific query for recommendations, sorted by newest
    search_query = "chinese dubbed martial arts OR chinese dubbed superpower OR chinese dubbed fantasy"
    videos = await search_dailymotion(search_query, sort_by='recent', limit=5)
    
    final_text = format_results(videos, "ð¥ Latest Dubbed Martial Arts/Superpower Picks ð¥")
    await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# --- CALLBACK QUERY HANDLER (For inline buttons) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles button clicks from the inline keyboard menu."""
    query = update.callback_query
    await query.answer() # Acknowledge button click
    
    if query.data == "btn_recommend":
        # We reuse the logic from the recommend command
        status_msg = await query.message.reply_text("ð <i>Curating recommendations...</i>", parse_mode=ParseMode.HTML)
        await update_search_progress(status_msg, context)
        search_query = "chinese dubbed martial arts OR chinese dubbed superpower OR chinese dubbed fantasy"
        videos = await search_dailymotion(search_query, sort_by='recent', limit=5)
        final_text = format_results(videos, "ð¥ Latest Dubbed Picks ð¥")
        await status_msg.edit_text(text=final_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        
    elif query.data == "btn_help_dubbed":
        await query.message.reply_text("ð¡ <b>To find a Chinese dubbed show:</b>\nJust type <code>/dubbed</code> followed by the title.\n\n<i>Example:</i> <code>/dubbed Battle Through The Heavens</code>", parse_mode=ParseMode.HTML)
        
    elif query.data == "btn_help_search":
        await query.message.reply_text("ð¡ <b>To do a general search:</b>\nJust type <code>/search</code> followed by whatever you want. I will fetch the 5 most viewed videos.\n\n<i>Example:</i> <code>/search music video</code>", parse_mode=ParseMode.HTML)

# --- MAIN SETUP ---
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing! Please set it in your Railway environment variables.")
        return

    # Build the application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("dubbed", dubbed_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("recommend", recommend_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Start the Bot
    logger.info("Bot is starting up...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
