import os

# Environment Configuration
CF_ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "your_account_id")
CF_API_TOKEN = os.environ.get("CF_API_TOKEN", "your_api_token")
CF_GATEWAY_ID = os.environ.get("CF_GATEWAY_ID", "my-ai-gateway")
MODEL_NAME = "@cf/meta/llama-3.1-8b-instruct"
DB_NAME = "job_scraper.db"
OUTPUT_DIR = "./applications"
MAX_DESCRIPTION_LENGTH_FOR_AI = 3000
