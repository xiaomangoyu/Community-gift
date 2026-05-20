# 2026-05-20 VLM 槽位化 Prompt 复盘

这轮 1-5 小样明显变好，核心变化不是让模型写得更华丽，而是把每个节点的职责切清楚。

## 本轮有效经验

### 1. VLM 不适合写最终 prompt

之前 VLM 被要求像参考 prompt 一样写完整 brief，容易把自己变成“设计文案生成器”：

- 输出很多抽象气质词，例如社群凝聚、守护感、记忆延展。
- 倾向写标题、招牌、标识、wordmark 一类高风险词。
- 把参考 prompt 的文风学走，但没有稳定继承产品骨架。
- 给下游带来噪音，最终 prompt 和 reference prompt 的结构越走越远。

更好的用法是让 VLM 只做 perception：

```text
看到了什么低层视觉事实
哪些可以变成灯头轮廓
哪些只能做边缘件 / 浮雕 / 握柄压纹
主色和辅助色是什么
哪些元素应该舍弃
```

### 2. 最终 prompt 要 template-first

最终 prompt 的稳定性来自固定骨架，而不是每次重新发挥：

```text
黑底产品摄影合同
完整单支应援棒
灯头 / 中央核心 / 连接件 / 手柄 / 底盖
唯一 exact text
主题元素长在棒体结构上
材质和颜色按产品槽位落地
prompt lint 检查风险词
```

主播信息、VLM 观察和 reference 命中都只作为 delta 填槽。宁愿少用几个元素，也不要破坏好 prompt 的段落顺序和产品合同。

### 3. LLM refiner 暂时没有必要默认开启

final LLM refiner 的收益是让语言更自然，但风险更大：

- 容易新增没授权的文字。
- 容易把“中文主题词”写成画面里的可见字。
- 容易把结构化槽位重新散文化。
- 会让 prompt lint 变成擦屁股，而不是前置约束。

当前更稳的策略是默认关闭 refiner，并移出主流入口。需要润色时，也应该作为显式实验路径，限制为“不改槽位、不改 exact text、不新增画面文字、不改产品结构”的轻量 smoothing。

### 4. Prompt 变短不是目的，变干净才是目的

这轮变好的原因不是单纯缩短，而是减少了三类污染：

- 抽象社群口号污染。
- 标识 / 铭牌 / 招牌类文字风险污染。
- VLM 长文风对最终模板的结构污染。

理想 prompt 可以保持参考 prompt 的中文审美密度，但每句话都要服务于产品结构、材质、颜色、构图或 exact text。

## 当前推荐链路

```text
streamer signals
  -> VLM perception JSON
  -> deterministic mapper
  -> color / shape / reference routers
  -> template-first final prompt
  -> prompt lint
  -> Seedream image
  -> human review contact sheet
```

### VLM perception JSON

只输出事实和低层视觉元素：

- `primary_symbol`
- `secondary_symbol`
- `style_pitch`
- `theme_forms`
- `material_cues`
- `color_cues`
- `handle`
- `avoid`

其中 `style_pitch` 只能是短标签，例如“电紫渡鸦利落风”，不能变成一整段设计文案。

### Deterministic mapper

把 VLM 元素映射到固定产品槽位：

- 主符号优先成为灯头轮廓。
- 辅助符号只能进入边缘件、浮雕、晶体节点、握柄压纹或底盖徽章。
- 颜色必须落在外壳、核心、包边、手柄或底部节点。
- exact text 只出现在灯头中央核心。

### Prompt lint

继续检查：

- exact text 是否唯一。
- 是否出现非 exact 的中文引号内容。
- 是否出现招牌、标题、标识、logo、wordmark 等风险词。
- 是否过度否定。
- 是否缺少应援棒硬锚点。

## 下一步判断标准

如果后续继续变好，说明 VLM 槽位化方向成立；下一刀应该继续优化 mapper 和 lint，而不是恢复 final LLM 自由润色。

如果后续又退化，优先排查：

1. VLM 是否又输出了完整文案。
2. `fusion_note` / `style_pitch` 是否被原样塞进最终 prompt。
3. reference router 是否命中太弱或 fallback 太泛。
4. prompt 是否新增了非 exact text 的可见文字暗示。
5. 主符号是否没有落到灯头结构，只停留在气质描述里。
