from flask import Flask, render_template, request, session,redirect,flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import os
app = Flask(__name__)

# CONFIGURATION 

app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "localhost")
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER", "root")
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD", "")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB", "placement_system")

app.secret_key = "student-placement-secret"

mysql = MySQL(app)

# HOME

@app.route("/")
def home():
    return render_template("index.html")

# STUDENT REGISTRATION

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        cgpa = request.form["cgpa"]

        try:
            cgpa = float(cgpa)
        except ValueError:
            return "Invalid CGPA"

        if cgpa < 0 or cgpa > 10:
            return "CGPA must be between 0 and 10"

        branch = request.form["branch"].strip()

        cursor = mysql.connection.cursor()

        # Check if email already exists
        cursor.execute(
            """
            SELECT student_id
            FROM students
            WHERE email = %s
            """,
            (email,)
        )

        existing_student = cursor.fetchone()

        if existing_student:
            cursor.close()

            flash("Email already registered. Please use a different email.")
            return redirect("/register")

        # Hash password
        hashed_password = generate_password_hash(password)

        # Insert student
        cursor.execute(
            """
            INSERT INTO students
            (name, email, password, cgpa, branch)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                name,
                email,
                hashed_password,
                cgpa,
                branch
            )
        )

        mysql.connection.commit()
        cursor.close()

        flash("Registration successful! You can now login.")
        return redirect("/")

    return render_template("register.html")

# STUDENT LOGIN


@app.route("/login", methods=["POST"])
def login():

    email = request.form["email"]
    password = request.form["password"]

    cursor = mysql.connection.cursor()

    cursor.execute(
        "SELECT * FROM students WHERE email = %s",
        (email,)
    )

    student = cursor.fetchone()

    cursor.close()

    if student is None:
        flash("Student not found. Please try with a valid email")
        return render_template("index.html")

    if check_password_hash(student[3], password):

        session["student_id"] = student[0]
        session["student_name"] = student[1]

        return redirect("/dashboard")

    flash("Incorrect password")
    return render_template('index.html')



# STUDENT DASHBOARD


@app.route("/dashboard")
def dashboard():

    if "student_id" not in session:
        return "Please login first"

    student_id = session["student_id"]

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        SELECT name, email, cgpa, branch
        FROM students
        WHERE student_id = %s
        """,
        (student_id,)
    )

    student = cursor.fetchone()

    cursor.close()

    return render_template(
        "dashboard.html",
        student=student
    )



# VIEW PLACEMENT DRIVES

@app.route("/drives")
def drives():

    if "student_id" not in session:
        return "Please login first"

    student_id = session["student_id"]

    cursor = mysql.connection.cursor()

    # Get logged-in student's CGPA and branch
    cursor.execute(
        """
        SELECT cgpa, branch
        FROM students
        WHERE student_id = %s
        """,
        (student_id,)
    )

    student = cursor.fetchone()

    if student is None:
        cursor.close()
        return "Student not found"

    student_cgpa = float(student[0])
    student_branch = student[1].strip().upper()

    # Get all placement drives
    cursor.execute(
        """
        SELECT
            placement_drives.drive_id,
            companies.company_name,
            placement_drives.job_role,
            placement_drives.minimum_cgpa,
            placement_drives.eligibility_branch,
            placement_drives.drive_date
        FROM placement_drives
        JOIN companies
        ON placement_drives.company_id = companies.company_id
        """
    )

    drive_rows = cursor.fetchall()

    drives = []

    # Branch name normalization
    branch_map = {
        "ECE": "ECE",
        "ELECTRONICS AND COMMUNICATION ENGINEERING": "ECE",
        "ELECTRONICS & COMMUNICATION ENGINEERING": "ECE",
        "ELECTRONICS AND COMMUNICATION": "ECE",

        "CSE": "CSE",
        "COMPUTER SCIENCE AND ENGINEERING": "CSE",

        "EEE": "EEE",
        "ELECTRICAL AND ELECTRONICS ENGINEERING": "EEE",

        "ME": "ME",
        "MECH": "ME",
        "MECHANICAL ENGINEERING": "ME",

        "CIVIL": "CIVIL",
        "CIVIL ENGINEERING": "CIVIL"
    }

    student_branch_normalized = branch_map.get(
        student_branch,
        student_branch
    )

    for drive in drive_rows:

        drive_id = drive[0]
        company_name = drive[1]
        job_role = drive[2]
        minimum_cgpa = float(drive[3])
        eligibility_branch = drive[4]
        drive_date = drive[5]

        eligibility_branch_normalized = branch_map.get(
            eligibility_branch.strip().upper(),
            eligibility_branch.strip().upper()
        )

        # Check both CGPA and branch
        cgpa_eligible = student_cgpa >= minimum_cgpa

        branch_eligible = (
            student_branch_normalized
            == eligibility_branch_normalized
        )

        eligible = cgpa_eligible and branch_eligible

        if eligible:
            eligibility_message = "Eligible"
        else:
            eligibility_message = "Not Eligible"

        drives.append(
            (
                drive_id,
                company_name,
                job_role,
                minimum_cgpa,
                eligibility_branch,
                drive_date,
                eligible,
                eligibility_message
            )
        )

    cursor.close()

    return render_template(
        "drives.html",
        drives=drives
    )


# APPLY FOR PLACEMENT


@app.route("/apply/<int:drive_id>", methods=["POST"])
def apply(drive_id):

    if "student_id" not in session:
        return "Please login first"

    student_id = session["student_id"]

    cursor = mysql.connection.cursor()

    # Get student details
    cursor.execute(
        """
        SELECT cgpa, branch
        FROM students
        WHERE student_id = %s
        """,
        (student_id,)
    )

    student = cursor.fetchone()

    # Get drive eligibility requirements
    cursor.execute(
        """
        SELECT minimum_cgpa, eligibility_branch
        FROM placement_drives
        WHERE drive_id = %s
        """,
        (drive_id,)
    )

    drive = cursor.fetchone()

    if student is None or drive is None:
        cursor.close()
        flash("Invalid student or placement drive.")
        return redirect("/drives")

    student_cgpa = float(student[0])
    student_branch = student[1]

    minimum_cgpa = float(drive[0])
    eligibility_branch = drive[1]

    # Check CGPA
    if student_cgpa < minimum_cgpa:
        cursor.close()
        flash("You are not eligible because your CGPA is below the requirement.")
        return redirect("/drives")

    # Check branch
    if student_branch.strip().upper() != eligibility_branch.strip().upper():
        cursor.close()
        flash("You are not eligible for this drive because of your branch.")
        return redirect("/drives")

    # Check duplicate application
    cursor.execute(
        """
        SELECT *
        FROM applications
        WHERE student_id = %s
        AND drive_id = %s
        """,
        (student_id, drive_id)
    )

    existing_application = cursor.fetchone()

    if existing_application:
        cursor.close()
        flash("You have already applied for this drive.")
        return redirect("/drives")

    # Apply
    cursor.execute(
        """
        INSERT INTO applications
        (student_id, drive_id, application_date)
        VALUES (%s, %s, CURDATE())
        """,
        (student_id, drive_id)
    )

    mysql.connection.commit()
    cursor.close()

    flash("Application submitted successfully!")
    return redirect("/applications")     


# MY APPLICATIONS


@app.route("/applications")
def applications():

    if "student_id" not in session:
        return "Please login first"

    student_id = session["student_id"]

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        SELECT
            companies.company_name,
            placement_drives.job_role,
            applications.application_date,
            applications.status
        FROM applications
        JOIN placement_drives
        ON applications.drive_id = placement_drives.drive_id
        JOIN companies
        ON placement_drives.company_id = companies.company_id
        WHERE applications.student_id = %s
        """,
        (student_id,)
    )

    applications = cursor.fetchall()

    cursor.close()

    return render_template(
        "applications.html",
        applications=applications
    )



# ADMIN LOGIN


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor = mysql.connection.cursor()

        cursor.execute(
            "SELECT * FROM admins WHERE email = %s",
            (email,)
        )

        admin = cursor.fetchone()

        cursor.close()

        if admin is None:
            flash("Admin not found")
            return redirect("/admin-login")

        # Current admin table uses a plain password
        if check_password_hash(admin[3], password):

            session["admin_id"] = admin[0]
            session["admin_name"] = admin[1]

            return redirect("/admin-dashboard")

        flash("Incorrect password")
        return redirect("/admin-login")

    return render_template("admin_login.html")



# ADMIN DASHBOARD


@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return "Please login as admin first"

    return render_template(
        "admin_dashboard.html",
        name=session["admin_name"]
    )



# ADD COMPANY


@app.route("/add-company", methods=["GET", "POST"])
def add_company():

    if "admin_id" not in session:
        return "Please login as admin first"

    if request.method == "POST":

        company_name = request.form["company_name"]
        location = request.form["location"]
        description = request.form["description"]

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            INSERT INTO companies
            (company_name, location, description)
            VALUES (%s, %s, %s)
            """,
            (company_name, location, description)
        )

        mysql.connection.commit()
        cursor.close()

        return redirect("/companies")

    return render_template("add_company.html")


# VIEW COMPANIES


@app.route("/companies")
def companies():

    if "admin_id" not in session:
        return "Please login as admin first"

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        SELECT
            company_id,
            company_name,
            location,
            description
        FROM companies
        """
    )

    companies = cursor.fetchall()

    cursor.close()

    return render_template(
        "companies.html",
        companies=companies
    )



# CREATE PLACEMENT DRIVE


@app.route("/add-drive", methods=["GET", "POST"])
def add_drive():

    if "admin_id" not in session:
        return "Please login as admin first"

    cursor = mysql.connection.cursor()

    # Get companies for dropdown
    cursor.execute(
        "SELECT company_id, company_name FROM companies"
    )

    companies = cursor.fetchall()

    if request.method == "POST":

        company_id = request.form["company_id"]
        job_role = request.form["job_role"]
        minimum_cgpa = request.form["minimum_cgpa"]
        eligibility_branch = request.form["eligibility_branch"]
        drive_date = request.form["drive_date"]

        cursor.execute(
            """
            INSERT INTO placement_drives
            (
                company_id,
                job_role,
                minimum_cgpa,
                eligibility_branch,
                drive_date
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                company_id,
                job_role,
                minimum_cgpa,
                eligibility_branch,
                drive_date
            )
        )

        mysql.connection.commit()
        cursor.close()

        return redirect("/drives")

    cursor.close()

    return render_template(
        "add_drive.html",
        companies=companies
    )


# VIEW STUDENTS - ADMIN


@app.route("/students")
def students():

    if "admin_id" not in session:
        return "Please login as admin first"

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        SELECT student_id, name, email, cgpa, branch
        FROM students
        """
    )

    students = cursor.fetchall()

    cursor.close()

    return render_template(
        "students.html",
        students=students
    )

# VIEW APPLICATIONS - ADMIN


@app.route("/admin-applications")
def admin_applications():

    if "admin_id" not in session:
        return "Please login as admin first"

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        SELECT
            applications.application_id,
            students.name,
            students.email,
            companies.company_name,
            placement_drives.job_role,
            applications.application_date,
            applications.status
        FROM applications
        JOIN students
        ON applications.student_id = students.student_id
        JOIN placement_drives
        ON applications.drive_id = placement_drives.drive_id
        JOIN companies
        ON placement_drives.company_id = companies.company_id
        """
    )

    applications = cursor.fetchall()

    cursor.close()

    return render_template(
        "admin_applications.html",
        applications=applications
    )



# CHANGE APPLICATION STATUS


@app.route("/update-status/<int:application_id>", methods=["POST"])
def update_status(application_id):

    if "admin_id" not in session:
        return "Please login as admin first"

    status = request.form["status"]

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        UPDATE applications
        SET status = %s
        WHERE application_id = %s
        """,
        (status, application_id)
    )

    mysql.connection.commit()

    cursor.close()

    return "Application status updated successfully!"

# LOGOUT

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")



# RUN APPLICATION


if __name__ == "__main__":
    app.run(debug=True)