import subprocess, re

def fetch(url):
    result = subprocess.run(['curl', '-s', '--max-time', '10', url], capture_output=True)
    return result.stdout.decode('latin-1')

html = fetch('https://www.seaoftranquility.org/reviews.php?op=showcontent&id=25538')

# The body is between <p align=justify> and <b>Added:
m = re.search(r'<p align=justify>(.*?)<b>Added:', html, re.DOTALL)
if m:
    raw = m.group(1)
    print('Raw body (first 300 chars):', repr(raw[:300]))
    body = re.sub(r'<[^>]+>', ' ', raw)
    body = re.sub(r'\s+', ' ', body).strip()
    print('Cleaned body (first 300 chars):', repr(body[:300]))
    print('Total body length:', len(body))