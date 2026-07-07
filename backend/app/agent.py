import os
import json
import time
from typing import Annotated, Dict, List, TypedDict, Any
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.tools import (
    get_llm, 
    search_web, 
    scrape_article, 
    summarize_article, 
    build_newsletter_html, 
    build_newsletter_markdown
)

# Define State Structure
class Article(TypedDict):
    title: str
    url: str
    snippet: str
    content: str
    summary: str

class ToolOutput(TypedDict):
    tool: str
    input: str
    output: str

class AgentMetrics(TypedDict):
    duration_seconds: float
    articles_count: int
    scraped_count: int
    search_count: int
    char_count: int
    revision_count: int

class AgentState(TypedDict):
    goal: str
    mode: str  # "autonomous" or "hitl"
    logs: List[str]
    plan: str
    search_queries: List[str]
    articles: List[Article]
    summaries: List[str]
    newsletter_subject: str
    newsletter_intro: str
    newsletter_outro: str
    newsletter_html: str
    newsletter_markdown: str
    critique: str
    revision_count: int
    user_feedback: str
    approved: bool
    status: str  # "planning", "researching", "summarizing", "writing", "reviewing", "waiting_for_feedback", "sending", "completed"
    llm_provider: str
    api_keys: Dict[str, str]
    metrics: AgentMetrics
    tool_outputs: List[ToolOutput]
    start_time: float

# --- Nodes ---

def plan_node(state: AgentState) -> Dict[str, Any]:
    goal = state.get("goal")
    llm_provider = state.get("llm_provider", "gemini")
    api_key = state.get("api_keys", {}).get(llm_provider)
    
    log_msg = "Planning research strategy based on goal..."
    print(f"[Agent] {log_msg}")
    
    # Initialize start time if not present
    start_time = state.get("start_time") or time.time()
    
    try:
        llm = get_llm(llm_provider, api_key)
        system = (
            "You are an expert search planner. Given a newsletter goal, "
            "formulate 2 to 3 distinct search queries to find the most relevant, "
            "up-to-date, and accurate articles and updates. "
            "Format your response as a simple list of queries, one per line. Do not write any other text."
        )
        human = f"Newsletter Goal: {goal}\n\nSearch Queries:"
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        queries = [q.strip().strip("-").strip("*").strip() for q in response.content.splitlines() if q.strip()]
        queries = [q for q in queries if q][:3]
        if not queries:
            queries = [goal]
    except Exception as e:
        print(f"[Agent Plan Step] Error: {e}")
        queries = [goal]
        
    res_msg = f"Formulated search queries: {queries}"
    
    tool_log = {
        "tool": "Search Planner",
        "input": f"Goal: {goal}",
        "output": f"Queries: {queries}"
    }
    
    metrics = state.get("metrics") or {
        "duration_seconds": 0.0,
        "articles_count": 0,
        "scraped_count": 0,
        "search_count": 0,
        "char_count": 0,
        "revision_count": 0
    }
    metrics["search_count"] = len(queries)
    
    return {
        "search_queries": queries,
        "logs": state.get("logs", []) + [log_msg, res_msg],
        "status": "researching",
        "tool_outputs": state.get("tool_outputs", []) + [tool_log],
        "metrics": metrics,
        "start_time": start_time
    }

def research_node(state: AgentState) -> Dict[str, Any]:
    queries = state.get("search_queries", [])
    tavily_key = state.get("api_keys", {}).get("tavily")
    tool_outputs = state.get("tool_outputs", [])
    
    log_msg = f"Researching: Querying web engines for {len(queries)} subjects..."
    logs = state.get("logs", []) + [log_msg]
    print(f"[Agent] {log_msg}")
    
    all_results = []
    seen_urls = set()
    
    for q in queries:
        results = search_web(q, max_results=4, api_key=tavily_key)
        tool_outputs.append({
            "tool": "Web Search (Tavily/DDG)",
            "input": f"Query: {q}",
            "output": f"Found {len(results)} search results."
        })
        for r in results:
            url = r.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
                
    selected_results = all_results[:6]
    
    sc_msg = f"Found {len(selected_results)} articles. Scraping full content..."
    logs.append(sc_msg)
    print(f"[Agent] {sc_msg}")
    
    articles = []
    scraped_count = 0
    
    for r in selected_results:
        content = scrape_article(r["url"])
        char_len = len(content)
        tool_outputs.append({
            "tool": "BeautifulSoup Scraper",
            "input": f"URL: {r['url']}",
            "output": f"Scraped content: {char_len} characters."
        })
        if char_len > 0:
            scraped_count += 1
            
        articles.append({
            "title": r.get("title", "Untitled Article"),
            "url": r.get("url", ""),
            "snippet": r.get("snippet", ""),
            "content": content,
            "summary": ""
        })
        
    done_msg = f"Scraping completed. Gathered text from {len(articles)} sources."
    logs.append(done_msg)
    
    metrics = state.get("metrics")
    metrics["articles_count"] = len(articles)
    metrics["scraped_count"] = scraped_count
    
    return {
        "articles": articles,
        "logs": logs,
        "status": "summarizing",
        "tool_outputs": tool_outputs,
        "metrics": metrics
    }

def summarize_node(state: AgentState) -> Dict[str, Any]:
    articles = state.get("articles", [])
    goal = state.get("goal")
    llm_provider = state.get("llm_provider", "gemini")
    api_key = state.get("api_keys", {}).get(llm_provider)
    tool_outputs = state.get("tool_outputs", [])
    
    log_msg = f"Summarizing {len(articles)} fetched articles..."
    logs = state.get("logs", []) + [log_msg]
    print(f"[Agent] {log_msg}")
    
    try:
        llm = get_llm(llm_provider, api_key)
    except Exception as e:
        err_msg = f"Error initializing LLM: {e}"
        logs.append(err_msg)
        return {"logs": logs, "status": "completed"}
        
    summaries = []
    updated_articles = []
    
    for art in articles:
        summary = summarize_article(llm, art["title"], art["snippet"], art["content"], goal)
        
        tool_outputs.append({
            "tool": "LLM Article Summarizer",
            "input": f"Article: {art['title']}\nGoal: {goal}",
            "output": f"Summary: {summary}"
        })
        
        art_copy = art.copy()
        art_copy["summary"] = summary
        updated_articles.append(art_copy)
        summaries.append(f"Title: {art['title']}\nSummary: {summary}")
        
    done_msg = f"Summarized {len(updated_articles)} articles contextually."
    logs.append(done_msg)
    
    return {
        "articles": updated_articles,
        "summaries": summaries,
        "logs": logs,
        "status": "writing",
        "tool_outputs": tool_outputs
    }

def write_node(state: AgentState) -> Dict[str, Any]:
    summaries = state.get("summaries")
    goal = state.get("goal")
    critique = state.get("critique", "")
    user_feedback = state.get("user_feedback", "")
    llm_provider = state.get("llm_provider", "gemini")
    api_key = state.get("api_keys", {}).get(llm_provider)
    tool_outputs = state.get("tool_outputs", [])
    
    revision_count = state.get("revision_count", 0)
    rev_desc = f" (Revision #{revision_count})" if revision_count > 0 else ""
    
    log_msg = f"Drafting newsletter editorial content{rev_desc}..."
    logs = state.get("logs", []) + [log_msg]
    print(f"[Agent] {log_msg}")
    
    try:
        llm = get_llm(llm_provider, api_key)
        system = (
            "You are an expert newsletter writer and curator. Your job is to draft the editorial text "
            "for a tech newsletter based on curated article summaries.\n"
            "You must output a JSON object with the following fields:\n"
            "- 'subject': A catchy, click-worthy email subject line.\n"
            "- 'editorial_intro': A high-quality introduction paragraph (3-4 sentences) that sets the stage, "
            "enthuses readers, and describes the core theme.\n"
            "- 'editorial_outro': A high-quality wrapping paragraph (2-3 sentences) summarizing the digest, "
            "urging engagement, and signing off.\n"
            "Do NOT write any HTML or surrounding Markdown. Return ONLY valid JSON."
        )
        
        summaries_text = "\n\n".join(summaries)
        
        feedback_section = ""
        if critique:
            feedback_section += f"\n\nSelf-Critique Review Feedback to address:\n{critique}"
        if user_feedback:
            feedback_section += f"\n\nUser Feedback to address:\n{user_feedback}"
            
        human = (
            f"Newsletter Goal: {goal}\n\n"
            f"Curated Article Summaries:\n{summaries_text}"
            f"{feedback_section}\n\n"
            f"Draft the JSON content:"
        )
        
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        content_text = response.content.strip()
        
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]
        content_text = content_text.strip()
        
        data = json.loads(content_text)
        subject = data.get("subject", f"Weekly Digest: {goal}")
        intro = data.get("editorial_intro", "")
        outro = data.get("editorial_outro", "")
    except Exception as e:
        print(f"[Agent Write Node] Writing error: {e}. Using fallbacks.")
        subject = f"Weekly Digest: {goal}"
        intro = f"Welcome to this week's AI insights. Here are the top stories on: '{goal}'."
        outro = "Thanks for reading. See you next week!"
        
    # Stitch both HTML and Markdown together
    html = build_newsletter_html(subject, state.get("articles", []), intro, outro)
    markdown = build_newsletter_markdown(subject, state.get("articles", []), intro, outro)
    
    tool_outputs.append({
        "tool": "Newsletter Compiler",
        "input": f"Subject: {subject}\nIntro length: {len(intro)} chars",
        "output": f"Compiled HTML ({len(html)} chars) & Markdown ({len(markdown)} chars)."
    })
    
    logs.append("Generated draft with newsletter subject, intro, and outro.")
    
    metrics = state.get("metrics")
    metrics["char_count"] = len(html)
    
    return {
        "newsletter_subject": subject,
        "newsletter_intro": intro,
        "newsletter_outro": outro,
        "newsletter_html": html,
        "newsletter_markdown": markdown,
        "logs": logs,
        "status": "reviewing",
        "user_feedback": "",
        "tool_outputs": tool_outputs,
        "metrics": metrics
    }

def review_node(state: AgentState) -> Dict[str, Any]:
    goal = state.get("goal")
    subject = state.get("newsletter_subject")
    html = state.get("newsletter_html")
    llm_provider = state.get("llm_provider", "gemini")
    api_key = state.get("api_keys", {}).get(llm_provider)
    revision_count = state.get("revision_count", 0)
    tool_outputs = state.get("tool_outputs", [])
    
    log_msg = "Performing self-reflection and quality critique..."
    logs = state.get("logs", []) + [log_msg]
    print(f"[Agent] {log_msg}")
    
    if revision_count >= 2:
        skip_msg = "Maximum self-critiques reached. Proceeding to review."
        logs.append(skip_msg)
        status = "waiting_for_feedback" if state.get("mode") == "hitl" and not state.get("approved") else "sending"
        return {
            "critique": "",
            "logs": logs,
            "status": status
        }
        
    try:
        llm = get_llm(llm_provider, api_key)
        system = (
            "You are a strict editorial critic. Evaluate the newsletter subject line and draft HTML against the user's goal.\n"
            "Assess:\n"
            "1. Alignment with goal.\n"
            "2. Readability, engaging tone, and flow.\n"
            "3. Formatting bugs or raw summaries.\n\n"
            "You must output a JSON object with the fields:\n"
            "- 'status': 'PASS' if the newsletter matches high standards, or 'REVISE' if adjustments are needed.\n"
            "- 'critique': A short bullet-pointed list of issues to fix. Keep it empty if status is PASS.\n"
            "Return ONLY valid JSON."
        )
        human = (
            f"Goal: {goal}\n"
            f"Subject: {subject}\n"
            f"HTML Draft snippet:\n{html[:2000]}\n\n"
            f"Critique and evaluate:"
        )
        
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        content_text = response.content.strip()
        if content_text.startswith("```json"):
            content_text = content_text[7:]
        if content_text.endswith("```"):
            content_text = content_text[:-3]
        content_text = content_text.strip()
        
        data = json.loads(content_text)
        critique_status = data.get("status", "PASS")
        critique = data.get("critique", "")
    except Exception as e:
        print(f"[Agent Review Node] Critique error: {e}. Skipping self-critique.")
        critique_status = "PASS"
        critique = ""
        
    tool_outputs.append({
        "tool": "Self-Critique Evaluator",
        "input": f"Revision index: {revision_count}",
        "output": f"Critiqe decision: {critique_status}.\nCritique notes: {critique or 'None'}"
    })
    
    metrics = state.get("metrics")
    metrics["revision_count"] = revision_count
    
    if critique_status == "REVISE" and critique:
        logs.append(f"Critique result: REVISE. Suggestions: {critique}")
        return {
            "critique": critique,
            "revision_count": revision_count + 1,
            "logs": logs,
            "status": "writing",
            "tool_outputs": tool_outputs,
            "metrics": metrics
        }
    else:
        logs.append("Critique result: PASS. Newsletter meets quality guidelines.")
        status = "waiting_for_feedback" if state.get("mode") == "hitl" and not state.get("approved") else "sending"
        return {
            "critique": "",
            "logs": logs,
            "status": status,
            "tool_outputs": tool_outputs,
            "metrics": metrics
        }

def hitl_node(state: AgentState) -> Dict[str, Any]:
    approved = state.get("approved", False)
    feedback = state.get("user_feedback", "")
    logs = state.get("logs", [])
    
    if approved:
        log_msg = "User approved the newsletter. Moving to distribution..."
        logs.append(log_msg)
        return {"logs": logs, "status": "sending"}
    elif feedback:
        log_msg = f"User rejected draft. Feedback received: '{feedback}'."
        logs.append(log_msg)
        
        metrics = state.get("metrics")
        metrics["revision_count"] = state.get("revision_count", 0) + 1
        
        return {
            "logs": logs,
            "status": "writing",
            "revision_count": state.get("revision_count", 0) + 1,
            "metrics": metrics
        }
    return {}

def send_node(state: AgentState) -> Dict[str, Any]:
    subject = state.get("newsletter_subject", "Curated Newsletter")
    html = state.get("newsletter_html", "")
    markdown = state.get("newsletter_markdown", "")
    logs = state.get("logs", [])
    
    log_msg = "Distributing newsletter (Simulated sending)..."
    logs.append(log_msg)
    print(f"[Agent] {log_msg}")
    
    # Save the output files locally
    import time
    timestamp = int(time.time())
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Save HTML
    html_filename = f"newsletter_{timestamp}.html"
    html_path = os.path.join(output_dir, html_filename)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
        
    # Save Markdown
    md_filename = f"newsletter_{timestamp}.md"
    md_path = os.path.join(output_dir, md_filename)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown)
        
    # Save Subject Line
    subject_filename = f"newsletter_{timestamp}_subject.txt"
    subject_path = os.path.join(output_dir, subject_filename)
    with open(subject_path, "w", encoding="utf-8") as f:
        f.write(subject)
        
    saved_msg = f"Newsletter successfully saved locally:\n- HTML: output/{html_filename}\n- Markdown: output/{md_filename}"
    logs.append(saved_msg)
    print(f"[Agent] {saved_msg}")
    
    # Calculate duration
    start_time = state.get("start_time") or time.time()
    elapsed = time.time() - start_time
    
    metrics = state.get("metrics")
    metrics["duration_seconds"] = round(elapsed, 1)
    
    return {
        "logs": logs + ["Execution completed successfully."],
        "status": "completed",
        "approved": True,
        "metrics": metrics
    }

# --- Routing Logics ---

def review_routing(state: AgentState):
    if state.get("status") == "writing":
        return "write"
    return "hitl"

def hitl_routing(state: AgentState):
    if state.get("status") == "writing":
        return "write"
    return "send"

# --- Building the Graph ---

workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("plan", plan_node)
workflow.add_node("research", research_node)
workflow.add_node("summarize", summarize_node)
workflow.add_node("write", write_node)
workflow.add_node("review", review_node)
workflow.add_node("hitl", hitl_node)
workflow.add_node("send", send_node)

# Set entry point
workflow.set_entry_point("plan")

# Set standard edges
workflow.add_edge("plan", "research")
workflow.add_edge("research", "summarize")
workflow.add_edge("summarize", "write")
workflow.add_edge("write", "review")

# Add conditional edges
workflow.add_conditional_edges(
    "review",
    review_routing,
    {
        "write": "write",
        "hitl": "hitl"
    }
)

workflow.add_conditional_edges(
    "hitl",
    hitl_routing,
    {
        "write": "write",
        "send": "send"
    }
)

workflow.add_edge("send", END)

# Compile graph with memory checkpointing
memory = MemorySaver()
agent_graph = workflow.compile(
    checkpointer=memory,
    interrupt_before=["hitl"]
)

def run_newsletter_agent(goal: str) -> dict:
    """
    Executes the newsletter agent fully autonomously from start to finish.
    One function call that does the entire job.
    """
    import uuid
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "goal": goal,
        "mode": "autonomous",
        "logs": ["Starting agent autonomously via run_newsletter_agent..."],
        "plan": "",
        "search_queries": [],
        "articles": [],
        "summaries": [],
        "newsletter_subject": "",
        "newsletter_intro": "",
        "newsletter_outro": "",
        "newsletter_html": "",
        "newsletter_markdown": "",
        "critique": "",
        "revision_count": 0,
        "user_feedback": "",
        "approved": True, 
        "status": "planning",
        "llm_provider": "gemini",
        "api_keys": {
            "gemini": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "",
            "openai": os.environ.get("OPENAI_API_KEY") or "",
            "tavily": os.environ.get("TAVILY_API_KEY") or ""
        },
        "metrics": {
            "duration_seconds": 0.0,
            "articles_count": 0,
            "scraped_count": 0,
            "search_count": 0,
            "char_count": 0,
            "revision_count": 0
        },
        "tool_outputs": [],
        "start_time": time.time()
    }
    
    agent_graph.invoke(initial_state, config)
    
    state = agent_graph.get_state(config)
    if len(state.next) > 0 and state.next[0] == "hitl":
        agent_graph.update_state(config, {"approved": True, "status": "sending"})
        agent_graph.invoke(None, config)
        
    final_state = agent_graph.get_state(config).values
    return final_state
