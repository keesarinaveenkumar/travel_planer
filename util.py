"""Small helpers shared by the web pages and the PDF export."""
import re


def inr(n):
    """Format like toLocaleString('en-IN'): ₹1,23,456."""
    n = int(n or 0)
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def slug(text, default="plan"):
    """ASCII-only, filename-safe version of a place name."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-")
    return s[:40] or default
