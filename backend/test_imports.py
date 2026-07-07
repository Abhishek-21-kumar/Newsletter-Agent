import sys
import os

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("Python Path:", sys.path)
print("Testing backend imports...")

try:
    from app.tools import get_llm, search_web, scrape_article, summarize_article, build_newsletter_html
    print("[OK] Tools imported successfully.")
    
    from app.agent import agent_graph
    print("[OK] Agent graph compiled and imported successfully.")
    
    from app.main import app
    print("[OK] FastAPI application imported successfully.")
    
    print("All core backend components loaded successfully without errors!")
except Exception as e:
    print("[ERROR] Error importing backend components:")
    import traceback
    traceback.print_exc()
    sys.exit(1)
