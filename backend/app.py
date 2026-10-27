import os
from flask import Flask, request, redirect, render_template, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(__name__,
            template_folder=str(BASE_DIR / "templates"),
            static_folder=str(BASE_DIR / "backend" / "static"))
app.secret_key = os.environ.get('SECRET_KEY', 'kuch_bhi_secret_key_likh_do')


DB_PATH = BASE_DIR / "expense_tracker.db"


def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                transaction_type TEXT NOT NULL
                    CHECK(transaction_type IN ('income', 'expense', 'Income', 'Expense')),
                transaction_date TEXT NOT NULL,
                description TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                relation TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)


# Make sure tables exist even when started via `flask run` / gunicorn
initialize_db()


def parse_amount(raw):
    """Return a valid positive amount or None."""
    try:
        amount = float(raw)
    except (ValueError, TypeError):
        return None
    if not 0 < amount < 1_000_000_000:
        return None
    return amount


@app.route('/')
@app.route('/index')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    user_id = session['user_id']

    transactions = conn.execute(
        "SELECT * FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, id DESC",
        (user_id,)
    ).fetchall()

    total_income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND LOWER(transaction_type) = 'income'",
        (user_id,)
    ).fetchone()[0]

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND LOWER(transaction_type) = 'expense'",
        (user_id,)
    ).fetchone()[0]

    conn.close()
    return render_template(
        'index.html',
        transactions=transactions,
        income=total_income,
        expenses=total_expenses,
        balance=total_income - total_expenses
    )


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    user_id = session['user_id']

    total_income = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND LOWER(transaction_type) = 'income'",
        (user_id,)
    ).fetchone()[0]

    total_expenses = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND LOWER(transaction_type) = 'expense'",
        (user_id,)
    ).fetchone()[0]

    balance = total_income - total_expenses
    savings = max(0, balance)

    # Group categories ignoring case and extra spaces ("Food", "food " -> one row)
    category_totals = conn.execute(
        """
        SELECT MIN(TRIM(category)) AS category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND LOWER(transaction_type) = 'expense'
        GROUP BY LOWER(TRIM(category))
        ORDER BY total DESC
        """,
        (user_id,)
    ).fetchall()

    conn.close()

    return render_template(
        'dashboard.html',
        income=total_income,
        expenses=total_expenses,
        balance=balance,
        savings=savings,
        categories=category_totals
    )


@app.route("/add", methods=["POST"])
def add_transaction():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    category = request.form.get("category", "").strip()
    transaction_type = request.form.get("type", "").lower()
    transaction_date = request.form.get("date", "") or request.form.get("transaction_date", "")
    description = request.form.get("description", "").strip()

    amount = parse_amount(request.form.get("amount", ""))
    if amount is None:
        return "Enter a valid positive amount.", 400

    if not category or not transaction_date:
        return "Please complete all fields.", 400

    if transaction_type not in ("income", "expense"):
        return "Invalid transaction type.", 400

    with get_db() as db:
        db.execute("""
            INSERT INTO transactions
            (user_id, transaction_date, transaction_type, category, amount, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session['user_id'], transaction_date, transaction_type, category, amount, description))

    return redirect(url_for('transactions'))


@app.route('/api/health')
def health():
    return {"database": "expense_tracker_family", "status": "ok"}


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        if not username or len(password) < 6:
            return "Username is required and password must be at least 6 characters.", 400

        hashed_password = generate_password_hash(password)
        db = get_db()

        try:
            db.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )
            db.commit()
        except sqlite3.IntegrityError:
            return "Username already exists!", 400
        finally:
            db.close()

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        db.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return "Galat username ya password!", 401

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        transaction_type = request.form.get('type', '').lower()
        category = request.form.get('category', '').strip()
        transaction_date = request.form.get('transaction_date', '')
        description = request.form.get('description', '').strip()
        amount = parse_amount(request.form.get('amount', ''))

        if amount is None:
            return "Enter a valid positive amount.", 400
        if not category or not transaction_date:
            return "Please complete all fields.", 400
        if transaction_type not in ("income", "expense"):
            return "Invalid transaction type.", 400

        with get_db() as db:
            db.execute(
                'INSERT INTO transactions (user_id, transaction_type, category, amount, transaction_date, description) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, transaction_type, category, amount, transaction_date, description)
            )
        return redirect(url_for('transactions'))

    db = get_db()
    transactions_list = db.execute(
        'SELECT * FROM transactions WHERE user_id = ? ORDER BY transaction_date DESC, id DESC',
        (user_id,)
    ).fetchall()
    db.close()

    return render_template('transactions.html', transactions=transactions_list)


@app.route("/delete/<int:id>", methods=["POST"])
def delete_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with get_db() as db:
        db.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (id, session['user_id']))
    return redirect(url_for('transactions'))


@app.route("/update/<int:id>", methods=["GET", "POST"])
def update_transaction(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        transaction_type = request.form.get("type", "").lower()
        transaction_date = request.form.get("transaction_date", "")
        description = request.form.get("description", "").strip()
        amount = parse_amount(request.form.get("amount", ""))

        if amount is None:
            return "Enter a valid positive amount.", 400
        if not category or not transaction_date:
            return "Please complete all fields.", 400
        if transaction_type not in ("income", "expense"):
            return "Invalid transaction type.", 400

        with get_db() as db:
            db.execute("""
                UPDATE transactions
                SET transaction_type = ?, category = ?, amount = ?, transaction_date = ?, description = ?
                WHERE id = ? AND user_id = ?
            """, (transaction_type, category, amount, transaction_date, description, id, user_id))

        return redirect(url_for('transactions'))

    db = get_db()
    transaction = db.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (id, user_id)
    ).fetchone()
    db.close()

    if transaction is None:
        return "Transaction not found.", 404

    return render_template("update.html", transaction=transaction)


@app.route('/family', methods=['GET', 'POST'])
def manage_family():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        name = request.form['name'].strip()
        relation = request.form['relation'].strip()

        if not name or not relation:
            conn.close()
            return "Name and relation are required.", 400

        conn.execute('INSERT INTO family_members (user_id, name, relation) VALUES (?, ?, ?)',
                     (user_id, name, relation))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_family'))

    family = conn.execute('SELECT * FROM family_members WHERE user_id = ?', (user_id,)).fetchall()
    conn.close()
    return render_template('family.html', family=family)


@app.route('/family/delete/<int:id>', methods=['POST'])
def delete_family_member(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    conn.execute('DELETE FROM family_members WHERE id = ? AND user_id = ?', (id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('manage_family'))


@app.route('/budgets', methods=['GET', 'POST'])
def budgets():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user_id = session['user_id']

    if request.method == 'POST':
        category = request.form['category'].strip()
        amount = parse_amount(request.form.get('amount', ''))

        if amount is None or not category:
            db.close()
            return "Enter a valid category and positive amount.", 400

        # Match existing budget ignoring case, so "Food" and "food" are one budget
        existing = db.execute(
            'SELECT id FROM budgets WHERE user_id = ? AND LOWER(TRIM(category)) = LOWER(?)',
            (user_id, category)
        ).fetchone()
        if existing:
            db.execute('UPDATE budgets SET amount = ? WHERE id = ?', (amount, existing['id']))
        else:
            db.execute('INSERT INTO budgets (user_id, category, amount) VALUES (?, ?, ?)',
                       (user_id, category, amount))
        db.commit()
        db.close()
        return redirect(url_for('budgets'))

    budgets_list = db.execute('SELECT * FROM budgets WHERE user_id = ?', (user_id,)).fetchall()

    # Keys are lowercased/trimmed; budgets.html looks them up with |trim|lower
    expenses_data = db.execute('''
        SELECT LOWER(TRIM(category)) AS category, SUM(amount) AS total
        FROM transactions
        WHERE user_id = ? AND LOWER(transaction_type) = 'expense'
        GROUP BY LOWER(TRIM(category))
    ''', (user_id,)).fetchall()

    expense_dict = {row['category']: row['total'] for row in expenses_data}
    db.close()

    return render_template('budgets.html', budgets=budgets_list, expense_dict=expense_dict)


if __name__ == '__main__':
    app.run(debug=True)