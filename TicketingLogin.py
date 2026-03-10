from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from datetime import datetime
from flask_mail import Mail, Message
from flask import jsonify
from datetime import date

app = Flask(__name__)
app.secret_key = "secretkey"

# ==============================
# MySQL Configuration
# ==============================
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'ticketing_system'
mysql = MySQL(app)

# ==============================
# LOGIN PAGE
# ==============================
@app.route('/')
def login_page():
    return render_template("login.html")

# ==============================
# REGISTER PAGE
# ==============================
@app.route('/register_page')
def register_page():
    return render_template("register.html")

# ==============================
# LOGIN FUNCTION (PLAIN TEXT PASSWORD)
# ==============================
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT id, username, email, department, password, role FROM users WHERE username=%s",
        (username,)
    )
    user = cur.fetchone()
    cur.close()

    # Plain text password comparison
    if user and user[4] == password:
        session['loggedin'] = True
        session['id'] = user[0]
        session['username'] = user[1]
        session['department'] = user[3]
        session['email'] = user[2]

        flash("Login Successful!", "success")

        if user[5].lower() == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    else:
        flash("Invalid Username or Password", "danger")
        return redirect(url_for('login_page'))

# ==============================
# ADMIN DASHBOARD
# ==============================
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'loggedin' in session and session['username'].lower() == 'admin':
        cur = mysql.connection.cursor()

        # Total users
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]

        # Total departments
        cur.execute("SELECT COUNT(DISTINCT department) FROM tickets")
        total_departments = cur.fetchone()[0]

        # ── All tickets ──
        cur.execute("""
            SELECT t.id, u.username, t.department, t.subject, t.description, t.status, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            ORDER BY t.created_at DESC
        """)
        all_tickets = cur.fetchall()

        # ── Open tickets today (for stats / notification) ──
        today = date.today()
        cur.execute("""
            SELECT t.id, u.username, t.department, t.subject, t.description, t.status, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE DATE(t.created_at) = %s AND t.status = 'Open'
            ORDER BY t.created_at ASC
        """, (today,))
        open_today_tickets = cur.fetchall()

        cur.close()

        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return render_template(
            "dashboard.html",
            username=session['username'],
            total_users=total_users,
            total_departments=total_departments,
            current_datetime=current_datetime,
            recent_tickets=all_tickets,      # table shows all tickets
            open_today_tickets=open_today_tickets  # use this in JS for notifications
        )

    return redirect(url_for('login_page'))


@app.route("/check_new_tickets")
def check_new_tickets():
    cur = mysql.connection.cursor()
    today = date.today()

    # Get all Open tickets for today
    cur.execute("""
        SELECT t.id, u.username, t.department, t.subject, t.description, t.status, t.created_at
        FROM tickets t
        JOIN users u ON t.user_id = u.id
        WHERE DATE(t.created_at) = %s AND t.status = 'Open'
        ORDER BY t.created_at ASC
    """, (today,))
    recent = cur.fetchall()
    cur.close()

    tickets_list = []
    for t in recent:
        tickets_list.append({
            "id": t[0],
            "user": t[1],
            "department": t[2],
            "subject": t[3],
            "description": t[4],
            "status": t[5],
            "created": t[6].strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify({
        "count": len(recent),
        "newTickets": tickets_list
    })
# ==============================
# ADMIN ACCOUNTS PAGE
# ==============================
@app.route('/admin/accounts')
def admin_accounts():
    if 'loggedin' in session and session['username'].lower() == 'admin':
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT id, username, email, department, password, role
            FROM users
            WHERE username != 'admin'
            ORDER BY id DESC
        """)
        users = cur.fetchall()

        cur.execute("SELECT DISTINCT department FROM users ORDER BY department ASC")
        departments = [row[0] for row in cur.fetchall()]

        cur.close()

        return render_template(
            "accounts.html",
            username=session['username'],
            users=users,
            departments=departments
        )

    return redirect(url_for('login_page'))

# ==============================
# UPDATE USER ACCOUNT (PLAIN TEXT PASSWORD)
# ==============================
@app.route('/update_user', methods=['POST'])
def update_user():
    user_id = request.form['id']
    username = request.form['username']
    email = request.form['email']
    department = request.form['department']
    role = request.form['role']
    password = request.form.get('password')  # optional

    cur = mysql.connection.cursor()

    if password:
        cur.execute("""
            UPDATE users
            SET username=%s, email=%s, department=%s, role=%s, password=%s
            WHERE id=%s
        """, (username, email, department, role, password, user_id))
    else:
        cur.execute("""
            UPDATE users
            SET username=%s, email=%s, department=%s, role=%s
            WHERE id=%s
        """, (username, email, department, role, user_id))

    mysql.connection.commit()
    cur.close()

    flash("User updated successfully!", "success")
    return redirect(url_for('admin_accounts'))

# ==============================
# USER DASHBOARD
# ==============================
@app.route('/user/dashboard', methods=['GET'])
def user_dashboard():
    if 'loggedin' in session and session['username'].lower() != 'admin':
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT t.id, u.username, t.department, t.subject, t.description, t.status, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.user_id = %s
            ORDER BY t.created_at DESC
        """, (session['id'],))
        tickets = cur.fetchall()
        cur.close()

        # Count tickets by status
        open_tickets = sum(1 for t in tickets if t[5] == 'Open')
        pending_tickets = sum(1 for t in tickets if t[5] == 'Pending')
        resolved_tickets = sum(1 for t in tickets if t[5] == 'Resolved')

        current_datetime = datetime.now().strftime("%B %d, %Y %I:%M:%S %p")
        return render_template(
            "userdashboard.html",
            username=session['username'],
            tickets=tickets,
            open_tickets=open_tickets,
            pending_tickets=pending_tickets,
            resolved_tickets=resolved_tickets,
            current_datetime=current_datetime
        )
    return redirect(url_for('login_page'))

# ==============================
# UPDATE TICKET STATUS
# ==============================
@app.route('/update_ticket_status', methods=['POST'])
def update_ticket_status():
    if 'loggedin' in session:
        ticket_id = request.form['ticket_id']
        status = request.form['status']

        cur = mysql.connection.cursor()
        cur.execute("UPDATE tickets SET status=%s WHERE id=%s", (status, ticket_id))
        mysql.connection.commit()
        cur.close()

        flash("Ticket updated successfully!", "success")

    return redirect(url_for('admin_dashboard'))

# ==============================
# USER HISTORY
# ==============================
@app.route('/user/history')
def user_history():
    if 'loggedin' in session and session['username'].lower() != 'admin':
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT t.id, u.username, t.department, t.subject, t.description, t.status, t.created_at
            FROM tickets t
            JOIN users u ON t.user_id = u.id
            WHERE t.user_id = %s
            ORDER BY t.created_at DESC
        """, (session['id'],))
        tickets = cur.fetchall()
        cur.close()
        return render_template("history.html", tickets=tickets, username=session['username'])
    return redirect(url_for('login_page'))

# ==============================
# REGISTER FUNCTION (PLAIN TEXT PASSWORD)
# ==============================
@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    department = request.form['department']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    if password != confirm_password:
        flash("Passwords do not match!", "danger")
        return redirect(url_for('register_page'))

    cur = mysql.connection.cursor()

    cur.execute("SELECT id FROM users WHERE username=%s", (username,))
    existing_user = cur.fetchone()
    if existing_user:
        flash("Username already exists!", "danger")
        cur.close()
        return redirect(url_for('register_page'))

    # Insert user with plain text password
    cur.execute("""
        INSERT INTO users (username, email, department, password, role)
        VALUES (%s, %s, %s, %s, %s)
    """, (username, email, department, password, 'user'))

    mysql.connection.commit()
    cur.close()

    flash("Registration successful! Please login.", "success")
    return redirect(url_for('login_page'))

# ==============================
# SUBMIT TICKET (Flask-Mail configured)
# ==============================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'bmciticketingsystem@gmail.com'
app.config['MAIL_PASSWORD'] = 'jsuo vvzz xwus ekhu'
app.config['MAIL_DEFAULT_SENDER'] = ('BMCI IT SUPPORT', 'bmciticketingsystem@gmail.com')

mail = Mail(app)

@app.route('/submit_ticket', methods=['POST'])
def submit_ticket():
    if 'loggedin' in session:
        user_id = session['id']
        username = session['username']
        user_email = session['email']
        department = request.form['department']
        subject = request.form['subject']
        description = request.form['description']
        status = "Open"

        cur = mysql.connection.cursor()
        # Insert the new ticket
        cur.execute("""
            INSERT INTO tickets (user_id, department, subject, description, status)
            VALUES (%s,%s,%s,%s,%s)
        """, (user_id, department, subject, description, status))
        mysql.connection.commit()

        # Get the ticket ID of the just submitted ticket
        ticket_id = cur.lastrowid
        cur.close()

        # Send confirmation email with only the ticket number
        try:
            msg = Message(
                subject=f"Ticket Submitted: #{ticket_id} - {subject}",
                recipients=[user_email],
                body=f"""Hello {username},

Your ticket has been successfully submitted.

Ticket Details:
Ticket Number: #{ticket_id}
Department: {department}
Subject: {subject}
Description: {description}
Status: {status}

You can track your ticket on your dashboard.

Regards,
BMCI IT Department"""
            )
            mail.send(msg)
        except Exception as e:
            print("Email sending failed:", e)

        flash(f"Ticket Submitted Successfully! Your Ticket Number is #{ticket_id}. A confirmation email has been sent.", "success")
        return redirect(url_for('user_dashboard'))

    return redirect(url_for('login_page'))

# ==============================
# LOGOUT
# ==============================
@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('login_page'))

@app.route('/admin/send_message', methods=['POST'])
def admin_send_message():
    if 'loggedin' in session and session['username'].lower() == 'admin':
        receiver_id = request.form.get('receiver_id')
        subject = request.form.get('subject')
        message_text = request.form.get('message')

        if not (receiver_id and subject and message_text):
            return jsonify({"success": False, "error": "Missing fields"})

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO messages (sender_id, receiver_id, subject, message)
                VALUES (%s, %s, %s, %s)
            """, (session['id'], receiver_id, subject, message_text))
            mysql.connection.commit()

            # Optional: send email notification
            cur.execute("SELECT email, username FROM users WHERE id=%s", (receiver_id,))
            user = cur.fetchone()
            if user:
                try:
                    msg = Message(
                        subject=f"New Message from Admin: {subject}",
                        recipients=[user[0]],
                        body=f"Hello {user[1]},\n\nYou received a new message from Admin:\n\n{message_text}"
                    )
                    mail.send(msg)
                except Exception as e:
                    print("Email send failed:", e)

            cur.close()
            return jsonify({"success": True})

        except Exception as e:
            print("DB Error:", e)
            return jsonify({"success": False, "error": str(e)})

    return jsonify({"success": False, "error": "Unauthorized"})


@app.route('/user/send_message', methods=['POST'])
def user_send_message():
    if 'loggedin' in session and session['username'].lower() != 'admin':
        receiver_id = request.form['receiver_id']  # Admin id
        subject = request.form['subject']
        message_text = request.form['message']

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO messages (sender_id, receiver_id, subject, message, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (session['id'], receiver_id, subject, message_text, 'Unread'))
            mysql.connection.commit()
            cur.close()

            # Optional: send email to admin
            # admin_email = 'bmciticketingsystem@gmail.com'
            # msg = Message(subject=f"New Message from {session['username']}: {subject}",
            #               recipients=[admin_email],
            #               body=message_text)
            # mail.send(msg)

            return jsonify({"success": True})
        except Exception as e:
            print("Error sending user message:", e)
            return jsonify({"success": False})
    return jsonify({"success": False})
# ==============================
# RUN APP
# ==============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000, debug=True)