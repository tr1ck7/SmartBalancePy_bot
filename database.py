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

    conn.commit()
    conn.close()

def add_expense(user_id, amount, category):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    msk_time = datetime.now(timezone.utc) + timedelta(hours = 3)
    now_str = msk_time.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)', (user_id, amount, category, now_str))

    conn.commit()
    conn.close()

def get_all_expenses(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, amount, category, date FROM expenses WHERE user_id = ? ORDER BY date DESC', (user_id,))
    rows = cursor.fetchall()
    conn.commit()
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