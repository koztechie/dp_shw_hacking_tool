import httpx

url = "https://devpost.com/api/hackathons?status[]=upcoming&status[]=open&page=1&per_page=100"
res = httpx.get(url)
data = res.json()["hackathons"]
for h in data[:5]:
    print(h["title"], h["displayed_location"], h["invite_only"], h["prize_amount"])
