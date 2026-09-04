#!/usr/bin/env python3
"""Build three native ComfyUI UI workflows for the MiniMax H3 wallpaper pipeline."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "workflows" / "ui"

MODEL = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
NSFW_LORA = "HMNSFW-AIO-V2.5.safetensors"
UPSCALE_MODEL = "RealESRGAN_x4plus.pth"

IMAGE_PROMPT = (
    "A high-end full-body 3D anime game character render blending Arknights: Endfield-like real-time "
    "PBR rendering with polished cinematic MMD rendering. Keep the clean silhouette, immaculate model "
    "work and precise detailing associated with a premium collectible figure, but depict a living "
    "character in a believable game world, not a literal statue or product photograph. One clearly "
    "adult fantasy woman age 25+ with elegant adult proportions and an original identity. Her face "
    "matches the refined Chinese anime game aesthetic of the references: a soft heart-shaped V-line "
    "face, gently rounded cheeks, a short delicate chin, very large slightly upturned almond eyes, "
    "crisp dark upper lash lines, glossy pink-violet gradient irises with layered catchlights, a tiny "
    "anime nose, tiny closed lips and a subtle friendly smile. Avoid a long realistic face, deep eye "
    "sockets, pronounced cheekbones, heavy nasolabial folds or a Western fashion-model face. Layered "
    "silver-blue hair with fine strand breakup, soft anisotropic sheen, translucent flyaway tips and "
    "natural variation rather than solid molded plastic grooves. Tasteful adult erotic styling: bare "
    "breasts visible, sheer black pantyhose with a clearly visible waistband at the hips; the tights "
    "cover only the waist, hips and legs below the waist, never the abdomen, torso or breasts. Use "
    "physically correct nylon translucency, fine weave, subtle wet specular highlights and a few "
    "realistic water droplets only on the tights below the waist, plus glossy black heeled shoes. "
    "Graceful neutral standing pose, no sexual activity. Natural matte skin with fine roughness, warm "
    "subsurface scattering, soft tonal variation and restrained highlights; skin must look alive and "
    "soft, never resin, wax, porcelain or glossy plastic. Use restrained game-skin roughness near "
    "0.5, subtle micro-normal variation and smooth highlight roll-off with no hard white specular "
    "spots on the face or torso. All exposed skin above the waistband is clean, dry and matte. "
    "Clearly differentiated materials: matte "
    "skin, damp translucent nylon, silky hair, lacquered shoes, brushed metal ornaments and realistic "
    "fabric or accessory surfaces. Full-body head-to-toe composition with the complete hairstyle, "
    "both hands, both legs and both heels fully inside the frame. Upright relaxed standing pose, "
    "vertical body axis, level horizon and exactly zero-degree camera roll; leave a small safe margin "
    "above the hair and below the heels while the adult character fills about 90 percent of the 16:9 "
    "frame height. Current-generation game-engine lighting with large-area diffused daylight from "
    "front-left, broad neutral skylight fill, soft wet-ground bounce under the face and legs, warm "
    "late-afternoon edge light on the hair and shoulders, and gentle cool environmental fill. "
    "Cinematic HDR exposure, bright readable "
    "eyes, smooth highlight roll-off, open detailed shadows, controlled nylon reflections and a clean "
    "three-dimensional face; the face is about one stop brighter than the background. Lighting is "
    "fully integrated into the game environment, with no photographic equipment visible and no "
    "blank white backdrop. A grounded outdoor industrial science-fantasy environment with wet stone "
    "and concrete, dark structural forms, natural rocks, lush green plants and subtle reflected sky, "
    "combining the environmental PBR feeling of a current-generation anime game with the clean "
    "character illumination of a high-quality MMD scene. No backlit silhouette, no harsh eye "
    "sockets, muddy amber cast or crushed blacks. Eye-level camera, 50mm lens, "
    "no wide-angle distortion, moderate depth of "
    "field around f/5.6, the entire character sharp from face to heels while only the distant "
    "background falls softly out of focus, ACES Filmic color, ultra-clean 16:9 desktop wallpaper. "
    "Adult only, age 25+, no child, no minor, no teenager, no school uniform, no childlike body "
    "proportions. No literal figurine, no display base, no toy photography, no resin skin, no PVC "
    "skin, no wax skin, no porcelain skin, no doll joints, no clay render, no low-poly mesh, no flat "
    "2D illustration, no real-person photorealism, no multiple people, no duplicate body, no extra "
    "limbs, no extra fingers, no malformed hands, no cropped head, no cropped feet, no tiny distant "
    "subject, no Dutch angle, no tilted horizon, no camera roll, no extreme perspective, no blurry "
    "face, no smeared eyes, no excessive bloom, no lighting flicker, no motion "
    "blur, no text, no logo, no watermark."
)

MOTION_PROMPT = (ROOT / "prompts" / "h3_live2d_loop_default_en.txt").read_text(encoding="utf-8").strip()


class Graph:
    def __init__(self, title: str, scale: float = 0.72, offset: tuple[float, float] = (180.0, 120.0)):
        self.title = title
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self.groups: list[dict] = []
        self.next_node_id = 1
        self.next_link_id = 1
        self.scale = scale
        self.offset = offset

    def add_node(
        self,
        node_type: str,
        pos: tuple[float, float],
        size: tuple[float, float],
        *,
        title: str | None = None,
        inputs: list[tuple[str, str, bool]] | None = None,
        outputs: list[tuple[str, str]] | None = None,
        widgets: list | None = None,
        color: str | None = None,
        bgcolor: str | None = None,
    ) -> int:
        node_id = self.next_node_id
        self.next_node_id += 1
        in_items = []
        for name, input_type, optional in inputs or []:
            item = {"name": name, "type": input_type, "link": None}
            if optional:
                item["shape"] = 7
            in_items.append(item)
        out_items = [
            {"name": name, "type": output_type, "links": None}
            for name, output_type in outputs or []
        ]
        node = {
            "id": node_id,
            "type": node_type,
            "pos": list(pos),
            "size": list(size),
            "flags": {},
            "order": len(self.nodes),
            "mode": 0,
            "inputs": in_items,
            "outputs": out_items,
            "properties": {"Node name for S&R": node_type},
            "widgets_values": widgets or [],
        }
        if title:
            node["title"] = title
        if color:
            node["color"] = color
        if bgcolor:
            node["bgcolor"] = bgcolor
        self.nodes.append(node)
        return node_id

    def note(self, pos: tuple[float, float], size: tuple[float, float], title: str, text: str, color: str) -> int:
        node_id = self.add_node("MarkdownNote", pos, size, title=title, widgets=[text], color=color, bgcolor="#111111")
        self.node(node_id)["properties"] = {}
        return node_id

    def node(self, node_id: int) -> dict:
        return next(node for node in self.nodes if node["id"] == node_id)

    def connect(self, origin_id: int, origin_slot: int, target_id: int, target_slot: int, link_type: str) -> int:
        link_id = self.next_link_id
        self.next_link_id += 1
        self.links.append([link_id, origin_id, origin_slot, target_id, target_slot, link_type])
        origin = self.node(origin_id)["outputs"][origin_slot]
        if origin["links"] is None:
            origin["links"] = []
        origin["links"].append(link_id)
        self.node(target_id)["inputs"][target_slot]["link"] = link_id
        return link_id

    def group(self, title: str, bounding: tuple[float, float, float, float], color: str) -> None:
        self.groups.append({"id": len(self.groups) + 1, "title": title, "bounding": list(bounding), "color": color, "flags": {}})

    def workflow(self) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "revision": 0,
            "last_node_id": self.next_node_id - 1,
            "last_link_id": self.next_link_id - 1,
            "nodes": self.nodes,
            "links": self.links,
            "groups": self.groups,
            "config": {},
            "extra": {"ds": {"scale": self.scale, "offset": list(self.offset)}},
            "version": 0.4,
        }


def loader_inputs() -> dict[str, list[tuple[str, str, bool]]]:
    return {
        "unet": [("unet_name", "COMBO", False), ("weight_dtype", "COMBO", False)],
        "lora": [("model", "MODEL", False), ("lora_name", "COMBO", False), ("strength_model", "FLOAT", False)],
        "clip": [("clip_name", "COMBO", False), ("type", "COMBO", False), ("device", "COMBO", True)],
        "vae": [("vae_name", "COMBO", False)],
    }


def add_sampling(g: Graph, x: float, y: float, latent_source: int, model_source: int, vae_source: int, seed: int):
    noise = g.add_node(
        "RandomNoise", (x, y), (330, 90), title="🟢 Seed：每次抽卡改这里",
        inputs=[("noise_seed", "INT", False)], outputs=[("NOISE", "NOISE")], widgets=[seed, "randomize"],
        color="#1f5d3a", bgcolor="#163a29",
    )
    guider = g.add_node(
        "BasicGuider", (x + 380, y + 130), (300, 70),
        inputs=[("model", "MODEL", False), ("conditioning", "CONDITIONING", False)], outputs=[("GUIDER", "GUIDER")],
    )
    scheduler = g.add_node(
        "BasicScheduler", (x, y + 260), (330, 130), title="🔵 可调：步数默认 20",
        inputs=[("model", "MODEL", False), ("scheduler", "COMBO", False), ("steps", "INT", False), ("denoise", "FLOAT", False)],
        outputs=[("SIGMAS", "SIGMAS")], widgets=["simple", 20, 1.0], color="#244a66", bgcolor="#183347",
    )
    sampler_select = g.add_node(
        "KSamplerSelect", (x, y + 430), (330, 75), title="🔴 不建议调：采样器",
        inputs=[("sampler_name", "COMBO", False)], outputs=[("SAMPLER", "SAMPLER")], widgets=["res_multistep"],
        color="#663333", bgcolor="#452525",
    )
    sampler = g.add_node(
        "SamplerCustomAdvanced", (x + 760, y + 150), (270, 170),
        inputs=[("noise", "NOISE", False), ("guider", "GUIDER", False), ("sampler", "SAMPLER", False),
                ("sigmas", "SIGMAS", False), ("latent_image", "LATENT", False)],
        outputs=[("output", "LATENT"), ("denoised_output", "LATENT")],
    )
    g.connect(noise, 0, sampler, 0, "NOISE")
    g.connect(guider, 0, sampler, 1, "GUIDER")
    g.connect(sampler_select, 0, sampler, 2, "SAMPLER")
    g.connect(scheduler, 0, sampler, 3, "SIGMAS")
    g.connect(latent_source, 1, sampler, 4, "LATENT")
    g.connect(model_source, 0, guider, 0, "MODEL")
    g.connect(latent_source, 0, guider, 1, "CONDITIONING")
    g.connect(model_source, 0, scheduler, 0, "MODEL")
    decode = g.add_node(
        "VAEDecode", (x + 1100, y + 170), (250, 80),
        inputs=[("samples", "LATENT", False), ("vae", "VAE", False)], outputs=[("IMAGE", "IMAGE")],
    )
    g.connect(sampler, 0, decode, 0, "LATENT")
    g.connect(vae_source, 0, decode, 1, "VAE")
    return {"noise": noise, "scheduler": scheduler, "sampler_select": sampler_select, "sampler": sampler, "decode": decode}


def build_t2i() -> dict:
    g = Graph("01 H3 HMNSFW 文生图抽卡", scale=0.62, offset=(130, 130))
    g.note((20, 10), (920, 390), "使用说明", """# 01｜H3 + HMNSFW 文生图抽卡

每次 Queue 生成同一 image seed 的最短 5 帧包，并自动保存你选择的其中一帧。真正的“抽卡”是改变 Seed 后再次 Queue。

- **🟢 建议调：** 完整提示词、Seed、HMNSFW 强度、抽帧序号。
- **🔵 可调：** 步数；质量稳定后一般保持 20。
- **🔴 不建议调：** 模型、VAE、1024×576、length=5、采样器。它们是本机验证组合。

默认提示词已改为 **终末地式实时二游 PBR + 高质量 MMD 电影渲染 + 少量手办般精致轮廓**。人物是活体二游角色，不是实体塑料手办：自然哑光皮肤、柔和次表面散射、湿润透明丝袜、丝质头发和金属饰件彼此材质分明。脸模继续参考精致二游的大眼、小鼻、V形脸。

默认采用完整头到脚全身像、水平地平线和 0° 相机滚转，人物约占 16:9 画面高度的 90%，头发与鞋底均留安全边距。打光采用前左大面积漫射日光、天空补光、湿地面反弹光、暖色边缘光和冷色环境光；背景是岩石、绿植、湿地面与工业结构组成的实机场景，不出现摄影灯具。整个人物从脸到鞋保持清晰，只有远景虚化。

HMNSFW 默认 0.30；建议 0.20–0.50。过高可能让脸和身体过度风格化。选中原始帧会同时保留，并经 RealESRGAN x4plus 修复后无裁剪缩放为 **2560×1440**。只生成明确成年人内容。""", "#315c45")
    prompt = g.add_node(
        "PrimitiveStringMultiline", (20, 450), (920, 420), title="🟢 建议调 ①｜完整文生图提示词",
        inputs=[("value", "STRING", False)], outputs=[("STRING", "STRING")], widgets=[IMAGE_PROMPT],
        color="#1f5d3a", bgcolor="#163a29",
    )
    strength = g.add_node(
        "PrimitiveFloat", (20, 920), (280, 90), title="🟢 建议调 ②｜HMNSFW：0.20–0.50",
        inputs=[("value", "FLOAT", False)], outputs=[("FLOAT", "FLOAT")], widgets=[0.3], color="#1f5d3a", bgcolor="#163a29",
    )
    frame_index = g.add_node(
        "PrimitiveInt", (330, 920), (280, 90), title="🟢 建议调 ③｜抽取帧 0–4",
        inputs=[("value", "INT", False)], outputs=[("INT", "INT")], widgets=[0, "fixed"], color="#1f5d3a", bgcolor="#163a29",
    )
    li = loader_inputs()
    unet = g.add_node("UNETLoader", (1030, 40), (610, 100), title="🔴 基础 H3（不要换）", inputs=li["unet"], outputs=[("MODEL", "MODEL")], widgets=[MODEL, "default"], color="#663333", bgcolor="#452525")
    lora = g.add_node("LoraLoaderModelOnly", (1030, 180), (610, 110), title="HMNSFW V2.5（必需）", inputs=li["lora"], outputs=[("MODEL", "MODEL")], widgets=[NSFW_LORA, 0.3], color="#1f5d3a", bgcolor="#163a29")
    clip = g.add_node("CLIPLoader", (1030, 330), (610, 120), title="🔴 H3 文本编码器（不要换）", inputs=li["clip"], outputs=[("CLIP", "CLIP")], widgets=[CLIP, "minimax", "default"], color="#663333", bgcolor="#452525")
    vae = g.add_node("VAELoader", (1030, 490), (610, 90), title="🔴 H3 Video VAE（不要换）", inputs=li["vae"], outputs=[("VAE", "VAE")], widgets=[VIDEO_VAE], color="#663333", bgcolor="#452525")
    h3 = g.add_node(
        "MiniMaxH3ImageToVideo", (1740, 120), (540, 520), title="H3 伪文生图｜固定 1024×576×5",
        inputs=[("clip", "CLIP", False), ("vae", "VAE", False), ("first_frame", "IMAGE", True), ("last_frame", "IMAGE", True),
                ("prompt", "STRING", False), ("width", "INT", False), ("height", "INT", False), ("length", "INT", False)],
        outputs=[("positive", "CONDITIONING"), ("LATENT", "LATENT")], widgets=[IMAGE_PROMPT, 1024, 576, 5],
        color="#663333", bgcolor="#452525",
    )
    g.connect(unet, 0, lora, 0, "MODEL")
    g.connect(strength, 0, lora, 2, "FLOAT")
    g.connect(clip, 0, h3, 0, "CLIP")
    g.connect(vae, 0, h3, 1, "VAE")
    g.connect(prompt, 0, h3, 4, "STRING")
    sampling = add_sampling(g, 2390, 70, h3, lora, vae, 2026083013)
    preview = g.add_node("PreviewImage", (3850, 40), (520, 360), title="5 帧预览：同一个 seed 的短时序包", inputs=[("images", "IMAGE", False)], outputs=[("IMAGE", "IMAGE")])
    select = g.add_node(
        "ImageFromBatch", (3850, 450), (330, 110), title="按序号抽取 1 帧",
        inputs=[("image", "IMAGE", False), ("batch_index", "INT", False), ("length", "INT", False)], outputs=[("IMAGE", "IMAGE")], widgets=[0, 1],
    )
    save = g.add_node(
        "SaveImage", (4270, 450), (500, 320), title="保留原始 1024×576 PNG",
        inputs=[("images", "IMAGE", False), ("filename_prefix", "STRING", False)], outputs=[("IMAGE", "IMAGE")],
        widgets=["H3_T2I_Selected"],
    )
    upscale_model = g.add_node(
        "UpscaleModelLoader", (4270, 40), (500, 90), title="🔴 2K 超分模型｜RealESRGAN x4plus",
        inputs=[("model_name", "COMBO", False)], outputs=[("UPSCALE_MODEL", "UPSCALE_MODEL")],
        widgets=[UPSCALE_MODEL], color="#663333", bgcolor="#452525",
    )
    upscale = g.add_node(
        "ImageUpscaleWithModel", (4840, 40), (500, 140), title="AI 修复细节｜单张图显存安全",
        inputs=[("upscale_model", "UPSCALE_MODEL", False), ("image", "IMAGE", False)], outputs=[("IMAGE", "IMAGE")],
        color="#244a66", bgcolor="#183347",
    )
    scale_2k = g.add_node(
        "ImageScale", (5410, 40), (500, 170), title="🔴 2K 2560×1440｜Lanczos｜不裁剪",
        inputs=[("image", "IMAGE", False), ("upscale_method", "COMBO", False), ("width", "INT", False),
                ("height", "INT", False), ("crop", "COMBO", False)],
        outputs=[("IMAGE", "IMAGE")], widgets=["lanczos", 2560, 1440, "disabled"], color="#663333", bgcolor="#452525",
    )
    preview_2k = g.add_node(
        "PreviewImage", (5980, 40), (540, 360), title="2K 选中帧预览｜确认脸模和锐度",
        inputs=[("images", "IMAGE", False)], outputs=[("IMAGE", "IMAGE")],
    )
    save_2k = g.add_node(
        "SaveImage", (5980, 450), (540, 320), title="保存 2K PNG｜推荐供第 2 步使用",
        inputs=[("images", "IMAGE", False), ("filename_prefix", "STRING", False)], outputs=[("IMAGE", "IMAGE")],
        widgets=["H3_T2I_Selected_2K"],
    )
    g.connect(sampling["decode"], 0, preview, 0, "IMAGE")
    g.connect(sampling["decode"], 0, select, 0, "IMAGE")
    g.connect(frame_index, 0, select, 1, "INT")
    g.connect(select, 0, save, 0, "IMAGE")
    g.connect(upscale_model, 0, upscale, 0, "UPSCALE_MODEL")
    g.connect(select, 0, upscale, 1, "IMAGE")
    g.connect(upscale, 0, scale_2k, 0, "IMAGE")
    g.connect(scale_2k, 0, preview_2k, 0, "IMAGE")
    g.connect(scale_2k, 0, save_2k, 0, "IMAGE")
    g.group("🟢 建议调：提示词 / HMNSFW / 抽帧", (0, 420, 970, 630), "#2f855a")
    g.group("🔴 不建议调：固定模型与 1024×576×5", (1000, 10, 1320, 670), "#9b3d3d")
    g.group("🟢/🔵 抽卡 Seed 与采样", (2360, 10, 1420, 560), "#3f789e")
    g.group("输出：预览 5 帧、保留原图并生成 2K", (3820, 10, 2740, 840), "#8b6b32")
    return g.workflow()


def build_i2v() -> dict:
    g = Graph("02 H3 HMNSFW 图生视频抽卡", scale=0.62, offset=(130, 120))
    g.note((20, 10), (940, 260), "使用说明", """# 02｜H3 + HMNSFW 图生视频抽卡

从 ComfyUI **output** 目录选择第 1 步保存的 PNG。该图片同时连接 first_frame 与 last_frame，实际锁定首尾帧；固定图片和动作提示词，通过改变 Video Seed 反复 Queue 抽卡。

- **🟢 建议调：** 输入图、动作提示词、Video Seed、HMNSFW 强度。
- **🔵 可调：** 步数；默认 20。动作过大优先换 seed，再收紧提示词。
- **🔴 不建议调：** 首尾帧双连接、1024×576、73 帧、24fps、模型和采样器。

默认动作是多部位、低幅度 Live2D 循环：呼吸、头部、眼神、微表情、头发、衣摆、饰件和环境同时做小周期运动，并在结尾回到初始状态。HMNSFW 默认 0.30；建议 0.20–0.50。此流程不加载音频 VAE，输出静音 MP4，给显存和内存留余量。""", "#315c45")
    image = g.add_node(
        "LoadImageOutput", (20, 320), (420, 430), title="🟢 建议调 ①｜选择第 1 步输出 PNG",
        inputs=[("image", "COMBO", False)], outputs=[("IMAGE", "IMAGE"), ("MASK", "MASK")],
        widgets=["H3_T2I_Selected_Test.png [output]"], color="#1f5d3a", bgcolor="#163a29",
    )
    prompt = g.add_node(
        "PrimitiveStringMultiline", (490, 320), (760, 430), title="🟢 建议调 ②｜完整动作提示词",
        inputs=[("value", "STRING", False)], outputs=[("STRING", "STRING")], widgets=[MOTION_PROMPT], color="#1f5d3a", bgcolor="#163a29",
    )
    strength = g.add_node(
        "PrimitiveFloat", (20, 800), (300, 90), title="🟢 建议调 ③｜HMNSFW：0.20–0.50",
        inputs=[("value", "FLOAT", False)], outputs=[("FLOAT", "FLOAT")], widgets=[0.3], color="#1f5d3a", bgcolor="#163a29",
    )
    li = loader_inputs()
    unet = g.add_node("UNETLoader", (1360, 40), (610, 100), title="🔴 基础 H3（不要换）", inputs=li["unet"], outputs=[("MODEL", "MODEL")], widgets=[MODEL, "default"], color="#663333", bgcolor="#452525")
    lora = g.add_node("LoraLoaderModelOnly", (1360, 180), (610, 110), title="HMNSFW V2.5（必需）", inputs=li["lora"], outputs=[("MODEL", "MODEL")], widgets=[NSFW_LORA, 0.3], color="#1f5d3a", bgcolor="#163a29")
    clip = g.add_node("CLIPLoader", (1360, 330), (610, 120), title="🔴 H3 文本编码器（不要换）", inputs=li["clip"], outputs=[("CLIP", "CLIP")], widgets=[CLIP, "minimax", "default"], color="#663333", bgcolor="#452525")
    vae = g.add_node("VAELoader", (1360, 490), (610, 90), title="🔴 仅 Video VAE；不加载音频", inputs=li["vae"], outputs=[("VAE", "VAE")], widgets=[VIDEO_VAE], color="#663333", bgcolor="#452525")
    h3 = g.add_node(
        "MiniMaxH3ImageToVideo", (2070, 100), (540, 540), title="H3 I2V｜固定 1024×576×73",
        inputs=[("clip", "CLIP", False), ("vae", "VAE", False), ("first_frame", "IMAGE", True), ("last_frame", "IMAGE", True),
                ("prompt", "STRING", False), ("width", "INT", False), ("height", "INT", False), ("length", "INT", False)],
        outputs=[("positive", "CONDITIONING"), ("LATENT", "LATENT")], widgets=[MOTION_PROMPT, 1024, 576, 73], color="#663333", bgcolor="#452525",
    )
    g.connect(unet, 0, lora, 0, "MODEL")
    g.connect(strength, 0, lora, 2, "FLOAT")
    g.connect(clip, 0, h3, 0, "CLIP")
    g.connect(vae, 0, h3, 1, "VAE")
    g.connect(image, 0, h3, 2, "IMAGE")
    g.connect(image, 0, h3, 3, "IMAGE")
    g.connect(prompt, 0, h3, 4, "STRING")
    sampling = add_sampling(g, 2720, 70, h3, lora, vae, 2026083014)
    create = g.add_node(
        "CreateVideo", (4200, 130), (330, 120), title="🔴 固定 24fps / 8-bit / 无音频",
        inputs=[("images", "IMAGE", False), ("fps", "FLOAT", False), ("audio", "AUDIO", True), ("bit_depth", "INT", True)],
        outputs=[("VIDEO", "VIDEO")], widgets=[24.0, 8], color="#663333", bgcolor="#452525",
    )
    save = g.add_node(
        "SaveVideo", (4620, 80), (720, 260), title="保存并预览 MP4｜换 Seed 继续抽卡",
        inputs=[("video", "VIDEO", False), ("filename_prefix", "STRING", False), ("format", "COMBO", False), ("codec", "COMFY_DYNAMICCOMBO_V3", False)],
        outputs=[("video", "VIDEO")], widgets=["minimax_h3/ui_i2v_hmnsfw/draw", "mp4", "auto"],
    )
    g.connect(sampling["decode"], 0, create, 0, "IMAGE")
    g.connect(create, 0, save, 0, "VIDEO")
    g.group("🟢 建议调：输入图 / 动作提示词 / HMNSFW", (0, 290, 1280, 640), "#2f855a")
    g.group("🔴 不建议调：固定模型与 1024×576×73", (1330, 10, 1320, 670), "#9b3d3d")
    g.group("🟢/🔵 Video Seed 与采样", (2690, 10, 1420, 560), "#3f789e")
    g.group("输出：静音 24fps MP4", (4170, 10, 1210, 370), "#8b6b32")
    return g.workflow()


def build_4k() -> dict:
    g = Graph("03 视频超分 4K", scale=0.68, offset=(160, 130))
    g.note((20, 10), (970, 300), "使用说明", """# 03｜已选视频 AI 超分到 4K

把第 2 步最终选中的 MP4 拖入或上传到 LoadVideo。源视频必须是 1024×576（16:9），本流程只等比例输出 3840×2160，**不裁剪、不拉伸**。

- **🟢 建议调：** 输入视频。
- **🔵 可调：** 输出文件名前缀；AI 每批帧数在本机必须保持 1。
- **🔴 不建议调：** 3840×2160、Lanczos、24fps、float16、RealESRGAN 模型。

该节点按 1 帧子批次执行 RealESRGAN x4，再等比例缩到 4K。73 帧实测峰值 2.92GiB 显存 / 25.61GiB 内存。不要改成整批 ImageScale：实测会把 32GB 内存吃满。H3 与超分分开运行，不会同时占显存。""", "#315c45")
    load = g.add_node(
        "LoadVideo", (20, 370), (540, 380), title="🟢 建议调｜上传最终选中的 1024×576 MP4",
        inputs=[("file", "COMBO", False)], outputs=[("VIDEO", "VIDEO")],
        widgets=["H3_I2V_Draw_Test_73f_1024x576.mp4"], color="#1f5d3a", bgcolor="#163a29",
    )
    components = g.add_node(
        "GetVideoComponents", (650, 470), (280, 110),
        inputs=[("video", "VIDEO", False)], outputs=[("images", "IMAGE"), ("audio", "AUDIO"), ("fps", "FLOAT"), ("frame_count", "INT")],
    )
    up_model = g.add_node(
        "UpscaleModelLoader", (1050, 360), (430, 90), title="🔴 RealESRGAN x4plus（不要换）",
        inputs=[("model_name", "COMBO", False)], outputs=[("UPSCALE_MODEL", "UPSCALE_MODEL")], widgets=[UPSCALE_MODEL], color="#663333", bgcolor="#452525",
    )
    ai = g.add_node(
        "ImageUpscaleWithModelBatched", (1550, 350), (500, 200), title="🔵 AI 分批：per_batch=1（不要增大）",
        inputs=[("upscale_model", "UPSCALE_MODEL", False), ("images", "IMAGE", False), ("per_batch", "INT", False),
                ("downscale_ratio", "FLOAT", True), ("downscale_method", "COMBO", True), ("precision", "COMBO", True)],
        outputs=[("IMAGE", "IMAGE")], widgets=[1, 1.0, "lanczos", "float16"], color="#244a66", bgcolor="#183347",
    )
    ai_final = g.add_node(
        "ImageScale", (2140, 380), (430, 150), title="🔴 等比例缩到 3840×2160｜不裁剪",
        inputs=[("image", "IMAGE", False), ("upscale_method", "COMBO", False), ("width", "INT", False), ("height", "INT", False), ("crop", "COMBO", False)],
        outputs=[("IMAGE", "IMAGE")], widgets=["lanczos", 3840, 2160, "disabled"], color="#663333", bgcolor="#452525",
    )
    create = g.add_node(
        "CreateVideo", (2690, 390), (340, 120), title="🔴 固定 24fps / 8-bit / 静音",
        inputs=[("images", "IMAGE", False), ("fps", "FLOAT", False), ("audio", "AUDIO", True), ("bit_depth", "INT", True)],
        outputs=[("VIDEO", "VIDEO")], widgets=[24.0, 8], color="#663333", bgcolor="#452525",
    )
    save = g.add_node(
        "SaveVideo", (3130, 320), (820, 260), title="🔵 可调输出名｜保存 3840×2160 MP4",
        inputs=[("video", "VIDEO", False), ("filename_prefix", "STRING", False), ("format", "COMBO", False), ("codec", "COMFY_DYNAMICCOMBO_V3", False)],
        outputs=[("video", "VIDEO")], widgets=["minimax_h3/ui_4k/final_3840x2160", "mp4", "auto"],
    )
    g.connect(load, 0, components, 0, "VIDEO")
    g.connect(components, 0, ai, 1, "IMAGE")
    g.connect(up_model, 0, ai, 0, "UPSCALE_MODEL")
    g.connect(ai, 0, ai_final, 0, "IMAGE")
    g.connect(ai_final, 0, create, 0, "IMAGE")
    g.connect(create, 0, save, 0, "VIDEO")
    g.group("🟢 建议调：输入视频", (0, 340, 970, 450), "#2f855a")
    g.group("🔵/🔴 分批 AI 超分：per_batch 固定 1", (1020, 310, 1590, 290), "#9b3d3d")
    g.group("输出：3840×2160，不裁剪", (2660, 280, 1330, 340), "#8b6b32")
    return g.workflow()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    workflows = {
        "01_H3_HMNSFW_文生图抽卡.json": build_t2i(),
        "02_H3_HMNSFW_图生视频抽卡.json": build_i2v(),
        "03_已选视频超分4K.json": build_4k(),
    }
    requested = set(sys.argv[1:])
    unknown = requested.difference(workflows)
    if unknown:
        raise SystemExit(f"unknown workflow name(s): {', '.join(sorted(unknown))}")
    for name, workflow in workflows.items():
        if requested and name not in requested:
            continue
        path = OUTPUT / name
        path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {path} nodes={len(workflow['nodes'])} links={len(workflow['links'])} groups={len(workflow['groups'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
