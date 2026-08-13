"""Optional external research; disabled without explicit Tavily configuration."""
import requests
import config

class WebSearch:
    def search(self, query: str):
        if not config.TAVILY_API_KEY:
            return {"status":"unavailable","message":"Tavily is not configured; no external market claims were made.","results":[]}
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key":config.TAVILY_API_KEY,"query":query,"max_results":config.TAVILY_MAX_RESULTS,"search_depth":"advanced"},
                          timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        return {"status":"success","results":r.json().get("results",[])}
