import sqlite3
from datetime import datetime
from .config import DB_NAME

class Database:
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.db_name)
        self.init_schema()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def init_schema(self):
        c = self.conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                career_url TEXT,
                job_link_pattern TEXT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_profile TEXT,
                job_preferences TEXT,
                min_score INTEGER DEFAULT 80
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                job_url TEXT UNIQUE,
                title TEXT,
                location TEXT,
                salary TEXT,
                description TEXT,
                last_seen_date TEXT,
                relevancy_score INTEGER DEFAULT 0,
                processed_for_resume BOOLEAN DEFAULT 0,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            )
        ''')

        # Insert default config if empty
        c.execute('SELECT COUNT(*) FROM preferences')
        if c.fetchone()[0] == 0:
            c.execute('''
                INSERT INTO preferences (candidate_profile, job_preferences, min_score)
                VALUES (?, ?, ?)
            ''', (
                "Senior Full-Stack Developer with 10 years experience in Python, Cloudflare, and AI.",
                "Looking for remote senior roles, minimum $150k salary, focused on AI infrastructure.",
                85
            ))

        c.execute('SELECT COUNT(*) FROM companies')
        if c.fetchone()[0] == 0:
            c.execute('''
                INSERT INTO companies (name, career_url, job_link_pattern)
                VALUES (?, ?, ?)
            ''', ("Cloudflare", "https://careers.cloudflare.com/jobs", "/jobs/"))

        self.conn.commit()

    def get_preferences(self):
        c = self.conn.cursor()
        c.execute("SELECT candidate_profile, job_preferences, min_score FROM preferences LIMIT 1")
        return c.fetchone()

    def get_companies(self):
        c = self.conn.cursor()
        c.execute("SELECT id, name, career_url, job_link_pattern FROM companies")
        return [{'id': r[0], 'name': r[1], 'career_url': r[2], 'job_link_pattern': r[3]} for r in c.fetchall()]

    def upsert_job(self, job_dict):
        c = self.conn.cursor()
        c.execute("SELECT id, location, salary, description FROM jobs WHERE job_url = ?", (job_dict['job_url'],))
        row = c.fetchone()

        has_changed = False
        is_new = False
        job_id = None

        if row:
            job_id = row[0]
            if row[1] != job_dict['location'] or row[2] != job_dict['salary'] or row[3] != job_dict['description']:
                has_changed = True
                c.execute("""
                    UPDATE jobs
                    SET title = ?, location = ?, salary = ?, description = ?, last_seen_date = ?
                    WHERE id = ?
                """, (job_dict['title'], job_dict['location'], job_dict['salary'], job_dict['description'], datetime.now().isoformat(), job_id))
        else:
            is_new = True
            c.execute("""
                INSERT INTO jobs (company_id, job_url, title, location, salary, description, last_seen_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (job_dict['company_id'], job_dict['job_url'], job_dict['title'], job_dict['location'], job_dict['salary'], job_dict['description'], datetime.now().isoformat()))
            job_id = c.lastrowid

        self.conn.commit()
        return job_id, is_new, has_changed

    def update_job_score(self, job_id, score):
        c = self.conn.cursor()
        c.execute("UPDATE jobs SET relevancy_score = ? WHERE id = ?", (score, job_id))
        self.conn.commit()

    def mark_job_processed(self, job_id):
        c = self.conn.cursor()
        c.execute("UPDATE jobs SET processed_for_resume = 1 WHERE id = ?", (job_id,))
        self.conn.commit()

    def is_job_processed(self, job_id):
        c = self.conn.cursor()
        row = c.execute("SELECT processed_for_resume FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row[0] if row else False
