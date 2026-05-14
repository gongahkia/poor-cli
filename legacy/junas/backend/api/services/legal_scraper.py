"""Legal source scraping service ported from Junas legal_api.rs."""
from __future__ import annotations
import logging
from dataclasses import dataclass
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SSO_BASE = "https://sso.agc.gov.sg"
COMMONLII_BASE = "https://www.commonlii.org"
REQUEST_TIMEOUT = 15

@dataclass
class LegalSearchResult:
    title: str
    url: str
    snippet: str
    source: str

async def search_sso_statutes(query: str, max_results: int = 10) -> list[LegalSearchResult]:
    url = f"{SSO_BASE}/Search/Content?SearchPhrase={quote_plus(query)}&Category=Acts"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers={"User-Agent": "Junas/1.0 (legal-research-tool)"})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    results: list[LegalSearchResult] = []
    for a_tag in soup.find_all("a", href=True):
        if len(results) >= max_results:
            break
        href = a_tag["href"]
        text = a_tag.get_text(strip=True)
        if not text or len(text) < 3:
            continue
        if "/Act/" not in href and "/SL/" not in href:
            continue
        full_url = href if href.startswith("http") else f"{SSO_BASE}{href}"
        results.append(LegalSearchResult(
            title=text[:200], url=full_url,
            snippet=f"Singapore statute matching '{query}'", source="SSO",
        ))
    return results

async def search_commonlii_cases(query: str, max_results: int = 10) -> list[LegalSearchResult]:
    url = f"{COMMONLII_BASE}/cgi-bin/sinosrch.cgi?method=auto&query={quote_plus(query)}&meta=%2Fsg&mask_path="
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(url, headers={"User-Agent": "Junas/1.0 (legal-research-tool)"})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    results: list[LegalSearchResult] = []
    for li in soup.find_all("li"):
        if len(results) >= max_results:
            break
        a_tag = li.find("a", href=True)
        if not a_tag:
            continue
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)
        if not title:
            continue
        full_url = href if href.startswith("http") else f"{COMMONLII_BASE}{href}"
        snippet_parts = li.get_text(strip=True).replace(title, "", 1).strip()
        results.append(LegalSearchResult(
            title=title[:200], url=full_url,
            snippet=snippet_parts[:300], source="CommonLII",
        ))
    return results
