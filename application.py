import os
import re
import requests

from flask import Flask, session, render_template, url_for, redirect, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from functools import wraps
from passlib.apps import custom_app_context as pwd_context

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/0.11/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
	if request.method == "POST":

		# search function
		# get the word the user has typed in
		search_term = request.form.get('search').lower()

		if not search_term:
			return render_template('index.html')

		# get all the books that match the search term from the database
		result = db.execute("SELECT * FROM books WHERE lower(title) LIKE '%"+search_term+"%' OR lower(author) LIKE '%"+search_term+"%' OR isbn LIKE '%"+search_term+"%'").fetchall()

		if result is None:
			return 'No books found for this search'
		
		return render_template('index.html', books=result)
	else:
		return render_template('index.html')

@app.route("/books/<int:book_id>")
@login_required
def book(book_id):
	""" Lists details about the selected book """

	# Make sure book exists
	book = db.execute('SELECT * FROM books WHERE id=:id', {'id':book_id}).fetchone()
	if book is None:
		return "No such book exists"

	reviews = db.execute('SELECT * FROM reviews WHERE book_id=:book_id', {'book_id': book_id}).fetchall()

	api_key = 'ijPpfHxJx8huayP3JgCM9Q'

	# make request using Goodreads API
	res = requests.get('https://www.goodreads.com/book/review_counts.json', params={'key':api_key, 'isbns':book.isbn})
	data = res.json()
	# get the average reating from Goodreads
	avg_rat = data['books'][0]['average_rating']
	# get the number of ratings from Goodreads
	num_rat = data['books'][0]['work_ratings_count']

	return render_template('book.html', book=book, reviews=reviews, avg_rat=avg_rat, num_rat=num_rat)

@app.route("/review/<int:book_id>", methods=['POST'])
@login_required
def review(book_id):
	""" Add review to the database and display it on book's page"""

	# check if the user has already posted a review for this specific book
	reviewed = db.execute('SELECT * FROM reviews WHERE user_id=:user_id AND book_id=:book_id', {'user_id': session['user_id'], 'book_id': book_id}).fetchall()
	if reviewed:
		return 'You cannot post multiple reviews for the same book'

	# get rating
	rating = request.form.get('rating')
	if not rating:
		return 'You must provide a rating'

	# get review
	review = request.form.get('review')
	if not review:
		return 'You must provide a review'

	# add review to the database
	db.execute('INSERT INTO reviews (rating, review_text, user_id, book_id) VALUES (:rating, :review_text, :user_id, :book_id)',
	{'rating': rating, 'review_text': review, 'user_id': session['user_id'], 'book_id': book_id})
	db.commit()

	return redirect(url_for('book', book_id=book_id))


@app.route("/login", methods=["GET", "POST"])
def login():
	"""Log user in """

	# forget any user_id
	session.clear()

	# if user reached this route via POST
	if request.method == "POST":

		# ensure username was submitted
		if not request.form.get('username'):
			return 'You must provide a username'
		# ensure password was submitted
		elif not request.form.get('password'):
			return 'You must type in your password'

		# query database for this user's data
		user = db.execute("SELECT * FROM users WHERE username=:username", {'username':request.form.get('username')}).fetchall()

		if len(user) != 1 or not pwd_context.verify(request.form.get('password'), user[0]['hash']):
			return 'Invalid username and/or password'

		# remember which user has logged in
		session['user_id'] = user[0]['id']

		#redirect user to home page
		return redirect(url_for('index'))
	# if user reached this route via GET
	else:
		return render_template("login.html")

@app.route('/register', methods=['GET','POST'])
def register():
	""" Register new user """

	# if user reached this route via POST
	if request.method == 'POST':

		# ensure username was submitted
		if not request.form.get('username'):
			return 'You must provide a username'
		# ensure password was submitted
		elif not request.form.get('password'):
			return 'You must type in your password'
		elif not request.form.get('password_conf'):
			return 'You must confirm the password you have typed'

		pass_sub = request.form.get('password')
		pass_conf = request.form.get('password_conf')

		if not pass_sub == pass_conf:
			return 'The passwords do not match!'
		else:
			# Securely store the inserted password
			hash = pwd_context.encrypt(pass_sub)

		# insert user in the database (users table)
		insert = db.execute("INSERT INTO users (username,hash) VALUES (:username, :hash)", {'username':request.form.get('username'), 'hash':hash})
		db.commit()
		# if the username already exists in the database return a message
		if not insert:
			return 'This username already exists'
	
		return redirect(url_for('login'))
	else:
		return render_template("register.html")

@app.route('/logout')
def logout():
	""" Log user out """

	# forget any user_id
	session.clear()

	# redirect user to login form
	return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():

	# if user reached this route via POST
	if request.method == 'POST':

		old_pass = request.form.get('old_pass')
		new_pass = request.form.get('new_pass')
		new_pass_conf = request.form.get('new_pass_conf')

		# ensure username was submitted
		if not old_pass:
			return 'You must provide your old password'
		# ensure password was submitted
		elif not new_pass:
			return 'You must type in your new password'
		elif not new_pass_conf:
			return 'You must confirm the new password you have typed'

		print("about to confirm that the old password is correct")
		# confirm that the old password provided is correct
		user = db.execute('SELECT hash FROM users WHERE id=:id', {'id': session['user_id']}).first()
		print(user)
		if not pwd_context.verify(old_pass, user[0]):
			print('The old password is not correct')
			return 'The old password is not correct'
		elif not new_pass == new_pass_conf:
			print("The new passwords do not match")
			return 'The new passwords do not match'

		print("new pass hashed: " + pwd_context.encrypt(new_pass))
		print('about to update the database')
		print(session['user_id'])
		db.execute('UPDATE users SET hash=:hash WHERE id=:id', {'hash': pwd_context.encrypt(new_pass), 'id': session['user_id']})
		db.commit()
		print('database updated!')
		return redirect(url_for('index'))
	else:
		return render_template('change_password.html')

@app.route('/api/<string:isbn>')
def book_api(isbn):
	""" Return details about a single book """

	# make sure book exists
	book = db.execute('SELECT * FROM books WHERE isbn=:isbn', {'isbn': isbn}).fetchone()
	if book is None:
		return jsonify({'error': 'Invalid ISBN number'}), 404

	# get needed data from Goodreads
	api_key = 'ijPpfHxJx8huayP3JgCM9Q'

	res = requests.get('https://www.goodreads.com/book/review_counts.json', params={'key':api_key, 'isbns':isbn})
	data = res.json()
	# get the average reating from Goodreads
	avg_rat = data['books'][0]['average_rating']
	# get the number of ratings from Goodreads
	rev_count = data['books'][0]['reviews_count']

	# API response
	return jsonify({
			'title': book.title,
			'author': book.author,
			'year': book['publication_year'],
			'isbn': book.isbn,
			'review_count': rev_count,
			'average_score': avg_rat
		})