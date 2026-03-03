"""
Simple web-search helpers for current-information lookups.
"""

import re
from html import unescape


async def brave_search(query: str, api_key: str, count: int = 5) -> str:
    """Search via Brave Search API and return formatted text results."""
    import aiohttp

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": count}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return f"Brave search failed ({resp.status}): {body[:300]}"
                payload = await resp.json()

        results = payload.get("web", {}).get("results", [])
        if not results:
            return "No web search results found."

        lines = []
        for item in results[:count]:
            title = item.get("title", "(no title)")
            result_url = item.get("url", "(no url)")
            description = item.get("description", "(no snippet)")
            lines.append(f"Title: {title}\nURL: {result_url}\nSnippet: {description}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Brave search error: {e}"


def _strip_html(text: str) -> str:
    stripped = re.sub(r"<[^>]+>", "", text)
    return unescape(stripped).strip()


async def duckduckgo_search(query: str, count: int = 5) -> str:
    """Fallback HTML scraping search using DuckDuckGo."""
    import aiohttp
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=20) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return f"DuckDuckGo search failed ({resp.status}): {body[:300]}"
                html = await resp.text()

        title_matches = re.findall(
            r'<a[^>]*class="result__a"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet_matches = re.findall(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        url_matches = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )

        if not title_matches:
            return "No web search results found."

        lines = []
        for idx, raw_title in enumerate(title_matches[:count]):
            title = _strip_html(raw_title)
            result_url = url_matches[idx] if idx < len(url_matches) else "(no url)"
            snippet = (
                _strip_html(snippet_matches[idx])
                if idx < len(snippet_matches)
                else "(no snippet)"
            )
            lines.append(f"Title: {title}\nURL: {result_url}\nSnippet: {snippet}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"DuckDuckGo search error: {e}"
