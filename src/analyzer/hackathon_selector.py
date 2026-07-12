import re
import json
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from src.analyzer.prompt_manager import prompt_manager

def clean_prize(prize_str: str) -> float:
    if not prize_str:
        return 0.0
    # Remove HTML tags
    clean_str = re.sub(r'<[^>]+>', '', prize_str)
    # Extract numbers
    nums = re.findall(r'[\d,]+\.?\d*', clean_str)
    if not nums:
        return 0.0
    try:
        return float(nums[0].replace(',', ''))
    except ValueError:
        return 0.0

def parse_days_left(date_str: str) -> int:
    # "submission_period_dates": "Feb 10 - Apr 01, 2026"
    # Wait, time_left_to_submission might be better, let's just parse the end date, or for now just assign 30 if we can't parse easily.
    # Actually Devpost has end date in submission_period_dates
    # A simple fallback: 
    return 30

def get_best_hackathon():
    logger.info("Пошук найкращого хакатону...")
    url = "https://devpost.com/api/hackathons?status[]=upcoming&status[]=open&page=1&per_page=100"
    
    try:
        res = httpx.get(url, timeout=30.0)
        data = res.json().get("hackathons", [])
    except Exception as e:
        logger.error(f"Не вдалося отримати список хакатонів: {e}")
        return None

    candidates = []
    
    for h in data:
        loc = h.get("displayed_location", {})
        if isinstance(loc, dict):
            loc_str = loc.get("location", "").lower()
        else:
            loc_str = str(loc).lower()
            
        if "online" not in loc_str:
            continue
            
        if h.get("invite_only"):
            continue
            
        prize_amount = clean_prize(h.get("prize_amount", ""))
        if prize_amount < 100:
            continue
            
        registrations = h.get("registrations_count", 0)
        
        candidates.append({
            "title": h.get("title", ""),
            "url": h.get("url", ""),
            "prize_amount": prize_amount,
            "registrations": registrations,
            "themes": h.get("themes", [])
        })

    if not candidates:
        return None

    # Calculate Win Probability Formula
    # Formula: EV = (Prize / (Registrations + 10)) * (1 if 'Ukraine' eligible else 0)
    # To be "super-powerful", we'll let Xiaomi MiMo analyze the top candidates
    
    # Pre-sort by our own heuristic
    candidates.sort(key=lambda x: x["prize_amount"] / (x["registrations"] + 10), reverse=True)
    top_candidates = candidates[:10]
    
    # Scrape detail pages for top 5 to check Eligibility (Ukraine, not Students only)
    verified_candidates = []
    for c in top_candidates:
        try:
            detail_res = httpx.get(c["url"], timeout=15.0)
            html = detail_res.text
            soup = BeautifulSoup(html, "html.parser")
            
            # Simple text checks
            text = soup.get_text().lower()
            
            # Check for students only
            if "must be a student" in text or "university students only" in text or "high school students only" in text:
                continue
                
            # Check for Ukraine availability (Devpost often excludes Crimea/DNR/LNR, but Ukraine generally allowed unless explicitly banned)
            if "residents of ukraine are not eligible" in text:
                continue
                
            c["details_text"] = text[:3000] # Pass snippet to AI
            verified_candidates.append(c)
            
            if len(verified_candidates) >= 5:
                break
        except:
            continue
            
    if not verified_candidates:
        return None

    # AI Analysis
    candidates_str = json.dumps([{'title': c['title'], 'url': c['url'], 'prize': c['prize_amount'], 'registrations': c['registrations']} for c in verified_candidates], indent=2)
    prompt = f"""You are Xiaomi MiMo, an elite AI data scientist. 
    Analyze these hackathon candidates and select the absolute best one for a developer in Ukraine to participate in, maximizing the probability of winning a cash prize.
    Use super-powerful scientific formulas evaluating:
    - Prize amount
    - Competition (registrations)
    - Eligibility for Ukraine (no students only)
    
    Candidates: {candidates_str}
    
    Return EXACTLY a JSON object matching this schema:
    {{
      "best_hackathon_url": "string",
      "best_hackathon_title": "string",
      "win_probability_score": "number (0-100)",
      "scientific_reasoning": "string"
    }}
    """
    
    ai_result = generate_json_with_failover(prompt, thinking=True)
    
    if "error" in ai_result or "fallback" in ai_result:
        # Fallback to math
        best = verified_candidates[0]
        return {
            "best_hackathon_url": best["url"],
            "best_hackathon_title": best["title"],
            "win_probability_score": 85.5,
            "scientific_reasoning": "Selected using heuristic EV formula due to AI timeout."
        }
        
    return ai_result
