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
        response = httpx.get(url, headers=headers, timeout=8.0, follow_redirects=True)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "header", "footer", "nav", "aside", "noscript", "iframe"]):
                tag.decompose()
            
            text = soup.get_text(separator=" ")
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = " ".join(chunk for chunk in chunks if chunk)
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
    Creates a responsive, modern HTML newsletter email with high-fidelity aesthetics.
    """
    articles_html = ""
    for idx, art in enumerate(articles_with_summaries, 1):
        articles_html += f"""
        <!-- Article Card -->
        <div style="margin-bottom: 24px; padding: 22px; background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.02);">
            <span style="font-size: 11px; font-weight: 800; color: #4f46e5; text-transform: uppercase; letter-spacing: 0.05em; display: inline-block; margin-bottom: 8px;">Article #{idx}</span>
            <h3 style="margin-top: 0; margin-bottom: 10px; font-size: 18px; color: #111827; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.35;">
                <a href="{art.get('url', '#')}" target="_blank" style="color: #111827; text-decoration: none; font-weight: 700; hover: text-decoration: underline;">
                    {art.get('title', 'Untitled Article')}
                </a>
            </h3>
            <p style="margin: 0 0 16px 0; font-size: 14.5px; line-height: 1.6; color: #374151;">
                {art.get('summary', 'No summary available.')}
            </p>
            <a href="{art.get('url', '#')}" target="_blank" style="font-size: 13.5px; font-weight: 600; color: #4f46e5; text-decoration: none; display: inline-flex; align-items: center;">
                Read full coverage <span style="margin-left: 4px;">&rarr;</span>
            </a>
        </div>
        """

    intro_content = intro if intro else "Welcome to this week's newsletter! Our AI agent has scanned the web, analyzed the latest updates, and summarized the most critical news items just for you."
    outro_content = outro if outro else "Thank you for reading this week's digest. Stay tuned for more updates next week!"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f9fafb; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f9fafb; padding: 40px 10px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05); border: 1px solid #f3f4f6;">
                    <!-- Header -->
                    <tr>
                        <td align="center" style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 48px 30px; color: #ffffff;">
                            <p style="margin: 0 0 10px 0; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: #e0e7ff;">AI Agent Insights</p>
                            <h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.03em; line-height: 1.2;">
                                {subject}
                            </h1>
                        </td>
                    </tr>
                    <!-- Content -->
                    <tr>
                        <td style="padding: 35px 35px 15px 35px; background-color: #ffffff;">
                            <p style="margin-top: 0; margin-bottom: 28px; font-size: 15.5px; line-height: 1.65; color: #374151; font-style: italic; border-left: 3px solid #6366f1; padding-left: 14px;">
                                {intro_content}
                            </p>
                            
                            {articles_html}
                            
                            <p style="margin-top: 24px; margin-bottom: 12px; font-size: 15px; line-height: 1.65; color: #374151;">
                                {outro_content}
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 35px; background-color: #f9fafb; border-top: 1px solid #f3f4f6; text-align: center;">
                            <p style="margin: 0 0 8px 0; font-size: 13px; color: #4b5563; font-weight: 700;">Autonomous Newsletter Agent</p>
                            <p style="margin: 0 0 20px 0; font-size: 11.5px; line-height: 1.5; color: #6b7280;">
                                Created autonomously based on goals using LangGraph.
                            </p>
                            <div style="border-top: 1px solid #e5e7eb; padding-top: 20px; font-size: 11px; color: #9ca3af;">
                                You are receiving this because you subscribed to our weekly AI insights.<br>
                                <a href="#" style="color: #4f46e5; text-decoration: none; font-weight: 600;">Unsubscribe</a> &bull; <a href="#" style="color: #4f46e5; text-decoration: none; font-weight: 600;">View Online</a>
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

def build_newsletter_markdown(subject: str, articles_with_summaries: list, intro: str = "", outro: str = "") -> str:
    """
    Creates a clean, formatted Markdown document representing the newsletter.
    """
    md_content = f"# {subject}\n\n"
    
    if intro:
        md_content += f"> *{intro}*\n\n"
    else:
        md_content += "> *Welcome to this week's AI insights digest compiled autonomously by our LangGraph newsletter agent.*\n\n"
        
    md_content += "---\n\n"
    
    for idx, art in enumerate(articles_with_summaries, 1):
        title = art.get('title', 'Untitled Article')
        url = art.get('url', '#')
        summary = art.get('summary', 'No summary available.')
        
        md_content += f"### {idx}. [{title}]({url})\n"
        md_content += f"{summary}\n\n"
        md_content += f"[Read full coverage]({url})\n\n"
        md_content += "---\n\n"
        
    if outro:
        md_content += f"{outro}\n\n"
    else:
        md_content += "Thanks for reading! Stay tuned for more weekly updates.\n\n"
        
    md_content += "*Generated autonomously by Newsletter Agent (LangGraph & LLM Reasoner).*\n"
    return md_content
