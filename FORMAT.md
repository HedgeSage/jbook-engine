# jbook Format Specification v1

Jbook 内容格式规范——定义 `course.yml` 和章节 markdown 的结构，供 /jbook 指令和 build 引擎使用。

## 目录结构

```
book/
├─ engine/          ← git submodule: jbook-engine
├─ content/
│  ├─ course.yml    ← 课程元信息
│  ├─ index.md      ← 首页（story map, lenses）
│  └─ chapters/
│     ├─ 00-1.md
│     ├─ 00-2.md
│     └─ ...
├─ assets/          ← 书级自定义（覆盖引擎默认值）
└─ site/            ← 构建输出（不手动编辑）
```

## course.yml

```yaml
course:
  title: "金融世界是怎样运转的"
  subtitle: "跟着一家面包店，看懂金融世界的运转"
  modules:
    - id: "01"
      title: "模块中文标题"
      slug: "english-slug"
      hero: "一句话概括这个模块要解决什么问题"
      chapters:
        - id: "01-1"
          title: "章节中文标题"
          slug: "chapter-slug"
          concepts:
            - {name: "概念名", en: "English", desc: "一句话解释"}
          components:             # 可选：控制章节渲染哪些部分
            - story
            - exploded_view
            - step_by_step
            - try
            - pitfalls
            - takeaways
            - map
            - forward_hook
        - id: "01-2"
          ...
```

- `id`: 编号，决定编排顺序
- `slug`: URL 安全标识符
- `components`: 不写则全部渲染

## 章节 Markdown（每章一个文件）

### 必选字段

```markdown
## Scene
（故事场景：150-250 字，用具体人物和情境引入本章主题。每本书独立设计叙事，不得跨书复用角色。角色和场景由本书内容决定，不预设固定主角）
```

### 可选字段（由 course.yml components 控制）

```markdown
## Diagram
（SVG 插图——机制拆解图，遵守 SVG 绘制规则）

## Steps
- 步骤一
- 步骤二
（3-7 条，概括本章核心逻辑链条）

## Explanations
### 01 · 小标题
（第一层解释：用比喻和故事引出概念，不超过 3 段）

### 02 · 小标题
（第二层解释：展开机制，可含数学公式但始终绑在故事上）

### 03 · 小标题
（第三层解释：深层含义，连接前后章节）

## Try
### 思维实验标题
（引导读者主动思考的问题或小练习）

## Pitfalls
### 误区标题
（常见误解 + 纠正，1-3 个）

## Takeaways
1. 要点一
2. 要点二
3. 要点三
（3-5 条精炼总结）

## Map
（在全书结构中的位置标记）

## ForwardHook
（向下一章的过渡句，1-2 句话）
```

## 写作风格

- **日本机制拆解科普书风格**：教育性但不学术，像《如果高中棒球社女经理读了德鲁克》
- **对话感**：像在跟读者讲一个有意思的事，而非上课
- **故事贯穿**：用具体人物和具体情境锚定抽象概念。每本书设计独立叙事——独立角色、独立世界观，不跨书混用
- **中文流畅**：不直接翻译英文术语，用直觉类比

## SVG 绘制规则

所有 SVG 插图遵守以下规则：

1. **方向线**：实线 1.5px + `marker-end` 箭头
2. **主题线**：虚线 ≤1px，无箭头
3. **线条不穿过方框**：连接线端点止于方框边缘，间隔 ≥10px
4. **连接线抵达目标**：箭头尖端触及目标框边缘，间隙 ≤5px
5. **viewBox 覆盖**：覆盖所有元素并预留 5% 边界缓冲

线条不要穿过方框内部（除非是图表内有意为之的数据线或分隔线）。

## 首页 index.md

```markdown
## Overview
（课程总览，3-5 段，解释本书的编排逻辑和目标读者）

## StoryFlow
（故事线概览，说明本书角色如何贯穿全书。每本书使用独立角色和世界观，不与 jbook 系列其他书籍共享叙事）

## Lenses
### 📊 现金流视角
（说明本视角看什么）

### ⚠️ 风险视角
（说明本视角看什么）

### 🧠 决策视角
（说明本视角看什么）
```

三个 Lenses 对应三种阅读路径，分别用 `cash`、`risk`、`decision` 主题色。

## 构建

```bash
cd book/
python3 engine/build.py
# 输出到 site/
```
