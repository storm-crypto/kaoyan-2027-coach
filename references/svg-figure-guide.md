# SVG 配图参考

错题卡里的图不是插画，是**决策载体**。它存在的唯一理由是：这道题的关键信息是空间的 / 结构的 / 时序的，用文字加 LaTeX 说清楚要绕一大圈，画出来一眼就懂。

调用 `create_figure.py` 之前先读这份文件，取对应骨架改，不要从零手搓。

---

## 0. 决策门：先问该不该画

按顺序问三句，任何一句答"不"就别画：

1. 这张图承载的信息，用两行文字说得清楚吗？说得清楚 → **不画**。
2. 图上的每个元素都来自题面给定量或已推出的量吗？有臆造 → **不画**（或只画确定的部分）。
3. 删掉这张图，`规范解法` 还完整吗？完整且不损失理解 → **不画**。

**判据一句话：如果这张图删掉，解释力没有损失，就不该画。**

纯代数变形题、纯概念辨析题、题面已给图且无新增信息的题，一律不画。

---

## 1. 硬性技术约束（`create_figure.py` 会逐条校验）

Obsidian 把 `.svg` 当 `<img>` 加载，这决定了一切限制：

| 约束 | 原因 |
|------|------|
| 必须有 `viewBox` | 没有它缩放行为不可控，图会被裁 |
| 禁止 `<foreignObject>` | `<img>` 渲染路径下整块不显示，是"图是空白"的头号原因 |
| 禁止 `<script>`、`on*=` 事件属性 | 不执行，且是安全面 |
| 禁止任何 `http(s)://` 外链、`@import` | 外部图片/字体/样式一律加载不出来 |
| 禁止 `<image>`（嵌位图） | 嵌位图就失去矢量图的意义 |
| `font-family` 必须带 `sans-serif` / `serif` / `monospace` 兜底 | 换设备不掉字 |
| 字号 ≥ 12px | 图在卡片里缩到 480px 宽，10px 会糊 |
| 文本必须是 Unicode，不能是 LaTeX | SVG 不渲染公式；`$x^2$` 会被脚本自动转成 `x²`，但复杂式子请自己写好 |
| 必须内嵌 `prefers-color-scheme` 深色适配 | 否则夜里打开是一片黑底黑线 |
| **上色写成「字面色属性 + CSS 类覆盖」双层，禁止 `fill="var(--x)"`** | 不支持 CSS 变量的渲染器会判定整个属性无效，fill 回落成黑、stroke 回落成无，整张图变黑块 |
| ≤ 32KB（>8KB 会告警） | 图太复杂说明它在替解法讲话，该拆 |

---

## 2. 通用骨架（所有图从这里开始）

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 320" role="img" aria-label="一句话说明这张图画的是什么">
  <style>
    :root{
      --ink:#1f2933;      /* 主线条、文字 */
      --bg:#fdfdfb;       /* 画布底色 */
      --accent:#2f6f9f;   /* 主角：本题的关键对象 */
      --accent2:#b3541e;  /* 对照：容易混淆的那个对象 */
      --fill:#2f6f9f2e;   /* 区域填充（带透明度） */
      --grid:#9aa5b1;     /* 辅助线、网格、刻度 */
    }
    @media (prefers-color-scheme: dark){
      :root{
        --ink:#e6e8eb; --bg:#1e1f22; --accent:#7fb3d5;
        --accent2:#e8955c; --fill:#7fb3d533; --grid:#5c6670;
      }
    }
    text{font-family:-apple-system,"PingFang SC","Microsoft YaHei",Arial,sans-serif;font-size:14px}
    /* 这些类只负责「在支持 CSS 变量的环境里把字面色换成主题色」 */
    .bg{fill:var(--bg)}
    .ink{fill:var(--ink)}
    .label{font-size:13px;fill:var(--grid)}
    .axis{stroke:var(--ink)}
    .curve{stroke:var(--accent)}
    .curve2{stroke:var(--accent2)}
    .dash{stroke:var(--grid)}
    .region{fill:var(--fill);stroke:var(--accent)}
    .box{stroke:var(--ink)}
    .curve-label{fill:var(--accent)}
    .curve2-label{fill:var(--accent2)}
    .hollow{fill:var(--bg);stroke:var(--accent)}
    .solid{fill:var(--accent)}
    .range{stroke:var(--accent)}
  </style>
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path class="ink" d="M0 0 L10 5 L0 10 z" fill="#1f2933"/>
    </marker>
  </defs>
  <rect class="bg" x="0" y="0" width="480" height="320" fill="#fdfdfb"/>
  <!-- 图形内容 -->
</svg>
```

**上色必须双层写，这是最容易踩且后果最重的一条**：

```svg
<!-- ✗ 错：不支持 CSS 变量的渲染器会让整个 fill 属性失效，回落成黑色 -->
<rect fill="var(--bg)" .../>

<!-- ✓ 对：字面色兜底 + CSS 类覆盖（CSS 优先级高于 presentation attribute） -->
<rect class="bg" fill="#fdfdfb" .../>
```

支持 CSS 变量的环境（Obsidian）走主题色并跟随深浅模式；不支持的环境退回一张浅色可读图。**`create_figure.py` 会直接拒绝 `fill="var(...)"`。**

常用的字面色兜底对照：`.ink`→`#1f2933` · `.bg`→`#fdfdfb` · `.accent/.curve/.region 描边`→`#2f6f9f` · `.accent2/.curve2`→`#b3541e` · `.label/.dash/.grid`→`#9aa5b1` · `.region 填充`→`#2f6f9f2e`

线宽、虚线、`fill="none"` 这类不涉及颜色的属性直接写在元素上即可：
`<path class="axis" d="..." stroke="#1f2933" stroke-width="1.5" fill="none"/>`

**为什么底色 `<rect>` 不能省**：万一 `prefers-color-scheme` 没跟随 Obsidian 主题，有这层不透明底色，图至少永远是「浅底深线」的可读状态，不会变成黑底黑线。它和上面的双层写法是同一件事的两半——**任何一层适配失效，图都还得是可读的**。

**画布约定**：宽 480（常用）/ 640（信息多）/ 720（时序图），四周留 32px 边距，字号正文 14px、次要标注 13px。

---

## 3. 分类骨架

### 3.1 坐标系 + 积分区域（数学一最高频）

最小要素：**坐标轴与箭头 · 边界曲线 · 曲线方程标注 · 区域填充 · 交点坐标 · 积分方向条带**。

```svg
  <!-- 坐标轴 -->
  <path class="axis" d="M60 270 H450" stroke="#1f2933" stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>
  <path class="axis" d="M60 270 V40"  stroke="#1f2933" stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>
  <text class="ink" x="452" y="275" fill="#1f2933">x</text>
  <text class="ink" x="52" y="36" fill="#1f2933">y</text>
  <text class="label" x="46" y="286" fill="#9aa5b1">O</text>

  <!-- 区域：y=x² 与 y=x 之间 -->
  <path class="region" d="M60 270 Q160 250 260 110 L60 270 Z" fill="#2f6f9f2e" stroke="#2f6f9f" stroke-width="1.5"/>
  <path class="curve"  d="M60 270 Q160 250 260 110" stroke="#2f6f9f" stroke-width="2" fill="none"/>
  <path class="curve2" d="M60 270 L260 110"        stroke="#b3541e" stroke-width="2" fill="none"/>
  <text class="curve-label" x="266" y="106" fill="#2f6f9f">y = x²</text>
  <text class="curve2-label" x="200" y="175" fill="#b3541e">y = x</text>

  <!-- 积分方向条带：一条竖线代表「先 y 后 x」 -->
  <path class="dash" d="M170 245 V178" stroke="#9aa5b1" stroke-width="1" stroke-dasharray="4 3" fill="none"
        marker-start="url(#arrow)" marker-end="url(#arrow)"/>
  <text class="label" x="176" y="216" fill="#9aa5b1">x 固定，y 从 x² 扫到 x</text>

  <!-- 交点 -->
  <circle class="ink" cx="260" cy="110" r="3.5" fill="#1f2933"/>
  <text class="label" x="266" y="126" fill="#9aa5b1">(1, 1)</text>
```

极坐标区域另加：从原点出发的两条角度射线 + 一段圆弧 + `θ` 与 `r` 的范围标注。

### 3.2 函数作图（极值 / 拐点 / 渐近线 / 根的个数）

最小要素：**坐标轴 · 曲线 · 极值点与拐点（画点 + 标坐标）· 渐近线用虚线 · 与 x 轴交点个数**。

- 曲线用 `<path class="curve" d="M... C..."/>` 三次贝塞尔逼近，**不要**追求数值精确。
- 只要不是按真实比例画的，就在右下角加一行 `<text class="label">示意，非按比例</text>`。
- 讨论根的个数时，把水平线 `y = a` 画成 `.dash`，并标出它与曲线的交点数。

### 3.3 数轴（收敛域 / 分类讨论区间）

```svg
  <path class="axis" d="M60 160 H420" stroke="#1f2933" stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>
  <!-- 空心=开区间 -->
  <circle class="hollow" cx="160" cy="160" r="5" fill="#fdfdfb" stroke="#2f6f9f" stroke-width="2"/>
  <!-- 实心=闭区间 -->
  <circle class="solid" cx="320" cy="160" r="5" fill="#2f6f9f"/>
  <path class="range" d="M160 160 H320" stroke="#2f6f9f" stroke-width="4" fill="none"/>
  <text class="ink" x="150" y="186" fill="#1f2933">-1</text>
  <text class="ink" x="312" y="186" fill="#1f2933">1</text>
  <text class="label" x="200" y="140" fill="#9aa5b1">收敛域 (-1, 1]</text>
```

端点必须用空心/实心区分开闭——这正是级数题最常丢分的地方。

### 3.4 二维随机变量分布区域 / 几何概型

同 3.1 的区域画法，另加：**总样本空间的矩形边框（`.box`）** + **事件区域填充** + 两块面积的标注。图的意义就是"面积比 = 概率"。

### 3.5 位段划分条（Cache 地址 / 浮点格式 / IP 地址通用）

最小要素：**总位宽 · 每段名称 · 每段位宽数字 · 位序标注 · 位宽之和校验**。

```svg
  <!-- 32 位地址：标记 20 位 | 组号 7 位 | 块内 5 位；矩形宽度与位宽成正比 -->
  <g class="ink" fill="#1f2933">
    <rect class="region" x="40"  y="120" width="240" height="48" fill="#2f6f9f2e" stroke="#2f6f9f" stroke-width="1.5"/>
    <rect class="box"    x="280" y="120" width="84"  height="48" fill="none" stroke="#1f2933" stroke-width="1.5"/>
    <rect class="box"    x="364" y="120" width="60"  height="48" fill="none" stroke="#1f2933" stroke-width="1.5"/>
    <text x="120" y="150">标记 Tag</text>
    <text x="296" y="150">组号</text>
    <text x="374" y="150">块内</text>
    <text class="label" x="146" y="186" fill="#9aa5b1">20 位</text>
    <text class="label" x="308" y="186" fill="#9aa5b1">7 位</text>
    <text class="label" x="382" y="186" fill="#9aa5b1">5 位</text>
    <text class="label" x="40"  y="112" fill="#9aa5b1">31</text>
    <text class="label" x="414" y="112" fill="#9aa5b1">0</text>
    <text class="label" x="40"  y="212" fill="#9aa5b1">20 + 7 + 5 = 32 ✓</text>
  </g>
```

**每段矩形宽度必须与位宽成正比**，否则图在说谎。最后那行求和校验必须写出来。

### 3.6 状态转移图（进程状态 / 自动机 / TCP 状态）

最小要素：**状态节点 · 有向边 · 每条边上的触发事件**。没有触发事件的箭头等于没画。

```svg
  <g class="ink" fill="#1f2933">
    <rect class="box" x="60"  y="60" width="110" height="44" rx="8" fill="none" stroke="#1f2933" stroke-width="1.5"/>
    <text x="88" y="88">就绪</text>
    <rect class="box" x="290" y="60" width="110" height="44" rx="8" fill="none" stroke="#1f2933" stroke-width="1.5"/>
    <text x="318" y="88">运行</text>
    <path class="axis" d="M170 76 H288" stroke="#1f2933" stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>
    <text class="label" x="196" y="66" fill="#9aa5b1">调度</text>
    <path class="axis" d="M288 96 H172" stroke="#1f2933" stroke-width="1.5" fill="none" marker-end="url(#arrow)"/>
    <text class="label" x="188" y="116" fill="#9aa5b1">时间片到</text>
  </g>
```

### 3.7 时序图（TCP 握手 / 流水线时空图 / CSMA/CD 时间轴）

最小要素：**两条（或多条）竖直时间线 + 参与方标签 · 斜向箭头表示报文 · 每个箭头上的报文内容 · 时间自上而下**。

流水线时空图用网格：横轴时钟周期（每格等宽 + 周期编号），纵轴指令，每条指令的五段用不同 `fill` 的小矩形错位排开，段名写在格子里。

### 3.8 树 / 链表 / 图结构

最小要素：**节点圆或方框 + 节点值 · 边 · 关键指针（头/尾/待插入位置）用 `--accent2` 突出**。

- 二叉树：节点 `<circle r="18">`，值居中 `text-anchor="middle" dominant-baseline="central"`。
- B+ 树分裂这类**过程题**：画「分裂前 → 分裂后」两张，或一张图上下两栏，中间一个向下箭头写"分裂"。
- 链表：方框分两格（数据域 / 指针域），指针用带箭头的折线连到下一个节点。

---

## 4. 反例清单（这些都会被拒或看不了）

- 用 `<foreignObject>` 塞 HTML/MathML 来"渲染公式" → 白图
- `font-family="LatinModern Math"` 之类的单一字体、无兜底 → 换机器掉字
- `fill="var(--bg)"` 这样只写变量、不写字面兜底色 → 不支持 CSS 变量的渲染器里整张图变黑块（脚本直接拒）
- 只写字面色、不加 CSS 类 → 图不会跟随深色主题，夜里刺眼（脚本不拦，但读起来难受）
- 硬编码纯黑 `#000` / 纯白 `#fff` 当兜底色 → 对比过硬，用骨架给的 `#1f2933` / `#fdfdfb`
- 字号 10px 想塞更多标注 → 缩到 480px 后没法读，宁可拆成两张图
- 把整道题的最终答案写进图里 → `/review` 时一打开卡片就泄底
- 坐标随手编：题目没给交点却在图上标 `(2, 4)` → 这是幻觉，比不画更糟
- 一张图画完整道题的所有步骤 → 拆成图1/图2，各自只负责一个认知动作

---

## 5. 落盘流程

```bash
python3 scripts/create_figure.py \
  --question-id qid-xxxxxxxxxxxx \
  --slug 积分区域 \
  --caption "图1：原积分区域 D 与先 y 后 x 的条带方向" <<'SVG'
<svg ...>...</svg>
SVG
```

拿到返回的 `figure_arg`，原样传给建卡：

```bash
python3 scripts/create_wrong_card.py 数学一 ... \
  --figure "错题本/_附图/qid-xxxxxxxxxxxx/qid-xxxxxxxxxxxx-01-积分区域.svg|图1：原积分区域 D 与先 y 后 x 的条带方向"
```

- `--figure` → 落在 `### 图示`（详解区，紧跟突破口小节之后）
- `--question-figure` → 落在 `### 题目` 末尾，**只用于题面本来就带的图**；解题辅助图不要放这里，否则 `/review` 一打开就泄题
- 复习时补图：`update_card.py --figure "..."`，已有图示区块会追加而不是覆盖
- caption 统一写成 `图N：一句话`，`规范解法` 里用"见图1"引用，图文才对得上
