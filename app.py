from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, jsonify
from google.cloud import dialogflow
from google.oauth2 import service_account
import uuid
import os
import re

app = Flask(__name__)
app.secret_key = 'my-student-task-app-secret-123'

def get_db_connection():
    if os.environ.get('DATABASE_URL'):
        import psycopg2
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
    else:
        conn = sqlite3.connect('student_tasks.db')
        conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_username(username):
    """Validate username format"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    if len(username) > 20:
        return False, "Username must be less than 20 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, ""

def validate_email(email):
    """Validate email format"""
    if len(email) > 100:
        return False, "Email must be less than 100 characters"
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Please enter a valid email address"
    return True, ""

def validate_password(password):
    """Validate password strength"""
    if len(password) < 6:
        return False, "Password must be at least 6 characters long"
    if len(password) > 100:
        return False, "Password must be less than 100 characters"
    # Check for at least one number and one letter
    if not re.search(r'\d', password) or not re.search(r'[a-zA-Z]', password):
        return False, "Password must contain at least one letter and one number"
    return True, ""

def sanitize_input(text):
    """Basic input sanitization"""
    if not text:
        return text
    # Remove potentially harmful characters
    text = re.sub(r'[<>&\"\']', '', text)
    return text.strip()

def check_existing_user(username, email):
    """Check if username or email already exists"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        existing_user = cur.execute(
            'SELECT id, username, email FROM users WHERE username = ? OR email = ?', 
            (username, email)
        ).fetchone()
        
        if existing_user:
            if existing_user['username'] == username:
                return False, "Username already exists"
            if existing_user['email'] == email:
                return False, "Email already registered"
        
        return True, ""
    except Exception as e:
        return False, f"Database error: {str(e)}"
    finally:
        cur.close()
        conn.close()

def get_urgency_class(due_date_str):
    """Calculate urgency class based on due date"""
    if not due_date_str:
        return ''
    
    try:
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        if due_date < today:
            return 'urgent-overdue'
        elif due_date == today:
            return 'urgent-today'
        elif due_date == tomorrow:
            return 'urgent-tomorrow'
        else:
            return ''
    except:
        return ''

@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/dashboard')
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get and sanitize form data
        username = sanitize_input(request.form.get('username', ''))
        email = sanitize_input(request.form.get('email', ''))
        password = request.form.get('password', '')
        
        # Validate required fields
        if not username or not email or not password:
            flash('Please fill in all required fields!', 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
        
        # Validate username
        is_valid_username, username_error = validate_username(username)
        if not is_valid_username:
            flash(username_error, 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
        
        # Validate email
        is_valid_email, email_error = validate_email(email)
        if not is_valid_email:
            flash(email_error, 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
        
        # Validate password
        is_valid_password, password_error = validate_password(password)
        if not is_valid_password:
            flash(password_error, 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
        
        # Check if user already exists
        user_exists, exists_error = check_existing_user(username, email)
        if not user_exists:
            flash(exists_error, 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
        
        # Create new user
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute(
                'INSERT INTO users (username, email, password, created_at) VALUES (?, ?, ?, ?)',
                (username, email, hash_password(password), datetime.now())
            )
            conn.commit()
            
            # Get the new user ID
            new_user = cur.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
            
            cur.close()
            conn.close()
            
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
            return render_template('register.html', 
                                 username=username, 
                                 email=email)
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        
        # Validate required fields
        if not username or not password:
            flash('Please enter both username and password!', 'error')
            return render_template('login.html')
        
        # Basic username validation
        if len(username) < 3 or len(username) > 20:
            flash('Invalid username format!', 'error')
            return render_template('login.html')
        
        # Basic password validation
        if len(password) < 1:
            flash('Please enter your password!', 'error')
            return render_template('login.html')
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            user = cur.execute(
                'SELECT * FROM users WHERE username = ? AND password = ?',
                (username, hash_password(password))
            ).fetchone()
            
            cur.close()
            conn.close()
            
            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['login_time'] = datetime.now().isoformat()
                
                flash(f'Welcome back, {user["username"]}!', 'success')
                return redirect('/dashboard')
            else:
                flash('Invalid username or password!', 'error')
                return render_template('login.html')
        
        except Exception as e:
            flash(f'Login error: {str(e)}', 'error')
            return render_template('login.html')
    
    return render_template('login.html')



@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # --- Subject creation ---
    if request.method == 'POST' and 'new_subject' in request.form:
        new_subject = request.form['new_subject']
        if new_subject:
            cur.execute(
                'INSERT INTO subjects (user_id, name) VALUES (?, ?)',
                (session['user_id'], new_subject)
            )
            conn.commit()
    
    # --- Task creation ---
    if request.method == 'POST' and 'title' in request.form:
        title = request.form['title']
        description = request.form['description']
        due_date = request.form['due_date']
        priority = request.form['priority']
        subject_id = request.form.get('subject_id')
        notes = request.form.get('notes', '')  # Add initial notes
        
        cur.execute(
            'INSERT INTO tasks (user_id, title, description, due_date, priority, subject_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (session['user_id'], title, description, due_date, priority, subject_id, notes)
        )
        task_id = cur.lastrowid
        
        # Add initial note to history if provided
        if notes.strip():
            cur.execute(
                'INSERT INTO task_history (task_id, user_id, note_text) VALUES (?, ?, ?)',
                (task_id, session['user_id'], f"Initial notes: {notes}")
            )
        
        conn.commit()
        return redirect('/dashboard')
    
    # --- Fetch subjects ---
    subjects = cur.execute(
        'SELECT * FROM subjects WHERE user_id = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    
    # --- Task filters ---
    subject_filter = request.args.get('subject', 'all')
    search_query = request.args.get('search', '')
    
    base_query = '''
        SELECT tasks.*, subjects.name as subject_name, subjects.color as subject_color 
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ?
    '''
    query_params = [session['user_id']]
    
    if subject_filter != 'all':
        base_query += ' AND subjects.name = ?'
        query_params.append(subject_filter)
    
    if search_query:
        base_query += ' AND (tasks.title LIKE ? OR tasks.description LIKE ? OR subjects.name LIKE ? OR tasks.notes LIKE ?)'
        search_term = f'%{search_query}%'
        query_params.extend([search_term, search_term, search_term, search_term])
    
    base_query += '''
        ORDER BY 
            CASE 
                WHEN due_date < date('now') THEN 1
                WHEN due_date = date('now') THEN 2
                WHEN due_date = date('now', '+1 day') THEN 3
                ELSE 4
            END,
            CASE priority 
                WHEN 'high' THEN 1 
                WHEN 'medium' THEN 2 
                WHEN 'low' THEN 3 
            END, 
            due_date
    '''
    
    tasks = cur.execute(base_query, query_params).fetchall()
    
    # --- Stats ---
    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task['completed'])
    pending_tasks = total_tasks - completed_tasks
    
    cur.close()
    conn.close()
    
    return render_template('dashboard_notes.html', 
                         tasks=tasks,
                         subjects=subjects,
                         subject_filter=subject_filter,
                         search_query=search_query,
                         total_tasks=total_tasks,
                         completed_tasks=completed_tasks,
                         pending_tasks=pending_tasks,
                         get_urgency_class=get_urgency_class)

@app.route('/complete_task', methods=['POST'])
def complete_task():
    if 'user_id' not in session:
        return redirect('/login')
    
    task_id = request.form['task_id']
    conn = get_db_connection()
    conn.execute(
        'UPDATE tasks SET completed = 1 WHERE id = ? AND user_id = ?',
        (task_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    return redirect('/dashboard')




@app.route('/delete_task', methods=['POST'])
def delete_task():
    if 'user_id' not in session:
        return redirect('/login')
    
    task_id = request.form['task_id']
    conn = get_db_connection()
    conn.execute(
        'DELETE FROM tasks WHERE id = ? AND user_id = ?',
        (task_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    return redirect('/dashboard')

@app.route('/delete_subject/<int:subject_id>')
def delete_subject(subject_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    # Remove subject from tasks first
    conn.execute(
        'UPDATE tasks SET subject_id = NULL WHERE subject_id = ? AND user_id = ?',
        (subject_id, session['user_id'])
    )
    # Delete the subject
    conn.execute(
        'DELETE FROM subjects WHERE id = ? AND user_id = ?',
        (subject_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    return redirect('/dashboard')

#EXPORT
@app.route('/export/txt')
def export_txt():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    
    # Get filter parameters
    subject_filter = request.args.get('subject', 'all')
    search_query = request.args.get('search', '')
    
    # Build the query (same as dashboard)
    base_query = '''
        SELECT tasks.*, subjects.name as subject_name
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ?
    '''
    
    query_params = [session['user_id']]
    
    if subject_filter != 'all':
        base_query += ' AND subjects.name = ?'
        query_params.append(subject_filter)
    
    if search_query:
        base_query += ' AND (tasks.title LIKE ? OR tasks.description LIKE ? OR subjects.name LIKE ?)'
        search_term = f'%{search_query}%'
        query_params.extend([search_term, search_term, search_term])
    
    base_query += ' ORDER BY due_date, priority'
    
    tasks = conn.execute(base_query, query_params).fetchall()
    conn.close()
    
    # Generate text content
    content = f"Student Task Manager - Task List\n"
    content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    content += f"User: {session['username']}\n"
    content += "=" * 50 + "\n\n"
    
    for task in tasks:
        status = "✅ COMPLETED" if task['completed'] else "⏳ PENDING"
        priority = task['priority'].upper()
        subject = task['subject_name'] or "No Subject"
        
        content += f"TITLE: {task['title']}\n"
        content += f"SUBJECT: {subject}\n"
        content += f"PRIORITY: {priority} | DUE: {task['due_date']} | STATUS: {status}\n"
        if task['description']:
            content += f"DESCRIPTION: {task['description']}\n"
        content += "-" * 30 + "\n"
    
    # Create response with text file
    from io import StringIO
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=tasks_{datetime.now().strftime("%Y%m%d")}.txt'
    
    return response

@app.route('/export/print')
def export_print():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    
    # Get filter parameters
    subject_filter = request.args.get('subject', 'all')
    search_query = request.args.get('search', '')
    
    # Build the query (same as dashboard)
    base_query = '''
        SELECT tasks.*, subjects.name as subject_name
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ?
    '''
    
    query_params = [session['user_id']]
    
    if subject_filter != 'all':
        base_query += ' AND subjects.name = ?'
        query_params.append(subject_filter)
    
    if search_query:
        base_query += ' AND (tasks.title LIKE ? OR tasks.description LIKE ? OR subjects.name LIKE ?)'
        search_term = f'%{search_query}%'
        query_params.extend([search_term, search_term, search_term])
    
    base_query += ' ORDER BY due_date, priority'
    
    tasks = conn.execute(base_query, query_params).fetchall()
    conn.close()
    
    return render_template('print_view.html', 
                         tasks=tasks,
                         subject_filter=subject_filter,
                         search_query=search_query,
                         username=session['username'])

@app.route('/print-view')
def print_view():
    """Simple print-friendly page"""
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    tasks = conn.execute('''
        SELECT tasks.*, subjects.name as subject_name 
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ? AND tasks.completed = 0
        ORDER BY due_date, priority
    ''', (session['user_id'],)).fetchall()
    conn.close()
    
    return render_template('print_simple.html', 
                         tasks=tasks, 
                         username=session['username'],
                         now=datetime.now(),
                         get_urgency_class=get_urgency_class)  # Add this line!

#ADD NOTES

@app.route('/add_note/<int:task_id>', methods=['POST'])
def add_note(task_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    note_text = request.form['note_text']
    if note_text.strip():
        conn = get_db_connection()
        
        # Add to task history
        conn.execute(
            'INSERT INTO task_history (task_id, user_id, note_text) VALUES (?, ?, ?)',
            (task_id, session['user_id'], note_text.strip())
        )
        
        # Update main task notes (keep a summary)
        conn.execute(
            'UPDATE tasks SET notes = COALESCE(notes || "\n", "") || ? WHERE id = ? AND user_id = ?',
            (f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note_text}", task_id, session['user_id'])
        )
        
        conn.commit()
        conn.close()
    
    return redirect('/dashboard')

@app.route('/task_details/<int:task_id>')
def task_details(task_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    
    # Get task details
    task = conn.execute('''
        SELECT tasks.*, subjects.name as subject_name, subjects.color as subject_color 
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.id = ? AND tasks.user_id = ?
    ''', (task_id, session['user_id'])).fetchone()
    
    # Get task history
    history = conn.execute('''
        SELECT * FROM task_history 
        WHERE task_id = ? AND user_id = ?
        ORDER BY created_at DESC
    ''', (task_id, session['user_id'])).fetchall()
    
    conn.close()
    
    if not task:
        return "Task not found"
    
    return render_template('task_details.html', 
                         task=task, 
                         history=history,
                         get_urgency_class=get_urgency_class)  # Add this line!

#TIMER
@app.route('/study_timer')
def study_timer():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    subjects = conn.execute(
        'SELECT * FROM subjects WHERE user_id = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    
    # Get recent study sessions for stats
    recent_sessions = conn.execute('''
        SELECT study_sessions.*, subjects.name as subject_name
        FROM study_sessions 
        LEFT JOIN subjects ON study_sessions.subject_id = subjects.id 
        WHERE study_sessions.user_id = ?
        ORDER BY study_sessions.created_at DESC
        LIMIT 10
    ''', (session['user_id'],)).fetchall()
    
    # Calculate weekly stats
    weekly_stats = conn.execute('''
        SELECT 
            SUM(duration_minutes) as total_minutes,
            COUNT(*) as session_count,
            strftime('%Y-%m-%d', created_at) as study_date
        FROM study_sessions 
        WHERE user_id = ? AND created_at >= date('now', '-7 days')
        GROUP BY study_date
        ORDER BY study_date DESC
    ''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('study_timer.html',
                         subjects=subjects,
                         recent_sessions=recent_sessions,
                         weekly_stats=weekly_stats)

@app.route('/save_study_session', methods=['POST'])
def save_study_session():
    if 'user_id' not in session:
        return redirect('/login')
    
    duration = request.form['duration']
    subject_id = request.form.get('subject_id')
    notes = request.form.get('notes', '')
    session_type = request.form.get('session_type', 'focus')
    
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO study_sessions (user_id, subject_id, duration_minutes, notes, session_type) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], subject_id if subject_id else None, duration, notes, session_type)
    )
    conn.commit()
    conn.close()
    
    return redirect('/study_timer')

@app.route('/study_stats')
def study_stats():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    
    # Overall stats
    total_stats = conn.execute('''
        SELECT 
            SUM(duration_minutes) as total_minutes,
            COUNT(*) as total_sessions,
            AVG(duration_minutes) as avg_duration
        FROM study_sessions 
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Subject breakdown
    subject_stats = conn.execute('''
        SELECT 
            subjects.name,
            SUM(study_sessions.duration_minutes) as total_minutes,
            COUNT(*) as session_count
        FROM study_sessions 
        LEFT JOIN subjects ON study_sessions.subject_id = subjects.id 
        WHERE study_sessions.user_id = ?
        GROUP BY subjects.name
        ORDER BY total_minutes DESC
    ''', (session['user_id'],)).fetchall()
    
    # Daily streak (consecutive days with study sessions)
    streak_data = conn.execute('''
        WITH dates AS (
            SELECT DISTINCT date(created_at) as study_date
            FROM study_sessions 
            WHERE user_id = ?
            ORDER BY study_date DESC
        ),
        streaks AS (
            SELECT 
                study_date,
                julianday(study_date) - julianday(LAG(study_date, 1, study_date) OVER (ORDER BY study_date)) as diff
            FROM dates
        )
        SELECT COUNT(*) as current_streak
        FROM streaks
        WHERE diff = 1
        ORDER BY study_date DESC
        LIMIT 1
    ''', (session['user_id'],)).fetchone()
    
    conn.close()
    
    return render_template('study_stats.html',
                         total_stats=total_stats,
                         subject_stats=subject_stats,
                         streak_data=streak_data)

#calendar
# calendar
@app.route('/calendar')
def calendar_view():
    if 'user_id' not in session:
        return redirect('/login')
    
    # Get month and year from URL parameters (default to current month)
    year = request.args.get('year', type=int, default=datetime.now().year)
    month = request.args.get('month', type=int, default=datetime.now().month)
    
    conn = get_db_connection()
    
    # Get tasks for the selected month
    tasks = conn.execute('''
        SELECT tasks.*, subjects.name as subject_name, subjects.color as subject_color 
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ? 
        AND strftime('%Y-%m', tasks.due_date) = ?
        ORDER BY tasks.due_date, tasks.priority
    ''', (session['user_id'], f"{year:04d}-{month:02d}")).fetchall()
    
    # Add calendar_color based on priority
    def get_priority_color(priority, is_overdue=False):
        if is_overdue:
            return '#ff0000'  # Red for overdue
        elif priority == 'high':
            return '#ff4444'  # Red
        elif priority == 'medium':
            return '#ffaa00'  # Orange
        elif priority == 'low':
            return '#44ff44'  # Green
        else:
            return '#666666'  # Default gray
    
    # Group tasks by date for the calendar and add color
    tasks_by_date = {}
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    for task in tasks:
        date_str = task['due_date']
        is_overdue = date_str < today_str
        
        # Add calendar_color to each task
        task_dict = dict(task)
        task_dict['calendar_color'] = get_priority_color(task['priority'], is_overdue)
        
        if date_str not in tasks_by_date:
            tasks_by_date[date_str] = []
        tasks_by_date[date_str].append(task_dict)
    
    # Calculate statistics
    total_tasks_this_month = len(tasks)
    days_with_tasks = len(tasks_by_date)
    
    # Calculate overdue tasks
    overdue_count = 0
    for date_str, date_tasks in tasks_by_date.items():
        if date_str < today_str:
            overdue_count += len(date_tasks)
    
    # Calculate calendar data
    import calendar
    cal = calendar.Calendar()
    month_days = cal.monthdayscalendar(year, month)
    
    # Get previous and next month for navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    # Calculate previous and next month names
    prev_month_name = datetime(prev_year, prev_month, 1).strftime('%B') if prev_month else ''
    next_month_name = datetime(next_year, next_month, 1).strftime('%B') if next_month else ''
    
    conn.close()
    
    return render_template('calendar.html',
                         year=year,
                         month=month,
                         month_name=datetime(year, month, 1).strftime('%B %Y'),
                         month_days=month_days,
                         tasks_by_date=tasks_by_date,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         prev_month_name=prev_month_name,
                         next_month_name=next_month_name,
                         total_tasks_this_month=total_tasks_this_month,
                         days_with_tasks=days_with_tasks,
                         overdue_count=overdue_count,
                         datetime=datetime,
                         get_urgency_class=get_urgency_class)

@app.route('/calendar/day/<date>')
def calendar_day_view(date):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    
    # Get tasks for the specific date
    tasks = conn.execute('''
        SELECT tasks.*, subjects.name as subject_name, subjects.color as subject_color 
        FROM tasks 
        LEFT JOIN subjects ON tasks.subject_id = subjects.id 
        WHERE tasks.user_id = ? AND tasks.due_date = ?
        ORDER BY tasks.priority, tasks.created_at
    ''', (session['user_id'], date)).fetchall()
    
    conn.close()
    
    return render_template('calendar_day.html', 
                         tasks=tasks, 
                         date=date,
                         datetime=datetime,  # Pass datetime to template
                         get_urgency_class=get_urgency_class)

@app.route('/update_task_date/<int:task_id>', methods=['POST'])
def update_task_date(task_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    new_date = request.form['new_date']
    
    conn = get_db_connection()
    conn.execute(
        'UPDATE tasks SET due_date = ? WHERE id = ? AND user_id = ?',
        (new_date, task_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    
    return redirect(request.referrer or '/calendar')

#chatbot
# Dialogflow chatbot routes
@app.route('/chatbot')
def chatbot():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('chatbot.html')

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
    
    user_message = request.json['message']
    
    try:
        # Get Dialogflow response
        bot_response = detect_intent_texts(
            "studenttaskbot-yoce",  # Your Project ID
            str(session['user_id']),  # Use user ID as session ID
            user_message,
            "en"
        )
        
        return jsonify({'response': bot_response})
        
    except Exception as e:
        print("Dialogflow error:", e)
        # Fallback response if Dialogflow fails
        return jsonify({'response': f"I'm having trouble connecting right now. Error: {str(e)}"})

def detect_intent_texts(project_id, session_id, text, language_code):
    """Returns the result of detect intent with texts as inputs."""
    
    # Path to your service account key file
    credentials_path = 'studenttaskbot-yoce-5d14b6c469b5.json'
    
    if not os.path.exists(credentials_path):
        return "Chatbot setup incomplete. Please configure Dialogflow credentials."
    
    credentials = service_account.Credentials.from_service_account_file(credentials_path)
    session_client = dialogflow.SessionsClient(credentials=credentials)
    
    session = session_client.session_path(project_id, session_id)
    text_input = dialogflow.TextInput(text=text, language_code=language_code)
    query_input = dialogflow.QueryInput(text=text_input)
    
    response = session_client.detect_intent(
        request={"session": session, "query_input": query_input}
    )
    
    return response.query_result.fulfillment_text

# Quick task routes
@app.route('/quick_task', methods=['POST'])
def quick_task():
    if 'user_id' not in session:
        return redirect('/login')
    
    title = request.form['title']
    due_days = int(request.form.get('due_days', 0))
    
    from datetime import datetime, timedelta
    due_date = (datetime.now() + timedelta(days=due_days)).strftime('%Y-%m-%d')
    
    if due_days == 0:
        priority = 'high'
    elif due_days <= 2:
        priority = 'medium'
    else:
        priority = 'low'
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO tasks (user_id, title, due_date, priority) VALUES (?, ?, ?, ?)',
        (session['user_id'], title, due_date, priority)
    )
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect('/dashboard')


# -------------------- QUICK COMPLETE --------------------
@app.route('/quick_complete/<int:task_id>')
def quick_complete(task_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        'UPDATE tasks SET completed = 1 WHERE id = ? AND user_id = ?',
        (task_id, session['user_id'])
    )
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect('/dashboard')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

# Error handlers - simplified
@app.errorhandler(404)
def not_found_error(error):
    return "Page not found", 404

@app.errorhandler(500)
def internal_error(error):
    return "Internal server error", 500

if __name__ == '__main__':
    app.run(debug=True)

if __name__ == '__main__':
    # For production, use environment variable for port
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)