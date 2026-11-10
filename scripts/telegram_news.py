#!/usr/bin/env python3
"""
telegram_news.py
─────────────────────────────────────────────────────────────────
Lets the site owner edit the Home page News section by sending messages
to a private Telegram bot. GitHub Actions runs this every 10 minutes
(see .github/workflows/telegram_news.yml).

Commands (send them to the bot):
  /news Title | detail | https://link | 2027
        Adds an item to the News list, placed by year (newest first, a new
        item goes above older items of the same year). Only the title is
        required. The other parts can come in any order: a part starting
        with http(s):// or www. is the link (the title becomes clickable;
        the address itself is not shown), a 4-digit number is the year (default:
        the current year), anything else is the detail line. A new line
        works as a separator too.
  /list        Shows the current news items, numbered.
  /delete N    Removes item N of /list.
  /undo        Removes the top item (same as /delete 1).
  /help        Shows this help.

Environment:
  TELEGRAM_BOT_TOKEN   token from @BotFather
  TELEGRAM_USER_ID     numeric Telegram id of the only person allowed
  GITHUB_OUTPUT        (set by Actions) receives changed=true|false

Safety:
  - Messages from anyone else are ignored.
  - _data/cv.yml is edited as text, so comments and layout are kept; every
    edit is checked with a YAML parser before it is accepted.
  - Messages are acknowledged to Telegram only after the commit is pushed.
    If the push fails, Telegram keeps them and the next run retries.
  - Without the two secrets the script does nothing and exits normally.
─────────────────────────────────────────────────────────────────
"""

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CV = ROOT / "_data" / "cv.yml"

HELP = (
    "Commands:\n"
    "/news Title | detail | https://link | 2027\n"
    "   adds a news item (only the title is required; a new line also\n"
    "   works as separator; the year defaults to this year)\n"
    "/list - show the current news, numbered\n"
    "/delete N - remove item N\n"
    "/undo - remove the top item\n"
    "/help - this message"
)


# ── Telegram ────────────────────────────────────────────────────

def api(token, method, **params):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in params.items()}
    ).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as r:
        body = json.load(r)
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {body}")
    return body["result"]


# ── Editing the news block of cv.yml ─────────────────────────────

def split_news(text):
    """Return (before, head, items, after): the news block cut into its items.

    head = lines between 'news:' and the first item (e.g. indented comments);
    items = list of item texts, each starting with '  - '.
    """
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, l in enumerate(lines) if l.rstrip() == "news:")
    except StopIteration:
        raise RuntimeError("No top-level 'news:' key found in _data/cv.yml")
    end = start + 1
    while end < len(lines):
        l = lines[end]
        if l.strip() and not l.startswith((" ", "\t")):
            break  # next top-level key or column-0 comment
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1  # keep blank lines that separate sections outside the block

    head, items = [], []
    for l in lines[start + 1:end]:
        if l.startswith("  - "):
            items.append(l)
        elif items:
            items[-1] += l
        else:
            head.append(l)
    before = "".join(lines[:start + 1])
    after = "".join(lines[end:])
    return before, "".join(head), items, after


def join_news(before, head, items, after):
    body = head + "".join(i if i.endswith("\n") else i + "\n" for i in items)
    return before + body + after


def load_news(text):
    news = (yaml.safe_load(text) or {}).get("news") or []
    if not isinstance(news, list):
        raise RuntimeError("'news' in cv.yml is not a list")
    return news


def q(s):
    """Quote a string for YAML (a JSON string is a valid YAML scalar)."""
    return json.dumps(s, ensure_ascii=False)


def parse_news_args(arg):
    parts = [p.strip() for p in re.split(r"[|\n]", arg) if p.strip()]
    if not parts:
        raise ValueError("Please give at least a title, e.g.\n/news Keynote at IEEE SENSORS | Vienna, Austria")
    item = {"title": parts[0], "year": datetime.date.today().year}
    details = []
    for p in parts[1:]:
        if re.match(r"https?://\S+$", p):
            item["url"] = p
        elif re.match(r"www\.\S+\.\S+$", p):
            item["url"] = "https://" + p
        elif re.fullmatch(r"(19|20)\d\d", p):
            item["year"] = int(p)
        else:
            details.append(p)
    if details:
        item["detail"] = " · ".join(details)
    return item


def add_news(text, item):
    before, head, items, after = split_news(text)
    block = f"  - year: {item['year']}\n    title: {q(item['title'])}\n"
    if "url" in item:
        block += f"    url: {q(item['url'])}\n"
    if "detail" in item:
        block += f"    detail: {q(item['detail'])}\n"
    old_news = load_news(text)
    if len(old_news) != len(items):
        raise RuntimeError("Could not read the news list in cv.yml; nothing was changed")
    # Newest first: put the item above the first one of the same or an older year.
    pos = next((i for i, n in enumerate(old_news)
                if not isinstance(n.get("year"), int) or n["year"] <= item["year"]), len(items))
    new = join_news(before, head, items[:pos] + [block] + items[pos:], after)
    new_news = load_news(new)
    expected = {k: item[k] for k in ("year", "title", "url", "detail") if k in item}
    if len(new_news) != len(old_news) + 1 or new_news[pos] != expected:
        raise RuntimeError("Check failed after adding the item; nothing was changed")
    return new, pos + 1


def delete_news(text, n):
    before, head, items, after = split_news(text)
    if not 1 <= n <= len(items):
        raise ValueError(f"There is no item {n}; the list has {len(items)} items (see /list)")
    old_news = load_news(text)
    removed = old_news[n - 1]
    new = join_news(before, head, items[:n - 1] + items[n:], after)
    new_news = load_news(new)
    if new_news != old_news[:n - 1] + old_news[n:]:
        raise RuntimeError("Check failed after removing the item; nothing was changed")
    return new, removed


def list_news(text):
    news = load_news(text)
    if not news:
        return "The News list is empty."
    rows = []
    for i, n in enumerate(news, 1):
        row = f"{i}. [{n.get('year', '')}] {n.get('title', '')}"
        if n.get("detail"):
            row += f"\n    {n['detail']}"
        rows.append(row)
    out = "\n".join(rows)
    return out if len(out) < 3900 else out[:3900] + "\n…"


# ── Handling messages ───────────────────────────────────────────

def handle(text, msg_text):
    """Return (new_text, reply, commit_note or None)."""
    m = re.match(r"\s*/(\w+)(?:@\w+)?\s*(.*)", msg_text or "", re.S)
    if not m:
        return text, "I only understand commands.\n\n" + HELP, None
    cmd, arg = m.group(1).lower(), m.group(2).strip()

    if cmd in ("start", "help"):
        return text, HELP, None
    if cmd == "list":
        return text, list_news(text), None
    if cmd == "news":
        item = parse_news_args(arg)
        new, pos = add_news(text, item)
        return (new, f"✅ Added to News as item {pos} (newest first):\n[{item['year']}] {item['title']}",
                f"add \"{item['title']}\"")
    if cmd in ("delete", "undo"):
        if cmd == "undo":
            n = 1
        elif arg.isdigit():
            n = int(arg)
        else:
            raise ValueError("Use /delete N, where N is the number shown by /list")
        new, removed = delete_news(text, n)
        title = removed.get("title", "")
        return new, f"🗑 Removed from News:\n{title}", f"remove \"{title}\""
    return text, f"Unknown command /{cmd}.\n\n" + HELP, None


def git(*args):
    subprocess.run(["git", *args], cwd=ROOT, check=True)


def commit_and_push(notes):
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git("add", str(CV.relative_to(ROOT)))
    msg = "news: " + "; ".join(notes) + " (via Telegram)"
    git("commit", "-m", msg)
    for attempt in range(3):
        try:
            git("pull", "--rebase", "origin", "main")
            git("push", "origin", "HEAD:main")
            return
        except subprocess.CalledProcessError:
            print(f"Push failed (attempt {attempt + 1}), retrying…")
    raise RuntimeError("Could not push the change to GitHub")


def set_output(changed):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    owner = os.environ.get("TELEGRAM_USER_ID", "").strip()
    if not token or not owner.isdigit():
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_USER_ID not set; nothing to do.")
        set_output(False)
        return
    owner = int(owner)

    updates = api(token, "getUpdates", timeout=0, allowed_updates=["message"])
    if not updates:
        print("No new messages.")
        set_output(False)
        return
    last_id = max(u["update_id"] for u in updates)

    original = text = CV.read_text(encoding="utf-8")
    replies, notes = [], []
    for u in updates:
        msg = u.get("message") or {}
        sender = (msg.get("from") or {}).get("id")
        chat = (msg.get("chat") or {}).get("id")
        if sender != owner or chat is None:
            print(f"Ignored update {u['update_id']} from {sender}")
            continue
        try:
            text, reply, note = handle(text, msg.get("text"))
            if note:
                notes.append(note)
        except (ValueError, RuntimeError) as e:
            reply = f"⚠️ {e}"
        replies.append((chat, reply))

    changed = text != original
    if changed:
        CV.write_text(text, encoding="utf-8")
        commit_and_push(notes)  # on failure: exit with error, nothing is acknowledged
        replies = [(c, r + ("\nThe site will update in about 2 minutes." if r.startswith(("✅", "🗑")) else ""))
                   for c, r in replies]

    for chat, reply in replies:
        try:
            api(token, "sendMessage", chat_id=chat, text=reply, disable_web_page_preview=True)
        except Exception as e:  # a failed reply must not block the acknowledgement
            print(f"Could not send reply: {e}")

    api(token, "getUpdates", offset=last_id + 1, timeout=0)  # acknowledge processed messages
    print(f"Processed {len(updates)} update(s); changed={changed}")
    set_output(changed)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
