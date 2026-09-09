# TikZ 配图参考（立体与精确曲线）

TikZ 只在一种情况下用：**图里的几何必须被算出来，AI 手写 SVG 坐标会算错**。典型是三维体、曲面、空间曲线，以及形状必须准确的函数图像。其余一律走 `references/svg-figure-guide.md`。

Obsidian 里靠 `obsidian-tikzjax` 插件渲染，本机没有 TeX。这意味着：**编译错误只有打开卡片才看得到**。所以宁可画得朴素，也不要用没把握的宏包和语法。

---

## 0. 决策门：三道门都过才用 TikZ

1. **该不该画**：同 `svg-figure-guide.md` 第 0 节。删掉图解释力不损失就不画。
2. **2D 投影够不够**：三重积分、曲面积分的难点多半是「投影区域 D 长什么样」「z 的上下限是谁」，这两件事都是平面图，用 SVG 画。只有「两个曲面谁上谁下」「相交后的立体想不出来」「曲面的法向量指向哪边」这类真正三维的困惑才画立体图。
3. **坐标能不能手算**：位置定性就行的示意图（数轴、平面区域、状态框）用 SVG。图里出现 z 轴、或曲线形状必须准确（真实的 y = x·e^{-x} 而不是随手一条弧线），用 TikZ。

**一句话：图里有 z 轴，或曲线形状必须准，用 TikZ；其余用 SVG。**

---

## 1. 硬性技术约束（`create_figure.py --kind tikz` 会逐条校验）

| 约束 | 原因 |
|------|------|
| 必须有 `\begin{document} ... \end{document}`，`\usepackage` / `\usetikzlibrary` 写在它之前 | obsidian-tikzjax 要求这个结构 |
| 禁止 `\documentclass` | 插件自己加，重复会编译失败 |
| 宏包只能用：`tikz` `pgfplots` `tikz-3dplot` `tikz-cd` `circuitikz` `chemfig` `array` `amsmath` `amstext` `amsfonts` `amssymb` `xcolor` | 插件只内置这些，其它一律编译失败 |
| **图内禁止中文** | TikZJax 没有 CJK 字体，中文渲染成空白或方块。中文说明全部放进 `--caption` |
| 花括号、`\begin`/`\end` 必须配平 | 本机没有 TeX 预编译，这是最常见的失败原因 |
| 禁止 `\input` `\include` `\write` `\catcode` | 插件无法读写外部文件 |
| ≤ 16KB（>4KB 告警） | 首次编译在浏览器里跑，图大了要等好几秒 |
| 源码不带 ```` ``` ```` 围栏 | 围栏由建卡脚本按图源类型自动加 |

另外三条不硬拦但必须遵守：

- 用 `pgfplots` 就写 `\pgfplotsset{compat=1.16}`。
- 用 `tikz-3dplot` 就调 `\tdplotsetmaincoords{θ}{φ}`，否则三维视角退化成平面。
- **深色模式靠插件反色**，所以填充色用低饱和（`blue!10` `orange!20`），线用 `blue!60!black` 这类中等深度。纯黑纯白反色后最刺眼。

---

## 2. 通用骨架

```tikz
\usepackage{tikz-3dplot}
\usetikzlibrary{arrows.meta, calc}
\begin{document}
\tdplotsetmaincoords{65}{125}
\begin{tikzpicture}[tdplot_main_coords, scale=1.6, >=Stealth, font=\small]
  % 坐标轴
  \draw[->] (0,0,0) -- (1.6,0,0) node[anchor=north east]{$x$};
  \draw[->] (0,0,0) -- (0,1.6,0) node[anchor=north west]{$y$};
  \draw[->] (0,0,0) -- (0,0,1.5) node[anchor=south]{$z$};
  % 图形内容
\end{tikzpicture}
\end{document}
```

`\tdplotsetmaincoords{65}{125}` 是看得最清楚的通用视角；上面的面看不见时把第一个数改小（50），底面看不见时改大（75）。

**画布约定**：`scale` 1.4 到 1.8 之间；字号 `\small`；标注用 `node[anchor=...]` 贴在对象旁边，不要用绝对坐标硬摆。

---

## 3. 分类骨架

### 3.1 三重积分的积分体（最高频）

最小要素：**上曲面 · 下曲面 · 交线 · 投影区域 D（虚线 + 淡填充）· 每个曲面的方程标注**。

```tikz
\usepackage{tikz-3dplot}
\usetikzlibrary{arrows.meta}
\begin{document}
\tdplotsetmaincoords{65}{125}
\begin{tikzpicture}[tdplot_main_coords, scale=1.6, >=Stealth, font=\small]
  \draw[->] (0,0,0) -- (1.6,0,0) node[anchor=north east]{$x$};
  \draw[->] (0,0,0) -- (0,1.6,0) node[anchor=north west]{$y$};
  \draw[->] (0,0,0) -- (0,0,1.5) node[anchor=south]{$z$};
  % 上曲面：平面 z=1 截出的圆盘
  \draw[thick, fill=blue!10, fill opacity=0.5]
    plot[domain=0:360, samples=60, variable=\t] ({cos(\t)},{sin(\t)},1) -- cycle;
  \node[anchor=south west] at (0.7,0.7,1) {$z=1$};
  % 下曲面：抛物面 z=x²+y²，用母线示意
  \foreach \a in {0,45,...,315} {
    \draw[blue!60!black] plot[domain=0:1, samples=20, variable=\r]
      ({\r*cos(\a)},{\r*sin(\a)},{\r*\r});
  }
  \node[anchor=west, blue!60!black] at (0.75,0,0.55) {$z=x^2+y^2$};
  % 投影区域 D
  \draw[dashed, thick, fill=orange!20, fill opacity=0.4]
    plot[domain=0:360, samples=60, variable=\t] ({cos(\t)},{sin(\t)},0) -- cycle;
  \node[anchor=north, orange!70!black] at (0.3,-0.9,0) {$D:\ x^2+y^2\le 1$};
\end{tikzpicture}
\end{document}
```

- 球面用 `\tdplotdrawarc` 或 `\foreach` 画纬线圈；锥面用从顶点出发的母线。
- 投影 D 永远画在 z = 0 平面上，用虚线和淡色，它是「先二后一」「先一后二」的分界依据。
- 交线（两曲面相交）用 `thick` 实线突出：它决定 D 的边界方程。

### 3.2 曲面积分：曲面 + 法向量 + 投影

最小要素：**曲面片 · 法向量箭头（标 n，注明指向上侧/外侧）· 投影方向 · 投影区域**。

在 3.1 骨架基础上加一个法向量：

```tikz
  % 曲面上一点的法向量：题目说「上侧」就朝 +z
  \coordinate (P) at (0.5,0.5,0.5);
  \draw[->, thick, red!70!black] (P) -- ($(P)+(0,0,0.5)$) node[anchor=west]{$\vec n$};
  \fill[red!70!black] (P) circle (0.6pt);
```

高斯公式题：再画一个封闭补面（`fill=gray!20`），标 `\Sigma_1`，图说明里写「补面后闭合，用高斯公式」。

### 3.3 空间曲线 + 方向（曲线积分、斯托克斯）

最小要素：**曲线 · 方向箭头 · 曲线所在曲面的交线来源 · 起终点**。

```tikz
\usetikzlibrary{arrows.meta, decorations.markings}
...
  \draw[thick, blue!60!black,
        postaction={decorate, decoration={markings, mark=at position 0.3 with {\arrow{Stealth}}}}]
    plot[domain=0:360, samples=80, variable=\t] ({cos(\t)},{sin(\t)},{1-cos(\t)-sin(\t)});
  \node[anchor=west, blue!60!black] at (1,0,0.2) {$\Gamma$};
```

曲线是两曲面的交线时（如 x²+y²=1 与 x+y+z=1），把两张曲面都淡淡画出来，交线加粗。方向要和题目「从 z 轴正向看为逆时针」一致，画完自己对一遍。

### 3.4 精确函数图像（pgfplots）

当曲线的形状本身是结论（极值在哪、和 x 轴交几次、渐近线在哪）时用 pgfplots 算，不要用 SVG 贝塞尔手糊。

```tikz
\usepackage{pgfplots}
\pgfplotsset{compat=1.16}
\begin{document}
\begin{tikzpicture}[font=\small]
\begin{axis}[
  axis lines=middle, xlabel=$x$, ylabel=$y$,
  xmin=-0.5, xmax=5, ymin=-0.2, ymax=0.6,
  width=9cm, height=6cm, samples=120,
  xtick={1,2,3,4}, ytick={0.2,0.4},
]
  \addplot[blue!60!black, thick, domain=0:5] {x*exp(-x)};
  \addplot[dashed, gray] {0.2};            % 讨论根个数的水平线 y=a
  \addplot[only marks, mark=*] coordinates {(1, 0.3679)};
  \node[anchor=south west] at (axis cs:1,0.3679) {$(1,\,e^{-1})$};
  \node[anchor=north east] at (axis cs:4.8,0.2) {$y=a$};
\end{axis}
\end{tikzpicture}
\end{document}
```

- `domain` 必须覆盖题目讨论的区间，别让曲线在关键点前断掉。
- 极值点、拐点、交点只标题面给定或已推出的值。算不出精确值就只画点不标坐标。
- 渐近线用 `dashed`。

---

## 4. 反例清单

- 图内写中文 → 空白或方块（脚本直接拒）
- `\usepackage{ctex}` `\usepackage{tikz-euclide}` 这类插件没有的宏包 → 编译失败（脚本直接拒）
- 一张图里同时画积分体、投影、法向量、切片、方向箭头 → 拆成图1（体与投影）、图2（切片或法向量）
- 视角随手写 `\tdplotsetmaincoords{0}{0}` → 退化成平面图，白用了 TikZ
- 用 `fill=black` `draw=white` → 深色模式反色后要么消失要么刺眼
- 把最终积分值或答案写在图上 → `/review` 一打开就泄底
- 手写 200 行 TikZ 追求逼真 → 编译慢、错误率高，这张图已经在替解法讲话

---

## 5. 落盘流程

```bash
python3 scripts/create_figure.py \
  --question-id qid-xxxxxxxxxxxx \
  --kind tikz \
  --slug 积分体 \
  --caption "图1：抛物面 z=x²+y² 与平面 z=1 围成的 Ω 及其投影 D" <<'TIKZ'
\usepackage{tikz-3dplot}
...
\end{document}
TIKZ
```

- 返回的 `figure_arg` 原样传 `create_wrong_card.py --figure` / `update_card.py --figure`，和 SVG 完全一样。
- 源码存成 `错题本/_附图/[qid]/[qid]-NN-[slug].tikz`，卡片里内联为 ```` ```tikz ```` 代码块，前面一行 `%%图源：路径%%` 注释（阅读视图不可见）用来追溯。
- 中文说明只能写在 caption，规范解法里用「见图1」引用。caption 里的公式用 `$...$` 包裹，建卡脚本会拒绝裸公式。
- **建卡后在 Obsidian 里打开确认三件事**：编译出来了（不是红色报错框）、视角能看清上下曲面、深色模式下线条没消失。首次编译要等几秒，别急着判定失败。
