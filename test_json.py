import json

text = '{"a": 1} garbage }'
try:
    json.loads(text)
except Exception as e:
    print("loads error:", type(e), str(e))

decoder = json.JSONDecoder()
try:
    obj, idx = decoder.raw_decode(text)
    print("raw_decode success:", obj, "index:", idx)
except Exception as e:
    print("raw_decode error:", type(e), str(e))

