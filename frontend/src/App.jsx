import React, { useState, useEffect, useRef } from 'react';
import { 
  Sparkles, 
  Settings, 
  Send, 
  RotateCw, 
  Check, 
  X, 
  FileText, 
  Code, 
  AlertTriangle, 
  Eye, 
  Cpu, 
  Terminal,
  Settings2,
  Download,
  ChevronDown,
  ChevronUp,
  Clock,
  BookOpen,
  History,
  FileCode,
  Info
} from 'lucide-react';
import './App.css';

const API_BASE = 'http://127.0.0.1:8000';

function App() {
  // Goal and config states
  const [goal, setGoal] = useState("Create a weekly newsletter on latest AI agent news and send it to our subscribers.");
  const [mode, setMode] = useState("hitl"); // "hitl" or "autonomous"
  const [llmProvider, setLlmProvider] = useState("gemini");
  
  // Settings Modal states
  const [showSettings, setShowSettings] = useState(false);
  const [geminiKey, setGeminiKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [tavilyKey, setTavilyKey] = useState("");
  const [backendKeysStatus, setBackendKeysStatus] = useState({
    gemini_configured: false,
    openai_configured: false,
    tavily_configured: false
  });

  // Runner States
  const [threadId, setThreadId] = useState(null);
  const [status, setStatus] = useState("idle"); // idle, planning, researching, summarizing, writing, reviewing, waiting_for_feedback, sending, completed, error
  const [logs, setLogs] = useState([]);
  const [newsletterSubject, setNewsletterSubject] = useState("");
  const [newsletterHtml, setNewsletterHtml] = useState("");
  const [newsletterMarkdown, setNewsletterMarkdown] = useState("");
  const [articles, setArticles] = useState([]);
  const [revisionCount, setRevisionCount] = useState(0);
  const [approved, setApproved] = useState(false);
  const [critique, setCritique] = useState("");
  
  // Advanced State Fields
  const [metrics, setMetrics] = useState({
    duration_seconds: 0.0,
    articles_count: 0,
    scraped_count: 0,
    search_count: 0,
    char_count: 0,
    revision_count: 0
  });
  const [toolOutputs, setToolOutputs] = useState([]);
  
  // Accordion toggle state
  const [openToolIndex, setOpenToolIndex] = useState(null);

  // Tabs: preview, code, markdown, tool-logs
  const [activeTab, setActiveTab] = useState("preview"); 
  const [feedback, setFeedback] = useState("");
  const [showFeedbackForm, setShowFeedbackForm] = useState(false);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);
  
  const logsEndRef = useRef(null);

  // Auto-scroll logs terminal
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Load configured keys on mount
  useEffect(() => {
    fetchKeysStatus();
  }, []);

  const fetchKeysStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      if (res.ok) {
        const data = await res.json();
        setBackendKeysStatus(data);
      }
    } catch (e) {
      console.error("Failed to load settings status from backend:", e);
    }
  };

  // Start polling when threadId is set and status requires it
  useEffect(() => {
    let intervalId = null;

    if (threadId && !["completed", "error"].includes(status)) {
      intervalId = setInterval(async () => {
        try {
          const res = await fetch(`${API_BASE}/api/status/${threadId}`);
          if (!res.ok) {
            throw new Error("Status query failed");
          }
          const data = await res.json();
          
          setStatus(data.status);
          setLogs(data.logs);
          setNewsletterSubject(data.newsletter_subject);
          setNewsletterHtml(data.newsletter_html);
          setNewsletterMarkdown(data.newsletter_markdown);
          setArticles(data.articles || []);
          setRevisionCount(data.revision_count);
          setApproved(data.approved);
          setMetrics(data.metrics || {
            duration_seconds: 0.0,
            articles_count: 0,
            scraped_count: 0,
            search_count: 0,
            char_count: 0,
            revision_count: 0
          });
          setToolOutputs(data.tool_outputs || []);
          
          // Capture current critique if generated
          if (data.status === "reviewing" || (data.status === "waiting_for_feedback" && logs.some(l => l.includes("Critique result")))) {
            // Find review logs or metrics
            const critiqueLog = data.logs.find(l => l.includes("Critique result: REVISE"));
            if (critiqueLog) {
              setCritique(critiqueLog);
            }
          }
          
          if (data.status === "completed" || (data.status === "waiting_for_feedback" && mode === "hitl")) {
            // Stop active interval if completed or waiting for user decision
            if (data.status === "completed") {
              clearInterval(intervalId);
            }
          }
        } catch (err) {
          console.error("Error polling state:", err);
          clearInterval(intervalId);
        }
      }, 1500);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [threadId, status, mode]);

  // Submit new goal / run agent
  const handleStart = async (e) => {
    e.preventDefault();
    if (!goal.trim()) return;

    setStatus("planning");
    setLogs(["Submitting goal details to backend...", "Planning agent workflow..."]);
    setNewsletterSubject("");
    setNewsletterHtml("");
    setNewsletterMarkdown("");
    setArticles([]);
    setRevisionCount(0);
    setApproved(false);
    setCritique("");
    setFeedback("");
    setShowFeedbackForm(false);
    setMetrics({
      duration_seconds: 0.0,
      articles_count: 0,
      scraped_count: 0,
      search_count: 0,
      char_count: 0,
      revision_count: 0
    });
    setToolOutputs([]);

    const keysPayload = {};
    if (geminiKey) keysPayload.gemini = geminiKey;
    if (openaiKey) keysPayload.openai = openaiKey;
    if (tavilyKey) keysPayload.tavily = tavilyKey;

    try {
      const response = await fetch(`${API_BASE}/api/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal,
          mode: mode,
          llm_provider: llmProvider,
          api_keys: Object.keys(keysPayload).length > 0 ? keysPayload : null
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to start agent");
      }

      const data = await response.json();
      setThreadId(data.thread_id);
      setStatus(data.status);
    } catch (err) {
      console.error("Start agent failed:", err);
      setStatus("error");
      setLogs(prev => [...prev, `[ERROR] Failed to start agent: ${err.message}`]);
    }
  };

  // Human-in-the-loop decision: Approve
  const handleApprove = async () => {
    if (!threadId) return;
    setIsSubmittingAction(true);
    setLogs(prev => [...prev, "Approve request received. Transitioning agent..."]);

    try {
      const res = await fetch(`${API_BASE}/api/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: threadId,
          action: "approve"
        })
      });

      if (!res.ok) throw new Error("Approval action failed");
      const data = await res.json();
      setStatus(data.status);
    } catch (e) {
      console.error(e);
      setLogs(prev => [...prev, `[ERROR] Failed to submit approval: ${e.message}`]);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Human-in-the-loop decision: Reject with Feedback
  const handleFeedbackSubmit = async (e) => {
    e.preventDefault();
    if (!threadId || !feedback.trim()) return;

    setIsSubmittingAction(true);
    setLogs(prev => [...prev, `Submitting feedback to rewrite: "${feedback}"`]);
    setShowFeedbackForm(false);

    try {
      const res = await fetch(`${API_BASE}/api/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: threadId,
          action: "feedback",
          feedback: feedback
        })
      });

      if (!res.ok) throw new Error("Feedback submission failed");
      const data = await res.json();
      setStatus(data.status);
      setFeedback("");
    } catch (e) {
      console.error(e);
      setLogs(prev => [...prev, `[ERROR] Failed to submit feedback: ${e.message}`]);
    } finally {
      setIsSubmittingAction(false);
    }
  };

  // Settings Save
  const handleSaveSettings = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gemini_key: geminiKey || null,
          openai_key: openaiKey || null,
          tavily_key: tavilyKey || null
        })
      });

      if (res.ok) {
        alert("Settings saved successfully on the backend!");
        setShowSettings(false);
        fetchKeysStatus();
        setGeminiKey("");
        setOpenaiKey("");
        setTavilyKey("");
      } else {
        alert("Failed to save settings.");
      }
    } catch (e) {
      alert("Error saving settings: " + e.message);
    }
  };

  // Download logic (HTML or MD)
  const downloadFile = (content, filename, mimeType) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Render status helper badges
  const renderStatusBadge = () => {
    switch (status) {
      case "idle":
        return <span style={{ color: 'var(--text-muted)' }}>Idle</span>;
      case "planning":
        return <span style={{ color: 'var(--secondary)' }}>Planning...</span>;
      case "researching":
        return <span style={{ color: 'var(--secondary)' }}>Researching...</span>;
      case "summarizing":
        return <span style={{ color: 'var(--secondary)' }}>Summarizing...</span>;
      case "writing":
        return <span style={{ color: 'var(--secondary)' }}>Drafting...</span>;
      case "reviewing":
        return <span style={{ color: 'var(--primary)' }}>Critiquing...</span>;
      case "waiting_for_feedback":
        return <span style={{ color: 'var(--secondary)', fontWeight: 'bold' }}>Awaiting Feedback</span>;
      case "sending":
        return <span style={{ color: 'var(--accent)' }}>Sending...</span>;
      case "completed":
        return <span style={{ color: 'var(--accent)', fontWeight: 'bold' }}>✓ Completed</span>;
      case "error":
        return <span style={{ color: 'var(--danger)', fontWeight: 'bold' }}>✗ Error</span>;
      default:
        return <span>{status}</span>;
    }
  };

  // Stepper class determinations
  const getStepClass = (stepNum) => {
    // 1: Plan, 2: Research, 3: Summarize, 4: Draft, 5: Review, 6: Send/Done
    const currentIdx = ["idle", "planning", "researching", "summarizing", "writing", "reviewing", "waiting_for_feedback", "sending", "completed", "error"].indexOf(status);
    
    // mapping steps to status indexes
    // plan node (1) runs in 'planning' (status index 1)
    // research node (2) runs in 'researching' (status index 2)
    // summarize node (3) runs in 'summarizing' (status index 3)
    // write node (4) runs in 'writing' (status index 4)
    // review node (5) runs in 'reviewing' (status index 5)
    // send node (6) runs in 'sending' (status index 7) or completed (8)
    
    let active = false;
    let completed = false;

    if (status === "error") return "pending";

    if (stepNum === 1) {
      active = status === "planning";
      completed = currentIdx > 1;
    } else if (stepNum === 2) {
      active = status === "researching";
      completed = currentIdx > 2;
    } else if (stepNum === 3) {
      active = status === "summarizing";
      completed = currentIdx > 3;
    } else if (stepNum === 4) {
      active = status === "writing";
      completed = currentIdx > 4;
    } else if (stepNum === 5) {
      active = status === "reviewing" || status === "waiting_for_feedback";
      completed = currentIdx > 6;
    } else if (stepNum === 6) {
      active = status === "sending";
      completed = status === "completed";
    }

    return active ? "active" : completed ? "completed" : "pending";
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="logo-section">
          <Sparkles className="logo-icon" size={24} />
          <h1>Newsletter Agent</h1>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => setShowSettings(true)}>
            <Settings size={18} />
            Settings
          </button>
        </div>
      </header>

      {/* Main Layout Grid */}
      <div className="dashboard-grid">
        {/* Left Column: Controls, Stats, Terminal, and Timeline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Configuration Card */}
          <div className="panel">
            <h2 style={{ fontSize: '15px', fontWeight: '700', borderBottom: '1px solid var(--border-glass)', paddingBottom: '10px' }}>
              Control Panel
            </h2>
            <form onSubmit={handleStart} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="form-group">
                <label>Newsletter Goal</label>
                <textarea
                  className="textarea-field"
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  disabled={status !== "idle" && status !== "completed" && status !== "error"}
                  placeholder="Enter the topic and details for the newsletter..."
                />
              </div>

              <div className="form-group">
                <label>LLM Brain</label>
                <select
                  className="input-select"
                  value={llmProvider}
                  onChange={(e) => setLlmProvider(e.target.value)}
                  disabled={status !== "idle" && status !== "completed" && status !== "error"}
                >
                  <option value="gemini">Gemini 1.5 Flash (Recommended)</option>
                  <option value="openai">OpenAI GPT-4o-mini</option>
                </select>
              </div>

              <div className="toggle-group">
                <div className="toggle-label">
                  <span className="toggle-title">Human-in-the-Loop</span>
                  <span className="toggle-desc">Approve or edit before simulated sending</span>
                </div>
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={mode === "hitl"}
                    onChange={(e) => setMode(e.target.checked ? "hitl" : "autonomous")}
                    disabled={status !== "idle" && status !== "completed" && status !== "error"}
                  />
                  <span className="slider"></span>
                </label>
              </div>

              <button
                type="submit"
                className="btn btn-primary"
                disabled={(status !== "idle" && status !== "completed" && status !== "error") || !goal.trim()}
                style={{ width: '100%' }}
              >
                <Cpu size={18} />
                Generate Newsletter
              </button>
            </form>

            {/* Execution Statistics Dashboard Panel */}
            {status !== "idle" && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '4px' }}>
                <h3 style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Execution Statistics
                </h3>
                <div className="stats-grid">
                  <div className="stat-card">
                    <span className="stat-val">{metrics.duration_seconds}s</span>
                    <span className="stat-lbl">Duration</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-val">{metrics.scraped_count}/{metrics.articles_count}</span>
                    <span className="stat-lbl">Scrapes</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-val">{revisionCount}</span>
                    <span className="stat-lbl">Revisions</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-val">{metrics.char_count ? `${Math.round(metrics.char_count / 1024)}KB` : '0KB'}</span>
                    <span className="stat-lbl">HTML Size</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Logs Terminal */}
          <div className="logs-container">
            <div className="logs-header">
              <div className={`logs-dot ${status === "idle" || status === "completed" || status === "error" ? "idle" : ""}`}></div>
              <span className="logs-title">Agent Logs Terminal</span>
              <span style={{ marginLeft: 'auto', fontSize: '10px', color: 'var(--text-muted)' }}>
                Status: {renderStatusBadge()}
              </span>
            </div>
            <div className="logs-body">
              {logs.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Terminal offline. Initiate generation.</div>
              ) : (
                logs.map((log, index) => (
                  <div key={index} className="log-entry">
                    {log}
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </div>
        </div>

        {/* Right Column: Live Work Area & Tool Logger / Timeline */}
        <div className="panel" style={{ flexGrow: 1, minHeight: '600px' }}>
          {status === "idle" && !newsletterHtml && (
            <div className="workspace-empty">
              <Terminal size={64} className="workspace-empty-icon" />
              <h3>Newsletter Studio Workspace</h3>
              <p style={{ maxWidth: '400px' }}>
                Your curated articles and newsletter layouts will load here. Set your goal and launch the agent.
              </p>
            </div>
          )}

          {status !== "idle" && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', height: '100%' }}>
              {/* Stepper Progress Bar */}
              <div className="stepper">
                <div className={`step-item ${getStepClass(1)}`}>
                  <div className="step-bubble">1</div>
                  <span className="step-label">Plan</span>
                </div>
                <div className={`step-item ${getStepClass(2)}`}>
                  <div className="step-bubble">2</div>
                  <span className="step-label">Research</span>
                </div>
                <div className={`step-item ${getStepClass(3)}`}>
                  <div className="step-bubble">3</div>
                  <span className="step-label">Summarize</span>
                </div>
                <div className={`step-item ${getStepClass(4)}`}>
                  <div className="step-bubble">4</div>
                  <span className="step-label">Draft</span>
                </div>
                <div className={`step-item ${getStepClass(5)}`}>
                  <div className="step-bubble">5</div>
                  <span className="step-label">Review</span>
                </div>
                <div className={`step-item ${getStepClass(6)}`}>
                  <div className="step-bubble">6</div>
                  <span className="step-label">Done</span>
                </div>
              </div>

              {/* Generated Draft Preview / Accompanying Worksheets */}
              {newsletterHtml && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flexGrow: 1 }}>
                  <div className="workspace-header">
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.05em' }}>
                        Active Draft ({revisionCount > 0 ? `Revision ${revisionCount}` : 'Original'})
                      </span>
                      <h3 style={{ fontSize: '15px', fontWeight: '700' }}>{newsletterSubject}</h3>
                    </div>
                    
                    <div className="tabs">
                      <button 
                        className={`tab-btn ${activeTab === 'preview' ? 'active' : ''}`}
                        onClick={() => setActiveTab('preview')}
                      >
                        <Eye size={13} style={{ marginRight: '4px', display: 'inline', verticalAlign: 'middle' }} />
                        Preview
                      </button>
                      <button 
                        className={`tab-btn ${activeTab === 'code' ? 'active' : ''}`}
                        onClick={() => setActiveTab('code')}
                      >
                        <Code size={13} style={{ marginRight: '4px', display: 'inline', verticalAlign: 'middle' }} />
                        HTML
                      </button>
                      <button 
                        className={`tab-btn ${activeTab === 'markdown' ? 'active' : ''}`}
                        onClick={() => setActiveTab('markdown')}
                      >
                        <FileCode size={13} style={{ marginRight: '4px', display: 'inline', verticalAlign: 'middle' }} />
                        Markdown
                      </button>
                      <button 
                        className={`tab-btn ${activeTab === 'tool-logs' ? 'active' : ''}`}
                        onClick={() => setActiveTab('tool-logs')}
                      >
                        <Terminal size={13} style={{ marginRight: '4px', display: 'inline', verticalAlign: 'middle' }} />
                        Tool Log ({toolOutputs.length})
                      </button>
                    </div>

                    {/* Download buttons toolbar */}
                    <div className="preview-actions">
                      <button 
                        className="btn btn-secondary" 
                        onClick={() => downloadFile(newsletterHtml, 'newsletter.html', 'text/html')}
                        title="Download HTML Email File"
                        style={{ padding: '8px 12px' }}
                      >
                        <Download size={14} />
                        HTML
                      </button>
                      <button 
                        className="btn btn-secondary" 
                        onClick={() => downloadFile(newsletterMarkdown, 'newsletter.md', 'text/markdown')}
                        title="Download Markdown Document"
                        style={{ padding: '8px 12px' }}
                      >
                        <Download size={14} />
                        MD
                      </button>
                    </div>
                  </div>

                  {/* Render Tabs content */}
                  {activeTab === 'preview' && (
                    <div className="preview-container">
                      <iframe 
                        title="Newsletter HTML Preview"
                        className="iframe-element"
                        srcDoc={newsletterHtml}
                      />
                    </div>
                  )}

                  {activeTab === 'code' && (
                    <div className="code-container">
                      {newsletterHtml}
                    </div>
                  )}

                  {activeTab === 'markdown' && (
                    <div className="code-container" style={{ whiteSpace: 'pre-wrap' }}>
                      {newsletterMarkdown}
                    </div>
                  )}

                  {activeTab === 'tool-logs' && (
                    <div className="tool-list">
                      {critique && (
                        <div className="critique-card">
                          <div className="critique-title">
                            <Info size={16} />
                            Self-Critique Revision Logs (LLM Self-Reflection)
                          </div>
                          <div className="critique-text">
                            {critique}
                          </div>
                        </div>
                      )}
                      
                      {toolOutputs.length === 0 ? (
                        <div style={{ color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '20px' }}>
                          No tool execution logs registered yet.
                        </div>
                      ) : (
                        toolOutputs.map((item, idx) => (
                          <div className="tool-item" key={idx}>
                            <div 
                              className="tool-item-header"
                              onClick={() => setOpenToolIndex(openToolIndex === idx ? null : idx)}
                            >
                              <div className="tool-item-title">
                                <Terminal size={14} style={{ color: 'var(--primary)' }} />
                                <span>{item.tool}</span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                <span className="tool-item-badge">Active</span>
                                {openToolIndex === idx ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                              </div>
                            </div>
                            {openToolIndex === idx && (
                              <div className="tool-item-content">
                                <div className="tool-io-title">Parameter Input:</div>
                                <div className="tool-io-box">{item.input}</div>
                                <div className="tool-io-title">Execution Result:</div>
                                <div className="tool-io-box">{item.output}</div>
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  )}

                  {/* HITL Review Block */}
                  {status === "waiting_for_feedback" && (
                    <div className="hitl-banner">
                      <div className="hitl-header">
                        <AlertTriangle size={20} />
                        <span className="hitl-title">Human-in-the-Loop Critique Requested</span>
                      </div>
                      
                      {!showFeedbackForm ? (
                        <>
                          <p className="hitl-desc">
                            The agent has finished compiling the draft and ran self-reflection review. 
                            Please check the preview. Would you like to distribute the newsletter or enter critique feedback?
                          </p>
                          <div className="hitl-actions">
                            <button 
                              className="btn btn-accent" 
                              onClick={handleApprove}
                              disabled={isSubmittingAction}
                            >
                              <Check size={16} />
                              Approve & Send
                            </button>
                            <button 
                              className="btn btn-secondary" 
                              onClick={() => setShowFeedbackForm(true)}
                              disabled={isSubmittingAction}
                            >
                              <RotateCw size={16} />
                              Provide Revisions
                            </button>
                          </div>
                        </>
                      ) : (
                        <form onSubmit={handleFeedbackSubmit} className="feedback-form">
                          <div className="form-group">
                            <label>Revision instructions for the agent</label>
                            <textarea
                              className="textarea-field"
                              value={feedback}
                              onChange={(e) => setFeedback(e.target.value)}
                              placeholder="Describe what changes to make (e.g. 'Make the introduction shorter', 'Remove the third article', 'Highlight the Gemini 1.5 release more')..."
                              required
                            />
                          </div>
                          <div className="hitl-actions">
                            <button type="submit" className="btn btn-primary" disabled={isSubmittingAction || !feedback.trim()}>
                              <Send size={16} />
                              Re-draft Newsletter
                            </button>
                            <button 
                              type="button" 
                              className="btn btn-secondary" 
                              onClick={() => setShowFeedbackForm(false)}
                              disabled={isSubmittingAction}
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      )}
                    </div>
                  )}

                  {/* Completion Block */}
                  {status === "completed" && (
                    <div className="success-banner">
                      <Check size={24} style={{ flexShrink: 0 }} />
                      <div className="success-content">
                        <span className="success-title">Newsletter Curated and Sent!</span>
                        <span className="success-desc">
                          The final version has been successfully archived in your backend output folder:
                          <br />
                          📁 <code>C:/Users/Abhishek/.gemini/antigravity-ide/scratch/newsletter-agent/backend/output/</code>
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Loading States & Progress Visualizer Timeline (Before HTML is generated) */}
              {!newsletterHtml && status !== "error" && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '24px', flexGrow: 1, minHeight: '500px' }}>
                  {/* Big glowing double-ring loader */}
                  <div className="workspace-empty" style={{ borderRight: '1px solid var(--border-glass)' }}>
                    <div className="spinner-ring">
                      <div></div>
                      <div></div>
                      <div></div>
                    </div>
                    <h3 style={{ marginTop: '16px' }}>Agent is Working...</h3>
                    <p style={{ maxWidth: '380px', fontSize: '13px', lineHeight: 1.5 }}>
                      Current Phase: <strong style={{ color: 'var(--primary)' }}>{status.toUpperCase()}</strong>.
                      Executing agent nodes. Track progress on the execution timeline on the right.
                    </p>
                  </div>
                  
                  {/* Vertical Timeline Tracker */}
                  <div style={{ padding: '20px 10px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <h3 style={{ fontSize: '11px', fontWeight: '700', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Workflow Step Timeline
                    </h3>
                    <div className="timeline-container">
                      <div className={`timeline-item ${status === 'planning' ? 'active' : 'completed'}`}>
                        <div className="timeline-icon-wrap">
                          <div className="timeline-badge"></div>
                        </div>
                        <div className="timeline-content">
                          <span className="timeline-title">1. Search Planning</span>
                          <span className="timeline-desc">LLM parses goal and generates optimized search queries.</span>
                        </div>
                      </div>
                      
                      <div className={`timeline-item ${status === 'researching' ? 'active' : ['planning'].includes(status) ? 'pending' : 'completed'}`}>
                        <div className="timeline-icon-wrap">
                          <div className="timeline-badge"></div>
                        </div>
                        <div className="timeline-content">
                          <span className="timeline-title">2. Web Research & Scrape</span>
                          <span className="timeline-desc">Runs searches and extracts text from pages via BeautifulSoup.</span>
                        </div>
                      </div>
                      
                      <div className={`timeline-item ${status === 'summarizing' ? 'active' : ['planning', 'researching'].includes(status) ? 'pending' : 'completed'}`}>
                        <div className="timeline-icon-wrap">
                          <div className="timeline-badge"></div>
                        </div>
                        <div className="timeline-content">
                          <span className="timeline-title">3. Content Summarization</span>
                          <span className="timeline-desc">Creates contextual 2-3 sentence summaries of news articles.</span>
                        </div>
                      </div>
                      
                      <div className={`timeline-item ${status === 'writing' ? 'active' : ['planning', 'researching', 'summarizing'].includes(status) ? 'pending' : 'completed'}`}>
                        <div className="timeline-icon-wrap">
                          <div className="timeline-badge"></div>
                        </div>
                        <div className="timeline-content">
                          <span className="timeline-title">4. Newsletter Drafting</span>
                          <span className="timeline-desc">Drafts clicks-subject, intros, and compiles CSS templates.</span>
                        </div>
                      </div>
                      
                      <div className={`timeline-item ${status === 'reviewing' || status === 'waiting_for_feedback' ? 'active' : ['planning', 'researching', 'summarizing', 'writing'].includes(status) ? 'pending' : 'completed'}`}>
                        <div className="timeline-icon-wrap">
                          <div className="timeline-badge"></div>
                        </div>
                        <div className="timeline-content">
                          <span className="timeline-title">5. Critique & Revisions</span>
                          <span className="timeline-desc">Evaluates quality, fixes typos, and triggers loops.</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Error State */}
              {status === "error" && (
                <div className="workspace-empty">
                  <AlertTriangle size={64} style={{ color: 'var(--danger)' }} />
                  <h3 style={{ color: 'var(--danger)' }}>An Error Occurred</h3>
                  <p style={{ maxWidth: '400px', fontSize: '13px' }}>
                    The agent execution stopped due to a system failure. Please check the logs in the terminal panel on the left or verify your API keys in Settings.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      {showSettings && (
        <div className="modal-overlay">
          <div className="panel modal-content">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Settings2 className="logo-icon" size={20} />
                <span className="modal-title">API Keys Configurator</span>
              </div>
              <button className="close-btn" onClick={() => setShowSettings(false)}>
                <X size={20} />
              </button>
            </div>
            
            <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Configure keys to enable AI reasoning and search capabilities. 
              Keys will be saved to your local backend `.env` file securely.
            </p>
            
            <form onSubmit={handleSaveSettings} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <label>Gemini API Key</label>
                  {backendKeysStatus.gemini_configured && (
                    <span style={{ fontSize: '11px', color: 'var(--accent)' }}>✓ Configured in env</span>
                  )}
                </div>
                <input
                  type="password"
                  className="input-text"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                  placeholder="AI reasoning model (sk-...)"
                />
              </div>

              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <label>OpenAI API Key (Optional)</label>
                  {backendKeysStatus.openai_configured && (
                    <span style={{ fontSize: '11px', color: 'var(--accent)' }}>✓ Configured in env</span>
                  )}
                </div>
                <input
                  type="password"
                  className="input-text"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="Alternative model (sk-...)"
                />
              </div>

              <div className="form-group">
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <label>Tavily API Key (Optional)</label>
                  {backendKeysStatus.tavily_configured && (
                    <span style={{ fontSize: '11px', color: 'var(--accent)' }}>✓ Configured in env</span>
                  )}
                </div>
                <input
                  type="password"
                  className="input-text"
                  value={tavilyKey}
                  onChange={(e) => setTavilyKey(e.target.value)}
                  placeholder="For high-quality search search. Falls back to free DuckDuckGo."
                />
                <p style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  If left blank, the agent automatically runs web queries on <strong>DuckDuckGo search</strong> (completely free, no signup required).
                </p>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowSettings(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
