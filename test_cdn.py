import urllib.request, ssl
ssl._create_default_https_context = ssl._create_unverified_context
url = 'https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
resp = urllib.request.urlopen(req, timeout=15)
data = resp.read()
print(f'Downloaded {len(data)} bytes, status {resp.status}')
ct = resp.headers.get('Content-Type')
print(f'Content-Type: {ct}')
