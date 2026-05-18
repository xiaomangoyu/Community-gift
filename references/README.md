# 理想效果库使用说明

这个目录存放“被验证过的好效果”。它们不直接参与生图，而是参与两件事：

1. 推理：把好 prompt 和好图提炼成效果规则，指导新 prompt 的生成。
2. 复盘：人工对比新生成图和参考图，判断是否接近理想状态。

当前主工作流在读取效果库后，还会生成三层中间计划：

- `design_concept`：先决定主设计命题，只保留 1 个主符号和最多 1 个辅助符号。
- `text_plan`：判断文字由图像模型 one-shot 生成，还是先留空白铭牌后续程序化覆盖。
- `prompt_plan`：把摄影合同、产品结构、材质、保留元素、禁用元素和重试焦点结构化。

因此，效果库不应该继续沉淀“超长 prompt”。更有价值的是沉淀能进入这些计划层的规则：主体轮廓、材质气质、构图边界、强/弱反例和人工复看关注点。

## 当前新方向

后续用户会提供几条“底层好 prompt”。这些 prompt 是工作流的主干参考。

整理它们时，目标不是提炼几个松散关键词，而是还原它们为什么稳定：

- 段落顺序
- 摄影合同写法
- 产品骨架写法
- 材质公式
- 复杂度控制方式
- 负面约束位置
- 哪些句子需要重复强调
- 哪些变量槽位可以替换

主播数据只填少量槽位。宁愿少用主播字段，也要让最终 prompt 的结构、语气和节奏接近这些好 prompt。

VLM 审核当前默认关闭；pass / not pass 暂时由人工复盘后定义。等人工标准稳定后，VLM 可以作为批量质检和失败类型分类的辅助模块再接回。

## 推荐目录

```text
references/
  20260516_design_review.md # 当天设计工作流复盘和下一步判断
  effects.json          # 结构化后的理想效果卡片，工作流会读取这里
  effects.template.json # 单条效果卡片模板
  color_palettes.json   # 产品安全颜色库：main_color + palette
  images/               # 放已经验证过的好图
  raw_prompts/          # 临时放原始好 prompt，方便之后结构化
```

## 你给资料时的最小格式

每个好效果尽量给三样东西：

```text
1. 好图：放到 references/images/
2. 好 prompt：放到 references/raw_prompts/
3. 你觉得它为什么好：一句话也可以
```

例如：

```text
图片：references/images/acrylic_charm_01.png
prompt：references/raw_prompts/acrylic_charm_01.txt
为什么好：实体感强，透明材质高级，小尺寸也能看清主体。
```

之后再把它整理成 `effects.json` 里的效果卡片。

## 重要原则

- `source_prompt` 只保留做溯源，不会直接拼进新生图 prompt。
- `color_palettes.json` 用来把 CSV 颜色扩展成稳定产品配色；每个条目同时包含 `main_color` 和 `palette`。
- `reference_images` 当前主要给人工复盘看，不作为 Seedance 的参考图输入。
- 生图阶段只使用 `core_effect`、`composition_rules`、`material_rules`、`prompt_principles`、`avoid` 这些结构化规则。
- 长名字、多语言和复杂标点默认不要求图像模型拼字；理想效果应优先支持“空白中央铭牌 / 发光核心”的产品结构。
- 人工复看阶段先看方向、构图、完整性、文字、颜色和实体产品感；VLM 重新接回后再使用 `failure_types`：`cropping_fail`、`text_fail`、`concept_fail`、`complexity_fail`、`product_form_fail`、`material_fail`。
