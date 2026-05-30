# jbook-engine

出版社引擎——把 `course.yml` + markdown 章节编译成"日本科普书风格"静态网站。

**不包含任何书的内容**，只提供模板、样式和编译工具。

每本书是一个独立仓库，以 git submodule 方式引用本引擎。

## 使用

```bash
# 在书仓库中
git submodule add git@github.com:HedgeSage/jbook-engine.git engine
python3 engine/build.py    # 输出到 site/
python3 engine/svg_lint.py # SVG 质量检查
```

## 目录

```
engine/
├─ build.py           # 编译入口
├─ svg_lint.py        # SVG 几何质检
├─ templates/         # Jinja2 模板
│  ├─ chapter.html
│  ├─ module.html
│  ├─ index.html
│  ├─ concepts.html
│  ├─ source-map.html
│  └─ sidebar.html
styles.css            # 视觉系统
FORMAT.md             # 内容格式规范
```
