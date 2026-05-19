from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from pathlib import Path

from openai import AzureOpenAI

from .openai_client import SYSTEM_PROMPT
from ..host_vision import (
    HostVisionBrief,
    pick_exact_text,
    pick_vision_image,
)
from ..models import GiftDesign, HostInput, ImageEvaluation


VISION_BRIEF_WRITING_TEMPLATE = """按下面这个从 Cowhair 强 prompt 抽象出来的模板写当前主播 brief。
注意:这是写作模板,不是要你输出完整 prompt;你最终仍然只输出 JSON。

1. 开场产品合同:
黑色背景,固定45度朝右产品视角,完整展示整支打call棒,灯头/连接处/握柄/底部节点全部清晰。顶部为 {lamp_head_silhouette},中央为 {central_core_material} 实体核心,中间嵌入发光文字 {exact_text}。

2. 风格记忆:
整体风格围绕 "{exact_text}" 延展,设定为 {primary_symbol} × {material_or_texture_memory} × {idol_collectible_mood},整体气质偏 {mood_phrase},带一点 {streamer_visual_memory} 的视觉记忆。
=> 写入 style_pitch / mood.phrase。

3. 配色记忆:
整体配色采用 {main_color}、{secondary_color}、{accent_colors},形成 {palette_family} 的鲜明视觉记忆。主色/主材/中心核心各自负责什么视觉任务要说清楚。
=> 写入 palette.family/main_color/secondary_color/accent_colors/tags。

4. 材质对比:
材质以 {dominant_material}、{core_material}、{trim_material}、{surface_finish} 为主,强调 {soft_vs_hard_or_clear_vs_matte_contrast},形成收藏级3D产品质感。
=> 写入 materials.main/supporting/tags,优先使用图像模型容易执行的产品材质词。

5. 主题解构:
主题为 {primary_symbol}、{secondary_symbol} 与 {mood_symbol} 的解构设计:
将 {primary_symbol} 解构为灯头主体的 {primary_forms};
将 {secondary_symbol} 解构为灯头边缘/连接区/握柄上的 {secondary_forms};
将气质或内容感转译为 {connector_or_surface_details}。
=> 写入 signature_symbols 和 theme_forms。每个 forms 必须是能长在产品上的结构,不是平面图案。

6. 灯头主读感:
整体灯头像一个被 {primary_symbol} 与 {secondary_symbol} 包裹的 {idol_object_metaphor},主轮廓要清晰,中心核心要透亮完整,外部装饰不能遮挡文字与核心结构。
=> 写入 lamp_head_silhouette / silhouette_language / theme_forms.fusion_note。

7. 文字嵌入:
文字 {exact_text} 采用 {font_style_memory} 的立体发光字体,具有立体厚度、浮雕感、局部内发光、柔亮描边、嵌入式核心结构感。
=> 写入 text.style_hint。

8. 手柄与底部节点:
底部装饰设计为一体化 {theme_bottom_node},加入 {bottom_details},让视觉重点集中在灯头,同时保持整支比例完整、结构协调。
=> 写入 handle.main_material/surface_treatment/connector_detail/bottom_cap/decoration_continuation。

9. 总强调:
收藏级产品渲染、强3D体积感、真实材质厚度、清晰主光、边缘轮廓光、材质层次、核心局部发光、整支棒体不做全局霓虹泛光、干净商业海报感。
"""



class ModelHubGiftClient:
    """ModelHub/AzureOpenAI-compatible version of the gift design client."""

    def __init__(self) -> None:
        self.api_key = os.getenv("MODELHUB_API_KEY", "").strip()
        self.azure_endpoint = os.getenv("MODELHUB_AZURE_ENDPOINT", "").strip()
        self.api_version = os.getenv("MODELHUB_API_VERSION", "2024-02-01").strip()
        self.model = os.getenv("MODELHUB_MODEL", "").strip()
        if not self.api_key:
            raise ValueError("MODELHUB_API_KEY is missing.")
        if not self.azure_endpoint:
            raise ValueError("MODELHUB_AZURE_ENDPOINT is missing.")
        if not self.model:
            raise ValueError("MODELHUB_MODEL is missing.")
        self.client = AzureOpenAI(
            api_key=self.api_key,
            api_version=self.api_version,
            azure_endpoint=self.azure_endpoint,
            default_headers={"X-TT-LOGID": os.getenv("MODELHUB_LOGID", "community-gift-local")},
        )

    def analyze_host_visual_brief(self, host: HostInput) -> HostVisionBrief:
        """Vision-driven structured brief for a single host.

        Source priority: avatar.jpg → stickers.jpg → text-only (no image).
        Returns a fully-populated :class:`HostVisionBrief` so downstream
        routers and template_first slots never see empty values.
        """

        image_path, image_source = pick_vision_image(host)
        exact_text, text_source = pick_exact_text(host.community_name, host.host_name)

        raw = host.raw if isinstance(host.raw, dict) else {}
        signals_summary = {
            "host_name": host.host_name,
            "fan_club": host.community_name,
            "tier": raw.get("tier", ""),
            "host_symbols": raw.get("host_symbols", []),
            "comm_symbols": raw.get("comm_symbols", []),
            "primary_signals": raw.get("primary_signals", []),
            "missing_signals": raw.get("missing_signals", []),
            # Free-text paragraph describing the streamer's format / persona /
            # content type. Primary source of material inspiration.
            "characterization": raw.get("characterization", ""),
        }
        instruction = (
            "你是 TikTok 直播社群应援棒礼物的视觉设计 brief 生成器。"
            "根据提供的主播视觉素材(avatar 或 sticker)与 signals 摘要,产出一份"
            "**结构化的 JSON brief**,用于驱动一支高级实体应援棒(lightstick)的设计。"
            "\n\n最高优先级写作模板:\n"
            f"{VISION_BRIEF_WRITING_TEMPLATE}"
            "\n\n参考输出风格示例(节奏/词汇/具体程度,但不要照搬词组):\n"
            "  - style_pitch 例:甜酷果冻系守护精灵风 / 温柔梦幻紫色爱心偶像应援风 / 热带海岛夜晚应援风\n"
            "  - palette.family 例:甜冷糖果系 / 烟灰冷调 / 暖橙海岛系 / 紫色梦幻系\n"
            "  - materials.main 例:高光半透明果冻树脂 / 珠光奶油釉面塑胶 / 镜面珐琅\n"
            "  - theme_forms.primary.forms 例:[\"双果鼓包\",\"果冻球体\",\"果梗线\",\"叶片状小护片\"]\n"
            "  - lamp_head_silhouette 例:**优先有机/圆润/吹塑感**形状:椭圆果实双叶护片 / "
            "心形包裹双侧蝶翼 / 拱顶马铃薯块状 / 软糖球体融合双翼 / 蛋形包裹流线护片 / "
            "葫芦双联泡 / 水滴拉长拱冠;只在主播明确是 military/award/medal/badge/heraldic 才用"
            "锐角几何(盾形/六角晶体/勋章/纹章);避免多边形棱面拼接读感\n"
            "  - silhouette_language 例:鼓起、圆润、包裹、对称、轻轻上扬\n"
            "  - lighting 例:清晰主光、晶体折射、软硬高光对比、局部内发光\n"
            "  - mood.phrase 例:甜美、治愈、俏皮、亲切、软萌、带潮玩感\n"
            "  - handle.main_material 例:珠光奶白树脂 / 烟熏哑光金属 / 透明果冻晶体\n"
            "  - handle.surface_treatment 例:**光滑无缝吹塑曲面** / 半透明渐变果冻表面 / "
            "细腻磨砂釉面 / 微弱浮雕主题压纹(不要凹槽/螺纹/缠绕/橡胶颗粒,避免战术电筒感)\n"
            "  - handle.connector_detail 例:**细腻颈部收束 + 一圈极薄装饰边** / "
            "柔和过渡至灯头的曲面收口(像吹制玻璃的腰身)/ 一圈半透晶体环 + 微型主题切片(不要粗金属箍环,不要橡胶圈)\n"
            "  - handle.bottom_cap 例:**柔和水滴形收尾** + 中央主题徽章 / "
            "圆润穹顶收尾 + 主题压纹 / 自然内收的曲面尾盖(不要分段圆盘、不要可见按钮)\n"
            "  - handle.decoration_continuation 例:沿握柄向下延伸的细羽纹 / "
            "靠近灯头处嵌入小型主题晶体串 / 顶端 1/3 段刻有与灯头同色调的细纹\n"
            "\n硬规则:\n"
            "1. 不描述真人脸/五官/身份,不要主播脸出现在设计中。\n"
            "2. signature_symbols.primary/secondary 抽具体物象(动物/植物/物体/几何/emoji 概念),"
            "不要塞主播名或社群名作为符号。\n"
            "3. 如有 avatar 物象就 source='avatar';avatar 没明确物象再看 sticker(source='sticker');"
            "都没有就用 text_only,从 signals/symbols 文字推。\n"
            "4. theme_forms.primary.forms 至少 3 项,每项是一个具体的灯头结构词(2-6 字)。\n"
            "5. palette.tags / materials.tags / mood.tags 用英文小写下划线 tag(供 router 匹配)。\n"
            "6. exact_text 已由调用方决定(传入 'preselected_text' 字段),"
            "你必须把 text.exact_text 设为该值并填 text.source。"
            "你需要做的是写好 text.style_hint(字体气质中文描述)。\n"
            "7. **lamp_head_silhouette 必须是具体的形状名描述**(8-16 字),"
            "不可以只写'圆润'/'上扬'(那些是 silhouette_language 干的)。"
            "重点:避免心形 / 圆形默认,优先选择能区分这位主播的独特轮廓。\n"
            "8. **handle 五个字段全部填写**,不能空白。handle 是与灯头同等重要的视觉部分,"
            "材质/连接件/底盖必须延续主题色与材质语言。\n"
            "9. **材质必须有显著差异性**。从下列 8 个材质家族里挑一个作为**主导家族**,"
            "辅助材质必须来自**另一个不同家族**形成对比。不允许两项都属同一家族:\n"
            "   A. 树脂家族 — 高光半透明果冻树脂、珠光釉面塑胶、糖果硬树脂\n"
            "   B. 金属家族 — 拉丝铝、阳极氧化枪灰、镜面铬、做旧黄铜、玫瑰金\n"
            "   C. 织物家族 — 羊毛、丝绒、缝纫皮革、麻布、毛毡、印花布\n"
            "   D. 陶瓷家族 — 哑光陶、釉面瓷、青花、粗陶\n"
            "   E. 玻璃晶体家族 — 切面水晶、磨砂玻璃、吹制气泡玻璃、彩色玻璃\n"
            "   F. 木质家族 — 漆木、雕花原木、做旧木板、藤编\n"
            "   G. 涂层家族 — 哑光橡胶喷漆、做旧涂层、磨砂保护漆\n"
            "   H. 自然纹理家族 — 石材切片、贝母、骨刻、沙岩、矿物结晶\n"
            "**严禁默认到 '枪灰金属 + 烟熏亚克力' 或 '珠光树脂 + 香槟金' 这两个套路**。\n"
            "选家族时:\n"
            "   - 优先从 avatar 视觉看到的真实材质(布料/毛发/陶瓷/玻璃/木头)出发\n"
            "   - 其次从 characterization 中的内容形态(只有真正的 KO/PUBG/Free Fire/PK 才算 military)\n"
            "   - 文化暗示(异域/沙漠 → 黄铜 + 沙岩;海岛 → 玻璃 + 贝母;都市夜店 → 喷漆 + 玻璃;市井日常 → 陶 + 木)\n"
            "主辅之间必须有视觉对比:光泽 vs 磨砂、硬 vs 软、冷 vs 暖、反射 vs 吸光。\n"
            "10. 只输出 JSON object,不要 markdown,不要解释文字。"
        )
        payload = {
            "row_id": host.row_id,
            "host_name": host.host_name,
            "preselected_text": exact_text,
            "preselected_text_source": text_source,
            "image_source": image_source,
            "signals_summary": signals_summary,
        }
        schema_hint = {
            "row_id": "int",
            "host_name": "string",
            "text": {
                "exact_text": "string (use preselected_text verbatim)",
                "source": "string (use preselected_text_source verbatim)",
                "script": "latin | korean | arabic | chinese | mixed | empty",
                "style_hint": "Chinese description of font character",
            },
            "style_pitch": "1-sentence Chinese style framing",
            "palette": {
                "family": "Chinese palette family",
                "main_color": "Chinese color word",
                "secondary_color": "Chinese color word",
                "accent_colors": ["..."],
                "tags": ["english_lower_underscore"],
            },
            "materials": {
                "main": "Chinese material",
                "supporting": "Chinese material",
                "tags": ["english_lower_underscore"],
            },
            "signature_symbols": {
                "primary": "concrete visual object",
                "secondary": "concrete visual object or empty",
                "source": "avatar | sticker | text_only",
            },
            "theme_forms": {
                "primary": {
                    "symbol": "...",
                    "position": "灯头位置描述",
                    "forms": ["form1", "form2", "form3"],
                },
                "secondary": {"symbol": "", "position": "", "forms": []},
                "fusion_note": "",
            },
            "lamp_head_silhouette": "Chinese concrete shape name (8-16 chars)",
            "silhouette_language": "Chinese rhythm words separated by 、",
            "lighting": "Chinese lighting hints separated by 、",
            "mood": {
                "phrase": "Chinese mood words separated by 、",
                "tags": ["english_lower_underscore"],
            },
            "handle": {
                "main_material": "Chinese material",
                "surface_treatment": "Chinese surface treatment",
                "connector_detail": "Chinese connector detail",
                "bottom_cap": "Chinese bottom cap description",
                "decoration_continuation": "Chinese description of theme-handle continuity",
            },
        }
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    instruction
                    + "\n\n输入数据:\n"
                    + json.dumps(payload, ensure_ascii=False)
                    + "\n\n输出 schema 提示:\n"
                    + json.dumps(schema_hint, ensure_ascii=False)
                ),
            }
        ]
        if image_path:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_to_input_url(image_path)},
                }
            )

        text = self._chat(content, max_tokens=1400)
        data = _json_object(text)
        # Enforce caller-decided text — the LLM may not be trusted to pick
        # exact_text on its own.
        data.setdefault("text", {})
        data["text"]["exact_text"] = exact_text
        data["text"]["source"] = text_source
        data["row_id"] = host.row_id
        data.setdefault("host_name", host.host_name)
        brief = HostVisionBrief.model_validate(data)
        brief.image_source = image_source
        brief.image_path = image_path
        return brief

    def evaluate_candidate_image(
        self,
        image_path: str,
        design: GiftDesign,
        effect_context: list[dict],
    ) -> ImageEvaluation:
        content = [
            {
                "type": "text",
                "text": (
                    "请评估候选图是否接近理想效果库的审美标准。"
                    "参考图只用于验收，不要求复制颜色、文字或主题。"
                    "如果提供 negative_reference_images，它们是反例。"
                    "文字是硬约束：候选图只能有一个主文字。"
                    "如果 candidate_design.seedance_prompt 以 TEXT PRIORITY FIRST 开头，"
                    "必须以该段中引号里的 exact text 作为唯一正确文字，而不是 candidate_design.community_name。"
                    "主文字必须在灯头形状内部的中央发光核心或中央铭牌内；任何悬浮在灯头上方、外接 banner、写在手柄、连接件、底盖、边框、外圈装饰上的文字都视为失败。"
                    "如果 candidate_design.text_plan.mode 是 post_overlay_text，则候选图不应该有任何文字，只应该有空白中央铭牌/核心；出现伪字母也视为 text_fail。"
                    "任何拼写错误、乱码、额外签名、随机小字、破形字母、倾斜手柄文字都应作为严重问题扣分。"
                    "构图也是硬约束：主工作流必须是 1:1 正方形图，连续纯黑背景，不能有白色卡片/白色圆角面板/白色地面/展示板，整支应援棒从灯头到完整手柄和底部节点都要可见，底部节点下方要有黑色留白；头部特写、裁切、缺底盖都失败。"
                    "failure_types 请从这些值中选择，可多选：background_fail, cropping_fail, text_fail, concept_fail, complexity_fail, product_form_fail, material_fail, unknown_fail。"
                    "只输出 JSON object，字段：image_path,total_score,passed,scores,verdict,strengths,issues,prompt_revision_notes,failure_types。"
                ),
            },
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "candidate_design": design.model_dump(),
                        "ideal_effect_evaluation_context": effect_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        for effect in effect_context:
            for reference_image in effect.get("reference_images", []):
                content.extend(
                    [
                        {"type": "text", "text": "Positive ideal reference image:"},
                        {"type": "image_url", "image_url": {"url": self._image_to_input_url(reference_image)}},
                    ]
                )
            for reference_image in effect.get("negative_reference_images", []):
                content.extend(
                    [
                        {"type": "text", "text": "Negative reference image:"},
                        {"type": "image_url", "image_url": {"url": self._image_to_input_url(reference_image)}},
                    ]
                )
        content.extend(
            [
                {"type": "text", "text": "Candidate image:"},
                {"type": "image_url", "image_url": {"url": self._image_to_input_url(image_path)}},
            ]
        )
        text = self._chat(content, max_tokens=1200)
        evaluation = ImageEvaluation.model_validate(_json_object(text))
        evaluation.image_path = image_path
        return evaluation

    def _chat(self, content: list[dict], max_tokens: int) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=max_tokens,
            stream=False,
        )
        return (response.choices[0].message.content or "").strip()

    def _image_to_input_url(self, image: str) -> str:
        if image.startswith(("http://", "https://", "data:")):
            return image

        path = Path(image).expanduser()
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"


def _json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))
