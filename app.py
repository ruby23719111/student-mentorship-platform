"""Student Mentorship Platform application entry point."""

import os
import secrets
import sqlite3
from pathlib import Path

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


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "DATABASE_PATH", str(Path(app.instance_path) / "mentorship.db")
        ),
        SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    )
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

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
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
        selected_mentor_id = request.args.get("mentor", type=int)
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

        if selected_mentor_id is not None:
            sql += " AND mentor_profiles.id = ?"
            parameters.append(selected_mentor_id)
        elif search_term:
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
            selected_mentor_id=selected_mentor_id,
        )

    @app.get("/mentor/requests")
    def mentor_requests():
        if session.get("role") != "mentor":
            flash("Sign in as a Mentor to continue.", "error")
            return redirect(url_for("login"))
        return render_template(
            "dashboard_placeholder.html",
            heading="Pending requests",
            role="Mentor",
            next_issue="SCRUM-17 will implement Pending Requests from Figma H08.",
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
