import httpx
import re

c = httpx.Client(trust_env=False, timeout=10)
html = c.get("http://localhost:8080/").text
m = re.search(r'src="(/assets/[^"]+\.js)"', html)
js = m.group(1)
bundle = c.get(f"http://localhost:8080{js}").text
print("bundle:", js, len(bundle))
for token in ["agent_phase", "message_delta", "PHASE"]:
    print(token, "in bundle:", token in bundle)
