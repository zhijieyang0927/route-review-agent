from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .models import ScreenshotEvidence


NODE_HINTS = {
    "accept": "接单",
    "arrived": "到店",
    "store": "到店/商家",
    "pickup": "取餐",
    "delivered": "送达",
    "dropoff": "送达/落点",
}


def _infer_hints(path: Path) -> tuple[str, str]:
    name = path.stem.lower()
    node = ""
    for token, label in NODE_HINTS.items():
        if token in name:
            node = label
            break
    match = re.search(r"(?:order[_-]?)?(\d{3,})", name)
    order = match.group(1) if match else ""
    return node, order


def read_screenshots(paths: list[Path]) -> list[ScreenshotEvidence]:
    tesseract = shutil.which("tesseract")
    evidences: list[ScreenshotEvidence] = []
    for path in paths:
        node_hint, order_hint = _infer_hints(path)
        if not tesseract:
            evidences.append(
                ScreenshotEvidence(
                    path=str(path),
                    node_hint=node_hint,
                    order_hint=order_hint,
                    needs_confirmation=True,
                    error="未检测到 tesseract，截图已登记但未自动OCR。",
                )
            )
            continue
        try:
            completed = subprocess.run(
                [tesseract, str(path), "stdout", "-l", "eng+chi_sim"],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
            text = completed.stdout.strip()
            evidences.append(
                ScreenshotEvidence(
                    path=str(path),
                    node_hint=node_hint,
                    order_hint=order_hint,
                    text=text,
                    needs_confirmation=not bool(text),
                    error=completed.stderr.strip() if completed.returncode else "",
                )
            )
        except Exception as exc:
            evidences.append(
                ScreenshotEvidence(
                    path=str(path),
                    node_hint=node_hint,
                    order_hint=order_hint,
                    needs_confirmation=True,
                    error=f"OCR失败：{exc}",
                )
            )
    return evidences

