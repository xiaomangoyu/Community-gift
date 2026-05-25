# 社群礼物工作流 MVP

轻量链路：

```text
标准输入 CSV
  -> GPT-5.4 字段清洗
  -> GPT-5.4 提炼非人脸视觉符号
  -> 匹配 references/effects.json 里的理想效果规则
  -> GPT-5.4 结构化高级实体礼物方案
  -> 设计主概念 / 文字策略 / prompt plan 编排
  -> plan-driven Seedance 4.5 prompt
  -> Seedance 4.5 出首图
  -> 人工复看 5 张小样并记录问题
```

理想效果库里的好 prompt 和好图不直接参与生图，只参与规则推理和出图验收。
最终 prompt 默认由 template-first 规则确定性生成；旧的 LLM refiner 仅保留为手动实验开关。

当前 VLM 分两类使用：

- 上游 VLM perception：可以启用，但只允许输出事实、低层视觉元素和 lightstick 槽位，不写完整 prompt 文案。
- 下游 VLM evaluation：默认关闭。当前小样调参仍以人工复看为准；后续即使接回，也只输出失败类型和复盘信息，不能直接改写最终 prompt。

2026-05-20 的有效方向是：VLM 做短、结构化、可执行的槽位抽取；deterministic mapper / routers / template-first prompt 负责把槽位稳定装配成最终 prompt。详细复盘见 `references/20260520_vlm_slot_prompt_learnings.md`。

## 当前架构重点

工作流不再把 CSV 字段直接堆进一个大 prompt。每条主播数据会先生成三层计划：

| 层 | 输出字段 | 用途 |
| --- | --- | --- |
| 设计主概念 | `design_concept` | 只保留 1 个主符号和最多 1 个辅助符号，明确哪些字段要舍弃 |
| 文字策略 | `text_plan` | 记录 one-shot 图内文字的最终选择、来源和换字原因 |
| Prompt 计划 | `prompt_plan` | 固定摄影、产品结构、材质、保留元素、禁用元素和重试焦点 |

长主播名会先尝试使用 `主文字` / `社群名字` 作为图内文字；如果没有更短的社群文字，仍然先 one-shot 写主播名，不再默认切空白后置文字。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

把 `.env` 里的 key 和 Seedance endpoint 补好。

## CSV 字段

当前调参阶段的 CSV 只保留最少的人类设计信号。推荐字段：

```csv
主播名字,主色,辅助色,代表符号,直播氛围
```

这一层不要写 native prompt、输出类型、主体形态、材质语言、文字策略、禁用项、推荐礼物形态或长备注。当前共识是：CSV 只提供名字、颜色、元素和氛围；其他都由后续编排层和稳定 prompt 模板兜底。

### 数据表理解

当前 examples 里有两类 CSV，作用不同：

- `examples/sample.csv`：最小可运行样例。
- `examples/host_design_input_from_lark.csv`：从真实/半真实主播资料整理出的标准输入表，可以直接喂给 CLI。
- `examples/host_design_params_simplified.csv`：人工精读后的设计参数精选表，主要用于评审和挑测试样本；当前 CLI 会把它提升成标准输入形态后再运行。

`host_design_params_simplified.csv` 当前只保留这些字段：

| 字段 | 理解 |
| --- | --- |
| 主播名字 | 唯一必须稳定保留的身份字段，不在 CSV 阶段改写 |
| 主色 / 辅助色 | 只表达主播视觉色，不写材质和生图术语 |
| 代表符号 | 只保留 1-2 个自然语言元素，不写 prompt 词或复杂结构 |
| 直播氛围 | 只表达气质方向，例如甜酷、亲切、竞技、梦幻 |

当前主流程读取 `host_design_params_simplified.csv` 时只把它当作轻量 delta：

```text
主播名字 <- 主播名字
主色 <- 主色
辅助色 <- 辅助色
代表符号 <- 代表符号
直播氛围 <- 直播氛围
```

形态、材质、复杂度、禁用项、文字策略和输出类型不再由 CSV 决定。它们由 template-first 编排、效果库规则和全局产品合同兜底，避免 CSV 污染后续设计。

更细的映射和测试编排见 `references/design_mapping_orchestration.md`。

## 运行

只生成结构化方案和 prompt，不调用出图：

```bash
python -m community_gift.cli --csv examples/sample.csv --dry-run
```

没有 env 时，可以先用 mock 模式验证 CSV 和输出结构：

```bash
python -m community_gift.cli --csv examples/sample.csv --dry-run --mock
```

调用 Seedance 生成首图：

```bash
python -m community_gift.cli --csv examples/sample.csv
```

### Streamers Debug Preview

调试 `streamers/` 数据时，推荐用 debug preview 脚本。它会保留完整中间产物，并额外生成两张 contact sheet：

- `contact_sheet.jpg`：纯图预览。
- `contact_sheet_debug.jpg`：图片 + reference 命中、score、fallback、matched tags。

常用命令：

```bash
python3 scripts/run_streamers_debug_preview.py --start 0 --count 15
python3 scripts/run_streamers_debug_preview.py --start 15 --count 15
```

输出目录默认形如：

```text
outputs/preview_debug_<timestamp>_s<start>_n<count>/
  contact_sheet.jpg
  contact_sheet_debug.jpg
  route_summary.json
  routing_trace.json
  payloads/
  host_briefs/
  host_visions/
  debug_cards/
```

只验证路由和中间 JSON、不调用生图接口：

```bash
python3 scripts/run_streamers_debug_preview.py --start 0 --count 5 --dry-run
```

默认图片 provider 是 Seedream 4.5 HTTP：

```env
IMAGE_PROVIDER=seedream_http
GENERATION_CONCURRENCY=100
ENABLE_VLM_EVALUATION=false
EXPERIMENTAL_ENABLE_PROMPT_REFINER=false
```

主工作流已硬固定为 `seedream_http` / Seedream 4.5：不会使用 Grok，也不会因为 `SEEDANCE_API_KEY` / `SEEDANCE_BASE_URL` 存在而切到旧 Seedance 网关。`--image-provider` 只接受 `seedream_http`、`seedream`、`seedance` 这些别名。

`GENERATION_CONCURRENCY` 控制按行并发生成和评估的上限；小批量测试时 5 行会同时发起，不再一张一张排队。也可以临时覆盖：
VLM 审核默认关闭；当前小样调参不建议开启。只有后续需要批量质检时，才显式传 `--evaluate-images` 或设置 `ENABLE_VLM_EVALUATION=true`。
默认编排方式是 template-first：不让 LLM 从主播数据重新设计 prompt，而是使用稳定参考 prompt 骨架，只填入少量主播变量。最终 prompt 不再默认交给 LLM 自由重写；`routing_trace.json` / `debug_cards/` 会记录 deterministic prompt lint，用于检查 exact text、中文主题词引号、否定句过多、招牌/铭牌类危险词和硬产品锚点。旧的 final LLM refiner 已移出主流，只保留为显式实验开关；需要单独传入 `prompt_refiner_client` 并设置 `EXPERIMENTAL_ENABLE_PROMPT_REFINER=true` 才会尝试启用。

```bash
python -m community_gift.cli \
  --csv examples/sample.csv \
  --generation-concurrency 100
```

主工作流图片约定为 `1:1` 正方形，默认 `2048x2048`，用于减少产品细节和文字区域发糊。若需要快速小样，可临时降到 `1024x1024`。如需显式指定：

```bash
python -m community_gift.cli \
  --csv examples/sample.csv \
  --image-size 2048x2048
```

不要在主工作流里使用 `1024x1792` 这类竖图比例；竖图只适合旧 reference 单项测试，不适合作为主播礼物历史数据。

### Reference 路由和 tag 兜底

reference image 的选择是一个本地 deterministic 节点，不依赖线上模型。主链路是：

```text
HostInput / VLM vision
  -> HostBrief tags
  -> RetrievalIntent anchors
  -> tag_aliases.yaml 归一化和父级扩展
  -> ReferenceRouter 加权精确匹配
  -> top-N reference image + role_description
```

相关文件：

- `references/imgs/manifest.yaml`：reference 入库清单，决定每张图的 canonical tags、图片、prompt 和 `role_description`。
- `references/imgs/TAG_VOCAB.md`：canonical tag 词表。新增 manifest tag 时优先从这里选。
- `references/imgs/tag_aliases.yaml`：同义词和父级兜底。比如 `bunny -> rabbit`，`basketball -> sport_ball -> sport`。
- `community_gift/routing/tag_normalizer.py`：加载 `tag_aliases.yaml`，在 router 打分前同时处理主播 tags 和 manifest tags。
- `community_gift/routing/reference_router.py`：仍然只做精确交集打分；兜底层只改变进入打分的 tag 集合，不改 prompt、不改图片、不调用网络。

维护原则：

- manifest 里尽量写干净的 canonical tags，不要为每张图重复塞大量同义词。
- 新增高频别名、中文词、模型可能吐出的近义词时，优先改 `tag_aliases.yaml`。
- 新增大类兜底时要保守：适合 `rabbit -> animal`、`basketball -> sport_ball` 这种稳定父级；不要把主观风格随意互相映射。
- 排查错配时先看 `outputs/.../contact_sheet_debug.jpg` 和 `routing_trace.json` 里的 `matched_tags` / `score`，再决定是补 manifest tag 还是补 alias。
- 云端服务如果长进程常驻，更新 `tag_aliases.yaml` / `manifest.yaml` 后需要重启进程，让本地 YAML 配置重新加载。

### 抠图颜色约定

主流程可以继续使用纯黑背景，但产品本体不能再使用纯黑作为大面积主色。即使主播字段里写了黑色、黑鸟、glossy black resin，也只作为主题语义处理，实际产品外壳、手柄、轮廓和大面积装饰必须转成烟灰、枪灰、银灰、珠光灰、奶油白或彩色树脂，并保留清楚的灰/银/彩色边缘高光，方便后续从黑底抠图。

### 文字约定

图片里的文字是硬约束。当前策略是：

- 当前已调整为：图内唯一保真文字优先取 `主播名字` 的可读文本版；`主文字` / `社群名字` 仍用于设计语义和备选。
- 不让模型自由生成主播签名、副文字、口号或装饰性小字。
- 当前主流程默认 `one_shot_text`：唯一文字必须放在灯头中央发光核心或中央嵌入铭牌里，水平、居中、清晰。
- 长主播名优先替换成 `主文字` / `社群名字`；没有可用社群文字时仍先写主播名，避免首轮小样变成无字空白核心。
- 手柄必须无字；手柄只承接材质、握持结构和无字装饰，不能出现主播名、缩写、竖排字、斜排字或伪字母。
- one-shot 模式下中央核心 / 铭牌不能留空；post-overlay 模式下中央核心 / 铭牌必须保持干净空白，等待后置文字层。
- 当前不依赖 VLM 判定文字失败；人工复看时如果发现错拼、乱码、乱字或文字位置跑偏，下一轮直接切到 `post_overlay_text`。

输出目录默认是 `outputs/`：

- `structured_designs.csv`
- `structured_designs.json`，包含 `design_concept`、`text_plan`、`prompt_plan`
- 每条数据的出图结果，按行号和主播名保存
- `generation_results.json`，包含候选图路径、生成状态和最佳图路径；开启 VLM 时才会包含评分和失败类型

## 理想效果库

资料放在 `references/`：

```text
references/
  effects.json          # 工作流读取的结构化效果卡片
  effects.template.json # 单条卡片模板
  images/               # 已验证好图
  raw_prompts/          # 原始好 prompt 暂存
```

先把好图放进 `references/images/`，把原始好 prompt 放进
`references/raw_prompts/`，再按 `effects.template.json` 的格式整理到
`references/effects.json`。

如果要指定另一个效果库：

```bash
python -m community_gift.cli --csv examples/sample.csv --effect-library references/effects.json
```

## Reference 效果测试

当前阶段可以先不接主播信息，直接测试某条好 prompt 能不能稳定生成
reference image 里的 Strong 应援棒产品效果：

```bash
python3 scripts/run_reference_effect_test.py --list
python3 scripts/run_reference_effect_test.py \
  --entry 4 \
  --provider seedream_http \
  --size 1024x1792 \
  --english-only
```

输出会保存到 `outputs/reference_tests/`，包含：

- `prompt.txt`
- `negative_prompt.txt`
- 生成图片
- provider raw response

后续需要批量质检时，可以再用 VLM 对比 Strong/Weak reference：

```bash
python3 scripts/evaluate_reference_effect.py outputs/reference_tests/.../entry_04_attempt_01_1.png
```

`references/effects.json` 里目前把 `20260515-204404.jpeg` 和
`20260515-204447.jpeg` 作为正向 Strong reference，把
`20260515-204516.jpeg` 作为 Weak 反例。
