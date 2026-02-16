"""CIF file management and query tool for MOF structures."""

import json
import re
from pathlib import Path
from typing import Any

import httpx

from nanobot.agent.tools.base import Tool


class CifManagerTool(Tool):
    """Manage and query CIF (Crystallographic Information File) structures."""

    name = "cif_manager"
    description = (
        "Manage MOF crystal structure CIF files. Actions: search (query index), "
        "info (read CIF header), import (add CIF file), list (show all entries), "
        "stats (database statistics)."
    )
    # NOTE: Flat schema for DeepSeek compat. When upgrading to GPT-5.2/Sonnet 4.5, consider richer nested schemas.
    # NOTE: 'metadata' is a JSON string for DeepSeek compatibility.
    #       Upgrade to nested object schema when switching to GPT-5.2/Sonnet 4.5.
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action to perform",
                "enum": ["search", "info", "import", "list", "stats"],
            },
            "query": {
                "type": "string",
                "description": (
                    "For search: keyword to match against name/formula/metal/linker/topology. "
                    "For info: MOF name."
                ),
            },
            "path": {
                "type": "string",
                "description": "For import: path to CIF file to import.",
            },
            "url": {
                "type": "string",
                "description": "For import: URL to download CIF file from.",
            },
            "metadata": {
                "type": "string",
                "description": (
                    "For import: JSON string with metadata like "
                    "{\"formula\": \"Cu3(BTC)2\", \"metal_center\": \"Cu\", \"linker\": \"BTC\", "
                    "\"topology\": \"tbo\", \"source\": \"CoRE-MOF\"}"
                ),
            },
        },
        "required": ["action"],
    }

    def __init__(self, workspace: Path | None = None):
        self.workspace = workspace or Path.cwd()
        self.data_dir = self.workspace / "mof_data"
        self.cif_dir = self.data_dir / "cif"
        self.computed_dir = self.data_dir / "computed"
        self.index_path = self.data_dir / "index.json"

    def _ensure_dirs(self) -> None:
        self.cif_dir.mkdir(parents=True, exist_ok=True)
        self.computed_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self, index: dict[str, Any]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _sanitize_name(name: str) -> str:
        cleaned = re.sub(r"[^\w\-.]", "_", (name or "").strip())
        cleaned = cleaned.strip("._")
        return cleaned or "unnamed_mof"

    async def execute(
        self,
        action: str,
        query: str | None = None,
        path: str | None = None,
        url: str | None = None,
        metadata: str | None = None,
        **kwargs: Any,
    ) -> str:
        self._ensure_dirs()

        if action == "search":
            return self._search(query or "")
        if action == "info":
            return self._info(query or "")
        if action == "import":
            return await self._import_cif(path=path, url=url, metadata_str=metadata)
        if action == "list":
            return self._list_all()
        if action == "stats":
            return self._stats()
        return f"Error: Unknown action '{action}'. Use: search, info, import, list, stats."

    def _search(self, query: str) -> str:
        if not query:
            return "Error: 'query' is required for search action"

        index = self._load_index()
        if not index:
            return "CIF database is empty. Use 'import' to add CIF files."

        query_lower = query.lower()
        matches: list[tuple[str, dict[str, Any]]] = []
        for name, entry in index.items():
            searchable = " ".join(
                [
                    name,
                    entry.get("formula", ""),
                    entry.get("metal_center", ""),
                    entry.get("linker", ""),
                    entry.get("topology", ""),
                    entry.get("source", ""),
                ]
            ).lower()
            if query_lower in searchable:
                matches.append((name, entry))

        if not matches:
            return f"No CIF entries match '{query}'"

        lines = [f"Found {len(matches)} matches for '{query}':\n"]
        for name, entry in matches[:20]:
            formula = entry.get("formula", "N/A")
            metal = entry.get("metal_center", "N/A")
            source = entry.get("source", "N/A")
            lines.append(f"  {name}: {formula} (metal: {metal}, source: {source})")

            computed = entry.get("computed", {})
            if computed:
                lcd = computed.get("lcd", "?")
                pld = computed.get("pld", "?")
                sa = computed.get("sa_m2g", "?")
                vf = computed.get("void_fraction", "?")
                lines.append(f"    LCD={lcd}Å PLD={pld}Å SA={sa}m²/g VF={vf}")

        if len(matches) > 20:
            lines.append(f"\n... and {len(matches) - 20} more. Refine your query.")

        return "\n".join(lines)

    def _info(self, name: str) -> str:
        if not name:
            return "Error: 'query' (MOF name) is required for info action"

        index = self._load_index()
        entry = index.get(name)

        if not entry:
            for key, value in index.items():
                if key.lower() == name.lower():
                    name = key
                    entry = value
                    break

        if not entry:
            return f"MOF '{name}' not found in index. Use 'search' to find available entries."

        cif_path = self.cif_dir / entry.get("file", f"{name}.cif")
        lines = [f"MOF: {name}"]
        lines.append(f"Formula: {entry.get('formula', 'N/A')}")
        lines.append(f"Metal center: {entry.get('metal_center', 'N/A')}")
        lines.append(f"Linker: {entry.get('linker', 'N/A')}")
        lines.append(f"Topology: {entry.get('topology', 'N/A')}")
        lines.append(f"Source: {entry.get('source', 'N/A')}")
        lines.append(f"CIF file: {cif_path}")

        computed = entry.get("computed", {})
        if computed:
            lines.append("\nComputed properties:")
            for key, value in computed.items():
                lines.append(f"  {key}: {value}")

        if cif_path.exists():
            try:
                cif_text = cif_path.read_text(encoding="utf-8", errors="replace")
                header_lines = []
                for line in cif_text.split("\n")[:50]:
                    if line.startswith("_cell_") or line.startswith("_symmetry_"):
                        header_lines.append(line.strip())
                if header_lines:
                    lines.append("\nCrystal data (from CIF):")
                    for header_line in header_lines:
                        lines.append(f"  {header_line}")
            except Exception:
                pass

        return "\n".join(lines)

    async def _import_cif(
        self,
        path: str | None = None,
        url: str | None = None,
        metadata_str: str | None = None,
    ) -> str:
        metadata: dict[str, Any] = {}
        if metadata_str:
            try:
                metadata = json.loads(metadata_str)
            except json.JSONDecodeError:
                return "Error: 'metadata' must be a valid JSON string"

        if url:
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    response = await client.get(url, timeout=30.0)
                    response.raise_for_status()
                    content = response.text

                raw_name = metadata.pop("name", None)
                if not raw_name:
                    raw_name = url.rstrip("/").split("/")[-1]
                    raw_name = re.sub(r"\.cif$", "", raw_name, flags=re.I)
                name = self._sanitize_name(raw_name)

                cif_path = self.cif_dir / f"{name}.cif"
                cif_path.write_text(content, encoding="utf-8")
            except Exception as e:
                return f"Error downloading CIF: {e}"
        elif path:
            source_path = Path(path).expanduser()
            if not source_path.exists():
                return f"Error: File not found: {path}"

            raw_name = metadata.pop("name", None) or source_path.stem
            name = self._sanitize_name(raw_name)
            cif_path = self.cif_dir / f"{name}.cif"

            if source_path != cif_path:
                import shutil

                shutil.copy2(source_path, cif_path)
        else:
            return "Error: Either 'path' or 'url' is required for import"

        index = self._load_index()
        index[name] = {
            "file": f"{name}.cif",
            "source": metadata.get("source", "manual"),
            "formula": metadata.get("formula", ""),
            "metal_center": metadata.get("metal_center", ""),
            "linker": metadata.get("linker", ""),
            "topology": metadata.get("topology", ""),
        }
        self._save_index(index)
        return f"Imported: {name} -> {cif_path}"

    def _list_all(self) -> str:
        index = self._load_index()
        if not index:
            return "CIF database is empty."

        lines = [f"CIF database: {len(index)} entries\n"]
        for name, entry in list(index.items())[:50]:
            formula = entry.get("formula", "N/A")
            metal = entry.get("metal_center", "N/A")
            has_computed = "yes" if entry.get("computed") else "no"
            lines.append(f"  {name}: {formula} (metal: {metal}) [computed: {has_computed}]")

        if len(index) > 50:
            lines.append(f"\n... showing 50 of {len(index)}. Use 'search' to filter.")
        return "\n".join(lines)

    def _stats(self) -> str:
        index = self._load_index()
        total = len(index)
        computed_count = sum(1 for item in index.values() if item.get("computed"))
        metals = {item.get("metal_center", "") for item in index.values() if item.get("metal_center")}
        sources = {item.get("source", "") for item in index.values() if item.get("source")}

        cif_files = list(self.cif_dir.glob("*.cif")) if self.cif_dir.exists() else []
        orphan_files = max(0, len(cif_files) - total)

        lines = [
            "CIF Database Statistics:",
            f"  Total entries: {total}",
            f"  With computed properties: {computed_count}",
            f"  CIF files on disk: {len(cif_files)}",
            f"  Unindexed files: {orphan_files}",
            f"  Metal centers: {', '.join(sorted(metals)) if metals else 'N/A'}",
            f"  Sources: {', '.join(sorted(sources)) if sources else 'N/A'}",
        ]
        return "\n".join(lines)
