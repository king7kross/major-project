from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import requests
import re
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MySQL configurations
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'book_db'

mysql = MySQL(app)

# Helper function to check if user is logged in
def is_logged_in():
    return 'user' in session

@app.route('/')
@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/package')
def package():
    return render_template('package.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('home'))
    errors = []
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors.append("Valid email is required.")
        if not password:
            errors.append("Password is required.")
        if not errors:
            cur = mysql.connection.cursor()
            cur.execute("SELECT username, email, password FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            cur.close()
            if user and check_password_hash(user[2], password):
                session['user'] = {'username': user[0], 'email': user[1]}
                return redirect(url_for('home'))
            else:
                errors.append("Invalid email or password.")
    return render_template('login.html', errors=errors)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if is_logged_in():
        flash('You are already logged in.', 'info')
        return redirect(url_for('home'))
    errors = []
    success = ''
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not username:
            errors.append("Username is required.")
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            errors.append("Valid email is required.")
        if not password:
            errors.append("Password is required.")
        if password != confirm_password:
            errors.append("Passwords do not match.")
        if not errors:
            cur = mysql.connection.cursor()
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                errors.append("Email is already registered.")
            else:
                hashed_password = generate_password_hash(password)
                cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                            (username, email, hashed_password))
                mysql.connection.commit()
                success = "Registration successful. You can now login."
            cur.close()
    return render_template('register.html', errors=errors, success=success)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/book', methods=['GET', 'POST'])
def book():
    if not is_logged_in():
        return redirect(url_for('login'))
    if request.method == 'POST':
        # Validate form data
        required_fields = ['name', 'email', 'phone', 'address', 'location', 'guests', 'arrivals', 'departure']
        for field in required_fields:
            if not request.form.get(field):
                flash('All details are mandatory.', 'error')
                return redirect(url_for('book'))
        # Store booking details in session
        session['booking_details'] = {
            'name': request.form['name'],
            'email': session['user']['email'],
            'phone': request.form['phone'],
            'address': request.form['address'],
            'location': request.form['location'],
            'guests': request.form['guests'],
            'arrivals': request.form['arrivals'],
            'departure': request.form['departure']
        }
        return redirect(url_for('checkout'))
    return render_template('book.html')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not is_logged_in():
        return redirect(url_for('login'))
    booking = session.get('booking_details')
    if not booking:
        flash('No booking details found.', 'error')
        return redirect(url_for('book'))
    price = int(booking.get('guests', 0)) * 10000
    if request.method == 'POST':
        if 'remove_booking' in request.form:
            session.pop('booking_details', None)
            return redirect(url_for('home'))
        elif 'proceed_payment' in request.form:
            return redirect(url_for('payment_gateway'))
    return render_template('checkout.html', booking=booking, price=price)

@app.route('/payment_gateway', methods=['GET', 'POST'])
def payment_gateway():
    if not is_logged_in():
        return redirect(url_for('login'))
    errors = []
    if request.method == 'POST':
        card_number = request.form.get('card_number', '').strip()
        expiry = request.form.get('expiry', '').strip()
        cvv = request.form.get('cvv', '').strip()
        name_on_card = request.form.get('name_on_card', '').strip()
        if not re.fullmatch(r'\d{16}', card_number):
            errors.append("Please enter a valid 16-digit card number.")
        if not re.fullmatch(r'(0[1-9]|1[0-2])\/\d{2}', expiry):
            errors.append("Please enter a valid expiry date in MM/YY format.")
        if not re.fullmatch(r'\d{3}', cvv):
            errors.append("Please enter a valid 3-digit CVV.")
        if not name_on_card:
            errors.append("Please enter the name on the card.")
        if not errors:
            booking_details = session.get('booking_details')
            if not booking_details:
                errors.append("No booking details found in session.")
            else:
                cur = mysql.connection.cursor()
                try:
                    cur.execute(
                        "INSERT INTO book_form (name, email, phone, address, location, guests, arrivals, departure) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (booking_details['name'], booking_details['email'], booking_details['phone'], booking_details['address'],
                         booking_details['location'], booking_details['guests'], booking_details['arrivals'], booking_details['departure'])
                    )
                    mysql.connection.commit()
                    booking_id = cur.lastrowid
                    booking_code = f"{os.urandom(4).hex()[:8]}"
                    price = int(booking_details.get('guests', 0)) * 10000
                    cur.execute(
                        "INSERT INTO payments (booking_id, card_number, name_on_card, price) VALUES (%s, %s, %s, %s)",
                        (booking_code, card_number, name_on_card, price)
                    )
                    mysql.connection.commit()
                    session['booking_id'] = booking_id
                    session['booking_code'] = booking_code
                    session.pop('booking_details', None)
                    return redirect(url_for('payment'))
                except Exception as e:
                    mysql.connection.rollback()
                    errors.append("Failed to process payment. Please try again.")
                finally:
                    cur.close()
    return render_template('payment_gateway.html', errors=errors)

@app.route('/payment')
def payment_page():
    if not is_logged_in():
        return redirect(url_for('login'))
    booking_id = session.get('booking_id')
    booking_code = session.get('booking_code')
    if not booking_id or not booking_code:
        flash('Booking information could not be retrieved. Please try again.', 'error')
        return render_template('payment.html', booking=None, payment=None, booking_code=None)
    import MySQLdb.cursors
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    payment = None
    booking = None
    try:
        cur.execute("SELECT * FROM payments WHERE booking_id = %s", (booking_code,))
        payment = cur.fetchone()
        cur.execute("SELECT * FROM book_form WHERE id = %s", (booking_id,))
        booking = cur.fetchone()
    finally:
        cur.close()
    return render_template('payment.html', booking=booking, payment=payment, booking_code=booking_code)

@app.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.get_json()
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'reply': 'Empty message received'})
    if len(user_message) > 1000:
        return jsonify({'reply': 'Message too long. Please shorten your input.'})
    request_body = {
        'contents': [
            {
                'parts': [
                    {'text': user_message}
                ]
            }
        ]
    }
    try:
        response = requests.post(api_url, json=request_body, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        candidates = response_data.get('candidates', [])
        if candidates:
            content = candidates[0].get('message', {}).get('content') or candidates[0].get('content')
            if isinstance(content, dict):
                parts = content.get('parts', [])
                if parts:
                    bot_reply = parts[0].get('text', '')
                else:
                    bot_reply = str(content)
            else:
                bot_reply = content or 'Sorry, no response.'
            return jsonify({'reply': bot_reply})
        else:
            return jsonify({'reply': 'Invalid response from Gemini API.'})
    except Exception:
        return jsonify({'reply': 'An internal error occurred. Please try again later.'})

@app.route('/payment')
def payment():
    if not is_logged_in():
        return redirect(url_for('login'))
    booking_id = session.get('booking_id')
    booking_code = session.get('booking_code')
    if not booking_id or not booking_code:
        flash('Booking information could not be retrieved. Please try again.', 'error')
        return render_template('payment.html', booking=None, payment=None, booking_code=None)
    cur = mysql.connection.cursor()
    payment = None
    booking = None
    try:
        cur.execute("SELECT * FROM payments WHERE booking_id = %s", (booking_code,))
        payment = cur.fetchone()
        cur.execute("SELECT * FROM book_form WHERE id = %s", (booking_id,))
        booking = cur.fetchone()
    finally:
        cur.close()
    return render_template('payment.html', booking=booking, payment=payment, booking_code=booking_code)

if __name__ == '__main__':
    app.run(debug=True)
