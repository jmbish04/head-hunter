from scrapling.fetchers import StealthySession
from urllib.parse import urljoin

class JobScraper:
    def __init__(self, headless=True):
        self.session = StealthySession(headless=headless, solve_cloudflare=True)

    def __enter__(self):
        self.session.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.__exit__(exc_type, exc_val, exc_tb)

    def fetch(self, url):
        return self.session.fetch(url)

    def find_links(self, page, base_url, pattern):
        job_links = []
        # 'page' here is a response object from StealthySession which has .css()
        for a in page.css('a'):
            href = a.attrib.get('href')
            if href and pattern in href:
                full_url = urljoin(base_url, href)
                if full_url not in job_links:
                    job_links.append(full_url)
        return job_links

    def extract_text(self, page):
        body = page.css('body')
        # Assuming .text property or similar exists on the element
        # Based on main.py: body[0].text
        if body:
            return body[0].text
        # Fallback to html_content if body extraction fails
        return getattr(page, 'html_content', '')
