import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
)
from .config import settings
from .database import get_user, create_or_update_user, upload_cv
from .encryption import encrypt_string, decrypt_string
from .notion_api import create_kb_page, extract_id_from_url

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

NOTION_TOKEN, NOTION_PAGE, CV_UPLOAD, GEMINI_KEY = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if user and user.get("notion_token") and user.get("cv_url") and user.get("gemini_api_key"):
        await update.message.reply_text(
            "Welcome back! Your profile is already set up. Use /apply on a job link to get started."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Hey! Let's set up your Jobert profile. I'll need a few things to get started.\n\n"
        "Step 1 — Notion Token:\n"
        "Please share your Notion Internal Integration Token (starts with ntn_).\n"
        "(Settings → Integrations → Create new integration)"
    )
    return NOTION_TOKEN

async def handle_notion_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    token = update.message.text
    # Validation logic: allow both ntn_ and secret_ prefixes
    if not (token.startswith("ntn_") or token.startswith("secret_")):
        await update.message.reply_text("That doesn't look like a valid Notion token. It should start with 'ntn_'. Please try again.")
        return NOTION_TOKEN

    context.user_data["notion_token"] = token
    
    await update.message.reply_text(
        "Token received! Step 2 — Notion Page:\n\n"
        "1. Open a page in Notion where you want Jobert to live.\n"
        "2. Click '...' → 'Connect to' → select your integration.\n"
        "3. Paste the URL of that page here."
    )
    return NOTION_PAGE

async def handle_notion_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text
    page_id = extract_id_from_url(url)
    
    if not page_id:
        await update.message.reply_text("I couldn't find a valid Notion Page ID in that URL. Please make sure you've copied the full link.")
        return NOTION_PAGE

    context.user_data["notion_parent_id"] = page_id
    
    await update.message.reply_text(
        "Page linked! Step 3 — CV:\n"
        "Please upload your CV as a PDF file."
    )
    return CV_UPLOAD

async def handle_cv_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.document:
         await update.message.reply_text("Please upload a file (PDF).")
         return CV_UPLOAD
         
    document = update.message.document
    if document.mime_type != "application/pdf":
        await update.message.reply_text("Please upload a PDF file.")
        return CV_UPLOAD

    file = await context.bot.get_file(document.file_id)
    content = await file.download_as_bytearray()
    
    context.user_data["cv_content"] = bytes(content)
    context.user_data["cv_name"] = document.file_name
    
    await update.message.reply_text(
        "CV received! Final Step — Gemini API Key:\n"
        "Paste your Gemini API key (from aistudio.google.com)."
    )
    return GEMINI_KEY

async def handle_gemini_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    key = update.message.text
    user_id = update.effective_user.id
    
    await update.message.reply_text("Setting up your profile and Knowledge Base...")
    
    try:
        # 1. Upload CV
        cv_url = upload_cv(user_id, context.user_data["cv_content"], context.user_data["cv_name"])
        
        # 2. Create Notion KB
        kb_page = await create_kb_page(context.user_data["notion_token"], context.user_data["notion_parent_id"])
        kb_url = kb_page.get("url", "https://notion.so")
        kb_id = kb_page.get("id")
        
        # 3. Save everything to Supabase
        create_or_update_user(
            user_id, 
            notion_token=encrypt_string(context.user_data["notion_token"]),
            gemini_api_key=encrypt_string(key),
            cv_url=cv_url,
            notion_kb_page_id=kb_id
        )
        
        await update.message.reply_text(
            f"All set! I've created your Knowledge Base page here:\n{kb_url}\n\n"
            "Please fill it in with any additional details you want the AI to know.\n"
            "You can now use /apply on any job link!"
        )
    except Exception as e:
        logger.error(f"Error during setup: {e}")
        await update.message.reply_text(
            f"Setup failed: {str(e)}\n\nPlease use /start to try again."
        )
        
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Use /start to try again.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    if not settings.TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN not set!")
        return
        
    application = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOTION_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notion_token)],
            NOTION_PAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notion_page)],
            CV_UPLOAD: [MessageHandler(filters.Document.ALL, handle_cv_upload)],
            GEMINI_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gemini_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    logger.info("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
