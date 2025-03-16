import sqlite3
import streamlit as st
import os

# Define the database location and name
DB_FOLDER = 'data'
DB_NAME = 'booking_system.db'
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)

def init_db():
    """Initialize the SQLite database and create tables if they don't exist."""
    # Create the data directory if it doesn't exist
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='appointments'")
    table_exists = c.fetchone()
    
    if table_exists:
        try:
            c.execute("SELECT email FROM appointments LIMIT 1")
        except sqlite3.OperationalError:
            st.write("Adding email column to existing database...")
            c.execute("ALTER TABLE appointments ADD COLUMN email TEXT DEFAULT 'no-email@example.com'")
            conn.commit()
    else:
        c.execute('''
        CREATE TABLE appointments
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         name TEXT NOT NULL,
         email TEXT NOT NULL,
         date TEXT NOT NULL,
         time TEXT NOT NULL,
         purpose TEXT,
         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
        ''')
        conn.commit()
    
    conn.close()

def add_appointment(name, email, date, time, purpose):
    """Add a new appointment to the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO appointments (name, email, date, time, purpose) VALUES (?, ?, ?, ?, ?)",
              (name, email, date, time, purpose))
    conn.commit()
    conn.close()

def get_appointments(name=None, email=None, date=None):
    """Retrieve appointments based on filters."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    query = "SELECT * FROM appointments"
    params = []
    
    conditions = []
    if name:
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{name}%")
    if email:
        conditions.append("LOWER(email) LIKE LOWER(?)")
        params.append(f"%{email}%")
    if date:
        conditions.append("date = ?")
        params.append(date)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY date, time"
    
    c.execute(query, params)
    appointments = c.fetchall()
    
    conn.close()
    return appointments

def check_appointment_exists(name, email, date, time):
    """Check if an appointment with the given details exists."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT * FROM appointments WHERE name = ? AND email = ? AND date = ? AND time = ?", 
            (name, email, date, time))
    result = c.fetchone()
    
    conn.close()
    return result is not None

def delete_appointment(id):
    """Delete an appointment by its ID."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id = ?", (id,))
    rows_affected = conn.total_changes
    conn.commit()
    conn.close()
    return rows_affected > 0

def get_table_structure():
    """Get the column names of the appointments table."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(appointments)")
    columns = c.fetchall()
    conn.close()
    return [col[1] for col in columns]