from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import ConfigError, load_config
from .models import utc_now
from .offline import require_online

if TYPE_CHECKING:
    from .store import RunStore
    from .tools.dispatcher import ToolResult


class WebToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebConfig:
    mode: str = "off"
    search_endpoint: str = ""
    allow_domains: tuple[str, ...] = ()
    deny_domains: tuple[str, ...] = ()
    max_bytes: int = 200_000
    user_agent: str = "poor-cli-web/1"
    respect_robots: bool = False
    timeout_seconds: int = 10


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _default_urlopen(request: urllib.request.Request, timeout: int = 10) -> Any:
    return _opener.open(request, timeout=timeout)


urlopen = _default_urlopen


def web_search(root: Path, store: RunStore | None, run_id: str | None, args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        raise WebToolError("query is required")
    require_online("web_search")
    config = _web_config(root)
    mode = str(args.get("mode") or config.mode)
    if mode == "native":
        payload = _native_search(root, query)
    elif mode == "custom":
        payload = _custom_search(config, query)
    elif mode == "free":
        payload = _free_search(config, query)
    else:
        return _result("web_search", False, error="web_search is disabled; configure tools.web.mode")
    payload["timestamp"] = utc_now()
    payload["query"] = query
    artifact_id = _record(store, run_id, "web.search", payload)
    payload["replay_id"] = artifact_id
    _record_citations(store, run_id, payload.get("results") or [], "web_search")
    return _result("web_search", True, payload)


def web_fetch(root: Path, store: RunStore | None, run_id: str | None, args: dict[str, Any]) -> ToolResult:
    raw_url = str(args.get("url") or "").strip()
    if not raw_url:
        raise WebToolError("url is required")
    require_online("web_fetch")
    config = _web_config(root)
    url = _safe_url(raw_url, config)
    robots = _robots_check(url, config) if config.respect_robots else {"allowed": True, "checked": False}
    if robots.get("allowed") is False:
        return _result("web_fetch", False, error=f"robots.txt disallows fetch: {url}", raw={"robots": robots})
    response = _open_checked(url, config)
    final_url = _safe_url(response["final_url"], config)
    data = response["body"]
    truncated = len(data) > config.max_bytes
    body = data[: config.max_bytes]
    content_type = response["content_type"]
    text = _sanitize(body.decode(_charset(content_type), errors="replace"), content_type)
    payload = {
        "url": url,
        "final_url": final_url,
        "content_type": content_type,
        "byte_count": len(data),
        "truncated": truncated,
        "content_hash": hashlib.sha256(body).hexdigest(),
        "content": text,
        "timestamp": utc_now(),
        "robots": robots,
    }
    artifact_id = _record(store, run_id, "web.fetch", payload)
    payload["replay_id"] = artifact_id
    _record(store, run_id, "web.cache", {key: payload[key] for key in ("url", "final_url", "content_hash", "timestamp")})
    _record_citations(store, run_id, [{"url": final_url, "title": final_url, "snippet": text[:240]}], "web_fetch")
    return _result("web_fetch", True, payload)


def _web_config(root: Path) -> WebConfig:
    try:
        config = load_config(root)
    except ConfigError:
        config = {}
    tools = config.get("tools") if isinstance(config, dict) else {}
    raw = tools.get("web") if isinstance(tools, dict) else {}
    web = raw if isinstance(raw, dict) else {}
    return WebConfig(
        mode=str(web.get("mode") or "off"),
        search_endpoint=str(web.get("search_endpoint") or ""),
        allow_domains=tuple(str(item).lower() for item in web.get("allow_domains") or []),
        deny_domains=tuple(str(item).lower() for item in web.get("deny_domains") or []),
        max_bytes=max(1, int(web.get("max_bytes") or 200_000)),
        user_agent=str(web.get("user_agent") or "poor-cli-web/1"),
        respect_robots=bool(web.get("respect_robots", False)),
        timeout_seconds=max(1, int(web.get("timeout_seconds") or 10)),
    )


def _native_search(root: Path, query: str) -> dict[str, Any]:
    config = load_config(root)
    route = config.get("routes", {}).get("researcher") or config.get("routes", {}).get("executor") or {}
    profile_id = str(route.get("profile") or config.get("active_provider") or "")
    profile = config.get("providers", {}).get(profile_id)
    caps = profile.get("capabilities") if isinstance(profile, dict) else {}
    if not isinstance(caps, dict) or not caps.get("web"):
        raise WebToolError("native web mode requires a provider profile with web capability")
    return {"source_provider": "native", "provider_profile": profile_id, "results": [], "provider_hosted": True}


def _custom_search(config: WebConfig, query: str) -> dict[str, Any]:
    if not config.search_endpoint:
        raise WebToolError("custom web search requires tools.web.search_endpoint")
    endpoint = _safe_url(config.search_endpoint, config)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": config.user_agent},
        method="POST",
    )
    with urlopen(request, timeout=config.timeout_seconds) as response:
        raw = json.loads(response.read().decode())
    results = _search_results(raw)
    return {"source_provider": "custom", "results": results}


def _free_search(config: WebConfig, query: str) -> dict[str, Any]:
    endpoint = config.search_endpoint or "https://duckduckgo.com/html/"
    url = _safe_url(f"{endpoint}?q={urllib.parse.quote(query)}", config)
    response = _open_checked(url, config)
    text = response["body"][: config.max_bytes].decode("utf-8", errors="replace")
    results = _parse_links(text, response["final_url"])[:5]
    return {"source_provider": "free-best-effort", "results": results}


def _search_results(payload: Any) -> list[dict[str, str]]:
    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        raise WebToolError("search endpoint response must contain results list")
    results = []
    for row in raw_results:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if not title or not url:
            raise WebToolError("search result requires title and url")
        results.append({"title": title, "url": url, "snippet": snippet, "source_provider": str(row.get("source_provider") or "")})
    return results


def _open_checked(url: str, config: WebConfig) -> dict[str, Any]:
    current = url
    for _ in range(4):
        request = urllib.request.Request(current, headers={"User-Agent": config.user_agent})
        try:
            with urlopen(request, timeout=config.timeout_seconds) as response:
                final = str(response.geturl() or current)
                body = response.read(config.max_bytes + 1)
                headers = response.headers
                return {"final_url": final, "body": body, "content_type": headers.get("Content-Type", "application/octet-stream")}
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location")
            if not location:
                raise WebToolError(f"redirect without location: {current}") from exc
            current = _safe_url(urllib.parse.urljoin(current, location), config)
    raise WebToolError(f"too many redirects: {url}")


def _safe_url(value: str, config: WebConfig) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise WebToolError(f"blocked URL scheme: {parsed.scheme or '<empty>'}")
    if parsed.username or parsed.password:
        raise WebToolError("blocked URL credentials")
    host = (parsed.hostname or "").strip(".").lower()
    if not host:
        raise WebToolError("URL host is required")
    if host == "localhost" or host.endswith(".localhost"):
        raise WebToolError("blocked localhost host")
    for ip in _resolved_ips(host):
        if not ip.is_global:
            raise WebToolError(f"blocked private or reserved address: {ip}")
    if config.allow_domains and not _domain_match(host, config.allow_domains):
        raise WebToolError(f"domain not in allowlist: {host}")
    if config.deny_domains and _domain_match(host, config.deny_domains):
        raise WebToolError(f"domain denied: {host}")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _resolved_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return []
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except (IndexError, ValueError):
            continue
    return out


def _domain_match(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _robots_check(url: str, config: WebConfig) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        response = _open_checked(robots_url, config)
    except Exception as exc:
        return {"checked": True, "allowed": True, "status": "unavailable", "error": str(exc)}
    rules = _parse_robots(response["body"].decode("utf-8", errors="replace"))
    path = parsed.path or "/"
    disallowed = any(path.startswith(rule) for rule in rules if rule)
    return {"checked": True, "allowed": not disallowed, "status": "ok", "robots_url": robots_url}


def _parse_robots(text: str) -> list[str]:
    active = False
    disallow: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            active = value in {"*", "poor-cli-web/1"}
        elif active and key == "disallow":
            disallow.append(value)
    return disallow


def _parse_links(text: str, base_url: str) -> list[dict[str, str]]:
    matches = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, flags=re.I | re.S)
    results = []
    for href, label in matches:
        url = urllib.parse.urljoin(base_url, html.unescape(href))
        title = re.sub(r"<[^>]+>", "", label)
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        if title and url.startswith(("http://", "https://")):
            results.append({"title": title, "url": url, "snippet": "", "source_provider": "free-best-effort"})
    return results


def _sanitize(text: str, content_type: str) -> str:
    if "html" in content_type:
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.I)
    return match.group(1) if match else "utf-8"


def _record(store: RunStore | None, run_id: str | None, kind: str, payload: dict[str, Any]) -> str:
    if store is None or not run_id:
        return ""
    artifact = store.put_artifact(run_id=run_id, kind=kind, data=payload)
    store.append_event(run_id, f"{kind}.created", {"artifact_id": artifact.artifact_id})
    return artifact.artifact_id


def _record_citations(store: RunStore | None, run_id: str | None, results: list[Any], source: str) -> None:
    for row in results:
        if isinstance(row, dict) and row.get("url"):
            _record(
                store,
                run_id,
                "web.citation",
                {"source": source, "url": str(row.get("url")), "title": str(row.get("title") or ""), "timestamp": utc_now()},
            )


def _result(name: str, ok: bool, output: Any = None, error: str | None = None, raw: dict[str, Any] | None = None) -> ToolResult:
    from .tools.dispatcher import ToolResult

    return ToolResult(name=name, ok=ok, output=output, error=error, raw=raw or {})
