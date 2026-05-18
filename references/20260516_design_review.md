# 2026-05-16 设计工作流复盘

## 总体判断

今天的结论比较明确：流程方向基本成立，但视觉效果还没有达到可用标准。

现在的问题不是“链路跑不通”，而是“设计语言还不够高级”。主播名字仍然不够清楚，文字位置也经常不对；同时字段映射太直接，像是在把 CSV 里的符号逐个塞进画面，而不是先形成一个有设计感的主概念。

更重要的一条原则是：选项只是辅助判断，不是画面元素清单。效果好时，模型可以少用字段；字段应该帮助判断主方向，而不是要求每个符号都出现。

## 今天做了什么

| 模块 | 已完成 | 当前价值 |
| --- | --- | --- |
| CSV 字段边界 | `host_design_params_simplified.csv` 只保留名字、颜色、元素和氛围 | 避免 CSV 变成半条 prompt 污染设计 |
| 主工作流比例 | 强制主流程使用 `1:1`；当天历史图为 `1024x1024`，下一轮默认提升到 `2048x2048` | 历史数据和产品图规格统一，同时降低发糊风险 |
| 主播名策略 | 图内唯一保真文字优先取主播名，去掉 emoji 和装饰符号 | 比使用社群名更贴近业务重点 |
| 无手柄文字约束 | 明确要求手柄无字，文字只能在灯头中央核心 / 中央铭牌 | 修正上一轮文字跑到手柄上的大问题 |
| 人工验收 | 当前先不用 VLM，改为人工复看每轮 5 张小样 | 方向、构图、文字、颜色问题肉眼更可靠 |
| 生成容错 | 单条生图失败应记录为失败项，不中断整批 | 批量跑图更稳定 |
| Lark 历史记录 | 已验证可以把图片 URL、CSV URL、运行目录 URL 写入 Base | 后续可以沉淀历史数据 |

## 今日跑图记录

| 轮次 | 输出目录 | 目的 | 结果 |
| --- | --- | --- | --- |
| `20260516-high-confidence-v1` | `outputs/history_runs/20260516-high-confidence-v1` | 高置信样本首轮 | 竖图比例不适合主流程，文字也不稳定 |
| `20260516-square-text-first-v1` | `outputs/history_runs/20260516-square-text-first-v1` | 测试主播名放 prompt 最前 | 文字权重提升，但仍混入旧设计字段里的额外文字 |
| `20260516-square-text-first-clean-v1` | `outputs/history_runs/20260516-square-text-first-clean-v1` | 清掉额外文字后再测 | `1:1` 成立，短名字较好，长名字仍易错拼 |
| `20260516-no-handle-text-v2` | `outputs/history_runs/20260516-no-handle-text-v2` | 强化“中央铭牌文字、手柄无字” | 5 张都生成成功，尺寸正确，但视觉效果未过线 |
| `20260516-2048-seedream-smoke-v1` | `outputs/history_runs/20260516-2048-seedream-smoke-v1` | 验证 `2048x2048` 高分辨率出图 | 实际输出 2048 正方形，但设计和文字位置仍未过线 |
| `20260516-232257-seedream-v2-name-anchor-5x` | `outputs/history_runs/20260516-232257-seedream-v2-name-anchor-5x` | 验证 v2 好 prompt 母版 + 主播名上方铭牌 + 元素/配色落位 | 批次未完整完成；第 1 条成功出图，第 4/5 条 Seedream 下游连接失败，第 2/3 条因批次中断未落图 |

## 2026-05-16 晚间更新：工作流收紧记录

### 最新验收决策：当前先不用 VLM

当前阶段先关闭 VLM 自动审核和自动重试。原因是本轮问题已经非常直观：画幅跑成横图、主体斜摆、握柄贴边、文字被直接烙进图里、黑色主体不利于抠图。这些问题用人工复看 5 张小样更快，也更符合真实审美判断。

当前验收流程改为：

```text
每轮生成 5 张
记录 prompt / raw response / 图片
人工复看方向是否正确
按共性问题改 prompt 模板或工作流
必要时再跑下一轮
```

VLM 暂时只作为未来批量阶段的可选模块。等人工 pass / not pass 标准稳定后，再把它接回去做批量筛图、失败类型分类和自动复盘，不在当前 prompt 调参阶段承担决策。

### 最新数据决策：CSV 只保留低污染信号

当前阶段不再把 `host_design_params_simplified.csv` 当作完整设计 brief。CSV 只保留：

```text
主播名字
主色 / 辅助色
代表符号
直播氛围
```

其他内容，包括输出类型、主体形态、材质语言、装饰强度、禁用项、映射理由、native prompt 和英文生图短语，都不在这个阶段读取。它们由后续编排层和全局 prompt 合同兜底。

原因是 CSV 一旦混入半成品 prompt，就会把下游设计污染成字段拼接。当前目标是让 CSV 提供干净差异化信号，让编排层负责取舍和产品化。

### 已改动

| 模块 | 改动 | 目的 |
| --- | --- | --- |
| 好 prompt 库 | `references/raw_prompts/prompt_inbox.md` 重写为 v2：母版、槽位、8 个风格卡、负面约束池 | 不再堆长 prompt，让好 prompt 成为可复用结构 |
| 效果库 | `references/effects.json` 改为 `heart_lightstick_prompt_library_v2`，并清空 `reference_images` | 避免 reference image 被误认为会进生图；只保留结构化规则 |
| 默认编排 | `community_gift/template_first.py` 改为 template-first 风格卡写法 | 让最终 prompt 结构和语气更接近 8 条好 prompt |
| 图像通道 | `community_gift/clients/image_client.py` 硬锁 `seedream_http`，Grok provider 直接报错 | 禁止跑偏到 Grok |
| 旧网关 | 删除 `community_gift/clients/seedance_client.py`，CLI 不再读取 `SEEDANCE_API_KEY / SEEDANCE_BASE_URL` 切旧网关 | 主流程固定 Seedream HTTP / Seedream 4.5 |
| 主播名落位 | `TextRenderPlan.mode` 从 `post_overlay_text` 改为 `one_shot_text` | 要求主播名直接出现在应援棒上方中间 |
| 主播元素/配色落位 | prompt 中新增“主播信息落位检查”段落 | 保证至少 1 个主播元素 + 1 组主播配色呼应到棒体 |

### 新共识

```text
好 prompt 母版结构仍然最高优先级。
但每条最终 prompt 必须完成三个落位：
1. 主播名字在应援棒上方中间的一体化发光主铭牌。
2. 至少一个主播元素落到棒体结构上。
3. 至少一组主播配色落到棒体材质 / 外壳 / 核心 / 包边 / 手柄 / 底座上。
```

这些共识已同步到：

- `references/design_mapping_orchestration.md`
- `references/raw_prompts/prompt_inbox.md`
- `references/effects.json`
- `community_gift/template_first.py`

### 本轮生图结果

运行目录：

```text
outputs/history_runs/20260516-232257-seedream-v2-name-anchor-5x
```

命令意图：

```text
max rows: 5
generation attempts: 1
generation concurrency: 5
image size: 2048x2048
VLM: off
provider: seedream_http / general_v4.5
reference image: none
```

实际结果：

| Row | 状态 | 文件 |
| --- | --- | --- |
| 1 Linda Passarinheira | 成功出图 | `images/001__Linda_Passarinheira_a01_1.png` |
| 2 TheAbandonedPotato | 已写 prompt，未落图 | `prompts/002_TheAbandonedPotato_a01.prompt.txt` |
| 3 Rey Xolo | 已写 prompt，未落图 | `prompts/003_Rey_Xolo_a01.prompt.txt` |
| 4 엘린장 | raw 返回下游连接失败，无图 | `images/004_엘린장_a01.seedream_http.json` |
| 5 La Sra. del Sombrero | raw 返回下游连接失败，无图，批次中断 | `images/005_La_Sra_del_Sombrero_a01.seedream_http.json` |

失败原因不是编排层异常，而是 Seedream 下游连接问题。raw 中关键信息：

```text
algo_status_code=110001
message="Couldn't process image. Try again later."
gateway_code=11101
Downstream Req Con Failed
POOL_FAILURE_RemoteConnectionFailure
```

### 后续处理建议

这轮先不要据此判断 prompt 好坏，因为只有第 1 张真正落图。下一步应该补跑失败项，建议：

```text
先用同一 run 的 prompts 补跑 2-5；
或者重新跑 5 张，但把接口重试次数提高到 3-4，并让单条失败不要中断整批。
```

代码层可改进：

- `generate_images` 不应因单条失败直接 raise 导致整批中断。
- `generation_results.json` 应记录 partial success / failed rows。
- 对 `algo_status_code=110001`、`gateway_code=11101` 这类网关失败做更明确重试。

## 5 张样本结果

| 样本 | 图像 | 分数 / 状态 | 主要问题 |
| --- | --- | --- | --- |
| Linda Passarinheira | `001__Linda_Passarinheira_a01_1.png` | 评估 JSON 失败 | 需要人工复看；本轮评估未能稳定返回结构化结果 |
| TheAbandonedPotato | `002_TheAbandonedPotato_a01_1.png` | 54 | 底部裁切，文字像贴在斜向 banner 上，复杂度高 |
| Rey Xolo | `003_Rey_Xolo_a01_1.png` | 62 | 中央文字稍好，但核心/铭牌结构不够明确，元素太多 |
| 엘린장 | `004_엘린장_a01_1.png` | 39 | 文字错误且位置错误，中央最大核心留空 |
| La Sra. del Sombrero | `005_La_Sra_del_Sombrero_a01_1.png` | 53 | 长名字不够稳，帽子/公鸡过于具象，缺少高级抽象 |

本轮所有图片尺寸均为 `1024x1024`；后续主流程默认提升到 `2048x2048`。

补充验证：`20260516-2048-seedream-smoke-v1` 已确认能输出 `2048x2048`。这能缓解发糊问题，但不能自动修复构型和文字位置问题。

## 做得好的

| 方向 | 说明 |
| --- | --- |
| 流程闭环 | 从 CSV 到设计、prompt、生图、评估、历史数据，链路基本通了 |
| 约束逐步清晰 | 比例、黑底、单支完整、主播名优先、手柄无字这些硬规则已经明确 |
| 问题暴露速度变快 | 5 张小样已经能快速暴露文字、裁切、复杂度、实体感等共性问题 |
| 文档沉淀有效 | README 和映射文档已经能说明当前工作流的基本假设 |

## 做得不好的

| 问题 | 表现 | 判断 |
| --- | --- | --- |
| 主播名不够可靠 | 长名字错拼、断行不稳、韩文乱码、位置跑偏 | one-shot 仍无法保证文字 100% 正确 |
| 文字位置不够产品化 | 文字出现在 banner、小牌、发光面表层，而不是稳定的中央核心铭牌 | prompt 约束有帮助，但模型执行不稳定 |
| 映射太直接 | 黑鸟、土豆、皇冠、狗、帽子、公鸡等容易被直接画成元素堆叠 | 需要先做设计综合，不应逐项入画 |
| 元素过多 | 每张都想表达 3-5 个符号，导致玩具感、徽章感、贴纸感变强 | 应减少元素，先保证一个主轮廓 |
| 高级感不足 | 有些图像偏 mascot、摆件、海报糖果感，不像收藏级应援棒 | 需要更强的 art direction，而不只是字段拼接 |
| 自动评估链路暂不适合当前阶段 | VLM 容易把自动重试带偏，且会增加排查噪音 | 当前关闭，先用人工复看定义 pass / not pass |

## 思维导图

```text
社群礼物工作流
├─ 已经成立的流程
│  ├─ 人工精读 CSV
│  ├─ 结构化设计字段
│  ├─ 1:1 生图
│  ├─ 人工复看 5 张小样
│  └─ Lark 历史数据
├─ 当前最大缺口
│  ├─ 名字不够清楚
│  ├─ 名字位置不够稳定
│  ├─ 符号映射太直译
│  └─ 画面缺少统一设计概念
├─ 新原则
│  ├─ 选项是判断辅助，不是画面清单
│  ├─ 每张图只保留一个主设计命题
│  ├─ 主符号决定轮廓，辅助符号只做材质或小结构
│  ├─ 先要高级产品感，再要符号覆盖率
│  └─ 文字必须服务产品结构，不做装饰性冒险
└─ 下一步方向
   ├─ 少元素强概念
   ├─ 先生成更好的无字产品结构
   ├─ 文字继续 one-shot 小样测试
   └─ 长名字保留程序化后置方案
```

## 下一步建议

| 方向 | 做法 |
| --- | --- |
| 设计编排 | 每个主播只选 `1 个主概念 + 1 个辅助气质`，不要把所有字段都塞进 prompt |
| 映射重写 | 把 `symbols` 从“必须出现”改成“可选设计灵感”，只让主符号塑造轮廓 |
| prompt 简化 | prompt 先写产品形态、主轮廓、材质，再写少量主题，不再列长元素清单 |
| 文字策略 | 短名字继续 one-shot；长名字、韩文、多标点名字优先考虑后置文字层 |
| 评估标准 | 效果评价应优先看产品设计感、文字正确、中央铭牌、完整轮廓，而不是字段覆盖率 |

## 当前结论

今天是有效推进：流程已经可以作为实验平台，但设计目标需要从“字段映射生成图”升级为“字段辅助做设计决策”。下一轮不应该继续增加约束，而应该减少画面负担，让模型先做出一个更像高级实体礼物的主设计。
