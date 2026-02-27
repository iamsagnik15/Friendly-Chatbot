from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from groq import Groq
import os

# ================= APP CONFIG ================= #

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_secret")

database_url = os.environ.get("DATABASE_URL")

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///database.db"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ================= DATABASE MODELS ================= #

class User(UserMixin, db.Model):
    __tablename__ = "users"   # avoid reserved word "user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Chat(db.Model):
    __tablename__ = "chats"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)

# ✅ IMPORTANT: CREATE TABLES AFTER MODELS
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= GROQ CONFIG ================= #

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are a friendly AI assistant for college students.
Be supportive, slightly funny, and explain clearly.
Keep answers short and helpful.
"""

# ================= ROUTES ================= #

@app.route("/")
def home():
    return redirect(url_for("login"))

# -------- REGISTER -------- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if User.query.filter_by(username=username).first():
            flash("Username already exists!")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")

# -------- LOGIN -------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("chat"))
        else:
            flash("Invalid credentials")

    return render_template("login.html")

# -------- CHAT PAGE -------- #

@app.route("/chat")
@login_required
def chat():
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.id.asc()).all()
    return render_template("chat.html", chats=chats, username=current_user.username)

# -------- ASK AI (GROQ) -------- #

@app.route("/ask", methods=["POST"])
@login_required
def ask():
    user_message = request.json.get("message")

    try:
        completion = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=200
        )

        reply = completion.choices[0].message.content

        new_chat = Chat(
            user_id=current_user.id,
            message=user_message,
            response=reply
        )

        db.session.add(new_chat)
        db.session.commit()

        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"reply": f"Groq Error: {str(e)}"})

# -------- DELETE SINGLE CHAT -------- #

@app.route("/delete_chat/<int:chat_id>")
@login_required
def delete_chat(chat_id):
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()

    if chat:
        db.session.delete(chat)
        db.session.commit()

    return redirect(url_for("chat"))

# -------- DELETE ALL CHATS -------- #

@app.route("/delete_all")
@login_required
def delete_all():
    Chat.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return redirect(url_for("chat"))

# -------- LOGOUT -------- #

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -------- FORGOT PASSWORD -------- #

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username")
        new_password = request.form.get("password")

        user = User.query.filter_by(username=username).first()

        if user:
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash("Password updated successfully.")
            return redirect(url_for("login"))
        else:
            flash("User not found.")

    return render_template("forgot_password.html")