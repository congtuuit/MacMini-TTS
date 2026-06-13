import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app_name TEXT,
            endpoint TEXT,
            voice_id TEXT,
            text_length INTEGER,
            processing_time REAL,
            audio_duration REAL,
            rtf REAL,
            cpu_percent REAL,
            ram_percent REAL,
            timestamp REAL
        )
    ''')
    conn.commit()
    conn.close()

def log_request(app_name: str, endpoint: str, voice_id: str, text_length: int, processing_time: float, audio_duration: float, rtf: float, cpu_percent: float, ram_percent: float):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO request_logs (app_name, endpoint, voice_id, text_length, processing_time, audio_duration, rtf, cpu_percent, ram_percent, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (app_name, endpoint, voice_id, text_length, processing_time, audio_duration, rtf, cpu_percent, ram_percent, time.time()))
    conn.commit()
    conn.close()

def get_recent_logs(limit: int = 50):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM request_logs ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    
    columns = [description[0] for description in cursor.description]
    logs = [dict(zip(columns, row)) for row in rows]
    
    conn.close()
    return logs

init_db()
