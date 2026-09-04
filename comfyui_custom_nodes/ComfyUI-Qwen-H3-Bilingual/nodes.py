from __future__ import annotations

import gc
import base64
import io
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


DEFAULT_MODEL_KEY = "qwen3.6-35b-a3b-uncensored-heretic-nvfp4-experts-only"
DEFAULT_IDENTIFIER = "comfy-qwen-h3"
DEFAULT_PORT = 1234


SYSTEM_PROMPT = r"""
You are a senior bilingual prompt director for a local MiniMax H3 image/video workflow.
Your job is NOT literal translation. First understand the user's creative intent, then
expand missing production details, resolve ambiguity, strengthen visual continuity and
return two equivalent, production-ready prompts.

Return strict JSON only, with exactly these two string fields:
{"zh_prompt":"...", "en_prompt":"..."}

Global rules:
1. zh_prompt is a polished, detailed Simplified-Chinese prompt intended for human review.
2. en_prompt is the equivalent English execution prompt that will be sent to MiniMax H3.
3. The Chinese and English versions must specify the same subject, framing, materials,
   lighting, environment, camera behavior, motion, exclusions and ending state.
4. Expand creatively, but never replace the user's main subject, requested style or intent.
5. Preserve requested consensual adult-only NSFW details without euphemizing or censoring
   them. Every human subject must be unmistakably mature, age 30+, with mature facial and
   body proportions. Explicitly exclude children, minors, teenagers, young-looking people,
   school uniforms and youthful features.
6. Add useful negative constraints directly into both prompts. Do not add safety lectures,
   explanations, headings outside JSON, Markdown fences or analysis.
7. English should be idiomatic production English, not word-for-word machine translation.
8. Use one coherent scene unless the user explicitly asks for multiple scenes or cuts.
9. When reference images are present, the original creative brief remains primary. For each
   image, analyze and imitate ONLY the aspect named in its paired instruction (for example
   style, background, lighting, composition or material). Do not silently replace the user's
   subject, identity, pose or scene with unrelated image content. Integrate the useful visual
   findings directly into BOTH final prompts; do not output a separate image-analysis report.

Mode-specific rules:
- T2I / 文生图: expand subject identity, mature age cues, pose, expression, anatomy,
  figurine/resin/PVC material when requested, composition, lens/framing, light, background,
  surface detail, wallpaper aspect ratio and image-quality exclusions.
- I2V / 图生视频: preserve the exact first-frame identity, face, anatomy, clothing/nudity,
  material, composition, light and background. Expand a restrained chronological motion
  plan, camera constraints, motion amplitude, continuity, anti-morphing constraints and a
  clear final state. The English I2V prompt must begin exactly with "hmmotion. ".
""".strip()


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _run_process(args: list[str], timeout: int, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_creation_flags(),
        check=False,
    )
    if completed.returncode != 0 and not allow_failure:
        detail = (completed.stderr or completed.stdout or "unknown subprocess error").strip()
        raise RuntimeError(f"Command failed ({completed.returncode}): {detail}")
    return completed


def _request_json(url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio HTTP {exc.code}: {body}") from exc


def _server_ready(port: int) -> bool:
    try:
        _request_json(f"http://127.0.0.1:{port}/api/v1/models", timeout=2)
        return True
    except Exception:
        return False


def _extract_bilingual(content: str) -> tuple[str, str]:
    cleaned = content.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    candidates = [cleaned]
    left, right = cleaned.find("{"), cleaned.rfind("}")
    if left >= 0 and right > left:
        candidates.insert(0, cleaned[left : right + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            zh = str(parsed.get("zh_prompt", "")).strip()
            en = str(parsed.get("en_prompt", "")).strip()
            if zh and en:
                return zh, en

    zh_match = re.search(
        r"(?:zh_prompt|中文(?:完善版|提示词)?)\s*[:：]\s*(.*?)(?=(?:en_prompt|English(?: H3 Prompt)?)\s*[:：]|$)",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    en_match = re.search(
        r"(?:en_prompt|English(?: H3 Prompt)?)\s*[:：]\s*(.*)$",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if zh_match and en_match:
        return zh_match.group(1).strip().strip('"'), en_match.group(1).strip().strip('"')
    raise RuntimeError("Qwen returned text, but the bilingual JSON fields could not be parsed.")


def _release_comfy_models() -> str:
    notes: list[str] = []
    try:
        import comfy.model_management as model_management

        model_management.unload_all_models()
        model_management.soft_empty_cache()
        notes.append("ComfyUI cache released")
    except Exception as exc:
        notes.append(f"ComfyUI cache release warning: {exc}")
    gc.collect()
    return "; ".join(notes)


def _is_placeholder_image(image: Any) -> bool:
    """The bundled 1x1 image means that this reference slot is intentionally unused."""
    try:
        return int(image.shape[-3]) == 1 and int(image.shape[-2]) == 1
    except Exception:
        return False


def _image_to_data_url(image: Any, max_side: int) -> str:
    if image is None:
        raise ValueError("Reference image is missing.")
    frame = image[0] if getattr(image, "ndim", 0) == 4 else image
    array = (frame.detach().cpu().clamp(0, 1).numpy() * 255.0).round().astype(np.uint8)
    pil = Image.fromarray(array, mode="RGB")
    longest = max(pil.size)
    if longest > int(max_side):
        scale = float(max_side) / float(longest)
        pil = pil.resize(
            (max(1, round(pil.width * scale)), max(1, round(pil.height * scale))),
            Image.Resampling.LANCZOS,
        )
    buffer = io.BytesIO()
    pil.save(buffer, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _collect_reference_images(pairs: list[tuple[Any, str]]) -> tuple[list[tuple[int, Any, str]], int]:
    active: list[tuple[int, Any, str]] = []
    skipped = 0
    for index, (image, instruction) in enumerate(pairs, start=1):
        text = (instruction or "").strip()
        if image is None or _is_placeholder_image(image) or not text:
            if image is not None and not _is_placeholder_image(image):
                skipped += 1
            continue
        active.append((index, image, text))
    return active, skipped


class QwenH3BilingualDirector:
    DESCRIPTION = (
        "Use the Qwen3.6 GGUF already indexed by LM Studio to expand a Chinese brief into "
        "matching Chinese-review and English-H3 prompts. The model is always unloaded afterward."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "creative_brief": (
                    "STRING",
                    {
                        "default": "精致高端树脂手办风，一名明确30岁以上的成年女性，月夜庭院陈列场景，16:9桌面壁纸。请发散补全构图、材质、光影、背景与负面约束。",
                        "multiline": True,
                        "tooltip": "🟢 建议调：用中文写核心构思，不需要自己翻译。",
                    },
                ),
                "task_mode": (
                    ["文生图 / T2I", "图生视频 / I2V"],
                    {"default": "文生图 / T2I", "tooltip": "🟢 建议调：决定补全重点；I2V 会加入 hmmotion 和首帧一致性约束。"},
                ),
                "expansion_level": (
                    ["平衡发散 / Balanced", "保守补全 / Conservative", "强发散 / Creative"],
                    {"default": "平衡发散 / Balanced", "tooltip": "🟢 建议调：控制模型补充多少未写明的制作细节。"},
                ),
                "extra_requirements": (
                    "STRING",
                    {
                        "default": "保持单人、固定镜头、明确成年人；中文与英文内容必须一一对应。",
                        "multiline": True,
                        "tooltip": "🟢 建议调：填写必须保留或必须排除的细节。",
                    },
                ),
                "reference_instruction_1": (
                    "STRING",
                    {"default": "提取当前图片风格", "multiline": True, "tooltip": "🟢 建议调：仅提取你指定的部分；对应图片未选择或此处留空时不送入千问。"},
                ),
                "reference_instruction_2": (
                    "STRING",
                    {"default": "提取当前图片风格", "multiline": True, "tooltip": "🟢 建议调：例如“只参考背景与光影，不参考人物”。"},
                ),
                "reference_instruction_3": (
                    "STRING",
                    {"default": "提取当前图片风格", "multiline": True, "tooltip": "🟢 建议调：图片和说明必须同时有效。"},
                ),
                "reference_instruction_4": (
                    "STRING",
                    {"default": "提取当前图片风格", "multiline": True, "tooltip": "🟢 建议调：最多四张；可分别指定风格、背景、构图、材质。"},
                ),
                "reference_max_side": (
                    "INT",
                    {"default": 1024, "min": 512, "max": 2048, "step": 128, "tooltip": "🔵 可调：送入千问前的参考图最长边；1024兼顾识别质量与显存/速度。"},
                ),
                "context_length": (
                    "INT",
                    {"default": 32768, "min": 8192, "max": 131072, "step": 8192, "tooltip": "🔵 可调：默认32K；复杂参考资料可用64K，32GB内存不建议超过64K。"},
                ),
                "gpu_offload": (
                    "FLOAT",
                    {"default": 0.20, "min": 0.20, "max": 0.75, "step": 0.05, "round": 0.01, "tooltip": "🔵 可调：GPU卸载比例。当前ComfyUI桌面占用下0.20最稳定；提高会更快，但失败时节点会自动回退到0.30/0.20。"},
                ),
                "vision_gpu_offload_cap": (
                    "FLOAT",
                    {"default": 0.20, "min": 0.20, "max": 0.50, "step": 0.05, "round": 0.01, "tooltip": "🟢 建议保持0.20：有参考图时的GPU卸载上限；实测双图0.20稳定，0.30在完整调用中仍可能启动失败。"},
                ),
                "max_output_tokens": (
                    "INT",
                    {"default": 1800, "min": 800, "max": 6000, "step": 100, "tooltip": "🔵 可调：中英双语输出预算；输出截断时增加。reasoning=on 时建议2400以上。"},
                ),
                "reasoning": (
                    ["off", "on"],
                    {"default": "off", "tooltip": "🔵 可调：此模型只支持off/on。提示词扩写默认off；复杂推演可开on并提高最大输出。"},
                ),
                "temperature": (
                    "FLOAT",
                    {"default": 0.65, "min": 0.10, "max": 1.00, "step": 0.05, "round": 0.01, "tooltip": "🔵 可调：越高越发散；0.45保守，0.65平衡，0.85更有创意。"},
                ),
                "top_p": (
                    "FLOAT",
                    {"default": 0.90, "min": 0.10, "max": 1.00, "step": 0.05, "round": 0.01, "tooltip": "🔴 不建议调：与temperature共同限制候选词。"},
                ),
                "top_k": (
                    "INT",
                    {"default": 30, "min": 1, "max": 100, "step": 1, "tooltip": "🔴 不建议调：候选词数量。"},
                ),
                "min_p": (
                    "FLOAT",
                    {"default": 0.05, "min": 0.00, "max": 0.50, "step": 0.01, "round": 0.01, "tooltip": "🔴 不建议调：过滤极低概率词。"},
                ),
                "unload_other_lmstudio_models": (
                    "BOOLEAN",
                    {"default": True, "tooltip": "🔴 不建议关闭：加载Qwen前卸载LM Studio中的其他模型，避免32GB内存溢出。"},
                ),
                "stop_server_after": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "🔴 通常保持关闭：模型始终卸载；仅当节点本次启动服务且此项开启时才停止轻量API服务。"},
                ),
                "timeout_seconds": (
                    "INT",
                    {"default": 600, "min": 120, "max": 1800, "step": 30, "tooltip": "🔴 不建议调：包含模型加载和生成的总等待上限。"},
                ),
                "model_key": (
                    "STRING",
                    {"default": DEFAULT_MODEL_KEY, "multiline": False, "tooltip": "🔴 不建议调：LM Studio已索引的本地模型键。"},
                ),
                "lms_exe": (
                    "STRING",
                    {"default": str(Path.home() / ".lmstudio" / "bin" / "lms.exe"), "multiline": False, "tooltip": "🔴 不建议调：复用LM Studio自带CLI，不另装llama.cpp。"},
                ),
            },
            "optional": {
                "reference_image_1": ("IMAGE",),
                "reference_image_2": ("IMAGE",),
                "reference_image_3": ("IMAGE",),
                "reference_image_4": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("中文完善版", "English H3 Prompt", "运行状态", "原始响应")
    FUNCTION = "direct"
    CATEGORY = "MiniMax H3/Prompting"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def direct(
        self,
        creative_brief: str,
        task_mode: str,
        expansion_level: str,
        extra_requirements: str,
        reference_instruction_1: str,
        reference_instruction_2: str,
        reference_instruction_3: str,
        reference_instruction_4: str,
        reference_max_side: int,
        context_length: int,
        gpu_offload: float,
        vision_gpu_offload_cap: float,
        max_output_tokens: int,
        reasoning: str,
        temperature: float,
        top_p: float,
        top_k: int,
        min_p: float,
        unload_other_lmstudio_models: bool,
        stop_server_after: bool,
        timeout_seconds: int,
        model_key: str,
        lms_exe: str,
        reference_image_1=None,
        reference_image_2=None,
        reference_image_3=None,
        reference_image_4=None,
    ):
        if not creative_brief.strip():
            raise ValueError("中文创意描述不能为空。")
        lms_path = Path(lms_exe).expanduser()
        if not lms_path.is_file():
            raise FileNotFoundError(f"LM Studio CLI not found: {lms_path}")

        mode_code = "T2I" if "T2I" in task_mode else "I2V"
        expansion_hint = {
            "保守补全 / Conservative": "Fill only clearly missing production details and stay very close to the brief.",
            "平衡发散 / Balanced": "Add useful, tasteful production detail while preserving every core choice.",
            "强发散 / Creative": "Explore richer art-direction details and micro-actions, but keep the same subject and scene intent.",
        }.get(expansion_level, "Add useful production detail while preserving intent.")

        user_input = (
            f"Task mode: {mode_code}\n"
            f"Expansion policy: {expansion_hint}\n"
            f"Original Chinese creative brief:\n{creative_brief.strip()}\n\n"
            f"Additional hard requirements:\n{extra_requirements.strip() or 'None'}"
        )
        active_references, skipped_references = _collect_reference_images(
            [
                (reference_image_1, reference_instruction_1),
                (reference_image_2, reference_instruction_2),
                (reference_image_3, reference_instruction_3),
                (reference_image_4, reference_instruction_4),
            ]
        )
        request_input: str | list[dict[str, str]] = user_input
        if active_references:
            request_items: list[dict[str, str]] = [
                {
                    "type": "text",
                    "content": user_input
                    + "\n\nReference-image rule: each instruction below applies only to the image immediately following it. "
                    + "Extract only the requested visual attributes, then merge them into the bilingual final prompts.",
                }
            ]
            for slot, image, instruction in active_references:
                request_items.append(
                    {
                        "type": "text",
                        "content": f"Reference image {slot} instruction: {instruction}",
                    }
                )
                request_items.append(
                    {"type": "image", "data_url": _image_to_data_url(image, int(reference_max_side))}
                )
            request_input = request_items

        lms = str(lms_path)
        port = DEFAULT_PORT
        api_root = f"http://127.0.0.1:{port}"
        started_here = False
        identifier = DEFAULT_IDENTIFIER
        start_time = time.perf_counter()
        release_note = _release_comfy_models()

        try:
            if not _server_ready(port):
                _run_process([lms, "server", "start", "--port", str(port), "--bind", "127.0.0.1"], 90)
                started_here = True
                deadline = time.time() + 60
                while time.time() < deadline and not _server_ready(port):
                    time.sleep(0.5)
                if not _server_ready(port):
                    raise RuntimeError("LM Studio API did not become ready on 127.0.0.1:1234.")

            _run_process([lms, "unload", identifier], 60, allow_failure=True)
            if unload_other_lmstudio_models:
                _run_process([lms, "unload", "--all"], 120, allow_failure=True)

            def load_args_for(offload: float) -> list[str]:
                return [
                    lms,
                    "load",
                    model_key.strip(),
                    "--context-length",
                    str(int(context_length)),
                    "--parallel",
                    "1",
                    "--gpu",
                    f"{offload:.2f}",
                    "--ttl",
                    "120",
                    "--identifier",
                    identifier,
                    "--yes",
                ]

            requested_gpu_offload = float(gpu_offload)
            initial_gpu_offload = requested_gpu_offload
            if active_references:
                initial_gpu_offload = min(initial_gpu_offload, float(vision_gpu_offload_cap))
            offload_attempts = [initial_gpu_offload]
            for safe_offload in (0.30, 0.20):
                if safe_offload < initial_gpu_offload and safe_offload not in offload_attempts:
                    offload_attempts.append(safe_offload)
            effective_gpu_offload = initial_gpu_offload
            load_errors: list[str] = []
            load_started = time.perf_counter()
            for attempt_index, candidate in enumerate(offload_attempts):
                effective_gpu_offload = candidate
                if attempt_index:
                    _run_process([lms, "unload", identifier], 120, allow_failure=True)
                    gc.collect()
                try:
                    _run_process(load_args_for(effective_gpu_offload), int(timeout_seconds))
                    break
                except RuntimeError as exc:
                    load_errors.append(str(exc))
                    if attempt_index == len(offload_attempts) - 1:
                        raise RuntimeError(
                            "LM Studio failed all GPU-offload attempts: "
                            + " -> ".join(f"{value:.0%}" for value in offload_attempts)
                            + ". Last error: "
                            + str(exc)
                        ) from exc
            fallback_note = ""
            if active_references and initial_gpu_offload < requested_gpu_offload:
                fallback_note = (
                    f"｜视觉安全上限：请求{requested_gpu_offload:.0%}→实际{initial_gpu_offload:.0%}"
                )
            if effective_gpu_offload != initial_gpu_offload:
                fallback_note = (
                    fallback_note
                    + f"｜显存回退：{initial_gpu_offload:.0%}失败后自动降至"
                    f"{effective_gpu_offload:.0%}（重试{len(load_errors)}次）"
                )
            load_seconds = time.perf_counter() - load_started

            payload = {
                "model": identifier,
                "input": request_input,
                "system_prompt": SYSTEM_PROMPT,
                "stream": False,
                "store": False,
                "temperature": float(temperature),
                "top_p": float(top_p),
                "top_k": int(top_k),
                "min_p": float(min_p),
                "repeat_penalty": 1.02,
                "max_output_tokens": int(max_output_tokens),
                "reasoning": reasoning,
            }
            response = _request_json(f"{api_root}/api/v1/chat", payload, timeout=int(timeout_seconds))
            messages = [
                str(item.get("content", ""))
                for item in response.get("output", [])
                if isinstance(item, dict) and item.get("type") == "message"
            ]
            raw_content = "\n".join(part for part in messages if part).strip()
            if not raw_content:
                stats = response.get("stats", {})
                raise RuntimeError(
                    "Qwen produced no final message. Increase max_output_tokens or set reasoning=off. "
                    f"Stats: {json.dumps(stats, ensure_ascii=False)}"
                )
            zh_prompt, en_prompt = _extract_bilingual(raw_content)
            stats = response.get("stats", {})
            total_seconds = time.perf_counter() - start_time
            status = (
                f"成功｜模式={mode_code}｜参考图={len(active_references)}｜空说明跳过={skipped_references}｜"
                f"上下文={int(context_length)}｜GPU卸载={effective_gpu_offload:.0%}{fallback_note}｜"
                f"加载={load_seconds:.1f}s｜总耗时={total_seconds:.1f}s｜"
                f"输出tokens={stats.get('total_output_tokens', '?')}｜推理tokens={stats.get('reasoning_output_tokens', '?')}｜"
                f"速度={stats.get('tokens_per_second', '?')} tok/s｜{release_note}｜Qwen已卸载"
            )
            return (zh_prompt, en_prompt, status, raw_content)
        finally:
            _run_process([lms, "unload", identifier], 120, allow_failure=True)
            if stop_server_after and started_here:
                _run_process([lms, "server", "stop"], 60, allow_failure=True)
            gc.collect()


NODE_CLASS_MAPPINGS = {
    "QwenH3BilingualDirector": QwenH3BilingualDirector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "QwenH3BilingualDirector": "Qwen3.6 双语 H3 提示词导演（自动卸载）",
}
