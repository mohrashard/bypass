import sys
import json
import os
import time
from playwright.sync_api import sync_playwright

def run_scraper(options_json):
    options = json.loads(options_json)
    subreddits_raw = options.get('subreddits', 'SaaS, Entrepreneur')
    query = options.get('query', '')
    mode = options.get('mode', 'comments')
    
    subreddits = [s.strip() for s in subreddits_raw.split(',') if s.strip()]
    
    all_leads = []
    
    print("[INFO] Initializing Playwright Stealth Scraper...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for sub in subreddits:
            print(f"[SEARCH] Scraping latest threads from /r/{sub}...", flush=True)
            
            # Navigate based on mode
            if mode == 'content':
                # Get best threads from the last month for content ideas
                url = f"https://old.reddit.com/r/{sub}/top/?sort=top&t=month"
            else:
                # Get fresh threads for active leads/comments
                url = f"https://old.reddit.com/r/{sub}/new/"
                
            page.goto(url, wait_until="domcontentloaded")
            
            try:
                page.wait_for_selector(".thing", timeout=10000)
            except Exception as e:
                print(f"[ERROR] No results or timeout on /r/{sub}", flush=True)
                continue
                
                
            posts = page.query_selector_all(".thing")[:25] 
            
            count = 0
            for post in posts:
                try:
                    title_element = post.query_selector("p.title a.title")
                    title = title_element.inner_text() if title_element else "No Title"
                    
                    url_href = title_element.get_attribute("href") if title_element else ""
                    if url_href.startswith("/r/"):
                        url_href = "https://old.reddit.com" + url_href
                        
                    comments_element = post.query_selector("a.bylink.comments")
                    comments_text = comments_element.inner_text() if comments_element else "0"
                    comments = comments_text.split(" ")[0] if comments_text else "0"
                    if comments == "comment":
                        comments = "0"
                    
                    upvotes_element = post.query_selector(".search-score") or post.query_selector(".score.unvoted")
                    upvotes = upvotes_element.inner_text().split(" ")[0] if upvotes_element else "0"
                    if upvotes == "•": 
                        upvotes = "hidden"

                    # Extract text content by clicking expando if it exists
                    content_text = ""
                    expando = post.query_selector('.expando-button.selftext')
                    if expando:
                        try:
                            # Only click if not already expanded
                            if "expanded" not in (expando.get_attribute("class") or ""):
                                expando.click(timeout=500)
                                post.wait_for_selector('.usertext-body .md', timeout=500, state="attached")
                        except Exception:
                            pass
                    
                    content_elem = post.query_selector(".usertext-body .md")
                    content_text = content_elem.inner_text().strip() if content_elem else ""
                    
                    all_leads.append({
                        "title": title,
                        "url": url_href,
                        "upvotes": upvotes,
                        "comments": comments,
                        "subreddit": sub,
                        "content": content_text
                    })
                    count += 1
                except Exception as e:
                    pass
                    
            print(f"[SUCCESS] Found {count} relevant threads in /r/{sub}")
            time.sleep(1.5)
            
        browser.close()
        
    output_file = os.path.join(os.path.dirname(__file__), '..', 'lead_engine', 'leads.json')
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_leads, f, indent=4)
        
    print(f"[SUCCESS] Successfully saved {len(all_leads)} total leads to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        options_json = sys.argv[2]
    else:
        options_json = '{"subreddits": "SaaS", "query": ""}'
        
    run_scraper(options_json)
