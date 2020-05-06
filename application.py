import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    tradings = db.execute("SELECT symbol, SUM(shares) AS total FROM tradings WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])
    quotes = {}
    for trading in tradings:
        quotes[trading["symbol"]] = lookup(trading["symbol"])
    users = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    cash = users[0]["cash"]
    value = 0
    for trading in tradings:
        value = value + trading["total"] * quotes[trading["symbol"]]["price"]
    return render_template("index.html", tradings=tradings, quotes=quotes, cash=cash, value=value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("must provide symbol", 403)
        quote = lookup(symbol)
        if quote == None:
            return apology("invalid stock symbol", 403)
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("input is not a positive integer", 403)
        if not shares:
            return apology("must provide shares", 403)
        if shares <= 0:
            return apology("input is not a positive integer", 403)
        price = quote["price"]
        rows = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = rows[0]["cash"]
        total = price * shares
        if total > cash:
            return apology("cannot afford the number of shares at the current price", 403)
        db.execute("UPDATE users SET cash = cash - :total WHERE id = :user_id", total=total, user_id=session["user_id"])
#        CREATE TABLE tradings (trading_id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, user_id INTEGER NOT NULL, symbol TEXT NOT NULL, shares INTEGER NOT NULL, price NUMERIC NOT NULL, timestamp datetime default current_timestamp, FOREIGN KEY(user_id) REFERENCES users(id))
        db.execute("INSERT INTO tradings (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=symbol,
                   shares=shares,
                   price=price)
        return redirect("/")


@app.route("/history")
@login_required
def history():
    tradings = db.execute("SELECT symbol, shares, price, timestamp FROM tradings WHERE user_id = :user_id ORDER BY timestamp ASC", user_id=session["user_id"])
    return render_template("history.html", tradings=tradings)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")
    else:
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if quote == None:
            return apology("invalid stock symbol", 403)
        return render_template("quoted.html", quote=quote)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")
        if not username:
            return apology("must provide username", 403)
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows) == 1:
            return apology("username already exists", 403)
        password = request.form.get("password")
        if not password:
            return apology("must provide password", 403)
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("must provide confirmation", 403)
        if password != confirmation:
            return apology("passwords do not match", 403)
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        rows = db.execute("SELECT symbol, SUM(shares) AS total FROM tradings WHERE user_id = :user_id GROUP BY symbol", user_id=session["user_id"])
        return render_template("sell.html", rows=rows)
    else:
        symbol = request.form.get("symbol")
        row = db.execute("SELECT SUM(shares) AS total FROM tradings WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol", user_id=session["user_id"], symbol=symbol)
#        check symbol
        if not symbol:
            return apology("must provide symbol", 403)
        if row[0]["total"] == 0:
            return apology("does not own any shares of that stock", 403)
#        check shares
        shares = request.form.get("shares")
        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("input is not a positive integer", 403)
        if not shares:
            return apology("must provide shares", 403)
        if shares <= 0:
            return apology("input is not a positive integer", 403)
        if shares > row[0]["total"]:
            return apology("does not own that many shares of the stock", 403)
        quote = lookup(symbol)
        price = quote["price"]
        user = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
        cash = user[0]["cash"]
        earnings = price * shares
        db.execute("UPDATE users SET cash = cash + :earnings WHERE id = :user_id", user_id=session["user_id"], earnings=earnings)
        db.execute("INSERT INTO tradings (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=symbol,
                   shares=-shares,
                   price=price)
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
