import sqlite3

# Connect to database
conn = sqlite3.connect('student_tasks.db')
cursor = conn.cursor()

# Create subjects table
cursor.execute('''
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT DEFAULT '#007bff',
    FOREIGN KEY (user_id) REFERENCES users (id)
)
''')

# Add subject_id column to tasks table if it doesn't exist
try:
    cursor.execute('ALTER TABLE tasks ADD COLUMN subject_id INTEGER')
    print("Added subject_id column to tasks table")
except:
    print("subject_id column already exists")

# Insert some default subjects for testing
cursor.execute('''
INSERT OR IGNORE INTO subjects (user_id, name, color) 
VALUES 
    (1, 'Math', '#ff4444'),
    (1, 'Science', '#44ff44'),
    (1, 'English', '#4444ff'),
    (1, 'History', '#ffff44')
''')

conn.commit()
conn.close()
print("Database updated successfully with subjects!")