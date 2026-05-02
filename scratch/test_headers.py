from bustapi.http.response import Headers

h = Headers()
h.add("Set-Cookie", "a=1")
h.add("Set-Cookie", "b=2")

print(f"Headers: {h}")
print(f"Items: {list(h.items())}")
print(f"Dict: {dict(h)}")
