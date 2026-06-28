# 前端开发与 UI 样式规范

> 本文档基于项目 `frontend/` 当前真实代码整理,描述既有的设计风格与开发约定。
> 新增页面/组件请遵循本规范,保持整体视觉与代码风格统一。
> 适用范围:`frontend/src` 下全部 Vue 组件、视图与样式。

---

## 1. 技术栈与工程约定

| 项目 | 选型 | 说明 |
|---|---|---|
| 框架 | Vue 3 | 统一使用 `<script setup>` + Composition API |
| 语言 | TypeScript | 所有 `.vue`、`.ts` 均用 TS,`lang="ts"` |
| 构建 | Vite 5 | 开发端口 `5173`,`/api` 代理到 `http://localhost:8000` |
| 状态 | Pinia | store 放 `src/stores/` |
| 路由 | Vue Router 4 | `createWebHistory`(History 模式) |
| HTTP | axios | 统一封装在 `src/api/client.ts` |
| 图表 | ECharts 5 + Lightweight Charts 4 | K 线优先用 Lightweight Charts |
| UI 组件库 | **无** | 全部手写,**不要引入** Element Plus / Ant Design Vue 等 |

**约定**
- **不使用 UI 组件库**,所有控件(按钮、表格、面板、标签)手写,保持轻量与风格统一。
- **没有路径别名**(`vite.config.ts` 未配置 `@`),组件间用相对路径导入,如 `import Sidebar from './components/layout/Sidebar.vue'`、`from '../../api/client'`。
- 全局样式仅一个文件 `src/style.css`,在 `main.ts` 中引入。

---

## 2. 主题与配色

项目为**单一深色主题(Dark Only)**,目前**没有亮色主题、没有主题切换机制**。颜色直接以十六进制写在各组件的 `scoped` 样式里(未使用 CSS 变量)。新增组件请复用下表色值,保证一致。

### 2.1 背景与层级(由深到浅)

| 用途 | 色值 | 出处 |
|---|---|---|
| 全局/最底背景、表头背景 | `#0b0f19` | `style.css` body、`.app` |
| 侧边栏、表格容器、列表项底 | `#111827` | `Sidebar`、`StrategyResultTable` |
| 卡片 / 面板 / 输入框 / 二级背景 | `#1f2937` | `.panel`、`input` |
| 列表项 hover | `#1a2230` | `.stock-item:hover` |
| 边框(深) | `#1f2937` | 卡片/表格分隔线 |
| 边框(浅,输入/按钮) | `#374151` | `input`、`.toggle-btn` |

### 2.2 文字

| 用途 | 色值 |
|---|---|
| 主文字 | `#e5e7eb` |
| 强调 / 标题强调(代码、股票名) | `#ffffff` |
| 次要文字 | `#d1d5db` |
| 弱化 / 占位 / 说明 | `#9ca3af` |
| 最弱 / 空状态 / 加载提示 | `#6b7280` |

### 2.3 品牌色 / 交互色

| 用途 | 色值 |
|---|---|
| 品牌主色(Logo、链接、操作按钮文字) | `#60a5fa` |
| 链接 hover | `#93c5fd` |
| 选中态 / 主操作按钮背景(active) | `#2563eb` |

### 2.4 股票涨跌色(重要:红涨绿跌)

遵循 A 股习惯,**红涨绿跌**,通过 `.up` / `.down` 两个类表达:

```css
.stock-change.up   { color: #ef4444; }  /* 涨 — 红 */
.stock-change.down { color: #22c55e; }  /* 跌 — 绿 */
```

| 语义 | 色值 | 备注 |
|---|---|---|
| 涨 / 正向 | `#ef4444`(浅 `#f87171`) | 标签底色用 `rgba(239,68,68,0.15)` |
| 跌 / 负向 | `#22c55e` | |
| 平 | 不加类(继承默认文字色) | |

**评分渐变**:评分类数据在 `#ef4444`(低 0 分)→ `#22c55e`(高 100 分)之间做 RGB 线性插值(见 `StrategyResultTable.vue` 的 `scoreStyle`),分数越高越绿。

**约定**:涨跌/正负值统一用 `.up` / `.down` 类控制颜色,**不要在模板里写内联颜色**;判断逻辑统一用 `changeClass(value)` 辅助函数(`>0 → 'up'`,`<0 → 'down'`,`=0 → ''`)。

---

## 3. 间距、圆角与尺寸

无 spacing token,但实际取值高度收敛于以下规律,新增样式请对齐:

### 3.1 圆角(radius)

| 元素 | 圆角 |
|---|---|
| 卡片 / 面板 | `10px` |
| 表格容器 | `8px` |
| 列表项 / 导航项 / 按钮 / toggle | `6px` |
| 输入框 / 标签 / 小元素 | `4px` |

### 3.2 内边距(padding)

| 元素 | padding |
|---|---|
| 卡片 / 面板 | `18px` |
| 表格单元格 `th/td` | `14px 16px` |
| 列表项 | `10px 12px` |
| 导航项 | `10px 12px`(子项 `8px 12px`) |
| 按钮 / 输入框 | `6px 10px` ~ `6px 14px` |
| 标签(tag) | `2px 8px` |

### 3.3 间距(gap)与布局尺寸

| 用途 | 值 |
|---|---|
| 大区块(section)纵向间距 | `28px` |
| 卡片网格 / 区块内 gap | `20px` |
| 区块标题与内容 | `14px` |
| 列表项之间 | `8px` |
| 侧边栏宽度 | `220px`(`flex-shrink: 0`) |
| 卡片网格列 | `repeat(auto-fit, minmax(360px, 1fr))` |

### 3.4 字号与字重

| 用途 | 字号 / 字重 |
|---|---|
| 区块大标题 `.section-title` | `17px` / `600` |
| 面板标题 `h2` | `16px` / `600` |
| 正文 / 表格 | `14px` |
| 次要文字 / 小按钮 / 标签 | `13px` |
| 最小(代码副行、说明) | `12px` |
| Logo | `20px` / `700` |

字体统一使用系统字体栈:
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
```

---

## 4. 布局结构

整体为「左侧固定侧边栏 + 右侧主内容滚动区」:

```
App.vue
├── Sidebar (固定 220px, 背景 #111827)
└── main-content (flex:1, overflow-y:auto, height:100vh)
    └── <router-view />
```

- 根容器 `.app`:`display:flex; height:100vh; width:100vw; background:#0b0f19`。
- 主内容区 `.main-content`:`flex:1; min-width:0; overflow-y:auto`(滚动只发生在主区,侧边栏固定)。
- 侧边栏导航项三态:默认 `#d1d5db`、hover 背景 `#1f2937`、active 背景 `#2563eb` 白字;分组标题可折叠(`▶` 旋转 90°)。

---

## 5. 通用 UI 模式(直接复用)

### 5.1 卡片 / 面板(Panel)

```css
.panel {
  background: #1f2937;
  border-radius: 10px;
  padding: 18px;
}
.panel-header {           /* 标题行:标题 + 右侧状态(加载中…) */
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
```

### 5.2 排行/列表项(可点击跳详情)

列表项用 `<router-link :to="`/stock/${code}`">`,左侧代码+名称,右侧涨跌值:

```css
.stock-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; border-radius: 6px;
  background: #111827; text-decoration: none;
  transition: background 0.2s;
}
.stock-item:hover { background: #1a2230; }
```

### 5.3 表格(Table)

```css
.result-table { background:#111827; border:1px solid #1f2937; border-radius:8px; overflow:hidden; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { background:#0b0f19; color:#9ca3af; font-weight:500; font-size:13px; }
th, td { padding:14px 16px; text-align:left; border-bottom:1px solid #1f2937; }
td { color:#e5e7eb; }
```
- 股票列:名称(白色 500)在上,代码(`#9ca3af` 12px)在下。
- 操作列:用 `.btn-link`(透明背景、`#60a5fa`、hover 下划线)放「加自选 / 详情」。

### 5.4 标签(Tag)

```css
.tag-dragon {            /* 高亮标签:半透明底 + 同色字 */
  padding: 2px 8px; border-radius: 4px;
  background: rgba(239, 68, 68, 0.15); color: #f87171;
  font-size: 12px; font-weight: 600;
}
```

### 5.5 分段切换按钮(Toggle)

```css
.toggle-btn { padding:6px 14px; border-radius:6px; border:1px solid #374151;
  background:#111827; color:#9ca3af; font-size:13px; }
.toggle-btn.active { background:#2563eb; color:#fff; border-color:#2563eb; }
```

### 5.6 状态文案

- 加载中:`<span class="loading-text">加载中...</span>`(`#6b7280`,13px)。
- 空数据:`<div class="empty">暂无数据</div>`(居中、`#6b7280`、上下留白)。

---

## 6. 组件与代码风格

### 6.1 单文件组件结构

固定顺序 `<template>` → `<script setup lang="ts">` → `<style scoped>`:

```vue
<template> ... </template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchXxx } from '../../api/client'
import type { XxxItem } from '../../api/client'

const props = defineProps<{ data: Xxx; loading: boolean }>()
defineEmits<{ (e: 'addWatchlist', code: string): void }>()
// ...
</script>

<style scoped> ... </style>
```

- **必须** `<script setup lang="ts">`,使用 Composition API(`ref` / `computed` / `onMounted`)。
- **必须** `<style scoped>`(唯一例外:`App.vue` 写全局布局样式用非 scoped)。
- `defineProps` / `defineEmits` 用 **TS 泛型**声明类型,不用运行时 `props: {}` 写法。
- 类型从 `api/client.ts` 用 `import type` 引入,避免重复定义。

### 6.2 CSS 类命名

- 使用**语义化、局部短名**(`.panel`、`.stock-item`、`.section-title`),**不用 BEM**。
- 状态/变体用组合类:`.stock-change.up`、`.nav-item.active`、`.toggle-btn.active`。
- 因为 `scoped`,类名只需在组件内唯一,无需加组件前缀。

### 6.3 工具函数约定

涉及展示格式化时,复用既有命名习惯(可在组件内本地定义):
- `formatAmount(n)`:金额转 `亿` / `万` 单位。
- `formatChange(n)`:带 `+/-` 的百分比字符串,如 `+1.23%`。
- `changeClass(n)`:返回 `'up' | 'down' | ''`。
- `formatDate(d)` / `formatYi(n)`:日期截断、`亿` 单位。

### 6.4 数据字段命名注意

部分概览类接口返回**中文字段名**(如 `stock.代码`、`stock.名称`、`stock.涨跌幅`),模板中按后端实际字段访问;而股票列表/策略等接口用英文字段(`code`、`name`、`change_pct`)。新增接口优先用**英文 snake_case** 字段,概览类沿用既有约定即可。

---

## 7. API 调用约定

- 全部 HTTP 调用集中在 `src/api/client.ts`,基于一个 axios 实例:
  ```ts
  const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
    timeout: 30000,
  })
  ```
- 导出**类型化的异步函数**,命名约定:
  - 读取:`fetchXxx(...)`(如 `fetchStockList`、`fetchRealtimeOverview`、`fetchSectorRanking`)。
  - 写入/同步:`syncXxx(...)`、`createXxx` / `renameXxx` / `deleteXxx`。
- 每个接口的请求/响应类型用 `interface` 显式声明并 `export`,供组件 `import type` 复用。
- 组件内调用模式:`onMounted` 触发,`loading` ref 控制状态,`try/catch/finally`,失败 `console.error`;并发请求用 `Promise.all`;可加「已加载则跳过」的简单缓存判断(见 `RealtimeTab` 的 `loadSectors`)。

---

## 8. 路由约定

定义于 `src/router/index.ts`:

- 路由 `name` 用 **kebab-case**(`stock-list`、`stock-detail`)。
- 每条路由带 `meta.title`(中文标题);属于「A 股」分组的加 `meta.parent: 'a-shares'`。
- 详情页用参数路由 `/stock/:code`,跳转统一 `:to="`/stock/${code}`"`。
- 视图组件放 `src/views/`,以 `XxxView.vue` 命名;业务组件按域分目录放 `src/components/<域>/`(如 `overview/`、`strategy/`、`layout/`)。

---

## 9. 响应式

- 主要面向桌面端;栅格用 `auto-fit + minmax` 自适应列数。
- 需要时用 `@media (max-width: 900px)` 做窄屏微调(如收窄 `.reason` 最大宽度)。

---

## 10. 新增页面/组件检查清单

- [ ] 使用 `<script setup lang="ts">` + `<style scoped>`
- [ ] 复用第 2 节色值,深色背景层级正确,涨跌用 `.up`/`.down`(红涨绿跌)
- [ ] 圆角/间距/字号对齐第 3 节取值
- [ ] 卡片、表格、列表项、标签、toggle 复用第 5 节既有模式,不引入 UI 库
- [ ] HTTP 调用写进 `api/client.ts`,函数 `fetch*/sync*` 命名 + 类型化
- [ ] 路由 `name` kebab-case、带 `meta.title`,组件按域归目录
- [ ] 加载态 `加载中...`、空态 `暂无数据` 文案与样式统一
