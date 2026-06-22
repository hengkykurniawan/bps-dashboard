import sqlite3
import os
from datetime import datetime

def get_db_connection(db_path="bps_data.db"):
    """Mengembalikan koneksi database SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path="bps_data.db"):
    """Inisialisasi tabel-tabel database."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # Buat tabel katalog untuk menyimpan metadata tabel statis beserta domain wilayahnya
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tabel_katalog (
        table_id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        subject_id INTEGER NOT NULL,
        domain_id TEXT NOT NULL,
        domain_name TEXT,
        excel_url TEXT,
        download_status TEXT DEFAULT 'PENDING',
        file_path TEXT,
        size_bytes INTEGER,
        last_updated TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()
    print(f"Database berhasil diinisialisasi di {db_path}")

def insert_or_update_table(db_path, table_data):
    """
    Memasukkan atau memperbarui metadata tabel statis.
    table_data harus berupa dictionary berisi detail tabel.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    now = datetime.now().isoformat()
    
    # Cek apakah tabel sudah terdaftar
    cursor.execute("SELECT download_status, file_path FROM tabel_katalog WHERE table_id = ?", (table_data['table_id'],))
    row = cursor.fetchone()
    
    if row is None:
        # Sisipkan data baru dengan status PENDING
        cursor.execute("""
        INSERT INTO tabel_katalog (
            table_id, title, subject_id, domain_id, domain_name, excel_url, download_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
        """, (
            table_data['table_id'],
            table_data['title'],
            table_data['subject_id'],
            table_data['domain_id'],
            table_data['domain_name'],
            table_data['excel_url'],
            now,
            now
        ))
        conn.commit()
        inserted = True
    else:
        # Jika sudah ada, update metadata umum, tapi pertahankan status download
        cursor.execute("""
        UPDATE tabel_katalog 
        SET title = ?, domain_id = ?, domain_name = ?, excel_url = ?, updated_at = ?
        WHERE table_id = ?
        """, (
            table_data['title'],
            table_data['domain_id'],
            table_data['domain_name'],
            table_data['excel_url'],
            now,
            table_data['table_id']
        ))
        conn.commit()
        inserted = False
        
    conn.close()
    return inserted

def get_pending_downloads(db_path):
    """Mengembalikan daftar baris tabel yang belum berhasil diunduh."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT table_id, title, domain_id, domain_name, excel_url 
        FROM tabel_katalog 
        WHERE download_status = 'PENDING' OR download_status = 'FAILED'
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_download_status(db_path, table_id, status, file_path=None, size_bytes=None):
    """Memperbarui status pengunduhan tabel."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE tabel_katalog
        SET download_status = ?,
            file_path = ?,
            size_bytes = ?,
            last_updated = ?,
            updated_at = ?
        WHERE table_id = ?
    """, (status, file_path, size_bytes, now, now, table_id))
    
    conn.commit()
    conn.close()
