"""
Hardware detection — estimate what model sizes a user's machine can handle.
Checks RAM, GPU (if available), and CPU cores.
"""

import os
import platform
import logging

logger = logging.getLogger(__name__)


def detect_hardware() -> dict:
    """Detect system hardware and return specs."""
    info = {
        "os": platform.system(),
        "arch": platform.machine(),
        "cpu_cores": os.cpu_count() or 1,
        "ram_gb": _get_ram_gb(),
        "gpu": _get_gpu_info(),
        "gpu_vram_gb": _get_gpu_vram_gb(),
    }
    return info


def _get_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024**3), 1)
    except ImportError:
        pass

    # Fallback for Windows
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "computersystem", "get", "totalphysicalmemory"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line.isdigit():
                    return round(int(line) / (1024**3), 1)
        except Exception:
            pass

    # Fallback for macOS/Linux
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    kb = int(line.split()[1])
                    return round(kb / (1024**2), 1)
    except Exception:
        pass

    return 0.0


def _get_gpu_info() -> str:
    """Detect GPU name."""
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name"],
                capture_output=True, text=True, timeout=5
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and l.strip() != "Name"]
            if lines:
                return lines[0]
        except Exception:
            pass
    return "unknown"


def _get_gpu_vram_gb() -> float:
    """Estimate GPU VRAM in GB."""
    gpu = _get_gpu_info().lower()

    # NVIDIA detection via nvidia-smi
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            vram_mb = int(result.stdout.strip().split("\n")[0].strip())
            return round(vram_mb / 1024, 1)
    except Exception:
        pass

    # Heuristic based on GPU name
    gpu_vram_map = {
        "rtx 4090": 24.0, "rtx 4080": 16.0, "rtx 4070": 12.0,
        "rtx 4060": 8.0, "rtx 3090": 24.0, "rtx 3080": 10.0,
        "rtx 3070": 8.0, "rtx 3060": 12.0, "rtx 2080": 8.0,
        "rtx 2060": 6.0, "gtx 1660": 6.0, "gtx 1080": 8.0,
        "rx 7900": 20.0, "rx 7800": 16.0, "rx 7600": 8.0,
        "rx 6800": 16.0, "rx 6700": 12.0,
    }
    for name, vram in gpu_vram_map.items():
        if name in gpu:
            return vram

    return 0.0


def suggest_models(hw: dict) -> list[dict]:
    """Suggest models based on hardware capabilities."""
    ram = hw.get("ram_gb", 0)
    vram = hw.get("gpu_vram_gb", 0)
    has_gpu = vram > 0

    suggestions = []

    # Rule of thumb: model needs ~0.7-1x VRAM for quantized, ~2x for full precision
    # For CPU: needs ~1.5x model size in RAM

    if has_gpu and vram >= 24:
        suggestions.append({"size": "70B", "quant": "Q4", "vram_needed": 40, "fits": vram >= 40, "quality": "excellent"})
        suggestions.append({"size": "34B", "quant": "Q6", "vram_needed": 26, "fits": vram >= 26, "quality": "excellent"})
        suggestions.append({"size": "13B", "quant": "Q8", "vram_needed": 14, "fits": True, "quality": "great"})
        suggestions.append({"size": "8B", "quant": "full", "vram_needed": 16, "fits": True, "quality": "great"})
    elif has_gpu and vram >= 16:
        suggestions.append({"size": "34B", "quant": "Q3", "vram_needed": 16, "fits": True, "quality": "good"})
        suggestions.append({"size": "13B", "quant": "Q6", "vram_needed": 10, "fits": True, "quality": "great"})
        suggestions.append({"size": "8B", "quant": "Q8", "vram_needed": 9, "fits": True, "quality": "great"})
        suggestions.append({"size": "3B", "quant": "full", "vram_needed": 6, "fits": True, "quality": "good"})
    elif has_gpu and vram >= 8:
        suggestions.append({"size": "13B", "quant": "Q3", "vram_needed": 7, "fits": True, "quality": "ok"})
        suggestions.append({"size": "8B", "quant": "Q5", "vram_needed": 6, "fits": True, "quality": "great"})
        suggestions.append({"size": "3B", "quant": "full", "vram_needed": 6, "fits": True, "quality": "great"})
    elif has_gpu and vram >= 4:
        suggestions.append({"size": "3B", "quant": "Q5", "vram_needed": 3, "fits": True, "quality": "good"})
        suggestions.append({"size": "1.5B", "quant": "full", "vram_needed": 3, "fits": True, "quality": "ok"})
    else:
        # CPU only
        if ram >= 32:
            suggestions.append({"size": "13B", "quant": "Q3", "ram_needed": 10, "fits": True, "quality": "ok"})
            suggestions.append({"size": "8B", "quant": "Q4", "ram_needed": 6, "fits": True, "quality": "good"})
            suggestions.append({"size": "3B", "quant": "full", "ram_needed": 6, "fits": True, "quality": "great"})
        elif ram >= 16:
            suggestions.append({"size": "8B", "quant": "Q3", "ram_needed": 5, "fits": True, "quality": "ok"})
            suggestions.append({"size": "3B", "quant": "Q5", "ram_needed": 3, "fits": True, "quality": "good"})
            suggestions.append({"size": "1.5B", "quant": "full", "ram_needed": 3, "fits": True, "quality": "good"})
        elif ram >= 8:
            suggestions.append({"size": "3B", "quant": "Q3", "ram_needed": 2, "fits": True, "quality": "ok"})
            suggestions.append({"size": "1.5B", "quant": "Q5", "ram_needed": 2, "fits": True, "quality": "good"})
            suggestions.append({"size": "0.5B", "quant": "full", "ram_needed": 1, "fits": True, "quality": "ok"})
        else:
            suggestions.append({"size": "1.5B", "quant": "Q2", "ram_needed": 1, "fits": True, "quality": "low"})
            suggestions.append({"size": "0.5B", "quant": "full", "ram_needed": 1, "fits": True, "quality": "ok"})

    return suggestions


def _get_live_usage() -> dict:
    """Live CPU/memory usage via psutil (empty dict if unavailable)."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "mem_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 1),
        }
    except Exception:
        return {}


def get_system_report() -> dict:
    """Full system report with hardware info and model suggestions."""
    hw = detect_hardware()
    suggestions = suggest_models(hw)
    return {
        "hardware": hw,
        "usage": _get_live_usage(),
        "suggested_models": suggestions,
        "recommendation": _get_recommendation(hw),
    }


def _get_recommendation(hw: dict) -> str:
    ram = hw.get("ram_gb", 0)
    vram = hw.get("gpu_vram_gb", 0)

    if vram >= 24:
        return "Your GPU can run large models (70B quantized). Best local experience."
    elif vram >= 16:
        return "Your GPU can run medium models (13-34B quantized). Great local experience."
    elif vram >= 8:
        return "Your GPU can run small-medium models (8-13B quantized). Good local experience."
    elif vram >= 4:
        return "Your GPU can run small models (3B). Consider cloud providers for larger models."
    elif ram >= 32:
        return "No dedicated GPU detected, but you have plenty of RAM for CPU inference (up to 13B)."
    elif ram >= 16:
        return "No dedicated GPU detected. You can run small models (3-8B) on CPU. Cloud providers recommended for quality."
    else:
        return "Limited hardware. Use cloud providers (OpenAI, Anthropic, Groq) for best results. Small local models (1.5B) possible."
