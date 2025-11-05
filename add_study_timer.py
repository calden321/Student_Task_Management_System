import sqlite3

# Connect to database
conn = sqlite3.connect('student_tasks.db')
cursor = conn.cursor()

# Create study_sessions table
cursor.execute('''
CREATE TABLE IF NOT EXISTS study_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject_id INTEGER,
    duration_minutes INTEGER NOT NULL,
    notes TEXT,
    session_type TEXT DEFAULT 'focus',  -- focus or break
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (subject_id) REFERENCES subjects (id)
)
''')

conn.commit()
conn.close()
print("Database updated successfully with study sessions table!")