from __future__ import annotations

import base64
import json
import mimetypes
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


class GiftOpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is missing.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

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
