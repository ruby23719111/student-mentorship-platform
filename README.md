# MentorLink — Student Mentorship Platform

MentorLink is a role-based Flask web application that supports the complete mentorship request and approval workflow between students and mentors.

## Live deployment

- Application: http://32.236.172.155/
- Health check: http://32.236.172.155/health
- EC2 instance ID: `i-0dda2dcd462ac8d51`
- AWS region: Asia Pacific (Sydney)

The QUT AWS environment only permits inbound rules from authorised individual IP addresses. Before the demonstration, the HTTP port 80 Security Group rule must use the current `My IP` `/32` address.

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Student | `kris.student@qut.edu.au` | `Student123!` |
| Mentor | `maya.mentor@qut.edu.au` | `Mentor123!` |

## Core workflow

1. A student signs in and searches available mentors.
2. The student submits a mentorship request with a learning goal and message.
3. The request is stored with a `Pending` status.
4. The selected mentor reviews and accepts or rejects the request.
5. Acceptance creates an active 12-week mentorship.
6. Both roles can view the updated mentorship state.

The application validates credentials, roles, request content, mentor capacity and conflicting active requests.

## Technology stack

- Python and Flask
- SQLite persistent database
- HTML and CSS
- Gunicorn application server
- Nginx reverse proxy
- systemd service management
- AWS EC2
- GitHub Actions automated tests

## Run locally

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    export SECRET_KEY='replace-with-a-random-development-secret'
    export DATABASE_PATH="$PWD/mentorship.db"
    .venv/bin/flask --app app run

Open `http://127.0.0.1:5000`.

## Automated tests

    .venv/bin/python -m unittest discover -s tests -v

The test suite covers authentication and role protection, validation, health checking, request withdrawal and acceptance of a valid mentorship request.

## EC2 deployment architecture

    Browser -> Nginx port 80 -> Gunicorn 127.0.0.1:8000 -> Flask -> SQLite

Gunicorn is restricted to the EC2 loopback interface. Nginx is the only application component listening on the public HTTP port.

Deployment templates are stored in:

- `deploy/mentorlink.service`
- `deploy/nginx-mentorlink.conf`

The systemd template assumes the repository is located at:

    /home/ubuntu/student-mentorship-platform

Runtime configuration is stored outside the repository in:

    /etc/mentorlink/mentorlink.env

Required environment variables:

- `SECRET_KEY`
- `DATABASE_PATH=/var/lib/mentorlink/mentorship.db`

The environment file and production database are deliberately excluded from GitHub.

## Manual deployment update

    cd /home/ubuntu/student-mentorship-platform
    git pull origin main
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m unittest discover -s tests -v
    sudo systemctl restart mentorlink
    sudo systemctl status mentorlink --no-pager
    curl http://127.0.0.1/health

## Security and limitations

- The private SSH key and application secrets are never committed.
- The environment file is readable only by `root`.
- AWS inbound access uses the QUT-required `My IP` `/32` rule.
- The deployment currently uses HTTP without TLS.
- SQLite is appropriate for this single-instance assessment deployment.
- The EC2 public IPv4 address may change if the instance is stopped and started.
