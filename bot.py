import os
import pandas as pd
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.error import Forbidden, BadRequest

# ================= إعدادات المسارات =================
# خليه يعمل على السيرفر بدون مسارات ويندوز
DATA_FILE = "file.xlsx"
USER_FILE = "users.xlsx"

# 🔐 رقم الأدمن
ADMIN_ID = 7189695330

# ================= تحميل البيانات =================
def load_data():
    try:
        return pd.read_excel(DATA_FILE)
    except Exception as e:
        print(f"❌ خطأ في تحميل file.xlsx: {e}")
        return None

def ensure_user_files():
    if not os.path.exists(USER_FILE):
        with pd.ExcelWriter(USER_FILE) as writer:
            pd.DataFrame(columns=['user_id','first_name','last_name','username','language_code','is_bot','count']).to_excel(writer, sheet_name='users', index=False)
            pd.DataFrame(columns=['user_id','first_name','last_name','username','language_code','is_bot','timestamp']).to_excel(writer, sheet_name='usage_log', index=False)

def log_usage(user):
    ensure_user_files()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        usage_log_df = pd.read_excel(USER_FILE, sheet_name='usage_log')
    except:
        usage_log_df = pd.DataFrame(columns=['user_id','first_name','last_name','username','language_code','is_bot','timestamp'])

    new_log = pd.DataFrame([[user.id, user.first_name or '', user.last_name or '',
                             user.username or '', user.language_code or '', user.is_bot, now_str]],
                           columns=['user_id','first_name','last_name','username','language_code','is_bot','timestamp'])
    usage_log_df = pd.concat([usage_log_df, new_log], ignore_index=True)

    try:
        users_df = pd.read_excel(USER_FILE, sheet_name='users')
    except:
        users_df = pd.DataFrame(columns=['user_id','first_name','last_name','username','language_code','is_bot','count'])

    if user.id in users_df['user_id'].values:
        users_df.loc[users_df['user_id'] == user.id, ['first_name','last_name','username','language_code','is_bot']] = [
            user.first_name or '', user.last_name or '', user.username or '', user.language_code or '', user.is_bot
        ]
        users_df.loc[users_df['user_id'] == user.id, 'count'] += 1
    else:
        new_user = pd.DataFrame([[user.id, user.first_name or '', user.last_name or '',
                                  user.username or '', user.language_code or '', user.is_bot, 1]],
                                columns=['user_id','first_name','last_name','username','language_code','is_bot','count'])
        users_df = pd.concat([users_df, new_user], ignore_index=True)

    with pd.ExcelWriter(USER_FILE) as writer:
        users_df.to_excel(writer, sheet_name='users', index=False)
        usage_log_df.to_excel(writer, sheet_name='usage_log', index=False)

# ================= تنسيق النتائج =================
def format_table(result):
    text = "📊 <b>النتائج:</b>\n\n"
    for _, row in result.iterrows():
        for col in result.columns:
            val = str(row[col])
            if len(val) > 50:
                val = val[:47] + "..."
            text += f"🔹 <b>{col}:</b> {val}\n"
        text += "\n"
    return text

# ================= أوامر البوت =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    log_usage(user)

    keyboard = [
        [InlineKeyboardButton("🔄 تحديث البيانات", callback_data="refresh")],
        [InlineKeyboardButton("ℹ️ حول البوت", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✨ مرحباً <b>{user.first_name}</b>!\n\n"
        "🔍 أرسل رقم الموقع للحصول على التفاصيل.",
        parse_mode="HTML", reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    log_usage(user)

    query = update.message.text.strip()
    if not query.isdigit():
        await update.message.reply_text("⚠️ الرجاء إدخال رقم فقط.", parse_mode="HTML")
        return

    data = load_data()
    if data is None:
        await update.message.reply_text("❌ لم أتمكن من تحميل البيانات.", parse_mode="HTML")
        return

    result = data[data.iloc[:, 0] == int(query)]
    if result.empty:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.", parse_mode="HTML")
    else:
        await update.message.reply_text(format_table(result), parse_mode="HTML")

async def refresh_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    load_data()
    await update.callback_query.answer("✅ تم تحديث البيانات.")
    await update.callback_query.message.edit_text("🔄 تم تحديث البيانات بنجاح.", parse_mode="HTML")

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.edit_text(
        "🤖 <b>بوت البحث</b>\n"
        "تم تطويره بواسطة شركة ربوع المعالي.\n"
        "<a href='https://www.facebook.com/ruboo.iq/'>📎 صفحتنا على فيسبوك</a>",
        parse_mode="HTML"
    )

# ================= الإرسال الجماعي =================
async def broadcast_message(app, message_text):
    ensure_user_files()
    users_df = pd.read_excel(USER_FILE, sheet_name='users')
    user_ids = users_df['user_id'].dropna().unique()

    sent = 0
    for user_id in user_ids:
        try:
            await app.bot.send_message(chat_id=int(user_id), text=message_text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except (Forbidden, BadRequest):
            continue

    print(f"✅ تم الإرسال إلى {sent} مستخدم.")
    return sent

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("🚫 ليس لديك صلاحية لتنفيذ هذا الأمر.")
        return

    message_text = "📢 تم تحديث مواقع البوت! يُرجى إعادة المحاولة للاستفادة من التحديث الجديد 🔄"
    await update.message.reply_text("⏳ جاري إرسال الرسالة لجميع المستخدمين...")
    count = await broadcast_message(context.application, message_text)
    await update.message.reply_text(f"✅ تم الإرسال إلى {count} مستخدم.")

# ================= تشغيل البوت =================
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("❌ BOT_TOKEN غير موجود!")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(refresh_data, pattern="refresh"))
    app.add_handler(CallbackQueryHandler(about_bot, pattern="about"))

    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == '__main__':
    main()
