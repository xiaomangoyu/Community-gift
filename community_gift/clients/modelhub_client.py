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


VISION_BRIEF_WRITING_TEMPLATE = """你不是最终 prompt 作者,而是视觉感知与槽位提取器。
只把主播素材转成可执行的 lightstick 结构槽位,不要写完整生图 prompt,不要写设计散文。

字段写法:
1. style_pitch: 8-18 个中文字符的短标签,例如 "粉紫蝶翼梦幻风" / "暖棕圆润玩具风" / "电蓝王冠街头风"。
   禁止出现 exact_text、主播名、社群名、引号、"围绕/延展/记忆/社群/守护/凝聚/招牌/标识/铭牌/logo"。
2. signature_symbols.primary/secondary: 具体可视物象,优先来自 avatar/sticker 明确可见物;不明确时才用 signals。
   只写物体名,例如 "蝴蝶" / "蜜瓜" / "皇冠" / "拳击手套";不要写人设、情绪、社群名。
3. lamp_head_silhouette: 8-16 字具体灯头形状,必须能被建模,例如 "双蝶翼包心灯头"、"椭圆薯体拱冠"。
4. theme_forms.*.forms: 每项 2-6 字,只写结构件,例如 "双翼护片"、"拱形冠齿"、"浅芽眼点"。
   禁止写平面图案、贴纸、文字、标识、招牌、故事。
5. palette: 颜色词短而明确; tags 用英文小写下划线,供 router 匹配。
6. materials: 只选两种主材/辅材,必须是产品材质,例如 "半透明果冻树脂"、"吹制气泡玻璃"、"哑光软皮包覆"。
7. text.style_hint: 只描述 exact_text 的字形和发光方式,不要出现招牌/标题/铭牌/logo/wordmark。
8. handle 五个字段: 写成短产品槽位,描述握柄材质、表面、连接、底盖、主题延续;不要写否定句。
9. mood.phrase: 4-6 个短气质词,用顿号分隔;不要写长句。
10. fusion_note: 默认留空;只有两个物象必须解释如何融合时,写 20 字以内结构说明。
"""


PROMPT_REFINER_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2] / "references" / "imgs" / "Boxer.txt"
)


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
            "你是 TikTok 直播社群应援棒礼物的视觉感知与槽位提取器。"
            "根据提供的主播视觉素材(avatar 或 sticker)与 signals 摘要,产出一份"
            "**结构化的 JSON brief**,用于驱动 deterministic template 生成高级实体应援棒(lightstick)。"
            "\n\n最高优先级写作模板:\n"
            f"{VISION_BRIEF_WRITING_TEMPLATE}"
            "\n\n字段示例(只学字段粒度,不要扩写成句子):\n"
            "  - style_pitch 例:甜酷果冻精灵风 / 紫色爱心梦幻风 / 热带海岛夜光风\n"
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
            "9. 所有字段必须短、结构化、可被 template 直接拼接;不要输出完整 prompt 句式,不要写营销文案。"
            "禁止词:招牌、标题、标识、铭牌、牌匾、logo、wordmark、社群凝聚、守护感、记忆延展、圣物。\n"
            "10. **材质必须有显著差异性**。从下列 8 个材质家族里挑一个作为**主导家族**,"
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
            "11. 只输出 JSON object,不要 markdown,不要解释文字。"
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
            "style_pitch": "short Chinese style label, 8-18 chars, no exact_text/name/prose",
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

    def refine_final_prompt(self, design: GiftDesign) -> str:
        """Rewrite the template-first draft into a reference-style final prompt."""

        exact_text = design.text_plan.exact_text or design.host_name
        example = _read_text_if_exists(PROMPT_REFINER_EXAMPLE_PATH)
        instruction = (
            "你是 Seedream 产品图 prompt 的最终终稿编辑器。"
            "你的任务不是重新设计,而是把 template-first draft 改写成类似强 reference prompt 的完整设计师终稿。"
            "参考例子只学习段落节奏、具体程度、材质/主题解构语言和主记忆点强化方式,不要照搬其中的主题、颜色或文字。"
            "你必须重写,不能原样返回 draft,也不能只改标点或只删一两句话。"
            "最终 prompt 必须使用中文撰写;除了 exact_text 本身,不要输出英文整句。"
            "\n\n目标:\n"
            "1. 保留所有硬约束:黑色背景、1:1 正方形、固定45度朝右产品视角、整支打call棒完整入画、"
            "灯头/连接处/握柄/底部节点全部清楚、单一产品、收藏级3D实体产品感。\n"
            "2. 保留 exact text,必须仍然只出现这一处主文字,不要改写、翻译或缩写。"
            "除 exact_text 外,不要把任何主题词、中文名、符号解释写成引号内的词、标题、标识、字样、招牌、logo、"
            "wordmark 或铭牌文字;主题词只能作为结构/材质/轮廓描述,不要靠近'文字/核心铭牌/可读标识'语境。"
            "不要在最终 prompt 里输出 exact_text 这个字段名,只写实际要渲染的文字本身。"
            "3. 保留主符号、主配色、主要材质、灯头轮廓、手柄主题延续和 negative 约束隐含的安全边界。"
            "4. 按强 reference prompt 的写法重排为自然段:产品合同、整体风格、配色、材质、主题解构、灯头整体读感、文字、手柄/底部、整体强调。"
            "5. 语言要像最终生图 prompt,不是 schema 拼接说明;合并重复句,去掉机械兜底句,让每段围绕同一个主记忆点推进。"
            "避免保留 template-first 的机械句式,例如反复使用'整体强调'、'来自某某系'、'所有外扩装饰'、"
            "'带有偶像周边收藏感'这类兜底表达;保留意思但换成更自然的 reference prompt 语言。"
            "输出 prompt 禁止出现这些 template-first 段落标记或句头:"
            "整体风格围绕、整体配色采用、材质以、主题为、让整体灯头像、手柄设计：、整体强调：。"
            "如果 draft 里有这些句子,必须改写成自然设计描述。"
            "6. 可以把 draft 里的槽位翻译成更顺的设计语言,但不能引入 draft 没有的新人设、新主题、新 reference 文字或新道具。"
            "7. 长度以中文 reference prompt 为准,通常 900-1500 个中文字符;不要输出超长英文说明。"
            "8. 不新增真人、人脸、海报、卡片、外接文字牌、复杂背景或全局霓虹泛光。"
            "\n\n输出格式:只输出 JSON object,字段为 prompt。不要 markdown,不要解释。"
        )
        payload = {
            "exact_text": exact_text,
            "host_name": design.host_name,
            "community_name": design.community_name,
            "primary_symbol": design.design_concept.primary_symbol,
            "material_language": design.material_language,
            "color_plan": design.color_plan,
            "required_elements": design.required_elements,
            "negative_constraints": design.negative_constraints,
            "draft_prompt": design.seedance_prompt,
            "style_example_boxer": example,
        }
        content = [
            {
                "type": "text",
                "text": instruction + "\n\n输入:\n" + json.dumps(payload, ensure_ascii=False),
            }
        ]
        text = self._chat(content, max_tokens=2200)
        data = _json_object(text)
        prompt = str(
            data.get("prompt")
            or data.get("final_prompt")
            or data.get("seedance_prompt")
            or ""
        ).strip()
        prompt = _sanitize_non_exact_quoted_terms(prompt, exact_text)
        return _safe_refined_prompt(prompt, design.seedance_prompt, exact_text)

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


def _read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _safe_refined_prompt(refined: str, original: str, exact_text: str) -> str:
    """Reject refiner output that dropped critical product/text anchors."""

    if not refined:
        return original
    ratio = len(refined) / max(1, len(original))
    if len(refined) < 450 or ratio < 0.5:
        return original
    if exact_text and exact_text not in refined:
        return original
    required_groups = [["黑色背景", "纯黑背景", "黑色棚拍", "纯黑棚拍"]]
    if any(not any(term in refined for term in group) for group in required_groups):
        return original
    return refined


def _sanitize_non_exact_quoted_terms(prompt: str, exact_text: str) -> str:
    """Remove quote emphasis from Chinese theme labels while preserving exact text."""

    exact_text = (exact_text or "").strip()
    prompt = _rewrite_literal_exact_text_label(prompt, exact_text)
    placeholders: dict[str, str] = {}
    if exact_text:
        for idx, wrapped in enumerate(
            [
                f"「{exact_text}」",
                f"“{exact_text}”",
                f'"{exact_text}"',
                f"'{exact_text}'",
            ]
        ):
            token = f"__EXACT_TEXT_QUOTE_{idx}__"
            if wrapped in prompt:
                placeholders[token] = wrapped
                prompt = prompt.replace(wrapped, token)

    prompt = re.sub(r"「([^」]*[\u4e00-\u9fff][^」]*)」", r"\1", prompt)
    prompt = re.sub(r"“([^”]*[\u4e00-\u9fff][^”]*)”", r"\1", prompt)
    prompt = re.sub(r'"([^"\n]*[\u4e00-\u9fff][^"\n]*)"', r"\1", prompt)
    prompt = re.sub(r"'([^'\n]*[\u4e00-\u9fff][^'\n]*)'", r"\1", prompt)

    for token, wrapped in placeholders.items():
        prompt = prompt.replace(token, wrapped)
    return prompt


def _rewrite_literal_exact_text_label(prompt: str, exact_text: str) -> str:
    """The refiner sometimes emits the field name ``exact_text`` literally."""

    if not exact_text:
        return prompt.replace("exact_text", "").replace("exact text", "")

    escaped = re.escape(exact_text)
    prompt = re.sub(
        rf"\bexact[_ ]text\s*仅在这一处出现\s*[:：]\s*{escaped}",
        f"文字“{exact_text}”仅在这一处出现",
        prompt,
        flags=re.I,
    )
    prompt = re.sub(
        rf"\bexact[_ ]text\s*[:：]?\s*{escaped}",
        f"文字“{exact_text}”",
        prompt,
        flags=re.I,
    )
    prompt = re.sub(r"\bexact[_ ]text\b\s*", "", prompt, flags=re.I)
    if not re.search(r"[\u4e00-\u9fff]", exact_text):
        prompt = re.sub(
            rf"认出[\u4e00-\u9fff]{{1,12}}主题与\s*{escaped}\s*这处核心文字",
            f"认出主视觉结构与“{exact_text}”这处核心文字",
            prompt,
        )
    return prompt
