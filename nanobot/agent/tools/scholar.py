"""Semantic Scholar and arXiv academic search tools."""

from typing import Any
import xml.etree.ElementTree as ET

import httpx

from nanobot.agent.tools.base import Tool


class SemanticScholarTool(Tool):
    """Search academic papers via Semantic Scholar API."""

    name = "scholar_search"
    description = (
        "Search academic papers on Semantic Scholar. Returns titles, authors, year, "
        "abstract, citation count, and PDF links."
    )
    # NOTE: Flat schema for DeepSeek compat. When upgrading to GPT-5.2/Sonnet 4.5, consider richer nested schemas.
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g. 'MOF gas adsorption sensing')",
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20, default 10)",
                "minimum": 1,
                "maximum": 20,
            },
            "year": {
                "type": "string",
                "description": "Year filter, e.g. '2024' or '2023-2026' (optional)",
            },
            "fields_of_study": {
                "type": "string",
                "description": "Field filter, e.g. 'Materials Science' or 'Chemistry' (optional)",
            },
        },
        "required": ["query"],
    }

    API_BASE = "https://api.semanticscholar.org/graph/v1"
    FIELDS = (
        "title,authors,year,abstract,citationCount,influentialCitationCount,openAccessPdf,"
        "externalIds,fieldsOfStudy,publicationDate"
    )

    def __init__(self, api_key: str | None = None):
        # Semantic Scholar works without an API key (lower rate limit).
        self.api_key = api_key or ""

    async def execute(
        self,
        query: str,
        count: int | None = None,
        year: str | None = None,
        fields_of_study: str | None = None,
        **kwargs: Any,
    ) -> str:
        n = min(max(count or 10, 1), 20)
        params: dict[str, Any] = {
            "query": query,
            "limit": n,
            "fields": self.FIELDS,
        }
        if year:
            params["year"] = year
        if fields_of_study:
            params["fieldsOfStudy"] = fields_of_study

        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.API_BASE}/paper/search",
                    params=params,
                    headers=headers,
                    timeout=15.0,
                )
                response.raise_for_status()

            data = response.json()
            papers = data.get("data", [])
            if not papers:
                return f"No results for: {query}"

            total = data.get("total", len(papers))
            lines = [f"Found {total} results for: {query}\n"]

            for i, paper in enumerate(papers, 1):
                title = paper.get("title", "Untitled")
                year_val = paper.get("year", "N/A")
                citations = paper.get("citationCount", 0)

                authors_list = paper.get("authors", [])
                authors = ", ".join(author.get("name", "") for author in authors_list[:5])
                if len(authors_list) > 5:
                    authors += f" et al. ({len(authors_list)} authors)"

                pdf_info = paper.get("openAccessPdf")
                pdf_url = pdf_info.get("url", "") if pdf_info else ""

                abstract = paper.get("abstract", "")
                if abstract and len(abstract) > 300:
                    abstract = abstract[:300] + "..."

                ext_ids = paper.get("externalIds", {})
                doi = ext_ids.get("DOI", "")
                arxiv_id = ext_ids.get("ArXiv", "")

                lines.append(f"--- Paper {i} ---")
                lines.append(f"Title: {title}")
                lines.append(f"Authors: {authors}")
                lines.append(f"Year: {year_val} | Citations: {citations}")
                if doi:
                    lines.append(f"DOI: {doi}")
                if arxiv_id:
                    lines.append(f"arXiv: {arxiv_id}")
                if pdf_url:
                    lines.append(f"PDF: {pdf_url}")
                if abstract:
                    lines.append(f"Abstract: {abstract}")
                lines.append("")

            return "\n".join(lines)
        except httpx.HTTPStatusError as e:
            return f"Error: Semantic Scholar API returned {e.response.status_code}"
        except Exception as e:
            return f"Error: {e}"


class ArxivTool(Tool):
    """Search preprints on arXiv."""

    name = "arxiv_search"
    description = "Search preprints on arXiv. Returns titles, authors, abstract, PDF links."
    # NOTE: Flat schema for DeepSeek compat. When upgrading to GPT-5.2/Sonnet 4.5, consider richer nested schemas.
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g. 'MOF gas sensor selectivity')",
            },
            "count": {
                "type": "integer",
                "description": "Number of results (1-20, default 10)",
                "minimum": 1,
                "maximum": 20,
            },
            "sort_by": {
                "type": "string",
                "description": "Sort: 'relevance', 'lastUpdatedDate', or 'submittedDate'",
                "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
            },
        },
        "required": ["query"],
    }

    ARXIV_API = "http://export.arxiv.org/api/query"

    async def execute(
        self,
        query: str,
        count: int | None = None,
        sort_by: str | None = None,
        **kwargs: Any,
    ) -> str:
        n = min(max(count or 10, 1), 20)
        sort = sort_by or "relevance"

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": n,
            "sortBy": sort,
            "sortOrder": "descending",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.ARXIV_API, params=params, timeout=15.0)
                response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            if not entries:
                return f"No arXiv results for: {query}"

            lines = [f"arXiv results for: {query}\n"]
            for i, entry in enumerate(entries, 1):
                title = self._extract_atom_text(entry, "title", ns).replace("\n", " ").strip()
                summary = self._extract_atom_text(entry, "summary", ns).replace("\n", " ").strip()
                if len(summary) > 300:
                    summary = summary[:300] + "..."

                published = self._extract_atom_text(entry, "published", ns)[:10]  # YYYY-MM-DD

                authors = [
                    (node.text or "").strip()
                    for node in entry.findall("atom:author/atom:name", ns)
                    if (node.text or "").strip()
                ]
                author_str = ", ".join(authors[:5])
                if len(authors) > 5:
                    author_str += f" et al. ({len(authors)} authors)"

                pdf_url = ""
                for link in entry.findall("atom:link", ns):
                    href = link.attrib.get("href", "")
                    if link.attrib.get("title") == "pdf" and href:
                        pdf_url = href
                        break
                    if link.attrib.get("type") == "application/pdf" and href and not pdf_url:
                        pdf_url = href

                id_text = self._extract_atom_text(entry, "id", ns)
                arxiv_id = id_text.split("/abs/")[-1] if id_text else ""

                categories = [
                    node.attrib.get("term", "")
                    for node in entry.findall("atom:category", ns)
                    if node.attrib.get("term", "")
                ]
                category_str = ", ".join(categories[:3])

                lines.append(f"--- Paper {i} ---")
                lines.append(f"Title: {title}")
                lines.append(f"Authors: {author_str}")
                lines.append(f"Published: {published} | Categories: {category_str}")
                lines.append(f"arXiv ID: {arxiv_id}")
                if pdf_url:
                    lines.append(f"PDF: {pdf_url}")
                lines.append(f"Abstract: {summary}")
                lines.append("")

            return "\n".join(lines)
        except ET.ParseError as e:
            return f"Error: Failed to parse arXiv XML: {e}"
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def _extract_atom_text(entry: ET.Element, tag: str, ns: dict[str, str]) -> str:
        node = entry.find(f"atom:{tag}", ns)
        return (node.text or "").strip() if node is not None else ""
