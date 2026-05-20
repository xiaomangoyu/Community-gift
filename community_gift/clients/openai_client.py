from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path

from openai import OpenAI

from ..models import GiftDesign, ImageEvaluation


SYSTEM_PROMPT = """你是一个 TikTok 直播社群礼物设计工作流助手。
目标：把主播信息抽象成一个可送出的高级实体礼物资产。
硬规则：
1. 复杂度必须简单，最多保留 2-4 个核心元素。
2. 不要主播脸，不做人像，不还原真人五官。
3. 可以从图片里提炼非人脸视觉符号，如帽子、发色、服装色、配饰、宠物、道具。
4. 方向偏高级实体礼物，不是海报，不是电竞 KV。
5. 可选形态包括应援棒、实体灯牌、收藏徽章、挂件、亚克力摆件、金属奖章、迷你奖杯、魔法权杖。
6. 重视材质：金属、亚克力、玻璃灯管、丝绒、皮革、宝石、珐琅、克制发光。
7. 输出要适合直播间小尺寸展示，社群名和主符号优先清楚。
"""

PROMPT_REFINER_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2] / "references" / "imgs" / "Boxer.txt"
)


class GiftOpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def refine_final_prompt(self, design: GiftDesign) -> str:
        """Rewrite the template-first draft into a reference-style final prompt."""

        exact_text = design.text_plan.exact_text or design.host_name
        example = _read_text_if_exists(PROMPT_REFINER_EXAMPLE_PATH)
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
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "你是 Seedream 产品图 prompt 的最终终稿编辑器。"
                        "不要重新设计,而是把 template-first draft 改写成类似强 reference prompt 的完整设计师终稿。"
                        "参考例子只学习段落节奏、具体程度、材质/主题解构语言和主记忆点强化方式,"
                        "不要照搬其中的主题、颜色或文字。你必须重写,不能原样返回 draft,"
                        "也不能只改标点或只删一两句话。最终 prompt 必须使用中文撰写;"
                        "除了 exact_text 本身,不要输出英文整句。\n\n"
                        "硬规则:保留黑色背景、1:1 正方形、固定45度朝右产品视角、整支打call棒完整入画、"
                        "灯头/连接处/握柄/底部节点全部清楚、单一收藏级3D实体产品。"
                        "exact_text 必须原样保留,画面中仍只出现这一处主文字。"
                        "除 exact_text 外,不要把任何主题词、中文名、符号解释写成引号内的词、标题、标识、字样、招牌、logo、"
                        "wordmark 或铭牌文字;主题词只能作为结构/材质/轮廓描述,不要靠近'文字/核心铭牌/可读标识'语境。"
                        "不要在最终 prompt 里输出 exact_text 这个字段名,只写实际要渲染的文字本身。"
                        "保留主符号、主配色、主要材质、灯头轮廓和手柄主题延续。"
                        "按强 reference prompt 的写法重排为自然段:产品合同、整体风格、配色、材质、主题解构、"
                        "灯头整体读感、文字、手柄/底部、整体强调。"
                        "语言要像最终生图 prompt,不是 schema 拼接说明;合并重复句,去掉机械兜底句,"
                        "让每段围绕同一个主记忆点推进。"
                        "避免保留 template-first 的机械句式,例如反复使用'整体强调'、'来自某某系'、"
                        "'所有外扩装饰'、'带有偶像周边收藏感'这类兜底表达;保留意思但换成更自然的 reference prompt 语言。"
                        "输出 prompt 禁止出现这些 template-first 段落标记或句头:"
                        "整体风格围绕、整体配色采用、材质以、主题为、让整体灯头像、手柄设计：、整体强调：。"
                        "如果 draft 里有这些句子,必须改写成自然设计描述。"
                        "可以把 draft 里的槽位翻译成更顺的设计语言,但不能引入 draft 没有的新人设、新主题、"
                        "新 reference 文字或新道具。长度以中文 reference prompt 为准,通常 900-1500 个中文字符;"
                        "不要输出超长英文说明。"
                        "不新增真人、人脸、海报、卡片、外接文字牌、复杂背景或全局霓虹泛光。\n\n"
                        "只输出 JSON object,字段为 prompt。不要 markdown,不要解释。\n\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
        )
        data = _json_object(response.output_text)
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
        content: list[dict] = [
            {
                "type": "input_text",
                "text": (
                    "请评估候选图是否接近理想效果库的审美标准。"
                    "理想库参考图只用于验收对比，不用于要求复制颜色、文字或主题。"
                    "如果提供 negative_reference_images，它们是反例，用来识别不够好的结构问题。"
                    "重点看：是否像实体礼物、是否符合核心效果、材质是否高级、"
                    "小尺寸是否清楚、是否违反 no human face/no poster 等约束。"
                    "文字是硬约束：候选图只能有一个主文字。"
                    "如果 candidate_design.seedance_prompt 以 TEXT PRIORITY FIRST 开头，"
                    "必须以该段中引号里的 exact text 作为唯一正确文字，而不是 candidate_design.community_name。"
                    "主文字必须在灯头形状内部的中央发光核心或中央铭牌内；任何悬浮在灯头上方、外接 banner、写在手柄、连接件、底盖、边框、外圈装饰上的文字都视为失败。"
                    "如果 candidate_design.text_plan.mode 是 post_overlay_text，则候选图不应该有任何文字，只应该有空白中央铭牌/核心；出现伪字母也视为 text_fail。"
                    "任何拼写错误、乱码、额外签名、随机小字、破形字母、倾斜手柄文字都应作为严重问题扣分。"
                    "构图也是硬约束：主工作流必须是 1:1 正方形图，连续纯黑背景，不能有白色卡片/白色圆角面板/白色地面/展示板，整支应援棒从灯头到完整手柄和底部节点都要可见，底部节点下方要有黑色留白；头部特写、裁切、缺底盖都失败。"
                    "failure_types 请从这些值中选择，可多选：background_fail, cropping_fail, text_fail, concept_fail, complexity_fail, product_form_fail, material_fail, unknown_fail。"
                    "输出 JSON。"
                ),
            },
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "candidate_design": design.model_dump(),
                        "ideal_effect_evaluation_context": effect_context,
                    },
                    ensure_ascii=False,
                ),
            },
            {"type": "input_text", "text": "Candidate image:"},
            {"type": "input_image", "image_url": self._image_to_input_url(image_path)},
        ]

        for effect in effect_context:
            for reference_image in effect.get("reference_images", []):
                content.extend(
                    [
                        {
                            "type": "input_text",
                            "text": f"Ideal reference image for effect {effect.get('id', '')}:",
                        },
                        {
                            "type": "input_image",
                            "image_url": self._image_to_input_url(reference_image),
                        },
                    ]
                )
            for reference_image in effect.get("negative_reference_images", []):
                content.extend(
                    [
                        {
                            "type": "input_text",
                            "text": f"Negative reference image for effect {effect.get('id', '')}:",
                        },
                        {
                            "type": "input_image",
                            "image_url": self._image_to_input_url(reference_image),
                        },
                    ]
                )

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            text_format=ImageEvaluation,
        )
        if response.output_parsed is None:
            evaluation = ImageEvaluation.model_validate_json(response.output_text)
        else:
            evaluation = response.output_parsed
        evaluation.image_path = image_path
        return evaluation

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
