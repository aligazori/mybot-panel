"""
ربات مدیریت گروه بله + API مینی اپ
نسخه ترکیبی - همه چیز در یک فایل
"""

import requests
import time
import json
import sqlite3
import re
import threading
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# ══════════════════════════════════════════════
#  تنظیمات - این بخش را ویرایش کنید
# ══════════════════════════════════════════════
BOT_TOKEN = "366695127:h8xj58vhhyjNTJaJrxd2rA3cUJgYlLA4KK4"  # ← توکن ربات خود را اینجا بگذارید
BASE_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
OWNER_IDS = [96221498]  # ← آیدی عددی خودتان
POLL_INTERVAL = 1
DB_FILE = "group_bot.db"

# ══════════════════════════════════════════════
#  بخش Flask (API مینی اپ)
# ══════════════════════════════════════════════
app = Flask(__name__)
CORS(app)

# ══════════════════════════════════════════════
#  بخش دیتابیس
# ══════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            lock_link INTEGER DEFAULT 0,
            lock_forward INTEGER DEFAULT 0,
            lock_sticker INTEGER DEFAULT 0,
            lock_media INTEGER DEFAULT 0,
            lock_english INTEGER DEFAULT 0,
            lock_long_msg INTEGER DEFAULT 0,
            welcome_enabled INTEGER DEFAULT 1,
            welcome_text TEXT DEFAULT 'سلام {name} عزیز!',
            captcha_enabled INTEGER DEFAULT 0,
            max_warnings INTEGER DEFAULT 3
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            chat_id INTEGER, user_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, time TEXT, message TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def get_setting(chat_id, key):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(f"SELECT {key} FROM group_settings WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        conn.close()
        if row is None:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
            conn.commit()
            conn.close()
            return 0 if key != "welcome_text" else "سلام {name} عزیز!"
        return row[0]
    except:
        conn.close()
        return 0

def set_setting(chat_id, key, value):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
    if isinstance(value, bool):
        value = 1 if value else 0
    conn.execute(f"UPDATE group_settings SET {key}=? WHERE chat_id=?", (value, chat_id))
    conn.commit()
    conn.close()

def add_warning(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO warnings (chat_id, user_id, count) VALUES (?,?,1) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET count=count+1",
        (chat_id, user_id)
    )
    c.execute("SELECT count FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    return count

def reset_warnings(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()
    conn.close()

def is_whitelisted(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_to_whitelist(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("INSERT OR IGNORE INTO whitelist (chat_id, user_id) VALUES (?,?)", (chat_id, user_id))
    conn.commit()
    conn.close()

def remove_from_whitelist(chat_id, user_id):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()
    conn.close()

def add_log(chat_id, message):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO activity_log (chat_id, time, message) VALUES (?, ?, ?)",
        (chat_id, datetime.now().strftime('%H:%M'), message)
    )
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════
#  بخش API بله
# ══════════════════════════════════════════════
def api_request(method, params=None):
    url = f"{BASE_URL}/{method}"
    try:
        resp = requests.post(url, data=params, timeout=35)
        return resp.json()
    except Exception as e:
        print(f"[ERROR] {method}: {e}")
        return None

def send_message(chat_id, text, reply_to=None, reply_markup=None, parse_mode=None):
    params = {"chat_id": chat_id, "text": text}
    if reply_to:
        params["reply_to_message_id"] = reply_to
    if reply_markup:
        params["reply_markup"] = json.dumps(reply_markup)
    if parse_mode:
        params["parse_mode"] = parse_mode
    return api_request("sendMessage", params)

def delete_message(chat_id, message_id):
    return api_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def ban_user(chat_id, user_id):
    return api_request("banChatMember", {"chat_id": chat_id, "user_id": user_id})

def unban_user(chat_id, user_id):
    return api_request("unbanChatMember", {"chat_id": chat_id, "user_id": user_id})

def mute_user(chat_id, user_id):
    permissions = {
        "can_send_messages": False,
        "can_send_media_messages": False,
        "can_send_other_messages": False,
        "can_add_web_page_previews": False
    }
    return api_request("restrictChatMember", {
        "chat_id": chat_id, "user_id": user_id,
        "permissions": json.dumps(permissions)
    })

def unmute_user(chat_id, user_id):
    permissions = {
        "can_send_messages": True,
        "can_send_media_messages": True,
        "can_send_other_messages": True,
        "can_add_web_page_previews": True
    }
    return api_request("restrictChatMember", {
        "chat_id": chat_id, "user_id": user_id,
        "permissions": json.dumps(permissions)
    })

def get_chat_member(chat_id, user_id):
    return api_request("getChatMember", {"chat_id": chat_id, "user_id": user_id})

def answer_callback(callback_id, text="", show_alert=False):
    return api_request("answerCallbackQuery", {
        "callback_query_id": callback_id, "text": text, "show_alert": show_alert
    })

# ══════════════════════════════════════════════
#  توابع کمکی
# ══════════════════════════════════════════════
def is_admin(chat_id, user_id):
    if user_id in OWNER_IDS:
        return True
    result = get_chat_member(chat_id, user_id)
    if result and result.get("ok"):
        status = result["result"].get("status", "")
        return status in ("creator", "administrator")
    return False

def get_user_name(user_obj):
    first = user_obj.get("first_name", "")
    last = user_obj.get("last_name", "")
    return f"{first} {last}".strip() or "کاربر"

def contains_link(text):
    if not text:
        return False
    patterns = [r'https?://\S+', r'www\.\S+', r'\w+\.(com|ir|org|net|info|me|io|co)\b', r't\.me/\S+', r'ble\.ir/\S+']
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False

def contains_english(text):
    if not text:
        return False
    return bool(re.search(r'[a-zA-Z]', text))

# ══════════════════════════════════════════════
#  پردازش دستورات
# ══════════════════════════════════════════════
def handle_command(msg, text, chat_id, user_id, message_id):
    cmd = text.split()[0].lower().split("@")[0]
    args = text[len(cmd):].strip()

    if cmd in ("/start", "/help"):
        help_text = (
            "🤖 <b>ربات مدیریت گروه بله</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>دستورات:</b>\n"
            "/lock link|forward|sticker|media|english|longmsg\n"
            "/unlock link|forward|sticker|media|english|longmsg\n"
            "/locks - وضعیت قفل‌ها\n"
            "/warn (ریپلای) - اخطار\n"
            "/ban (ریپلای) - مسدود\n"
            "/mute (ریپلای) - بی‌صدا\n"
            "/vip (ریپلای) - لیست سفید\n"
            "/settings - تنظیمات\n"
            "/id - آیدی"
        )
        send_message(chat_id, help_text, reply_to=message_id, parse_mode="HTML")
        return True

    if cmd == "/id":
        reply = msg.get("reply_to_message")
        if reply:
            uid = reply["from"]["id"]
            name = get_user_name(reply["from"])
            send_message(chat_id, f"👤 {name}\n🔢 آیدی: <code>{uid}</code>",
                         reply_to=message_id, parse_mode="HTML")
        else:
            send_message(chat_id, f"🔢 آیدی شما: <code>{user_id}</code>\n🔢 آیدی گروه: <code>{chat_id}</code>",
                         reply_to=message_id, parse_mode="HTML")
        return True

    if not is_admin(chat_id, user_id):
        return False

    reply_msg = msg.get("reply_to_message")
    reply_user_id = reply_msg["from"]["id"] if reply_msg else None

    lock_map = {
        "link": "lock_link", "forward": "lock_forward", "sticker": "lock_sticker",
        "media": "lock_media", "english": "lock_english", "longmsg": "lock_long_msg",
    }

    if cmd == "/lock":
        key = args.strip().lower()
        if key in lock_map:
            set_setting(chat_id, lock_map[key], 1)
            add_log(chat_id, f"🔒 قفل {key} فعال شد")
            send_message(chat_id, f"✅ قفل <b>{key}</b> فعال شد.", reply_to=message_id, parse_mode="HTML")
        return True

    if cmd == "/unlock":
        key = args.strip().lower()
        if key in lock_map:
            set_setting(chat_id, lock_map[key], 0)
            add_log(chat_id, f"🔓 قفل {key} غیرفعال شد")
            send_message(chat_id, f"🔓 قفل <b>{key}</b> غیرفعال شد.", reply_to=message_id, parse_mode="HTML")
        return True

    if cmd == "/locks":
        status_lines = []
        for name, col in lock_map.items():
            val = get_setting(chat_id, col)
            icon = "🔒" if val else "🔓"
            status_lines.append(f"{icon} {name}")
        send_message(chat_id, "📋 <b>وضعیت قفل‌ها:</b>\n" + "\n".join(status_lines),
                     reply_to=message_id, parse_mode="HTML")
        return True

    if cmd == "/warn":
        if not reply_user_id:
            send_message(chat_id, "⚠️ ریپلای کنید.", reply_to=message_id)
            return True
        if is_admin(chat_id, reply_user_id):
            send_message(chat_id, "❌ نمی‌توانید به ادمین اخطار بدهید.", reply_to=message_id)
            return True
        max_w = get_setting(chat_id, "max_warnings") or 3
        count = add_warning(chat_id, reply_user_id)
        name = get_user_name(reply_msg["from"])
        if count >= max_w:
            ban_user(chat_id, reply_user_id)
            reset_warnings(chat_id, reply_user_id)
            add_log(chat_id, f"🚫 {name} بن شد ({max_w} اخطار)")
            send_message(chat_id, f"🚫 {name} مسدود شد.", reply_to=message_id)
        else:
            add_log(chat_id, f"⚠️ اخطار به {name} ({count}/{max_w})")
            send_message(chat_id, f"⚠️ {name} یک اخطار گرفت. ({count}/{max_w})", reply_to=message_id)
        return True

    if cmd == "/ban" and reply_user_id:
        if not is_admin(chat_id, reply_user_id):
            ban_user(chat_id, reply_user_id)
            send_message(chat_id, f"🚫 {get_user_name(reply_msg['from'])} مسدود شد.", reply_to=message_id)
        return True

    if cmd == "/mute" and reply_user_id:
        if not is_admin(chat_id, reply_user_id):
            mute_user(chat_id, reply_user_id)
            send_message(chat_id, f"🔇 {get_user_name(reply_msg['from'])} بی‌صدا شد.", reply_to=message_id)
        return True

    if cmd == "/unmute" and reply_user_id:
        unmute_user(chat_id, reply_user_id)
        send_message(chat_id, "🔊 کاربر از بی‌صدا خارج شد.", reply_to=message_id)
        return True

    if cmd == "/del":
        if reply_msg:
            delete_message(chat_id, reply_msg["message_id"])
        delete_message(chat_id, message_id)
        return True

    if cmd == "/pin" and reply_msg:
        api_request("pinChatMessage", {"chat_id": chat_id, "message_id": reply_msg["message_id"]})
        send_message(chat_id, "📌 پیام سنجاق شد.", reply_to=message_id)
        return True

    if cmd == "/welcome":
        val = args.strip().lower()
        if val == "on":
            set_setting(chat_id, "welcome_enabled", 1)
            send_message(chat_id, "✅ خوش‌آمدگویی فعال شد.", reply_to=message_id)
        elif val == "off":
            set_setting(chat_id, "welcome_enabled", 0)
            send_message(chat_id, "❌ خوش‌آمدگویی غیرفعال شد.", reply_to=message_id)
        return True

    if cmd == "/setwelcome" and args:
        set_setting(chat_id, "welcome_text", args)
        send_message(chat_id, f"✅ متن خوش‌آمد ذخیره شد.", reply_to=message_id)
        return True

    if cmd == "/captcha":
        val = args.strip().lower()
        if val == "on":
            set_setting(chat_id, "captcha_enabled", 1)
            send_message(chat_id, "✅ کپچا فعال شد.", reply_to=message_id)
        elif val == "off":
            set_setting(chat_id, "captcha_enabled", 0)
            send_message(chat_id, "❌ کپچا غیرفعال شد.", reply_to=message_id)
        return True

    if cmd == "/vip" and reply_user_id:
        add_to_whitelist(chat_id, reply_user_id)
        send_message(chat_id, f"⭐ {get_user_name(reply_msg['from'])} به VIP اضافه شد.", reply_to=message_id)
        return True

    if cmd == "/unvip" and reply_user_id:
        remove_from_whitelist(chat_id, reply_user_id)
        send_message(chat_id, "✅ کاربر از VIP حذف شد.", reply_to=message_id)
        return True

    if cmd == "/settings":
        wel = "✅" if get_setting(chat_id, "welcome_enabled") else "❌"
        cap = "✅" if get_setting(chat_id, "captcha_enabled") else "❌"
        max_w = get_setting(chat_id, "max_warnings") or 3
        send_message(chat_id,
            f"⚙️ <b>تنظیمات گروه</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👋 خوش‌آمدگویی: {wel}\n"
            f"🧩 کپچا: {cap}\n"
            f"⚠️ حداکثر اخطار: {max_w}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"برای قفل‌ها: /locks",
            reply_to=message_id, parse_mode="HTML")
        return True

    return False

# ══════════════════════════════════════════════
#  پردازش فیلترها
# ══════════════════════════════════════════════
def check_filters(msg, chat_id, user_id, message_id, text):
    if is_admin(chat_id, user_id) or is_whitelisted(chat_id, user_id):
        return False

    violated = False
    reason = ""

    if get_setting(chat_id, "lock_link") and contains_link(text):
        violated, reason = True, "ارسال لینک"
    if get_setting(chat_id, "lock_forward") and ("forward_from" in msg or "forward_from_chat" in msg):
        violated, reason = True, "فوروارد"
    if get_setting(chat_id, "lock_sticker") and "sticker" in msg:
        violated, reason = True, "استیکر"
    if get_setting(chat_id, "lock_media") and any(k in msg for k in ("photo", "video", "animation", "document", "voice", "video_note")):
        violated, reason = True, "مدیا"
    if get_setting(chat_id, "lock_english") and contains_english(text):
        violated, reason = True, "انگلیسی"
    if get_setting(chat_id, "lock_long_msg") and text and len(text) > 300:
        violated, reason = True, "پیام طولانی"

    if violated:
        delete_message(chat_id, message_id)
        name = get_user_name(msg.get("from", {}))
        send_message(chat_id, f"⛔️ {name}، {reason} ممنوع است!")
        max_w = get_setting(chat_id, "max_warnings") or 3
        count = add_warning(chat_id, user_id)
        if count >= max_w:
            ban_user(chat_id, user_id)
            reset_warnings(chat_id, user_id)
            add_log(chat_id, f"🚫 {name} بن خودکار ({max_w} اخطار)")
            send_message(chat_id, f"🚫 {name} به دلیل {max_w} اخطار مسدود شد.")
        return True
    return False

# ══════════════════════════════════════════════
#  پردازش Callback (کپچا)
# ══════════════════════════════════════════════
def handle_callback(callback):
    data = callback.get("data", "")
    cb_id = callback["id"]
    user_id = callback["from"]["id"]
    chat_id = callback["message"]["chat"]["id"]
    msg_id = callback["message"]["message_id"]

    if data.startswith("captcha_"):
        target_id = int(data.split("_")[1])
        if user_id != target_id:
            answer_callback(cb_id, "این دکمه برای شما نیست!", show_alert=True)
            return
        unmute_user(chat_id, user_id)
        delete_message(chat_id, msg_id)
        answer_callback(cb_id, "✅ تایید شدید!")

# ══════════════════════════════════════════════
#  بخش Flask API (برای مینی اپ)
# ══════════════════════════════════════════════
@app.route('/')
def home():
    return jsonify({'status': 'ok', 'message': 'Bot + API is running ✅'})

@app.route('/api/stats')
def get_stats():
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({'ok': False, 'error': 'chat_id required'})
    
    active_locks = sum(1 for k in ['lock_link', 'lock_forward', 'lock_sticker', 'lock_media', 'lock_english', 'lock_long_msg'] if get_setting(chat_id, k))
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM whitelist WHERE chat_id=?", (chat_id,))
    vip_count = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(count), 0) FROM warnings WHERE chat_id=?", (chat_id,))
    warnings_count = c.fetchone()[0]
    conn.close()
    
    return jsonify({
        'ok': True,
        'result': {
            'totalMembers': 0,
            'activeLocks': active_locks,
            'vipUsers': vip_count,
            'warnings': warnings_count
        }
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def manage_settings():
    chat_id = request.args.get('chat_id')
    if request.method == 'GET':
        settings = {}
        for key in ['lock_link', 'lock_forward', 'lock_sticker', 'lock_media', 
                    'lock_english', 'lock_long_msg', 'welcome_enabled', 
                    'welcome_text', 'captcha_enabled', 'max_warnings']:
            settings[key] = get_setting(chat_id, key)
        return jsonify({'ok': True, 'result': settings})
    elif request.method == 'POST':
        data = request.json
        set_setting(chat_id, data.get('key'), data.get('value'))
        return jsonify({'ok': True})

@app.route('/api/vip', methods=['GET', 'DELETE'])
def manage_vip():
    chat_id = request.args.get('chat_id')
    if request.method == 'GET':
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id FROM whitelist WHERE chat_id=?", (chat_id,))
        users = [{'id': row[0], 'name': f'کاربر {row[0]}'} for row in c.fetchall()]
        conn.close()
        return jsonify({'ok': True, 'result': users})
    elif request.method == 'DELETE':
        user_id = request.args.get('user_id')
        remove_from_whitelist(chat_id, user_id)
        return jsonify({'ok': True})

@app.route('/api/warnings', methods=['GET', 'DELETE'])
def manage_warnings():
    chat_id = request.args.get('chat_id')
    if request.method == 'GET':
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT user_id, count FROM warnings WHERE chat_id=? AND count > 0", (chat_id,))
        users = [{'id': row[0], 'name': f'کاربر {row[0]}', 'count': row[1]} for row in c.fetchall()]
        conn.close()
        return jsonify({'ok': True, 'result': users})
    elif request.method == 'DELETE':
        user_id = request.args.get('user_id')
        reset_warnings(chat_id, user_id)
        return jsonify({'ok': True})

@app.route('/api/logs')
def get_logs():
    chat_id = request.args.get('chat_id')
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT time, message FROM activity_log WHERE chat_id=? ORDER BY id DESC LIMIT 50", (chat_id,))
    logs = [{'time': row[0], 'message': row[1]} for row in c.fetchall()]
    conn.close()
    return jsonify({'ok': True, 'result': logs})

# ══════════════════════════════════════════════
#  حلقه اصلی ربات
# ══════════════════════════════════════════════
def bot_loop():
    """ربات اصلی - پردازش پیام‌های بله"""
    offset = 0
    print("=" * 50)
    print("🤖 ربات بله شروع به کار کرد")
    print("=" * 50)
    
    api_request("getUpdates", {"offset": -1})
    
    while True:
        try:
            result = api_request("getUpdates", {"offset": offset + 1, "timeout": 30})
            if not result or not result.get("ok"):
                time.sleep(POLL_INTERVAL)
                continue
            
            for update in result.get("result", []):
                offset = update["update_id"]
                
                if "callback_query" in update:
                    handle_callback(update["callback_query"])
                    continue
                
                if "message" not in update:
                    continue
                
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                message_id = msg["message_id"]
                text = msg.get("text", "")
                user = msg.get("from", {})
                user_id = user.get("id", 0)
                chat_type = msg["chat"].get("type", "")
                
                if chat_type not in ("group", "supergroup"):
                    if text.startswith("/start"):
                        send_message(chat_id, "سلام! من را به یک گروه اضافه کنید. 🤖")
                    continue
                
                if "new_chat_members" in msg:
                    for member in msg["new_chat_members"]:
                        m_id = member["id"]
                        m_name = get_user_name(member)
                        if get_setting(chat_id, "captcha_enabled"):
                            mute_user(chat_id, m_id)
                            keyboard = {
                                "inline_keyboard": [[
                                    {"text": "من ربات نیستم ✅", "callback_data": f"captcha_{m_id}"}
                                ]]
                            }
                            send_message(chat_id, f"🧩 {m_name}، دکمه زیر را بزنید.", reply_markup=keyboard)
                        if get_setting(chat_id, "welcome_enabled"):
                            wel_text = get_setting(chat_id, "welcome_text")
                            if isinstance(wel_text, str):
                                wel_text = wel_text.replace("{name}", m_name)
                            send_message(chat_id, wel_text)
                    delete_message(chat_id, message_id)
                    continue
                
                if "left_chat_member" in msg:
                    delete_message(chat_id, message_id)
                    continue
                
                if check_filters(msg, chat_id, user_id, message_id, text):
                    continue
                
                if text.startswith("/"):
                    handle_command(msg, text, chat_id, user_id, message_id)
        
        except KeyboardInterrupt:
            print("\n🛑 ربات متوقف شد.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)


# ══════════════════════════════════════════════
#  شروع برنامه (سازگار با سرور Render)
# ══════════════════════════════════════════════

# 1. ساخت جداول دیتابیس به محض روشن شدن سرور
init_db()

# 2. تعریف تابعی برای اجرای ربات در پس‌زمینه
def start_bot_background():
    print("=" * 50)
    print("🤖 ربات بله در پس‌زمینه شروع به کار کرد")
    print("=" * 50)
    bot_loop()

# 3. اجرای ربات در یک Thread جداگانه
# (daemon=True یعنی اگر سرور خاموش شد، ربات هم خاموش شود)
bot_thread = threading.Thread(target=start_bot_background, daemon=True)
bot_thread.start()

# نکته مهم: سرور Flask (همان app) به صورت خودکار توسط Render/Gunicorn اجرا می‌شود
# و نیازی به کد اضافه برای آن در اینجا نیست.
