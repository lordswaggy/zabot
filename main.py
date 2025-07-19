import os
import logging

from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

# Setup logging
logging.basicConfig(level=logging.INFO)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("WorKeeBot")  # Your sheet name here
products_sheet = sheet.worksheet("Products")
orders_sheet = sheet.worksheet("Orders")

# Conversation states
QUANTITY, NAME, PHONE, ADDRESS = range(4)
user_data = {}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = products_sheet.get_all_records()
    for idx, item in enumerate(rows[:5]):
        caption = f"🌿 *{item['Name']}*\n💸 {item['Price']} ฿\n📝 {item['Description']}"
        keyboard = [
            [InlineKeyboardButton("🛒 Order", callback_data=str(idx))]
        ]
        await update.message.reply_photo(
            photo=item["ImageURL"],
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Handle order click
async def handle_order_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_index = int(query.data)
    user_data[query.from_user.id] = {"product_index": product_index}
    await query.message.reply_text("🔢 How many units do you want to order?")
    return QUANTITY

# Handle quantity
async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quantity_text = update.message.text.strip()

    if not quantity_text.isdigit() or int(quantity_text) <= 0:
        await update.message.reply_text("❌ Please enter a valid number (greater than 0).")
        return QUANTITY

    user_data[update.effective_user.id]["quantity"] = int(quantity_text)
    await update.message.reply_text("👤 What's your name?")
    return NAME

# Handle name
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("📞 What's your phone number?")
    return PHONE

# Handle phone
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["phone"] = update.message.text
    await update.message.reply_text("🏠 What's your delivery address?")
    return ADDRESS

# Handle address
async def handle_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    address = update.message.text
    data = user_data[user_id]
    product = products_sheet.get_all_records()[data["product_index"]]

    # Save order (without timestamp)
    orders_sheet.append_row([
        data["name"],
        data["phone"],
        address,
        product["Name"],
        data["quantity"]
    ])

    # Notify shop owner
    msg = (
        f"🆕 *New Order!*\n\n"
        f"👤 Name: {data['name']}\n"
        f"📞 Phone: {data['phone']}\n"
        f"🏠 Address: {address}\n"
        f"🌿 Product: *{product['Name']}*\n"
        f"🔢 Quantity: {data['quantity']}"
    )
    await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=msg, parse_mode="Markdown")
    await update.message.reply_text("✅ Thanks! Your order has been placed.")
    return ConversationHandler.END

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Order cancelled.")
    return ConversationHandler.END

# Main app
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_order_click)],
        states={
            QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.run_polling()
