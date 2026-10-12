#!/usr/bin/env python3
"""KCH notice collection. Runs independently of iPad; fail closed on bad HTML."""
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://www.kch.or.kr/user/board/lists/board_cd/notice"
DETAIL = "https://www.kch.or.kr/user/board/view/board_cd/notice/wr_no/"
KST = dt.timezone(dt.timedelta(hours=9))
OUT = Path(os.environ.get("KCH_OUTPUT_DIR", ".")).resolve()
LINK = re.compile(r"/user/board/view/board_cd/notice/wr_no/(\d+)")
DATE = re.compile(r"(?<!\d)((?:20)?\d{2})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})(?!\d)")
KEYWORDS = ("전공의", "레지던트")


def normal_date(s):
    m = DATE.search(s)
    if not m:
        return ""
    y, mon, day = [int(z) for z in m.groups()]
    if y < 100:
        y += 2000
    try:
        return dt.date(y, mon, day).isoformat()
    except ValueError:
        return ""


def download():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.6",
    })
    for attempt in range(3):
        try:
            r = session.get(URL, timeout=(12, 35), allow_redirects=True)
            r.raise_for_status()
            if len(r.content) < 3000 or "kch.or.kr" not in r.url:
                raise ValueError(f"unexpected response: bytes={len(r.content)}, final={r.url}")
            print(f"KCH_GET_OK attempt={attempt+1} status={r.status_code} bytes={len(r.content)}", flush=True)
            return r.content
        except (requests.RequestException, ValueError) as exc:
            print(f"KCH_GET_FAIL attempt={attempt+1}: {exc}", file=sys.stderr, flush=True)
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))


def collect(html):
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen = set()
    for a in soup.find_all("a", href=True):
        match = LINK.search(a.get("href", ""))
        if not match:
            continue
        number = int(match.group(1))
        if number in seen:
            continue
        # Official notice board uses row containers; do not scrape navigation labels.
        parent = a.find_parent("tr") or a.find_parent("li") or a.parent
        title = " ".join(a.stripped_strings).strip() or a.get("title", "").strip()
        title = re.sub(r"\s+", " ", title)
        if len(title) < 3 or len(title) > 300:
            continue
        date = normal_date(parent.get_text(" ", strip=True)) if parent else ""
        matches = [k for k in KEYWORDS if k in title]
        posts.append({
            "wr_no": number,
            "title": title,
            "date": date,
            "url": DETAIL + str(number),
            "relevant": bool(matches),
            "matched_keywords": matches,
            "detail_saved": False,
            "detail": None,
        })
        seen.add(number)
    if len(posts) < 10:
        raise RuntimeError(f"BAD_PARSE: only {len(posts)} unique notice links; old data preserved")
    dated = sum(bool(p["date"]) for p in posts)
    if dated < 5:
        raise RuntimeError(f"BAD_PARSE: only {dated}/{len(posts)} dates; old data preserved")
    previous_path = OUT / "kch_latest.json"
    if previous_path.exists():
        try:
            old = json.loads(previous_path.read_text(encoding="utf-8"))
            prev_posts = old.get("posts", [])
            oldmax = max(int(p["wr_no"]) for p in prev_posts)
            newmax = max(p["wr_no"] for p in posts)
            if newmax < oldmax:
                raise RuntimeError(f"STALE_PAGE: max id regressed {newmax} < {oldmax}")
            details = {int(p["wr_no"]): p for p in prev_posts}
            for post in posts:
                before = details.get(post["wr_no"], {})
                if before.get("detail_saved"):
                    post["detail_saved"] = True
                    post["detail"] = before.get("detail")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            print("WARNING: prior JSON could not be compared; continuing", file=sys.stderr)
    return posts


def main():
    raw = download()
    posts = collect(raw)
    now = dt.datetime.now(dt.timezone.utc)
    kst_date = now.astimezone(KST).date().isoformat()
    timestamp = now.isoformat(timespec="microseconds")
    relevant = [p for p in posts if p["relevant"]]
    data = {
        "generated_at": timestamp,
        "source": URL,
        "keywords": list(KEYWORDS),
        "post_count": len(posts),
        "relevant_count": len(relevant),
        "posts": posts,
        "relevant_posts": relevant,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    # Validate JSON before touching any existing public files.
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    json.loads(encoded)
    day_path = OUT / "daily" / (kst_date + ".json")
    day_path.parent.mkdir(parents=True, exist_ok=True)
    # All writes happen only after successful GET + structural validation.
    (OUT / "kch_latest.json").write_text(encoded, encoding="utf-8")
    day_path.write_text(encoded, encoding="utf-8")
    (OUT / "last_success.txt").write_text(timestamp + "\n", encoding="utf-8")
    status = {
        "published_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_generated_at": timestamp,
        "source_fresh_today_kst": True,
        "post_count": len(posts),
        "relevant_count": len(relevant),
        "collector": os.environ.get("KCH_COLLECTOR_NAME", "direct-server"),
    }
    (OUT / "mirror_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"KCH_DIRECT_SUCCESS generated_at={timestamp} day={kst_date} posts={len(posts)} relevant={len(relevant)}", flush=True)


if __name__ == "__main__":
    main()
