"""Student Mentorship Platform application entry point."""

import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


DEMO_USERS = (
    ("Kris Hsu", "kris.student@qut.edu.au", "Student123!", "student"),
    ("Alex Nguyen", "alex.student@qut.edu.au", "Student123!", "student"),
    ("Dr Maya Chen", "maya.mentor@qut.edu.au", "Mentor123!", "mentor"),
    ("Jordan Lee", "jordan.mentor@qut.edu.au", "Mentor123!", "mentor"),
    ("Aisha Rahman", "aisha.mentor@qut.edu.au", "Mentor123!", "mentor"),
)

DEMO_MENTOR_PROFILES = (
    (
        "maya.mentor@qut.edu.au",
        "Cloud & DevOps",
        "Cloud engineer helping students turn infrastructure ideas into practical plans.",
        2,
        1,
        1,
    ),
    (
        "jordan.mentor@qut.edu.au",
        "Product Management",
        "Product leader focused on discovery, prioritisation and measurable outcomes.",
        2,
        2,
        1,
    ),
    (
        "aisha.mentor@qut.edu.au",
        "UX Research",
        "UX researcher supporting inclusive interviews, synthesis and testing.",
        3,
        0,
        1,
    ),
)


def create_app(test_config: dict | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "DATABASE_PATH", str(Path(app.instance_path) / "mentorship.db")
        ),
        SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    )
    if test_config is not None:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    def csrf_token() -> str:
        token = session.get("_csrf_token")
        if token is None:
            token = secrets.token_urlsafe(32)
            session["_csrf_token"] = token
        return token

    def csrf_token_is_valid() -> bool:
        expected = session.get("_csrf_token", "")
        submitted = request.form.get("_csrf_token", "")
        return bool(
            expected
            and submitted
            and secrets.compare_digest(expected, submitted)
        )

    app.jinja_env.globals["csrf_token"] = csrf_token

    def format_date(value: str) -> str:
        return datetime.fromisoformat(value).strftime("%d %b %Y")

    app.jinja_env.filters["format_date"] = format_date

    def format_long_date(value: str) -> str:
        return datetime.fromisoformat(value).strftime("%d %B %Y")

    app.jinja_env.filters["format_long_date"] = format_long_date

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    def close_db(_error=None) -> None:
        database = g.pop("db", None)
        if database is not None:
            database.close()

    def initialise_database() -> None:
        database = get_db()
        schema_path = Path(app.root_path) / "schema.sql"
        database.executescript(schema_path.read_text(encoding="utf-8"))

        for name, email, password, role in DEMO_USERS:
            database.execute(
                """
                INSERT OR IGNORE INTO users (name, email, password_hash, role)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, generate_password_hash(password), role),
            )

        for email, expertise, bio, capacity, active_mentees, approved in (
            DEMO_MENTOR_PROFILES
        ):
            database.execute(
                """
                INSERT OR IGNORE INTO mentor_profiles (
                    user_id, expertise, bio, capacity, active_mentees, approved
                )
                SELECT id, ?, ?, ?, ?, ?
                FROM users
                WHERE email = ? AND role = 'mentor'
                """,
                (expertise, bio, capacity, active_mentees, approved, email),
            )
        database.commit()

    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        return redirect(url_for("login"))

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            role = request.form.get("role", "").strip().lower()
            errors = {}

            if not csrf_token_is_valid():
                errors["form"] = (
                    "Your sign-in session expired. Refresh the page and try again."
                )

            if not email:
                errors["email"] = "Enter your QUT email address."
            elif "@" not in email:
                errors["email"] = "Enter a valid email address."

            if not password:
                errors["password"] = "Enter your password."

            if role not in {"student", "mentor"}:
                errors["role"] = "Select Student or Mentor."

            user = None
            if not errors:
                user = get_db().execute(
                    "SELECT * FROM users WHERE email = ? AND role = ?",
                    (email, role),
                ).fetchone()

                if user is None or not check_password_hash(
                    user["password_hash"], password
                ):
                    errors["form"] = (
                        "The email, password or selected role is incorrect."
                    )

            if not errors and user is not None:
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["role"] = user["role"]
                destination = (
                    "student_mentors"
                    if user["role"] == "student"
                    else "mentor_requests"
                )
                return redirect(url_for(destination))

            return render_template(
                "login.html",
                errors=errors,
                entered_email=email,
                selected_role=role,
            )

        return render_template(
            "login.html", errors={}, entered_email="", selected_role="student"
        )

    @app.get("/student/mentors")
    def student_mentors():
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))

        search_term = request.args.get("q", "").strip()
        sql = """
            SELECT
                mentor_profiles.id,
                users.name,
                mentor_profiles.expertise,
                mentor_profiles.bio,
                mentor_profiles.capacity,
                mentor_profiles.active_mentees,
                mentor_profiles.capacity - mentor_profiles.active_mentees AS places
            FROM mentor_profiles
            JOIN users ON users.id = mentor_profiles.user_id
            WHERE mentor_profiles.approved = 1
        """
        parameters = []

        if search_term:
            sql += """
                AND (
                    users.name LIKE ?
                    OR mentor_profiles.expertise LIKE ?
                    OR mentor_profiles.bio LIKE ?
                )
            """
            pattern = f"%{search_term}%"
            parameters.extend((pattern, pattern, pattern))

        sql += " ORDER BY mentor_profiles.id"
        mentors = get_db().execute(sql, parameters).fetchall()

        return render_template(
            "student_mentors.html",
            mentors=mentors,
            search_term=search_term,
        )

    def get_available_mentor(mentor_id: int):
        return get_db().execute(
            """
            SELECT
                mentor_profiles.id,
                users.name,
                mentor_profiles.expertise,
                mentor_profiles.capacity - mentor_profiles.active_mentees AS places
            FROM mentor_profiles
            JOIN users ON users.id = mentor_profiles.user_id
            WHERE mentor_profiles.id = ?
              AND mentor_profiles.approved = 1
              AND mentor_profiles.active_mentees < mentor_profiles.capacity
            """,
            (mentor_id,),
        ).fetchone()

    @app.route("/student/requests/new/<int:mentor_id>", methods=("GET", "POST"))
    def student_request_new(mentor_id: int):
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))

        mentor = get_available_mentor(mentor_id)
        if mentor is None:
            flash("This Mentor is unavailable for new requests.", "error")
            return redirect(url_for("student_mentors"))

        learning_goal = ""
        message = ""
        errors = {}

        existing_request = get_db().execute(
            """
            SELECT id
            FROM mentorship_requests
            WHERE student_id = ? AND status IN ('pending', 'accepted')
            """,
            (session["user_id"],),
        ).fetchone()

        if existing_request is not None:
            flash(
                "You already have a pending or active mentorship request.",
                "error",
            )
            return redirect(
                url_for(
                    "student_request_submitted",
                    request_id=existing_request["id"],
                )
            )

        if request.method == "POST":
            learning_goal = request.form.get("learning_goal", "").strip()
            message = request.form.get("message", "").strip()

            if not csrf_token_is_valid():
                errors["form"] = (
                    "Your form session expired. Refresh the page and try again."
                )

            if len(learning_goal) < 20:
                errors["learning_goal"] = "Enter at least 20 characters."

            if len(message) < 20:
                errors["message"] = "Enter at least 20 characters."

            if not errors:
                submitted_at = datetime.now(
                    ZoneInfo("Australia/Brisbane")
                ).isoformat(timespec="seconds")
                try:
                    cursor = get_db().execute(
                        """
                        INSERT INTO mentorship_requests (
                            student_id,
                            mentor_profile_id,
                            learning_goal,
                            message,
                            status,
                            submitted_at
                        )
                        VALUES (?, ?, ?, ?, 'pending', ?)
                        """,
                        (
                            session["user_id"],
                            mentor["id"],
                            learning_goal,
                            message,
                            submitted_at,
                        ),
                    )
                    get_db().commit()
                except sqlite3.IntegrityError:
                    get_db().rollback()
                    errors["form"] = (
                        "You already have a pending or active mentorship request."
                    )
                else:
                    return redirect(
                        url_for(
                            "student_request_submitted",
                            request_id=cursor.lastrowid,
                        )
                    )

        return render_template(
            "student_request_form.html",
            mentor=mentor,
            learning_goal=learning_goal,
            message=message,
            errors=errors,
        )

    def get_student_request(request_id: int):
        return get_db().execute(
            """
            SELECT
                mentorship_requests.id,
                mentorship_requests.status,
                mentorship_requests.submitted_at,
                users.name AS mentor_name,
                mentor_profiles.expertise
            FROM mentorship_requests
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorship_requests.mentor_profile_id
            JOIN users ON users.id = mentor_profiles.user_id
            WHERE mentorship_requests.id = ?
              AND mentorship_requests.student_id = ?
            """,
            (request_id, session.get("user_id")),
        ).fetchone()

    @app.get("/student/requests")
    def student_requests():
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))

        latest_request = get_db().execute(
            """
            SELECT
                mentorship_requests.id,
                mentorship_requests.status,
                mentorship_requests.submitted_at,
                users.name AS mentor_name,
                mentor_profiles.expertise
            FROM mentorship_requests
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorship_requests.mentor_profile_id
            JOIN users ON users.id = mentor_profiles.user_id
            WHERE mentorship_requests.student_id = ?
            ORDER BY mentorship_requests.id DESC
            LIMIT 1
            """,
            (session["user_id"],),
        ).fetchone()

        return render_template(
            "student_requests.html",
            request_item=latest_request,
        )

    @app.post("/student/requests/<int:request_id>/withdraw")
    def student_request_withdraw(request_id: int):
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))
        if not csrf_token_is_valid():
            flash("Your form session expired. Review the request and try again.", "error")
            return redirect(url_for("student_requests"))

        cursor = get_db().execute(
            """
            UPDATE mentorship_requests
            SET status = 'withdrawn'
            WHERE id = ?
              AND student_id = ?
              AND status = 'pending'
            """,
            (request_id, session["user_id"]),
        )
        if cursor.rowcount != 1:
            get_db().rollback()
            flash("Only your pending request can be withdrawn.", "error")
            return redirect(url_for("student_requests"))

        get_db().commit()
        return redirect(url_for("student_requests"))

    def get_active_mentorship_for_student():
        return get_db().execute(
            """
            SELECT
                mentorship_requests.id AS request_id,
                students.name AS student_name,
                mentors.name AS mentor_name,
                mentor_profiles.expertise,
                mentorships.start_date,
                mentorships.end_date
            FROM mentorships
            JOIN mentorship_requests
                ON mentorship_requests.id = mentorships.request_id
            JOIN users AS students
                ON students.id = mentorship_requests.student_id
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorships.mentor_profile_id
            JOIN users AS mentors ON mentors.id = mentor_profiles.user_id
            WHERE mentorship_requests.student_id = ?
              AND mentorship_requests.status = 'accepted'
              AND mentorships.status = 'active'
            ORDER BY mentorships.id DESC
            LIMIT 1
            """,
            (session.get("user_id"),),
        ).fetchone()

    @app.get("/student/mentorships")
    def student_active_mentorships():
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))

        return render_template(
            "active_mentorship.html",
            mentorship=get_active_mentorship_for_student(),
            role="Student",
        )

    @app.get("/student/requests/<int:request_id>/submitted")
    def student_request_submitted(request_id: int):
        if session.get("role") != "student":
            flash("Sign in as a Student to continue.", "error")
            return redirect(url_for("login"))

        request_item = get_student_request(request_id)
        if request_item is None:
            flash("That mentorship request could not be found.", "error")
            return redirect(url_for("student_mentors"))
        if request_item["status"] == "accepted":
            return redirect(url_for("student_active_mentorships"))
        if request_item["status"] != "pending":
            return redirect(url_for("student_requests"))

        return render_template(
            "student_request_submitted.html",
            request_item=request_item,
        )

    @app.get("/mentor/requests")
    def mentor_requests():
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))

        pending_requests = get_db().execute(
            """
            SELECT
                mentorship_requests.id,
                mentorship_requests.learning_goal,
                mentorship_requests.submitted_at,
                students.name AS student_name
            FROM mentorship_requests
            JOIN users AS students
                ON students.id = mentorship_requests.student_id
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorship_requests.mentor_profile_id
            WHERE mentor_profiles.user_id = ?
              AND mentorship_requests.status = 'pending'
            ORDER BY mentorship_requests.submitted_at, mentorship_requests.id
            """,
            (session["user_id"],),
        ).fetchall()

        return render_template(
            "mentor_requests.html",
            pending_requests=pending_requests,
        )

    def get_mentor_request(request_id: int):
        return get_db().execute(
            """
            SELECT
                mentorship_requests.id,
                mentorship_requests.learning_goal,
                mentorship_requests.message,
                mentorship_requests.status,
                mentorship_requests.submitted_at,
                students.name AS student_name,
                mentor_profiles.id AS mentor_profile_id,
                mentor_profiles.expertise,
                mentor_profiles.capacity,
                mentor_profiles.active_mentees
            FROM mentorship_requests
            JOIN users AS students
                ON students.id = mentorship_requests.student_id
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorship_requests.mentor_profile_id
            WHERE mentorship_requests.id = ?
              AND mentor_profiles.user_id = ?
            """,
            (request_id, session.get("user_id")),
        ).fetchone()

    @app.get("/mentor/requests/<int:request_id>")
    def mentor_request_review(request_id: int):
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))

        request_item = get_mentor_request(request_id)
        if request_item is None:
            flash("That mentorship request could not be found.", "error")
            return redirect(url_for("mentor_requests"))
        if request_item["status"] == "accepted":
            return redirect(
                url_for("mentor_request_accepted", request_id=request_id)
            )
        if request_item["status"] == "rejected":
            return redirect(
                url_for("mentor_request_rejected", request_id=request_id)
            )
        if request_item["status"] != "pending":
            flash("That mentorship request is no longer pending.", "error")
            return redirect(url_for("mentor_requests"))

        return render_template(
            "mentor_request_review.html",
            request_item=request_item,
        )

    @app.post("/mentor/requests/<int:request_id>/decision")
    def mentor_request_decision(request_id: int):
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))
        if not csrf_token_is_valid():
            flash("Your form session expired. Review the request and try again.", "error")
            return redirect(
                url_for("mentor_request_review", request_id=request_id)
            )

        action = request.form.get("action", "")
        if action not in {"accept", "reject"}:
            flash("Choose Accept or Reject.", "error")
            return redirect(
                url_for("mentor_request_review", request_id=request_id)
            )

        request_item = get_mentor_request(request_id)
        if request_item is None:
            flash("That mentorship request could not be found.", "error")
            return redirect(url_for("mentor_requests"))
        if request_item["status"] != "pending":
            flash("That mentorship request has already been reviewed.", "error")
            return redirect(
                url_for("mentor_request_review", request_id=request_id)
            )

        database = get_db()
        try:
            database.execute("BEGIN IMMEDIATE")

            if action == "accept":
                capacity_update = database.execute(
                    """
                    UPDATE mentor_profiles
                    SET active_mentees = active_mentees + 1
                    WHERE id = ?
                      AND user_id = ?
                      AND active_mentees < capacity
                    """,
                    (request_item["mentor_profile_id"], session["user_id"]),
                )
                if capacity_update.rowcount != 1:
                    database.rollback()
                    flash(
                        "Your capacity is full. Update capacity before accepting this request.",
                        "error",
                    )
                    return redirect(
                        url_for("mentor_request_review", request_id=request_id)
                    )

                request_update = database.execute(
                    """
                    UPDATE mentorship_requests
                    SET status = 'accepted'
                    WHERE id = ? AND status = 'pending'
                    """,
                    (request_id,),
                )
                if request_update.rowcount != 1:
                    raise sqlite3.IntegrityError("Request was already reviewed")

                start_date = datetime.now(ZoneInfo("Australia/Brisbane")).date()
                end_date = start_date + timedelta(weeks=12)
                database.execute(
                    """
                    INSERT INTO mentorships (
                        request_id,
                        mentor_profile_id,
                        start_date,
                        end_date,
                        status
                    )
                    VALUES (?, ?, ?, ?, 'active')
                    """,
                    (
                        request_id,
                        request_item["mentor_profile_id"],
                        start_date.isoformat(),
                        end_date.isoformat(),
                    ),
                )
                destination = "mentor_request_accepted"
            else:
                request_update = database.execute(
                    """
                    UPDATE mentorship_requests
                    SET status = 'rejected'
                    WHERE id = ? AND status = 'pending'
                    """,
                    (request_id,),
                )
                if request_update.rowcount != 1:
                    raise sqlite3.IntegrityError("Request was already reviewed")
                destination = "mentor_request_rejected"

            database.commit()
        except sqlite3.IntegrityError:
            database.rollback()
            flash("That mentorship request has already been reviewed.", "error")
            return redirect(url_for("mentor_requests"))

        return redirect(url_for(destination, request_id=request_id))

    @app.get("/mentor/requests/<int:request_id>/accepted")
    def mentor_request_accepted(request_id: int):
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))

        mentorship = get_db().execute(
            """
            SELECT
                mentorship_requests.id AS request_id,
                students.name AS student_name,
                mentors.name AS mentor_name,
                mentor_profiles.expertise,
                mentorships.start_date,
                mentorships.end_date
            FROM mentorships
            JOIN mentorship_requests
                ON mentorship_requests.id = mentorships.request_id
            JOIN users AS students
                ON students.id = mentorship_requests.student_id
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorships.mentor_profile_id
            JOIN users AS mentors ON mentors.id = mentor_profiles.user_id
            WHERE mentorship_requests.id = ?
              AND mentor_profiles.user_id = ?
              AND mentorship_requests.status = 'accepted'
              AND mentorships.status = 'active'
            """,
            (request_id, session["user_id"]),
        ).fetchone()
        if mentorship is None:
            flash("That active mentorship could not be found.", "error")
            return redirect(url_for("mentor_requests"))

        return render_template(
            "mentor_request_accepted.html",
            mentorship=mentorship,
        )

    @app.get("/mentor/requests/<int:request_id>/rejected")
    def mentor_request_rejected(request_id: int):
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))

        request_item = get_mentor_request(request_id)
        if request_item is None or request_item["status"] != "rejected":
            flash("That declined request could not be found.", "error")
            return redirect(url_for("mentor_requests"))

        return render_template(
            "mentor_request_rejected.html",
            request_item=request_item,
        )

    @app.get("/mentor/mentorships")
    def mentor_active_mentorships():
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))

        mentorship = get_db().execute(
            """
            SELECT
                mentorship_requests.id AS request_id,
                students.name AS student_name,
                mentors.name AS mentor_name,
                mentor_profiles.expertise,
                mentorships.start_date,
                mentorships.end_date
            FROM mentorships
            JOIN mentorship_requests
                ON mentorship_requests.id = mentorships.request_id
            JOIN users AS students
                ON students.id = mentorship_requests.student_id
            JOIN mentor_profiles
                ON mentor_profiles.id = mentorships.mentor_profile_id
            JOIN users AS mentors ON mentors.id = mentor_profiles.user_id
            WHERE mentor_profiles.user_id = ?
              AND mentorship_requests.status = 'accepted'
              AND mentorships.status = 'active'
            ORDER BY mentorships.id DESC
            LIMIT 1
            """,
            (session["user_id"],),
        ).fetchone()

        return render_template(
            "active_mentorship.html",
            mentorship=mentorship,
            role="Mentor",
        )

    @app.post("/logout")
    def logout():
        if not csrf_token_is_valid():
            flash("Your session expired. Sign out again.", "error")
            return redirect(url_for("index"))
        session.clear()
        return redirect(url_for("login"))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    with app.app_context():
        initialise_database()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
