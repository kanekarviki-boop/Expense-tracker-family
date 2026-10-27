from flask import Flask, request, redirect, render_template, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)

DB_PATH = BASE_DIR / "expense_tracker.db"


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db():
    with get_db() as db:
        # Users table
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """)

        # Transactions table
        db.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT
        )
        """)
        
        # Budgets table
        db.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """)
        db.commit()


@app.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    with get_db() as db:
        user_id = session['user_id']
        transactions = db.execute("""
            SELECT * FROM transactions WHERE user_id = ?
            ORDER BY date DESC, id DESC
        """, (user_id,)).fetchall()

        income = db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions WHERE user_id = ? AND type = 'income'
        """, (user_id,)).fetchone()[0]

        expenses = db.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions WHERE user_id = ? AND type = 'expense'
        """, (user_id,)).fetchone()[0]

    return render_template(
        "index.html",
        transactions=transactions,
        income=income,
        expenses=expenses,
        balance=income - expenses
    )


@app.route("/add", methods=["POST"])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    category = request.form.get("category", "").strip()
    t_type = request.form.get("type", "")
    date = request.form.get("date", "")
    description = request.form.get("description", "")

    try:
        amount = float(request.form.get("amount", ""))
        if not 0 < amount < 1_000_000_000:
            raise ValueError
    except (ValueError, TypeError):
        return "Enter a valid positive amount.", 400

    if not category or not date:
        return "Please complete all fields.", 400

    if t_type not in ("income", "expense"):
        return "Invalid transaction type.", 400

    with get_db() as db:
        db.execute("""
            INSERT INTO transactions
            (user_id, type, category, amount, date, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session['user_id'], t_type, category, amount, date, description))

    return redirect("/")


@app.route("/delete/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    with get_db() as db:
        db.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (transaction_id, session['user_id'])
        )
    return redirect("/")


@app.route('/api/health') 
def health():
    return {"database": "expense_tracker_family", "status": "ok"}


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()
        except sqlite3.IntegrityError:
            return "Username pehle se hi maujood hai!"
        
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('index'))
        else:
            return "Galat username ya password!"
            
    return render_template('login.html')


@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    if request.method == 'POST':
        user_id = session['user_id']
        t_type = request.form['type']
        category = request.form['category']
        amount = request.form['amount']
        date = request.form['date']
        description = request.form['description']
        
        db.execute(
            'INSERT INTO transactions (user_id, type, category, amount, date, description) VALUES (?, ?, ?, ?, ?, ?)',
            (user_id, t_type, category, amount, date, description)
        )
        db.commit()
        db.close()
        return redirect(url_for('transactions'))
        
    user_id = session['user_id']
    transactions_list = db.execute(
        'SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC',
        (user_id,)
    ).fetchall()
    db.close()
    
    return render_template('transactions.html', transactions=transactions_list)


if __name__ == '__main__':
    initialize_db()
    app.run(debug=True)