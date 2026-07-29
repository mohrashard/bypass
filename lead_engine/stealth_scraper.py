from playwright.sync_api import sync_playwright
import json
import os
import time

def scrape_reddit(subreddits):
    all_leads = []
    with sync_playwright() as p:
        # Launch Chromium headless
        browser = p.chromium.launch(headless=True)
        # Create a context that masks us as a regular desktop user
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for sub in subreddits:
            print(f"Browsing /r/{sub}...")
            
            # BIG TRICK: We scrape old.reddit.com. It is 100x faster, purely HTML based, 
            # and doesn't trigger the insane React/CORS protections of the modern UI.
            page.goto(f"https://old.reddit.com/r/{sub}/new/", wait_until="domcontentloaded")
            
            try:
                # Wait for the post elements (which have class .thing in old reddit)
                page.wait_for_selector(".thing", timeout=10000)
            except Exception as e:
                print(f"Timeout waiting for posts on {sub}")
                continue
                
            # Get the top 5 posts on the page
            posts = page.query_selector_all(".thing")[:5] 
            
            for post in posts:
                try:
                    title_element = post.query_selector("p.title a.title")
                    title = title_element.inner_text() if title_element else "No Title"
                    
                    url = title_element.get_attribute("href") if title_element else ""
                    if url.startswith("/r/"):
                        url = "https://old.reddit.com" + url
                        
                    comments_element = post.query_selector("a.bylink.comments")
                    comments_text = comments_element.inner_text() if comments_element else "0"
                    comments = comments_text.split(" ")[0] if comments_text else "0"
                    if comments == "comment":
                        comments = "0"
                    
                    upvotes_element = post.query_selector(".score.unvoted")
                    upvotes = upvotes_element.inner_text() if upvotes_element else "0"
                    # old.reddit sometimes uses a dot for hidden scores
                    if upvotes == "•": 
                        upvotes = "hidden"
                    
                    all_leads.append({
                        "title": title,
                        "url": url,
                        "upvotes": upvotes,
                        "comments": comments,
                        "subreddit": sub
                    })
                    print(f"[{upvotes} upvotes | {comments} comments] {title}")
                except Exception as e:
                    print(f"Error parsing post: {e}")
                    
            print("-" * 50)
            time.sleep(2) # Human-like delay between pages
            
        browser.close()
        
    output_file = os.path.join(os.path.dirname(__file__), 'leads.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_leads, f, indent=4)
        
    print(f"\nSuccessfully saved {len(all_leads)} leads to {output_file}")

if __name__ == "__main__":
    target_subreddits = ['SaaS', 'Entrepreneur']
    print("Starting Playwright Stealth Scraper...\n")
    scrape_reddit(target_subreddits)
