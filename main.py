import os
import re
import time
from datetime import datetime
from src.config import OUTPUT_DIR, MAX_DESCRIPTION_LENGTH_FOR_AI
from src.database import Database
from src.ai import call_cloudflare_ai
from src.scraper import JobScraper

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"Starting job scan...")

    # Open single DB connection via context manager
    with Database() as db:
        prefs = db.get_preferences()
        if not prefs:
            print("No preferences configured. Exiting.")
            return

        candidate_profile, job_preferences, min_score = prefs
        companies = db.get_companies()

        print(f"Companies to check: {len(companies)}")

        with JobScraper(headless=True) as scraper:
            for company in companies:
                print(f"Scanning {company['name']} ({company['career_url']})...")
                try:
                    page = scraper.fetch(company['career_url'])
                    job_links = scraper.find_links(page, company['career_url'], company['job_link_pattern'])

                    print(f"-> Found {len(job_links)} potential job links.")

                    for link in job_links:
                        print(f"   Analyzing: {link}")
                        job_page = scraper.fetch(link)

                        # Extract text content safely
                        description = scraper.extract_text(job_page)
                        if not description:
                            description = "No description found."

                        # Structured Data Extraction via AI
                        trunc_desc = description[:MAX_DESCRIPTION_LENGTH_FOR_AI]
                        extraction_prompt = f"Extract the Job Title, Location, and Salary from this job description text. Return ONLY valid JSON like: {{\n  \"title\": \"...\",\n  \"location\": \"...\",\n  \"salary\": \"...\"\n}}\n\nText: {trunc_desc}"
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

                        # Use the persistent DB connection
                        job_id, is_new, has_changed = db.upsert_job(job_dict)

                        if is_new or has_changed:
                            print(f"   -> {'New' if is_new else 'Updated'} Job detected. Scoring...")

                            score_prompt = f"""Evaluate the following job against the candidate profile and preferences.
Candidate Profile: {candidate_profile}
Preferences: {job_preferences}

Job Title: {title}
Job Location: {location}
Job Salary: {salary}
Job Description: {trunc_desc}

Score the relevancy from 0 to 100. Return ONLY a valid JSON object with a single key "score" containing the integer. Example: {{"score": 85}}"""

                            score_data = call_cloudflare_ai(score_prompt, "You are a recruitment AI that only outputs valid JSON.", json_mode=True)
                            score = score_data.get('score', 0)

                            db.update_job_score(job_id, score)
                            print(f"   -> Relevancy Score: {score}/100")

                            # Check processed state using persistent connection method
                            processed = db.is_job_processed(job_id)

                            if score >= min_score and not processed:
                                print("   -> Threshold met! Generating Cover Letter and Resume...")
                                gen_prompt = f"""Write a tailored Cover Letter and Resume for the following job.
Candidate Profile: {candidate_profile}

Job Details:
Title: {title}
Company: {company['name']}
Location: {location}
Description: {trunc_desc}

Please output the result formatted cleanly in Markdown. Start with the Cover Letter, followed by a page break separator, then the Resume."""

                                materials = call_cloudflare_ai(gen_prompt, "You are an expert executive career coach and resume writer.")

                                safe_title = re.sub(r'[^A-Za-z0-9_\-]', '_', title)
                                safe_company = re.sub(r'[^A-Za-z0-9_\-]', '_', company['name'])
                                filename = f"{OUTPUT_DIR}/{safe_company}_{safe_title}_{int(time.time())}.md"

                                with open(filename, "w", encoding="utf-8") as f:
                                    f.write(materials)

                                db.mark_job_processed(job_id)
                                print(f"   -> Saved to {filename}")

                except Exception as e:
                    print(f"Error scanning {company['name']}: {e}")

if __name__ == "__main__":
    main()
