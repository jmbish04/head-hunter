# main.py
import sqlite3
import os
import json
import time
import re
from datetime import datetime
import requests
from urllib.parse import urljoin
from scrapling.fetchers import StealthySession

# Environment Configuration
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "your_account_id")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "your_api_token")
CF_GATEWAY_ID = os.environ.get("CF_GATEWAY_ID", "my-ai-gateway")
MODEL_NAME = "@cf/meta/llama-3.1-8b-instruct"
DB_NAME = "job_scraper.db"
OUTPUT_DIR = "./applications"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

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

    conn.commit()
    conn.close()

def call_cloudflare_ai(prompt, system_prompt="You are a helpful assistant.", json_mode=False):
    url = f"https://gateway.ai.cloudflare.com/v1/{CF_ACCOUNT_ID}/{CF_GATEWAY_ID}/workers-ai/{MODEL_NAME}"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        result = data.get("result", {}).get("response", "")

        if json_mode:
            result = result.replace("```json", "").replace("```", "").strip()
            # Find JSON boundaries just in case there is conversational text
            start = result.find('{')
            end = result.rfind('}') + 1
            if start != -1 and end != 0:
                result = result[start:end]
            return json.loads(result)

        return result
    except Exception as e:
        print(f"Error calling Cloudflare AI: {e}")
        return {} if json_mode else ""

def get_preferences():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT candidate_profile, job_preferences, min_score FROM preferences LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row

def get_companies():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, name, career_url, job_link_pattern FROM companies")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def upsert_job(job_dict):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, title, location, salary, description FROM jobs WHERE job_url = ?", (job_dict['job_url'],))
    row = c.fetchone()

    has_changed = False
    is_new = False
    job_id = None

    if row:
        job_id = row[0]
        if row[1] != job_dict['title'] or row[2] != job_dict['location'] or row[3] != job_dict['salary'] or row[4] != job_dict['description']:
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

    conn.commit()
    conn.close()
    return job_id, is_new, has_changed

def update_job_score(job_id, score):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE jobs SET relevancy_score = ? WHERE id = ?", (score, job_id))
    conn.commit()
    conn.close()

def mark_job_processed(job_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE jobs SET processed_for_resume = 1 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    init_db()
    prefs = get_preferences()
    if not prefs:
        print("No preferences configured. Exiting.")
        return

    candidate_profile, job_preferences, min_score = prefs
    companies = get_companies()

    print(f"Starting job scan. Companies to check: {len(companies)}")

    with StealthySession(headless=True, solve_cloudflare=True) as session:
        for company in companies:
            print(f"Scanning {company['name']} ({company['career_url']})...")
            try:
                page = session.fetch(company['career_url'])

                job_links = []
                for a in page.css('a'):
                    href = a.attrib.get('href')
                    if href and company['job_link_pattern'] in href:
                        full_url = urljoin(company['career_url'], href)
                        if full_url not in job_links:
                            job_links.append(full_url)

                print(f"-> Found {len(job_links)} potential job links.")

                for link in job_links:
                    print(f"   Analyzing: {link}")
                    job_page = session.fetch(link)

                    # Extract text content safely
                    body = job_page.css('body')
                    description = body[0].text if body else job_page.html_content

                    # Structured Data Extraction via AI
                    extraction_prompt = f"Extract the Job Title, Location, and Salary from this job description text. Return ONLY valid JSON like: {{\n  \"title\": \"...\",\n  \"location\": \"...\",\n  \"salary\": \"...\"\n}}\n\nText: {description[:3000]}"
                    ai_data = call_cloudflare_ai(extraction_prompt, "You are a data extraction AI that outputs strictly valid JSON.", json_mode=True)

                    title = ai_data.get('title', 'Unknown Title')
                    location = ai_data.get('location', 'Unknown Location')
                    salary = ai_data.get('salary', 'Not Specified')

                    job_dict = {
                        'company_id': company['id'],
                        'job_url': link,
                        'title': title,
                        'location': location,
                        'salary': salary,
                        'description': description
                    }

                    job_id, is_new, has_changed = upsert_job(job_dict)

                    if is_new or has_changed:
                        print(f"   -> {'New' if is_new else 'Updated'} Job detected. Scoring...")

                        score_prompt = f"""Evaluate the following job against the candidate profile and preferences.
Candidate Profile: {candidate_profile}
Preferences: {job_preferences}

Job Title: {title}
Job Location: {location}
Job Salary: {salary}
Job Description: {description[:3000]}

Score the relevancy from 0 to 100. Return ONLY a valid JSON object with a single key "score" containing the integer. Example: {{"score": 85}}"""

                        score_data = call_cloudflare_ai(score_prompt, "You are a recruitment AI that only outputs valid JSON.", json_mode=True)
                        score = score_data.get('score', 0)

                        update_job_score(job_id, score)
                        print(f"   -> Relevancy Score: {score}/100")

                        # Fetch the processed state to ensure we don't duplicate
                        conn = sqlite3.connect(DB_NAME)
                        processed = conn.execute("SELECT processed_for_resume FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]
                        conn.close()

                        if score >= min_score and not processed:
                            print("   -> Threshold met! Generating Cover Letter and Resume...")
                            gen_prompt = f"""Write a tailored Cover Letter and Resume for the following job.
Candidate Profile: {candidate_profile}

Job Details:
Title: {title}
Company: {company['name']}
Location: {location}
Description: {description[:3000]}

Please output the result formatted cleanly in Markdown. Start with the Cover Letter, followed by a page break separator, then the Resume."""

                            materials = call_cloudflare_ai(gen_prompt, "You are an expert executive career coach and resume writer.")

                            safe_title = re.sub(r'[^A-Za-z0-9_\-]', '_', title)
                            safe_company = re.sub(r'[^A-Za-z0-9_\-]', '_', company['name'])
                            filename = f"{OUTPUT_DIR}/{safe_company}_{safe_title}_{int(time.time())}.md"

                            with open(filename, "w", encoding="utf-8") as f:
                                f.write(materials)

                            mark_job_processed(job_id)
                            print(f"   -> Saved to {filename}")

            except Exception as e:
                print(f"Error scanning {company['name']}: {e}")

if __name__ == "__main__":
    main()
