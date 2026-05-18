# 2026-05-17 Lightstick Prompt Tuning Log

## Goal

本轮针对 5 张主播应援棒图，优先修三个问题：

1. 背景必须是连续纯黑，不能出现白色卡片、白色圆角面板、白色地面、产品说明板或分屏图。
2. 主播名字必须进入灯头形状内部，优先放在爱心中央核心或中央横向铭牌里，不能悬浮在应援棒上方、顶部皇冠、外接 banner、手柄或底座上。
3. 构图必须是完整应援棒，灯头、连接件、完整手柄和底部节点都要入画，不能是灯头特写。

## Runs

- `outputs/history_runs/20260516-234347-minimal-csv-5x`
  - 第一轮最小 CSV 后的 5 张图，整体方向变好，但暴露出白背景、名字外置、特写裁切问题。
- `outputs/history_runs/20260516-235604-internal-nameplate-retry-5x`
  - 加强“名字进内部铭牌”后再跑；Rey 和 La Sra 方向变好，Linda 反而触发产品说明白卡。
- `outputs/history_runs/20260517-000137-no-infographic-vlm-5x`
  - 开启 VLM 验收。Linda / Potato 生成遇到 504；Rey、엘린장、La Sra 均被 VLM 判为未通过。
- `outputs/history_runs/20260517-000655-final-candidates-5x`
  - 最后一轮候选。Linda、엘린장、La Sra 明显改善；Potato 仍触发白色产品说明板；Rey 该轮 504，所以沿用上一轮较好的 Rey 图做人工候选。

## Prompt Changes Applied

- 在主 prompt 开头加入黑背景硬合同：连续纯黑空间，禁止白色页面、白色圆角面板、白色卡片、白色地面、白色台面、展示板、展示框和矩形背景。
- 将名字位置从“可读主文字”收紧为“灯头形状内部的横向一体化发光铭牌”，明确禁止放在皇冠、帽檐、翅膀、顶部装饰、灯头上方、画面外、手柄、底座或外接 banner。
- 加入完整构图约束：整支产品高度 85%-90%，底部节点下方必须有纯黑留白，禁止近景、斜向特写、只拍灯头。
- 加入反信息图约束：禁止中文说明、箭头、引线、尺寸线、旁注、标题、段落文字、产品图解或信息图。
- 保留“产品本体不要纯黑”的抠图约定：背景可黑，但棒体使用烟灰、枪灰、银灰、珠光灰、透明树脂或彩色高光。

## VLM Snapshot

VLM run: `outputs/history_runs/20260517-000137-no-infographic-vlm-5x/run_summary.md`

| Host | Score | Failure types | Key issue |
| --- | ---: | --- | --- |
| Rey Xolo | 74 | `background_fail`, `text_fail` | 背景仍像白色圆角面板，名字在顶部皇冠外接铭牌。 |
| 엘린장 | 61 | `text_fail`, `cropping_fail` | 名字是伪韩文字，底部边距太紧。 |
| La Sra. del Sombrero | 51 | `cropping_fail`, `concept_fail`, `complexity_fail` | 手柄/底部被裁，帽檐主题弱，翼形抢主视觉。 |

## Manual Review Of Final Candidates

Final run: `outputs/history_runs/20260517-000655-final-candidates-5x`

| Host | Image | Status | Notes |
| --- | --- | --- | --- |
| Linda Passarinheira | `images/001__Linda_Passarinheira_a01_1.png` | Good candidate | 黑背景、完整棒体、名字在爱心核心内；整体已经接近可看候选。 |
| TheAbandonedPotato | `images/002_TheAbandonedPotato_a01_1.png` | Fail | 仍出现白色产品说明板/中文标注倾向；Potato 这个样本最容易触发“产品图解”。 |
| Rey Xolo | `images/003_Rey_Xolo_a01_1.png` | Generation fail | 最后一轮 504；暂时参考 `outputs/history_runs/20260516-235604-internal-nameplate-retry-5x/images/003_Rey_Xolo_a01_1.png`。 |
| 엘린장 | `images/004_엘린장_a01_1.png` | Partial pass | 黑背景、完整棒体、名字在灯头内部；韩文字仍不可靠，建议后续走后置贴字。 |
| La Sra. del Sombrero | `images/005_La_Sra_del_Sombrero_a01_1.png` | Partial pass | 黑背景、完整棒体、名字在灯头内部；拼写错成 Somerro，帽子主题仍弱。 |

## Prompt Files

- Linda: `outputs/history_runs/20260517-000655-final-candidates-5x/prompts/001__Linda_Passarinheira_a01.prompt.txt`
- Potato: `outputs/history_runs/20260517-000655-final-candidates-5x/prompts/002_TheAbandonedPotato_a01.prompt.txt`
- Rey: `outputs/history_runs/20260517-000655-final-candidates-5x/prompts/003_Rey_Xolo_a01.prompt.txt`
- 엘린장: `outputs/history_runs/20260517-000655-final-candidates-5x/prompts/004_엘린장_a01.prompt.txt`
- La Sra: `outputs/history_runs/20260517-000655-final-candidates-5x/prompts/005_La_Sra_del_Sombrero_a01.prompt.txt`

## Monday Fix List

1. Prompt 语言需要降噪：当前中文长 prompt 仍会诱发中文说明/产品图解。建议把生图 prompt 改成更短的英文 slot template，只保留结构、背景、名字位置、主符号、材质和 negative list。
2. 加白板/信息图自动拒绝：生成后检测大面积白色区域、矩形卡片、中文说明文字；命中则直接判 `background_fail` 或 `infographic_fail`，不进入候选。
3. 长名字和多语言文字要分流：韩文、长英文、西语长名建议默认生成空白中央铭牌，再程序化贴字。One-shot 文字只保留短英文名。
4. Potato 需要单独降复杂度：圆润土豆 + 竞猜圆环容易被模型理解成说明图/节目卡；应改成更像“圆润吉祥物灯头”，去掉“竞猜/问答/按钮/街机”这类会诱发 UI 图解的词。
5. La Sra 需要修主题路由：当前帽檐被映射成羽翼电光，导致帽子主题弱。应新增 `hat_brim` 专用概念模板：宽帽檐弧线、帽带宝石、少量羽饰，而不是 winged heart。
6. 504 需要按行断点续跑：失败行不应影响整批验收，CLI 增加 `--start-row` 或 `--row-filter` 会更方便单条重跑。

