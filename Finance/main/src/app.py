import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp
from datetime import datetime
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Ensure responses aren't cached
if app.config["DEBUG"]:

    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["PREFERRED_URL_SCHEME"] = "https"
app.config["DEBUG"] = False
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Get user's stocks and shares
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
        user_id=session["user_id"],
    )

    # Get user's cash balance
    cash = db.execute(
        "SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"]
    )[0]["cash"]

    # Initialize variables for total values
    total_value = cash
    grand_total = cash

    # Iterate over stocks and add price and total value
    for stock in stocks:
        quote = lookup(stock["symbol"])
        stock["name"] = quote["name"]
        stock["price"] = quote["price"]
        stock["value"] = stock["price"] * stock["total_shares"]
        total_value += stock["value"]
        grand_total += stock["value"]

    # Render the HTML template with data
    return render_template(
        "index.html",
        stocks=stocks,
        cash=cash,
        total_value=total_value,
        grand_total=grand_total,
    )


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        if not symbol or symbol == "":
            return apology("must provide symbol")

        if not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("must provide a positive integer number of shares")

        quote = lookup(symbol)
        if quote is None:
            return apology("symbol not found")

        price = quote["price"]
        total_cost = int(shares) * price
        cash = db.execute(
            "SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"]
        )[0]["cash"]

        if cash < total_cost:
            return apology("not enough money")

        # Update users table
        db.execute(
            "UPDATE users SET cash = cash - :total_cost WHERE id = :user_id",
            total_cost=total_cost,
            user_id=session["user_id"],
        )

        # Add the purchase to the history table
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
            user_id=session["user_id"],
            symbol=symbol,
            shares=shares,
            price=price,
        )

        formatted_total_cost = usd(total_cost)
        flash(f"Bought {shares} shares of {symbol} for {formatted_total_cost}!")
        return redirect("/")
    else:
        # Render the HTML template for buying stocks
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions."""
    # Query transaction history for the current user
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id = :user_id",
        user_id=session["user_id"],
    )

    # Render the HTML template with transaction history
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # Forget any user_id
    session.clear()

    # If the user reached the route via POST (by submitting a form)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")
        elif not request.form.get("password"):
            return apology("must provide password")

        username = request.form.get("username")
        password = request.form.get("password")

        # Check if the username exists in the database
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(user) != 1 or not check_password_hash(
            user[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = user[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # If the user reached the route via GET (by clicking a link or redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out."""

    # Forget any user_id
    session.clear()

    flash("Logged out successfully!")
    # Redirect user to login form
    return redirect(url_for("login"))


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        # Ensure input is not null
        if symbol == "":
            return apology("input is null", 400)

        if not lookup(symbol):
            return apology("invalid symbol", 400)
        else:
            quote = lookup(symbol)
            return render_template("quoted.html", symbol=quote)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    # Forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password and password confirmation were submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Ensure password and confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username does not already exist
        if len(rows) != 0:
            return apology("username already exists", 400)

        # Insert new user into database
        db.execute(
            "INSERT INTO users (username, hash) VALUES(?, ?)",
            request.form.get("username"),
            generate_password_hash(request.form.get("password")),
        )

        # Query database for newly inserted user
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        flash("Registered and logged in successfully!")
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        # Ensure stock symbol and number of shares were submitted
        stock_symbol = request.form.get("symbol")
        shares_to_sell = int(request.form.get("shares"))

        # Check if the symbol exists in the portfolio for the user
        portfolio = db.execute(
            "SELECT SUM(shares) AS total_shares FROM transactions WHERE user_id = :user_id AND symbol = :symbol GROUP BY symbol",
            user_id=session["user_id"],
            symbol=stock_symbol,
        )

        if not portfolio:
            return apology("You do not own any shares of this stock")

        total_shares = portfolio[0]["total_shares"]

        if shares_to_sell > total_shares:
            return apology("You may not sell more shares than you currently hold")

        # Get the current price of the stock
        quote = lookup(stock_symbol)

        if not quote:
            return apology("Stock symbol not valid, please try again")

        # Calculate the cost of the transaction
        cost = shares_to_sell * quote["price"]

        # Update the user's cash balance
        db.execute(
            "UPDATE users SET cash = cash + :cost WHERE id = :user_id",
            cost=cost,
            user_id=session["user_id"],
        )

        # Add the transaction to the history table
        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
            user_id=session["user_id"],
            symbol=stock_symbol,
            shares=-shares_to_sell,
            price=quote["price"],
        )

        flash(f"Sold {shares_to_sell} shares of {stock_symbol} for {usd(cost)}!")

        return redirect("/")
    else:
        # Pull all transactions belonging to the user
        owned_symbols = db.execute(
            "SELECT DISTINCT symbol FROM transactions WHERE user_id = :user_id",
            user_id=session["user_id"],
        )

        # Pass the owned_symbols to the template
        return render_template("sell.html", symbols=owned_symbols)
