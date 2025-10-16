import json
import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ---------- CONFIG ----------
# IMPORTANT: Use the numeric ID (-100...) for GROUP_ID if possible, 
# as it is more reliable for API calls than the username ("@phaaarr").
BOT_TOKEN = "8360019615:AAGzb73i7spmYtFu6o9UUat047weUDrHEIE"
GROUP_ID = "@phaaarr"  # group username (can be numeric ID: -100...)
ADMIN_IDS = [7317816083]  # Telegram numeric ID
DATA_FILE = "lectures.json"
# ----------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure data file exists
if not Path(DATA_FILE).exists():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "Phytochemistry": {"thread_id": None, "lectures": {}},
            "Microbiology": {"thread_id": None, "lectures": {}},
            "Pharmacology": {"thread_id": None, "lectures": {}},
            "Pharmaceutics": {"thread_id": None, "lectures": {}},
            "Analytical Chemistry": {"thread_id": None, "lectures": {}},
            "Medicinal Chemistry": {"thread_id": None, "lectures": {}}
        }, f, ensure_ascii=False, indent=2)

def load_data():
    """Loads the lecture data from the JSON file."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    """Saves the lecture data to the JSON file."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- BOT COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and shows the initial subject selection menu."""
    user = update.effective_user
    data = load_data()
    # Filter to only show subjects that actually have lectures
    available_subjects = {subj: info for subj, info in data.items() if info.get("lectures")}
    
    if not available_subjects:
        await update.message.reply_text("No lectures are currently available. Admins: use /help to see setup instructions.")
        return
        
    keyboard = [[InlineKeyboardButton(subj, callback_data=f"subject|{subj}")] for subj in available_subjects.keys()]
    
    await update.message.reply_text(
        f"Hi {user.first_name or 'student'} 👋\nChoose a subject:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides usage instructions for students and admins."""
    text = (
        "*Student usage:*\n"
        "• /start - Opens the subject menu to browse lectures.\n"
        "• All other non-command messages in private chat will show the subject menu.\n\n"
        "*Admin usage (in the lecture group):*\n"
        "• Reply to a lecture post with: `/capture SubjectName` (e.g. `/capture Pharmacology`)\n"
        "• `/list` - See a list of all indexed lectures and their IDs."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# Admin-only: capture a lecture
async def capture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command to capture and index a lecture file/message."""
    sender = update.effective_user
    if sender.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not an admin for this bot.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Reply to the lecture message in the group when using this command.")
        return

    msg = update.message.reply_to_message
    
    # Check if the command is used in the correct group (numeric or username)
    chat_id_check = str(update.effective_chat.id)
    if chat_id_check != GROUP_ID and update.effective_chat.username != GROUP_ID.strip('@'):
         await update.message.reply_text("This command must be used inside the lecture group.")
         return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: `/capture SubjectName` (e.g. `/capture Pharmacology`)", parse_mode="Markdown")
        return

    subject = " ".join(args).strip()
    data = load_data()
    if subject not in data:
        data[subject] = {"thread_id": None, "lectures": {}}

    message_id = msg.message_id
    # message_thread_id is only available if it's a topic thread
    thread_id = getattr(msg, "message_thread_id", None)
    
    # Store thread ID for the subject
    if thread_id and not data[subject].get("thread_id"):
        data[subject]["thread_id"] = thread_id

    # Determine title
    title = msg.caption.strip() if msg.caption else \
            (msg.document.file_name if msg.document and msg.document.file_name else \
            (msg.text.strip()[:200] if msg.text else f"message_{message_id}"))

    # Append message ID if a lecture with the same name already exists
    if title in data[subject]["lectures"]:
        title = f"{title} (ID:{message_id})"

    data[subject]["lectures"][title] = message_id
    save_data(data)

    await update.message.reply_text(
        f"✅ Saved lecture under *{subject}*:\n`{title}`\nMessage ID: {message_id}\nThread ID: {thread_id}",
        parse_mode="Markdown"
    )

# Admin: list indexed lectures
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only command to list all indexed subjects and lectures."""
    sender = update.effective_user
    if sender.id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not an admin for this bot.")
        return
    data = load_data()
    if not data:
        await update.message.reply_text("No subjects/lectures indexed yet.")
        return
    lines = ["*Indexed Lectures:*\n"]
    for subj, info in data.items():
        lectures = info.get("lectures", {})
        if not lectures:
            continue # Skip subjects with no lectures
        lines.append(f"*{subj}* (Thread ID: {info.get('thread_id', 'None')})")
        for t, mid in lectures.items():
            lines.append(f"  • {t} → MID: {mid}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# Handle buttons
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button clicks."""
    query = update.callback_query
    await query.answer()
    data = load_data()
    payload = query.data

    if payload.startswith("subject|"):
        # Handle subject selection
        subject = payload.split("|", 1)[1]
        info = data.get(subject)
        
        if not info or not info.get("lectures"):
            await query.edit_message_text("Subject or lectures not found.")
            return
            
        lectures = info["lectures"]
        
        # Create buttons for each lecture
        buttons = [
            [InlineKeyboardButton(
                title if len(title) <= 50 else title[:47]+"...", 
                callback_data=f"lecture|{subject}|{title}"
            )]
            for title in lectures.keys()
        ]
        # Add back button
        buttons.append([InlineKeyboardButton("⬅️ Back to Subjects", callback_data="back")])
        
        await query.edit_message_text(
            f"Lectures for *{subject}*:", 
            parse_mode="Markdown", 
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if payload == "back":
        # Go back to the main subject menu
        available_subjects = {subj: info for subj, info in data.items() if info.get("lectures")}
        kb = [[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in available_subjects.keys()]
        await query.edit_message_text("Choose a subject:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if payload.startswith("lecture|"):
        # Handle lecture selection (The fix is applied here)
        _, subject, title = payload.split("|", 2)
        info = data.get(subject)
        
        if not info:
            await query.edit_message_text("Subject missing.")
            return
            
        message_id = info["lectures"].get(title)
        
        if not message_id:
            await query.edit_message_text("Lecture not found.")
            return
            
        try:
            # --- FIX: Use copy_message instead of forward_message ---
            # This is the most reliable method for sending files across chats, 
            # especially if the source group has content protection enabled.
            await context.bot.copy_message(
                chat_id=query.from_user.id, # Destination: The user's private chat
                from_chat_id=GROUP_ID,       # Source: The lecture group ID/username
                message_id=message_id,       # The lecture file's message ID
            )
            
            await query.edit_message_text(f"✅ Sent *{title}* from *{subject}*.", parse_mode="Markdown")
            
        except Exception as e:
            logger.exception("Copy failed")
            # Clearer error message to guide the admin on checking group settings
            await query.edit_message_text(
                "❌ Failed to send the lecture. This likely means the bot is not an *administrator* in the lecture group, "
                "or it cannot read the file. Please verify bot permissions."
            )

async def show_subjects_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the subject menu when a user sends a non-command message in private chat."""
    data = load_data()
    available_subjects = {subj: info for subj, info in data.items() if info.get("lectures")}
    
    if not available_subjects:
        await update.message.reply_text("No lectures configured yet. Admins: use /help.")
        return
        
    kb = [[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in available_subjects.keys()]
    await update.message.reply_text("Choose a subject:", reply_markup=InlineKeyboardMarkup(kb))

def main():
    """Starts the bot."""
    if not BOT_TOKEN or not GROUP_ID or not ADMIN_IDS:
        print("ERROR: Set BOT_TOKEN, GROUP_ID, and ADMIN_IDS correctly before running.")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_user))
    app.add_handler(CommandHandler("capture", capture))
    app.add_handler(CommandHandler("list", admin_list))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Message Handler (catches any text message in private chat that isn't a command)
    # NOTE: Your previous filter was `filters.ChatType.PRIVATE & filters.Command("start")` which only 
    # handled `/start`. I've fixed it to handle all non-command messages in private chat, as intended 
    # by the function name `show_subjects_on_message`.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, show_subjects_on_message))
    
    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
