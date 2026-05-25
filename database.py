import sqlite3
from datetime import datetime, timedelta, timezone

def init_db():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            monthly_limit REAL DEFAULT 0,
            pinned_msg_id INTEGER DEFAULT NULL,
            limit_days INTEGER DEFAULT NULL,
            limit_start TIMESTAMP DEFAULT NULL
        )
    ''')

    for col, definition in [('limit_days', 'INTEGER DEFAULT NULL'), ('limit_start', 'TIMESTAMP DEFAULT NULL')]:
        try:
            cursor.execute(f'ALTER TABLE users ADD COLUMN {col} {definition}')
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


def add_expense(user_id, amount, category):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    msk_time = datetime.now(timezone.utc) + timedelta(hours=3)
    now_str = msk_time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        'INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)',
        (user_id, amount, category, now_str)
    )
    conn.commit()
    conn.close()


def get_total_expenses(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ?', (user_id,))
    total = cursor.fetchone()[0]
    conn.close()
    return total or 0.0


def set_limit_with_period(user_id, limit_amount, days):
    from datetime import datetime, timezone, timedelta
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    start = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (user_id, monthly_limit, limit_days, limit_start) VALUES (?, ?, ?, ?)',
            (user_id, limit_amount, days, start)
        )
    else:
        cursor.execute(
            'UPDATE users SET monthly_limit = ?, limit_days = ?, limit_start = ? WHERE user_id = ?',
            (limit_amount, days, start, user_id)
        )
    conn.commit()
    conn.close()

def get_limit_info(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT monthly_limit, limit_days, limit_start FROM users WHERE user_id = ?',
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row if row else (0.0, None, None)

def delete_limit(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET monthly_limit = 0, limit_days = NULL, limit_start = NULL WHERE user_id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()

def update_monthly_limit(user_id, limit_amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (user_id, monthly_limit) VALUES (?, ?)',
            (user_id, limit_amount)
        )
    else:
        cursor.execute(
            'UPDATE users SET monthly_limit = ? WHERE user_id = ?',
            (limit_amount, user_id)
        )
    conn.commit()
    conn.close()

def get_pinned_msg_id(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('SELECT pinned_msg_id FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def update_pinned_msg_id(user_id, msg_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            'INSERT INTO users (user_id, pinned_msg_id) VALUES (?, ?)',
            (user_id, msg_id)
        )
    else:
        cursor.execute(
            'UPDATE users SET pinned_msg_id = ? WHERE user_id = ?',
            (msg_id, user_id)
        )
    conn.commit()
    conn.close()


def get_all_expenses(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute(
        'SELECT id, amount, category, date FROM expenses WHERE user_id = ? ORDER BY date DESC',
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_expense(exp_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM expenses WHERE id = ?', (exp_id,))
    conn.commit()
    conn.close()


if __name__ == '__main__':
    init_db()
    print('База данных успешно инициализирована!')