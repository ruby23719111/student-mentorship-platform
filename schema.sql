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
