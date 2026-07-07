import os
import httpx
from bs4 import BeautifulSoup
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

def get_llm(provider: str = None, api_key: str = None):
    """
    Returns the appropriate LLM instance based on the provider and API key.
    """
    if not provider:
        if os.environ.get("GEMINI_API_KEY"):
            provider = "gemini"
        elif os.environ.get("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "gemini"  # Default fallback
            
    key = api_key or os.environ.get(f"{provider.upper()}_API_KEY")
    if not key:
        # Check alternative common names
        if provider == "gemini":
            key = os.environ.get("GOOGLE_API_KEY")
            
    if not key:
        raise ValueError(f"API key for {provider.upper()} is missing. Please set it in Settings.")

    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=key,
            temperature=0.2
        )
    elif provider == "openai":
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=key,
            temperature=0.2
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")

def search_web(query: str, max_results: int = 5, api_key: str = None) -> list:
    """
    Searches the web using Tavily (if API key is present) or falls back to DuckDuckGo.
    Returns list of dicts: [{"title": ..., "url": ..., "snippet": ...}]
    """
    tavily_key = api_key or os.environ.get("TAVILY_API_KEY")
    
    if tavily_key:
        try:
            print(f"[Search Tool] Using Tavily Search for query: '{query}'")
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "max_results": max_results,
                    "include_raw_content": False
                },
                timeout=10.0
            )
            if response.status_code == 200:
                results = response.json().get("results", [])
                return [{"title": r.get("title", "Untitled"), "url": r.get("url", ""), "snippet": r.get("content", "")} for r in results]
            else:
                print(f"[Search Tool] Tavily API returned status {response.status_code}. Falling back to DuckDuckGo.")
        except Exception as e:
            print(f"[Search Tool] Tavily Search failed: {e}. Falling back to DuckDuckGo.")
            
    # Fallback to DuckDuckGo Search (Free, no API key required)
    try:
        print(f"[Search Tool] Using DuckDuckGo Search for query: '{query}'")
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [{"title": r.get("title", "Untitled"), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in results]
    except Exception as e:
        print(f"[Search Tool] DuckDuckGo search failed: {e}")
        return []

def scrape_article(url: str) -> str:
    """
    Fetches the web page content and scrapes readable text, stripping tags.
    """
    if not url:
        return ""
    try:
        print(f"[Scrape Tool] Scraping article: {url}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        # Use httpx to scrape
        response = httpx.get(url, headers=headers, timeout=8.0, follow_redirects=True)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            # Remove scripts, styles, header, footer, etc.
            for tag in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "iframe"]):
                tag.decompose()
            
            # Get text
            text = soup.get_text(separator=" ")
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = " ".join(chunk for chunk in chunks if chunk)
            
            # Return snippet (limit to 3500 chars to avoid prompt bloat)
            return clean_text[:3500]
    except Exception as e:
        print(f"[Scrape Tool] Failed to scrape {url}: {e}")
    return ""

def summarize_article(llm, title: str, snippet: str, content: str, goal: str) -> str:
    """
    Calls the LLM to summarize the article contextually, focusing on relevancy to the newsletter goal.
    """
    text_to_summarize = content if content and len(content) > 100 else snippet
    if not text_to_summarize:
        return "No content available to summarize."
        
    system_prompt = (
        "You are an expert tech newsletter researcher. Your task is to summarize the provided article "
        "relevantly, keeping the newsletter's target goal in mind. "
        "Provide a concise, 2-3 sentence summary that highlights the most critical, interesting, and "
        "accurate facts. Do not write introductory or meta text like 'This article discusses...'; "
        "write directly for the newsletter readers."
    )
    
    human_prompt = (
        f"Newsletter Goal: {goal}\n\n"
        f"Article Title: {title}\n\n"
        f"Article Content/Excerpt:\n{text_to_summarize}\n\n"
        f"Contextual Summary:"
    )
    
    try:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        response = llm.invoke(messages)
        return response.content.strip()
    except Exception as e:
        print(f"[Summarizer Tool] Summarization failed: {e}")
        return snippet[:250] + "..." if len(snippet) > 250 else snippet

def build_newsletter_html(subject: str, articles_with_summaries: list, intro: str = "", outro: str = "") -> str:
    """
    Creates a responsive, modern HTML newsletter email.
    articles_with_summaries is a list of dicts: [{"title": ..., "url": ..., "summary": ...}]
    """
    articles_html = ""
    for idx, art in enumerate(articles_with_summaries, 1):
        articles_html += f"""
        <!-- Article Card -->
        <div style="margin-bottom: 24px; padding: 20px; background-color: #fcfcfd; border: 1px solid #eef0f3; border-radius: 8px;">
            <span style="font-size: 11px; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.05em; display: inline-block; margin-bottom: 6px;">Article #{idx}</span>
            <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 17px; color: #111827; font-family: inherit;">
                <a href="{art.get('url', '#')}" target="_blank" style="color: #111827; text-decoration: none; font-weight: 700;">
                    {art.get('title', 'Untitled Article')}
                </a>
            </h3>
            <p style="margin: 0 0 12px 0; font-size: 14px; line-height: 1.6; color: #4b5563;">
                {art.get('summary', 'No summary available.')}
            </p>
            <a href="{art.get('url', '#')}" target="_blank" style="font-size: 13px; font-weight: 600; color: #4f46e5; text-decoration: none; display: inline-flex; align-items: center;">
                Read full article &rarr;
            </a>
        </div>
        """

    intro_content = intro if intro else "Welcome to this week's curated newsletter! Our autonomous AI agent has scanned the web, analyzed the latest updates, and summarized the most critical news items just for you. Here are the top stories you should know about:"
    outro_content = outro if outro else "Thank you for reading this week's digest. Stay tuned for more updates next week!"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f3f4f6; padding: 40px 10px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%); padding: 40px 20px; color: #ffffff;">
                            <p style="margin: 0 0 8px 0; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #c7d2fe;">Weekly Digest</p>
                            <h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.025em; line-height: 1.2;">
                                {subject}
                            </h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 30px 30px 10px 30px; background-color: #ffffff;">
                            <p style="margin-top: 0; margin-bottom: 24px; font-size: 15px; line-height: 1.6; color: #374151;">
                                {intro_content}
                            </p>
                            
                            {articles_html}
                            
                            <p style="margin-top: 20px; margin-bottom: 0; font-size: 15px; line-height: 1.6; color: #374151;">
                                {outro_content}
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px; background-color: #f9fafb; border-top: 1px solid #f3f4f6; text-align: center;">
                            <p style="margin: 0 0 8px 0; font-size: 13px; color: #6b7280; font-weight: 600;">Autonomous Newsletter Agent</p>
                            <p style="margin: 0 0 16px 0; font-size: 11px; line-height: 1.5; color: #9ca3af;">
                                Generated autonomously based on goals using LangGraph and LLM reasoning.
                            </p>
                            <div style="border-top: 1px solid #e5e7eb; padding-top: 16px; font-size: 11px; color: #9ca3af;">
                                You are receiving this because you subscribed to our weekly AI insights.<br>
                                <a href="#" style="color: #6366f1; text-decoration: underline;">Unsubscribe</a> &bull; <a href="#" style="color: #6366f1; text-decoration: underline;">View Online</a>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
    return html_content
