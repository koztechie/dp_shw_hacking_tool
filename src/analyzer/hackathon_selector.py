import re
import json
import asyncio
import time
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.logger import logger
from src.analyzer.ai_client import generate_json_with_failover
from src.analyzer.prompt_validator import PromptSchemaValidator
from src.analyzer.cache import get_cached, set_cache

# Constants
CACHE_KEY = "smart_hackathon_selector_cache"
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours

def clean_prize(prize_str: str) -> float:
    if not prize_str:
        return 0.0
    clean_str = re.sub(r'<[^>]+>', '', str(prize_str))
    nums = re.findall(r'[\d,]+\.?\d*', clean_str)
    if not nums:
        return 0.0
    try:
        return float(nums[0].replace(',', ''))
    except ValueError:
        return 0.0

def parse_days_left(time_str: str) -> float:
    if not time_str:
        return 30.0
    text = str(time_str).lower()
    
    # Extract number if exists
    nums = re.findall(r'\d+', text)
    val = float(nums[0]) if nums else 1.0
    
    if "month" in text:
        return val * 30.0
    elif "day" in text:
        return val
    elif "hour" in text:
        return val / 24.0
    elif "minute" in text:
        return val / 1440.0
    return 30.0

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=True
)
async def fetch_page(client: httpx.AsyncClient, page: int) -> list:
    url = f"https://devpost.com/api/hackathons?status[]=upcoming&status[]=open&page={page}&per_page=100"
    res = await client.get(url, timeout=15.0)
    res.raise_for_status()
    return res.json().get("hackathons", [])

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    reraise=False
)
async def fetch_detail_page(client: httpx.AsyncClient, candidate: dict):
    try:
        res = await client.get(candidate["url"], timeout=15.0)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text().lower()
        
        # Anti-fragile checks
        if any(phrase in text for phrase in ["must be a student", "university students only", "high school students only", "students only"]):
            return None
        if "residents of ukraine are not eligible" in text:
            return None
        if re.search(r'team required:\s*[2-9]', text):
            return None
            
        candidate["details_text"] = text[:4000]
        return candidate
    except Exception as e:
        logger.warning(f"Failed to fetch detail for {candidate['title']} (skipping): {e}")
        return None

async def _calculate_best_hackathon_impl():
    logger.info("Пошук найкращого хакатону (God-tier Antifragile Mode)...")
    candidates = []
    
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=50, max_keepalive_connections=20)) as client:
        # Fetch first 5 pages concurrently (up to 500 hackathons)
        tasks = [fetch_page(client, p) for p in range(1, 6)]
        
        # We use return_exceptions=True to avoid crashing the whole batch if one page fails permanently
        pages = await asyncio.gather(*tasks, return_exceptions=True)
        
        raw_hackathons = []
        for p in pages:
            if isinstance(p, list):
                raw_hackathons.extend(p)
            else:
                logger.error(f"Devpost API page failed: {p}")
                
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
            days_left = parse_days_left(h.get("time_left_to_submission", ""))
            
            # Penalize hackathons that have lots of days left (competition will grow)
            # Boost hackathons ending soon (current registrations are close to final)
            time_penalty = max(1.0, days_left / 7.0)
            ev = prize_amount / (registrations * time_penalty + 10.0)
            
            candidates.append({
                "title": h.get("title", ""),
                "url": h.get("url", ""),
                "prize_amount": prize_amount,
                "registrations": registrations,
                "days_left": round(days_left, 1),
                "themes": h.get("themes", []),
                "ev_score": ev
            })

        if not candidates:
            return None

        # Pre-sort using our scientific EV formula
        candidates.sort(key=lambda x: x["ev_score"], reverse=True)
        top_candidates = candidates[:15]
        
        # Fetch details concurrently
        detail_tasks = [fetch_detail_page(client, c) for c in top_candidates]
        verified_results = await asyncio.gather(*detail_tasks)
        
        verified_candidates = [c for c in verified_results if c is not None][:5]

    if not verified_candidates:
        return None

    # AI Analysis with Schema Validation
    schema = PromptSchemaValidator.get_schema("hackathon_recommendation")
    
    # Prune heavy details_text before dumping to save tokens
    clean_candidates = []
    for c in verified_candidates:
        cc = c.copy()
        if "details_text" in cc:
            del cc["details_text"]
        clean_candidates.append(cc)
        
    candidates_str = json.dumps(clean_candidates, indent=2)
    
    prompt = f"""You are Xiaomi MiMo, an elite AI data scientist and algorithmic strategist. 
    Analyze these hackathon candidates and select the absolute best one for a developer in Ukraine to participate in, maximizing the probability of winning a cash prize.
    We already pre-calculated an 'ev_score' based on the formula: Prize / (Registrations * max(1, DaysLeft/7) + 10).
    Review the candidates and either agree with the highest 'ev_score' or pick another one if the prize-to-competition ratio is strategically better.
    
    Candidates: {candidates_str}
    
    Return EXACTLY a JSON object matching this schema: {json.dumps(schema)}
    """
    
    ai_result = await asyncio.to_thread(
        generate_json_with_failover,
        prompt=prompt,
        thinking=True,
        schema_name="hackathon_recommendation"
    )
    
    if "error" in ai_result or "fallback" in ai_result:
        logger.warning(f"AI timeout or error: {ai_result}. Falling back to strict math.")
        best = verified_candidates[0]
        return {
            "best_hackathon_url": best["url"],
            "best_hackathon_title": best["title"],
            "win_probability_score": round(min(99.9, best["ev_score"] * 10), 2),
            "scientific_reasoning": f"Selected using strict deterministic EV formula due to AI unavailability. Prize: ${best['prize_amount']}, Registrations: {best['registrations']}, Days Left: {best['days_left']}."
        }
        
    return ai_result

async def get_best_hackathon_async() -> dict:
    """
    Public entry point with Caching to ensure Antifragility against DDOS, 429s, and excessive API calls.
    """
    # 1. Check Cache
    cached_data = get_cached(CACHE_KEY)
    if cached_data and "timestamp" in cached_data:
        age_seconds = time.time() - cached_data["timestamp"]
        if age_seconds < CACHE_TTL_SECONDS:
            logger.info("⚡ Повертаю результат з кешу (швидка відповідь)")
            return cached_data["data"]
            
    # 2. Calculate Fresh
    result = await _calculate_best_hackathon_impl()
    
    # 3. Save to Cache
    if result and "error" not in result:
        cache_payload = {
            "timestamp": time.time(),
            "data": result
        }
        set_cache(CACHE_KEY, cache_payload)
        
    return result
