"""Zeo++ geometry computation tool for MOF structures."""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class ZeoppTool(Tool):
    """Run Zeo++ geometric analysis on MOF crystal structures."""

    name = "zeopp"
    description = (
        "Run Zeo++ geometry calculations on a CIF file. Computes pore diameters, "
        "surface area, pore volume, etc. Requires Zeo++ Docker container or local installation."
    )
    # NOTE: Flat schema for DeepSeek compat. When upgrading to GPT-5.2/Sonnet 4.5, consider richer nested schemas.
    # NOTE: 'calculations' is a comma-separated string for DeepSeek compatibility.
    #       Upgrade to array schema when switching to GPT-5.2/Sonnet 4.5.
    parameters = {
        "type": "object",
        "properties": {
            "cif_name": {
                "type": "string",
                "description": "Name of the MOF in the CIF database (e.g. 'HKUST-1')",
            },
            "calculations": {
                "type": "string",
                "description": (
                    "Comma-separated calculations: 'res' (pore diameters), "
                    "'sa' (surface area), 'vol' (pore volume), 'chan' (channels), 'all'. "
                    "Default: 'all'"
                ),
            },
            "probe_radius": {
                "type": "number",
                "description": "Probe radius in Angstroms (default 1.86 for N2)",
            },
        },
        "required": ["cif_name"],
    }

    def __init__(
        self,
        workspace: Path | None = None,
        use_docker: bool = True,
        docker_image: str = "zeopp:latest",
        zeopp_binary: str = "network",
    ):
        self.workspace = workspace or Path.cwd()
        self.data_dir = self.workspace / "mof_data"
        self.cif_dir = self.data_dir / "cif"
        self.computed_dir = self.data_dir / "computed"
        self.index_path = self.data_dir / "index.json"
        self.use_docker = use_docker
        self.docker_image = docker_image
        self.zeopp_binary = zeopp_binary

    async def execute(
        self,
        cif_name: str,
        calculations: str | None = None,
        probe_radius: float | None = None,
        **kwargs: Any,
    ) -> str:
        calcs = [item.strip().lower() for item in (calculations or "all").split(",") if item.strip()]
        if not calcs:
            calcs = ["all"]
        if "all" in calcs:
            calcs = ["res", "sa", "vol", "chan"]

        if "/" in cif_name or "\\" in cif_name or ".." in cif_name:
            return "Error: Invalid cif_name (path separators are not allowed)"

        probe = probe_radius or 1.86

        cif_path = self.cif_dir / f"{cif_name}.cif"
        if not cif_path.exists():
            for candidate in self.cif_dir.glob("*.cif"):
                if candidate.stem.lower() == cif_name.lower():
                    cif_path = candidate
                    cif_name = candidate.stem
                    break
            else:
                return (
                    f"Error: CIF file not found for '{cif_name}'. "
                    "Use cif_manager to import it first."
                )

        self.computed_dir.mkdir(parents=True, exist_ok=True)
        results: dict[str, Any] = {"mof_name": cif_name}
        errors: list[str] = []

        for calc in calcs:
            try:
                output = await self._run_calculation(cif_path, cif_name, calc, probe)
                results[calc] = self._parse_output(calc, output)
            except Exception as e:
                errors.append(f"{calc}: {e}")

        computed_path = self.computed_dir / f"{cif_name}_geo.json"
        computed_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

        self._update_index(cif_name, results)

        lines = [f"Zeo++ results for {cif_name}:"]
        lines.append(f"Probe radius: {probe} Å (N2)\n")

        if "res" in results:
            res = results["res"]
            lines.append("Pore diameters:")
            lines.append(f"  Largest cavity diameter (LCD): {res.get('lcd', 'N/A')} Å")
            lines.append(f"  Pore limiting diameter (PLD): {res.get('pld', 'N/A')} Å")
            lines.append(f"  Largest free sphere diameter: {res.get('lfsd', 'N/A')} Å")

        if "sa" in results:
            sa = results["sa"]
            lines.append("\nSurface area:")
            lines.append(f"  ASA (Accessible): {sa.get('asa_m2g', 'N/A')} m²/g")
            lines.append(f"  NASA (Non-accessible): {sa.get('nasa_m2g', 'N/A')} m²/g")

        if "vol" in results:
            vol = results["vol"]
            lines.append("\nPore volume:")
            lines.append(f"  Accessible volume: {vol.get('av_fraction', 'N/A')}")
            lines.append(f"  Accessible volume (cm³/g): {vol.get('av_cm3g', 'N/A')}")

        if "chan" in results:
            chan = results["chan"]
            lines.append("\nChannel analysis:")
            lines.append(f"  Dimensionality: {chan.get('dimensionality', 'N/A')}")

        if errors:
            lines.append(f"\nErrors: {'; '.join(errors)}")

        lines.append(f"\nFull results saved: {computed_path}")
        return "\n".join(lines)

    async def _run_calculation(self, cif_path: Path, name: str, calc: str, probe: float) -> str:
        """Run a single Zeo++ calculation."""
        output_suffix = {"res": ".res", "sa": ".sa", "vol": ".vol", "chan": ".chan"}
        suffix = output_suffix.get(calc, f".{calc}")
        output_file = self.computed_dir / f"{name}{suffix}"

        if self.use_docker:
            args = self._docker_args(cif_path, output_file, calc, probe)
        else:
            args = self._local_args(cif_path, output_file, calc, probe)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

        if process.returncode != 0:
            err_text = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Zeo++ {calc} failed (exit {process.returncode}): {err_text[:300]}")

        if output_file.exists():
            return output_file.read_text(encoding="utf-8")
        return stdout.decode("utf-8", errors="replace")

    def _docker_args(self, cif_path: Path, output_file: Path, calc: str, probe: float) -> list[str]:
        """Build docker run args (shell-free for command safety)."""
        cif_name = cif_path.name
        out_name = output_file.name

        base = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cif_path.parent}:/input:ro",
            "-v",
            f"{output_file.parent}:/output",
            self.docker_image,
            "network",
            "-ha",
        ]

        if calc == "res":
            return base + ["-res", f"/output/{out_name}", f"/input/{cif_name}"]
        if calc == "sa":
            return base + [
                "-sa",
                str(probe),
                str(probe),
                "2000",
                f"/output/{out_name}",
                f"/input/{cif_name}",
            ]
        if calc == "vol":
            return base + [
                "-vol",
                str(probe),
                str(probe),
                "50000",
                f"/output/{out_name}",
                f"/input/{cif_name}",
            ]
        if calc == "chan":
            return base + ["-chan", str(probe), f"/output/{out_name}", f"/input/{cif_name}"]
        raise ValueError(f"Unknown calculation type: {calc}")

    def _local_args(self, cif_path: Path, output_file: Path, calc: str, probe: float) -> list[str]:
        """Build local Zeo++ args."""
        base = [self.zeopp_binary, "-ha"]
        if calc == "res":
            return base + ["-res", str(output_file), str(cif_path)]
        if calc == "sa":
            return base + ["-sa", str(probe), str(probe), "2000", str(output_file), str(cif_path)]
        if calc == "vol":
            return base + ["-vol", str(probe), str(probe), "50000", str(output_file), str(cif_path)]
        if calc == "chan":
            return base + ["-chan", str(probe), str(output_file), str(cif_path)]
        raise ValueError(f"Unknown calculation type: {calc}")

    def _parse_output(self, calc: str, text: str) -> dict[str, Any]:
        """Parse Zeo++ output into structured fields."""
        result: dict[str, Any] = {"raw": text.strip()}

        if calc == "res":
            numbers = re.findall(r"[\d.]+", text)
            if len(numbers) >= 3:
                result["lcd"] = float(numbers[-3])
                result["pld"] = float(numbers[-2])
                result["lfsd"] = float(numbers[-1])
            return result

        if calc == "sa":
            asa_match = re.search(r"ASA_m\^2/g:\s*([\d.]+)", text)
            nasa_match = re.search(r"NASA_m\^2/g:\s*([\d.]+)", text)
            if asa_match:
                result["asa_m2g"] = float(asa_match.group(1))
            if nasa_match:
                result["nasa_m2g"] = float(nasa_match.group(1))
            if "asa_m2g" not in result:
                numbers = re.findall(r"[\d.]+", text)
                if len(numbers) >= 2:
                    result["asa_m2g"] = float(numbers[-2])
                    result["nasa_m2g"] = float(numbers[-1])
            return result

        if calc == "vol":
            av_match = re.search(r"AV_Volume_fraction:\s*([\d.]+)", text)
            avcm3_match = re.search(r"AV_cm\^3/g:\s*([\d.]+)", text)
            if av_match:
                result["av_fraction"] = float(av_match.group(1))
            if avcm3_match:
                result["av_cm3g"] = float(avcm3_match.group(1))
            return result

        if calc == "chan":
            dim_match = re.search(r"(\d+)_of_(\d+)", text)
            if dim_match:
                result["dimensionality"] = f"{dim_match.group(1)}D (of {dim_match.group(2)} channels)"
            return result

        return result

    def _update_index(self, cif_name: str, results: dict[str, Any]) -> None:
        """Update index.json with computed properties."""
        if not self.index_path.exists():
            return

        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return

        if cif_name not in index:
            return

        computed: dict[str, Any] = {"computed_at": datetime.now().isoformat()[:10]}

        res = results.get("res", {})
        if "lcd" in res:
            computed["lcd"] = res["lcd"]
            computed["pld"] = res.get("pld")

        sa = results.get("sa", {})
        if "asa_m2g" in sa:
            computed["sa_m2g"] = sa["asa_m2g"]

        vol = results.get("vol", {})
        if "av_fraction" in vol:
            computed["void_fraction"] = vol["av_fraction"]

        index[cif_name]["computed"] = computed
        self.index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
