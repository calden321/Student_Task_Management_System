import sqlite3

# Connect to database
conn = sqlite3.connect('student_tasks.db')
cursor = conn.cursor()

# Add notes column to tasks table if it doesn't exist
try:
    cursor.execute('ALTER TABLE tasks ADD COLUMN notes TEXT')
    print("Added notes column to tasks table")
except Exception as e:
    print("Notes column already exists or error:", e)

# Create task_history table for progress tracking
cursor.execute('''
CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    note_text TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks (id),
    FOREIGN KEY (user_id) REFERENCES users (id)
)
''')

conn.commit()
conn.close()
print("Database updated successfully with notes and history tracking!")