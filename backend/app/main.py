import os
import uuid
import time
import asyncio
from typing import Dict, Optional, Any, List
from pydantic import BaseModel
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv, set_key

from app.agent import agent_graph

# Load environment variables
load_dotenv()

app = FastAPI(title="Newsletter Agent API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core Schemas
class StartRequest(BaseModel):
    goal: str
    mode: str = "hitl"  # "autonomous" or "hitl"
    llm_provider: str = "gemini"
    api_keys: Optional[Dict[str, str]] = None

class RespondRequest(BaseModel):
    thread_id: str
    action: str  # "approve" or "feedback"
    feedback: Optional[str] = ""

class SettingsRequest(BaseModel):
    gemini_key: Optional[str] = None
    openai_key: Optional[str] = None
    tavily_key: Optional[str] = None

# Background Graph execution runner
async def run_graph_background(thread_id: str, inputs: Optional[Dict[str, Any]] = None):
    """
    Runs the compiled LangGraph in a background event loop for state updates.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        print(f"[API Server] Background job running graph for thread: {thread_id}")
        await asyncio.to_thread(agent_graph.invoke, inputs, config)
        
        # If the graph paused at the HITL boundary interrupt, check if the mode is autonomous
        state = agent_graph.get_state(config)
        if len(state.next) > 0 and state.next[0] == "hitl":
            values = state.values
            if values.get("mode") == "autonomous":
                print(f"[API Server] Autonomous mode detected for thread {thread_id}. Auto-approving...")
                agent_graph.update_state(config, {
                    "approved": True,
                    "status": "sending"
                })
                # Re-invoke to run hitl and send nodes
                await asyncio.to_thread(agent_graph.invoke, None, config)
        print(f"[API Server] Background job paused or ended for thread: {thread_id}")
    except Exception as e:
        print(f"[API Server] Error executing graph in background: {e}")
        try:
            state = agent_graph.get_state(config)
            current_logs = state.values.get("logs", []) if state and state.values else []
            agent_graph.update_state(config, {
                "logs": current_logs + [f"Error occurred during execution: {str(e)}"],
                "status": "error"
            })
        except Exception as state_err:
            print(f"[API Server] Failed to update error state: {state_err}")

# Endpoints

@app.post("/api/start")
def start_agent(request: StartRequest, background_tasks: BackgroundTasks):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Extract keys from request or fallback to backend .env variables
    req_keys = request.api_keys or {}
    api_keys = {
        "gemini": req_keys.get("gemini") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "",
        "openai": req_keys.get("openai") or os.environ.get("OPENAI_API_KEY") or "",
        "tavily": req_keys.get("tavily") or os.environ.get("TAVILY_API_KEY") or ""
    }
    
    initial_state = {
        "goal": request.goal,
        "mode": request.mode,
        "logs": ["Initial goal received. Starting agent..."],
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
        "approved": False,
        "status": "planning",
        "llm_provider": request.llm_provider,
        "api_keys": api_keys,
        "start_time": time.time(),
        "metrics": {
            "duration_seconds": 0.0,
            "articles_count": 0,
            "scraped_count": 0,
            "search_count": 0,
            "char_count": 0,
            "revision_count": 0
        },
        "tool_outputs": []
    }
    
    # Initialize the checkpoint in the checkpointer
    agent_graph.update_state(config, initial_state)
    
    # Launch execution task in background so we return HTTP immediately
    background_tasks.add_task(run_graph_background, thread_id, initial_state)
    
    return {"thread_id": thread_id, "status": "planning"}

@app.get("/api/status/{thread_id}")
def get_status(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = agent_graph.get_state(config)
    
    if not state.values:
        raise HTTPException(status_code=404, detail="Thread state not found")
        
    values = state.values
    is_paused = len(state.next) > 0 and state.next[0] == "hitl"
    
    status = values.get("status", "planning")
    if is_paused and values.get("mode") == "hitl" and not values.get("approved"):
        status = "waiting_for_feedback"
        
    # Calculate elapsed time dynamically if not completed
    elapsed = 0.0
    start_time = values.get("start_time")
    if start_time:
        if status in ["completed", "error"]:
            elapsed = values.get("metrics", {}).get("duration_seconds", 0.0)
        else:
            elapsed = round(time.time() - start_time, 1)
            
    metrics = values.get("metrics", {}).copy()
    metrics["duration_seconds"] = elapsed
        
    return {
        "thread_id": thread_id,
        "goal": values.get("goal"),
        "mode": values.get("mode"),
        "status": status,
        "logs": values.get("logs", []),
        "newsletter_subject": values.get("newsletter_subject"),
        "newsletter_html": values.get("newsletter_html"),
        "newsletter_markdown": values.get("newsletter_markdown", ""),
        "revision_count": values.get("revision_count", 0),
        "approved": values.get("approved", False),
        "is_paused": is_paused,
        "llm_provider": values.get("llm_provider", "gemini"),
        "metrics": metrics,
        "tool_outputs": values.get("tool_outputs", []),
        "articles": [
            {
                "title": art.get("title"),
                "url": art.get("url"),
                "summary": art.get("summary")
            } for art in values.get("articles", [])
        ]
    }

@app.post("/api/respond")
def respond_agent(request: RespondRequest, background_tasks: BackgroundTasks):
    config = {"configurable": {"thread_id": request.thread_id}}
    state = agent_graph.get_state(config)
    
    if not state.values:
        raise HTTPException(status_code=404, detail="Thread state not found")
        
    values = state.values
    
    if request.action == "approve":
        agent_graph.update_state(config, {
            "approved": True,
            "status": "sending"
        })
        background_tasks.add_task(run_graph_background, request.thread_id, None)
        return {"status": "sending"}
        
    elif request.action == "feedback":
        agent_graph.update_state(config, {
            "approved": False,
            "user_feedback": request.feedback,
            "status": "writing"
        })
        background_tasks.add_task(run_graph_background, request.thread_id, None)
        return {"status": "writing"}
        
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'feedback'.")

@app.get("/api/settings")
def get_settings():
    return {
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "tavily_configured": bool(os.environ.get("TAVILY_API_KEY"))
    }

@app.post("/api/settings")
def save_settings(request: SettingsRequest):
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    
    try:
        if not os.path.exists(env_path):
            with open(env_path, "w") as f:
                f.write("")
                
        if request.gemini_key:
            set_key(env_path, "GEMINI_API_KEY", request.gemini_key)
            os.environ["GEMINI_API_KEY"] = request.gemini_key
        if request.openai_key:
            set_key(env_path, "OPENAI_API_KEY", request.openai_key)
            os.environ["OPENAI_API_KEY"] = request.openai_key
        if request.tavily_key:
            set_key(env_path, "TAVILY_API_KEY", request.tavily_key)
            os.environ["TAVILY_API_KEY"] = request.tavily_key
            
        return {"message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")

# Mount static file server for outputs
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
output_dir = os.path.join(backend_dir, "output")
os.makedirs(output_dir, exist_ok=True)
app.mount("/output", StaticFiles(directory=output_dir), name="output")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
