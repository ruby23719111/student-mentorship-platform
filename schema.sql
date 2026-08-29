CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student', 'mentor'))
);

CREATE TABLE IF NOT EXISTS mentor_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    expertise TEXT NOT NULL,
    bio TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 0 CHECK (capacity >= 0),
    active_mentees INTEGER NOT NULL DEFAULT 0 CHECK (active_mentees >= 0),
    approved INTEGER NOT NULL DEFAULT 0 CHECK (approved IN (0, 1)),
    FOREIGN KEY (user_id) REFERENCES users (id),
    CHECK (active_mentees <= capacity)
);

CREATE TABLE IF NOT EXISTS mentorship_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    mentor_profile_id INTEGER NOT NULL,
    learning_goal TEXT NOT NULL CHECK (length(trim(learning_goal)) >= 20),
    message TEXT NOT NULL CHECK (length(trim(message)) >= 20),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn')),
    submitted_at TEXT NOT NULL,
    FOREIGN KEY (student_id) REFERENCES users (id),
    FOREIGN KEY (mentor_profile_id) REFERENCES mentor_profiles (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_open_request_per_student
ON mentorship_requests (student_id)
WHERE status IN ('pending', 'accepted');
