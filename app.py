"""Student Mentorship Platform application entry point."""

from flask import Flask, redirect, render_template, url_for


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    @app.get("/")
    def index():
        return redirect(url_for("login"))

    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

