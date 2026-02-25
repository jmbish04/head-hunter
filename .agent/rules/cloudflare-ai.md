# Cloudflare AI & Gateway Rules

1. **Routing**: All generative AI requests MUST route through Cloudflare AI Gateway.
2. **Endpoint Format**: `https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_name}/workers-ai/{model_name}`.
3. **Models**: Favor `@cf/meta/llama-3.1-8b-instruct` for fast, JSON-bound text extraction and scoring.
4. **Fallbacks**: Ensure `requests` wraps external calls in `try/except` blocks to prevent the scraper loop from crashing if the AI Gateway rate limits or times out.
