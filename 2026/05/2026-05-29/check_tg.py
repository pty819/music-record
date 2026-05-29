with open('/home/liyifan/music-record/recommend/2026-05-29.md') as f:
    content = f.read()
print(f'total chars: {len(content)}, lines: {content.count(chr(10))}')