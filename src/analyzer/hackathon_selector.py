import re
import json
import asyncio
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from src.analyzer.prompt_validator import PromptSchemaValidator

def clean_prize(prize_str: str) -> float:
    if not prize_str:
        return 0.0
    clean_str = re.sub(r'<[^>]+>', '', prize_str)
    nums = re.findall(r'[\d,]+\.?\d*', clean_str)
    if not nums:
        return 0.0
    try:
        return float(nums[0].replace(',', ''))
    except ValueError:
        return 0.0

async def fetch_page(client: httpx.AsyncClient, page: int):
    url = f"https://devpost.com/api/hackathons?status[]=upcoming&status[]=open&page={page}&per_page=100"
    try:
        res = await client.get(url, timeout=15.0)
        return res.json().get("hackathons", [])
    except Exception as e:
        logger.warning(f"Failed to fetch devpost page {page}: {e}")
        return []

async def fetch_detail_page(client: httpx.AsyncClient, candidate: dict):
    try:
        res = await client.get(candidate["url"], timeout=15.0)
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text().lower()
        
        # Anti-fragile checks
        if "must be a student" in text or "university students only" in text or "high school students only" in text:
            return None
        if "residents of ukraine are not eligible" in text:
            return None
            
        candidate["details_text"] = text[:3000]
        return candidate
    except Exception as e:
        logger.warning(f"Failed to fetch detail for {candidate['title']}: {e}")
        return None

async def get_best_hackathon_async():
    logger.info("Пошук найкращого хакатону (Асинхронний режим, антикрихкість увімкнена)...")
    candidates = []
    
    async with httpx.AsyncClient() as client:
        # Fetch first 3 pages concurrently (up to 300 hackathons)
        tasks = [fetch_page(client, p) for p in range(1, 4)]
        pages = await asyncio.gather(*tasks)
        
        raw_hackathons = []
        for p in pages:
            raw_hackathons.extend(p)
            
        # Deduplicate
        seen_urls = set()
        unique_hackathons = []
        for h in raw_hackathons:
            url = h.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_hackathons.append(h)
        
        for h in unique_hackathons:
            loc = h.get("displayed_location", {})
            loc_str = loc.get("location", "").lower() if isinstance(loc, dict) else str(loc).lower()
            
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

        # Sort heuristics: Prize / (Registrations + 10)
        candidates.sort(key=lambda x: x["prize_amount"] / (x["registrations"] + 10), reverse=True)
        top_candidates = candidates[:15]
        
        # Fetch details concurrently
        detail_tasks = [fetch_detail_page(client, c) for c in top_candidates]
        verified_results = await asyncio.gather(*detail_tasks)
        
        verified_candidates = [c for c in verified_results if c is not None][:5]

    if not verified_candidates:
        return None

    # AI Analysis with Schema Validation
    schema = PromptSchemaValidator.get_schema("hackathon_recommendation")
    candidates_str = json.dumps([{'title': c['title'], 'url': c['url'], 'prize': c['prize_amount'], 'registrations': c['registrations']} for c in verified_candidates], indent=2)
    
    prompt = f"""You are Xiaomi MiMo, an elite AI data scientist and algorithmic strategist. 
    Analyze these hackathon candidates and select the absolute best one for a developer in Ukraine to participate in, maximizing the probability of winning a cash prize.
    Use super-powerful scientific formulas evaluating Expected Value (EV):
    - Prize amount (higher is better)
    - Competition / Registrations (lower is better, EV = Prize / (Registrations + constant))
    - Eligibility for Ukraine (no students only)
    
    Candidates: {candidates_str}
    
    Return EXACTLY a JSON object matching this schema: {json.dumps(schema)}
    """
    
    # generate_json_with_failover is synchronous, but AI client has max_retries.
    # To run it without blocking the async event loop, we can use asyncio.to_thread
    ai_result = await asyncio.to_thread(
        generate_json_with_failover,
        prompt=prompt,
        thinking=True,
        schema_name="hackathon_recommendation"
    )
    
    if "error" in ai_result or "fallback" in ai_result:
        logger.warning(f"AI timeout or error: {ai_result}. Falling back to strict math.")
        best = verified_candidates[0]
        ev_score = min(99.9, (best["prize_amount"] / (best["registrations"] + 10)) * 10)
        return {
            "best_hackathon_url": best["url"],
            "best_hackathon_title": best["title"],
            "win_probability_score": round(ev_score, 2),
            "scientific_reasoning": "Selected using deterministic EV formula (Prize/Registrations) due to AI unavailability. Verified Ukraine-eligible."
        }
        
    return ai_result
