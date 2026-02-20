from flask import Flask, render_template, request, redirect, session
import psycopg
import os
from datetime import datetime
import PyPDF2
import re
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE_URL = os.environ.get("DATABASE_URL")

# ---------------- DATABASE CONNECTION ---------------- #
def connect_db():
    return psycopg.connect(DATABASE_URL)
def init_db():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT,
        password TEXT,
        role TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id SERIAL PRIMARY KEY,
        question TEXT,
        option1 TEXT,
        option2 TEXT,
        option3 TEXT,
        option4 TEXT,
        correct_answer TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS results(
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        score INTEGER,
        date TIMESTAMP
    )
    """)

    # Create default admin
    cursor.execute("SELECT * FROM users WHERE role='admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (name,email,password,role) VALUES (%s,%s,%s,%s)",
            ("Admin","admin@gmail.com","admin123","admin")
        )

    conn.commit()
    conn.close()

init_db()

# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/register", methods=["POST"])
def register():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO users (name,email,password,role) VALUES (%s,%s,%s,%s)",
        (request.form["name"], request.form["email"], request.form["password"], "student")
    )

    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/login", methods=["POST"])
def login():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (request.form["email"], request.form["password"])
    )

    user = cursor.fetchone()
    conn.close()

    if user:
        session["user_id"] = user[0]
        session["role"] = user[4]

        if user[4] == "admin":
            return redirect("/admin")
        return redirect("/dashboard")

    return "Invalid Login"

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/quiz")
def quiz():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions")
    questions = cursor.fetchall()

    conn.close()
    return render_template("quiz.html", questions=questions)

@app.route("/submit", methods=["POST"])
def submit():
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions")
    questions = cursor.fetchall()

    score = 0
    answer_sheet = []

    for q in questions:
        qid = str(q[0])
        user_answer = request.form.get(qid)
        correct_answer = q[6]

        if user_answer == correct_answer:
            score += 1

        answer_sheet.append({
            "question": q[1],
            "option1": q[2],
            "option2": q[3],
            "option3": q[4],
            "option4": q[5],
            "user_answer": user_answer,
            "correct_answer": correct_answer
        })

    cursor.execute(
        "INSERT INTO results (user_id,score,date) VALUES (%s,%s,%s)",
        (session["user_id"], score, datetime.now())
    )

    conn.commit()
    conn.close()

    return render_template("result.html", score=score, answers=answer_sheet)

@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT users.name, users.email, results.score, results.date
        FROM results
        JOIN users ON results.user_id = users.id
    """)

    data = cursor.fetchall()
    conn.close()

    return render_template("admin.html", results=data)

# ---------------- PDF UPLOAD ---------------- #

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if session.get("role") != "admin":
        return "Access Denied"

    if request.method == "POST":
        file = request.files["pdf"]

        if file:
            os.makedirs("uploads", exist_ok=True)
            filepath = os.path.join("uploads", secure_filename(file.filename))
            file.save(filepath)

            insert_questions_from_pdf(filepath)

            return "PDF Uploaded Successfully ✅ <br><a href='/admin'>Back</a>"

    return render_template("upload.html")

def insert_questions_from_pdf(pdf_path):
    conn = connect_db()
    cursor = conn.cursor()

    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()

    pattern = r"\d+\.\s(.*?)\nA\.\s(.*?)\nB\.\s(.*?)\nC\.\s(.*?)\nD\.\s(.*?)\nAnswer:\s([A-D])"
    matches = re.findall(pattern, text)

    for match in matches:
        question, o1, o2, o3, o4, answer = match
        cursor.execute("""
            INSERT INTO questions (question, option1, option2, option3, option4, correct_answer)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (question, o1, o2, o3, o4, answer))

    conn.commit()
    conn.close()

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)



