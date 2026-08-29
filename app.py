from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB_FILE = "group_bot.db"

# ══════════════════════════════════════════════
#  توابع دیتابیس
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
            chat_id INTEGER,
            user_id INTEGER,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            chat_id INTEGER,
            user_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            time TEXT,
            message TEXT
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
    
    # تبدیل boolean به integer
    if isinstance(value, bool):
        value = 1 if value else 0
    
    conn.execute(f"UPDATE group_settings SET {key}=? WHERE chat_id=?", (value, chat_id))
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════
#  API Endpoints
# ══════════════════════════════════════════════
@app.route('/')
def home():
    return jsonify({'status': 'ok', 'message': 'Bot API is running ✅'})

@app.route('/api/stats')
def get_stats():
    chat_id = request.args.get('chat_id')
    if not chat_id:
        return jsonify({'ok': False, 'error': 'chat_id required'})
    
    active_locks = 0
    for key in ['lock_link', 'lock_forward', 'lock_sticker', 'lock_media', 'lock_english', 'lock_long_msg']:
        if get_setting(chat_id, key):
            active_locks += 1
    
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
        key = data.get('key')
        value = data.get('value')
        set_setting(chat_id, key, value)
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
        conn = sqlite3.connect(DB_FILE)
        conn.execute("DELETE FROM whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        conn.commit()
        conn.close()
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
        conn = sqlite3.connect(DB_FILE)
        conn.execute("DELETE FROM warnings WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        conn.commit()
        conn.close()
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
#  شروع سرور
# ══════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)