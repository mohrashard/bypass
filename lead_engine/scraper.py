import urllib.request
import json
import time
import os

def fetch_reddit_posts(subreddit, limit=10):
    url = f'https://www.reddit.com/r/{subreddit}/new.json?limit={limit}'
    # Reddit requires a custom User-Agent so we don't get blocked
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 LeadEngine/1.0'
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
            posts = []
            for child in data.get('data', {}).get('children', []):
                post_data = child.get('data', {})
                
                # Basic filtering: Ignore pinned/stickied posts
                if post_data.get('stickied'):
                    continue
                    
                posts.append({
                    'title': post_data.get('title'),
                    'author': post_data.get('author'),
                    'upvotes': post_data.get('ups'),
                    'comments': post_data.get('num_comments'),
                    'url': f"https://www.reddit.com{post_data.get('permalink')}",
                    'text': post_data.get('selftext', '')[:200] + ('...' if len(post_data.get('selftext', '')) > 200 else ''),
                    'created_utc': post_data.get('created_utc')
                })
            return posts
    except urllib.error.HTTPError as e:
        print(f"HTTP Error fetching {subreddit}: {e.code} - {e.reason}")
        return []
    except Exception as e:
        print(f"Error fetching {subreddit}: {e}")
        return []

if __name__ == "__main__":
    # You can change these to target your specific niche!
    target_subreddits = ['SaaS', 'Entrepreneur', 'SideProject']
    all_leads = []
    print("Starting Lead Engine Scraper...\n")
    
    for sub in target_subreddits:
        print(f"Fetching latest from /r/{sub}...")
        posts = fetch_reddit_posts(sub, limit=5)
        
        for post in posts:
            all_leads.append(post)
            print(f"[{post['upvotes']} upvotes | {post['comments']} comments] {post['title']}")
        
        print("-" * 50)
        time.sleep(2) # Be nice to Reddit's servers so we don't get IP banned
        
    # Save the output to a JSON file that our Chrome Extension will read later
    output_file = os.path.join(os.path.dirname(__file__), 'leads.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_leads, f, indent=4)
        
    print(f"\nSuccessfully saved {len(all_leads)} leads to {output_file}")
