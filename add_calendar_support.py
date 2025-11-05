import sqlite3

# Connect to database
conn = sqlite3.connect('student_tasks.db')
cursor = conn.cursor()

# Add a color column to tasks for calendar display (optional)
try:
    cursor.execute('ALTER TABLE tasks ADD COLUMN calendar_color TEXT')
    print("Added calendar_color column to tasks table")
except Exception as e:
    print("Calendar color column already exists or error:", e)

# Update existing tasks with color based on priority
cursor.execute('''
    UPDATE tasks SET calendar_color = 
        CASE 
            WHEN priority = 'high' THEN '#ff4444'
            WHEN priority = 'medium' THEN '#ffaa00' 
            WHEN priority = 'low' THEN '#44ff44'
            ELSE '#666666'
        END
    WHERE calendar_color IS NULL
''')

conn.commit()
conn.close()
print("Database updated successfully for calendar support!")