import requests
import json
from .config import CF_ACCOUNT_ID, CF_API_TOKEN, CF_GATEWAY_ID, MODEL_NAME

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
