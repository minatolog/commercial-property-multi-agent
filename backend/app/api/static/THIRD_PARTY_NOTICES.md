# 第三方资源声明（Task 027）

本目录的前端页面复用开源模板资源。**页面运行时不访问 CDN、Google Fonts、远程图片或外部 Node 服务**，
全部资源随仓库以固定版本提供。

## 1. 实际引入的资源

| 文件（本仓库） | 上游来源 | 版本 | 许可证 | 本项目修改 |
|---|---|---|---|---|
| `vendor/tabler/css/tabler.min.css` | [`@tabler/core`](https://www.npmjs.com/package/@tabler/core) → `dist/css/tabler.min.css` | 1.7.4 | MIT | 删除文件末尾的 `/*# sourceMappingURL=tabler.min.css.map */` 注释（未附带 `.map`，避免浏览器请求 404 缺失资源）；其余字节未改动 |
| `vendor/tabler/js/tabler.min.js` | [`@tabler/core`](https://www.npmjs.com/package/@tabler/core) → `dist/js/tabler.min.js` | 1.7.4 | MIT | 删除文件末尾的 `//# sourceMappingURL=tabler.min.js.map` 注释；其余字节未改动 |
| `vendor/tabler/LICENSE` | [tabler/tabler `LICENSE` @ tag `@tabler/core@1.7.4`](https://github.com/tabler/tabler/blob/%40tabler%2Fcore%401.7.4/LICENSE) | 1.7.4 tag | MIT | 无（原文） |

获取记录（2026-11-10，Asia/Shanghai）：

- 下载地址：`https://registry.npmjs.org/@tabler/core/-/core-1.7.4.tgz`
- npm `dist.integrity`：`sha512-fHAPnsKl9JnJJkLxE5UbPkLUBlgn/G1b0urLh5LMGt2DnebpK2tZNEKD/8YiwGz67EoNahGretSsHovDOvJGWA==`
- npm `dist.shasum`（SHA-1）：`2e1c25053d79d491319966e5b2864d68f39bcb2c`
- 下载的 tarball SHA-256：`ccb1631d26cec2589d357556c8fe86bbba75ef0bcf672a4939a7ed5d4ab7319c`
  （本机大小 4,627,544 字节）
- tarball 内 `package/package.json` 的 `version` 为 `1.7.4`，`license` 为 `MIT`。

落地文件 SHA-256（去掉 `sourceMappingURL` 注释**之后**的实际字节）：

| 文件 | 字节数 | SHA-256 |
|---|---|---|
| `vendor/tabler/css/tabler.min.css` | 686,694 | `d75139f3ec33bff19063eca16f8628dbd3d9e43066878ade0b9ccc9780fd1de1` |
| `vendor/tabler/js/tabler.min.js` | 149,338 | `962d5921689cc277fcb7dda8449204f0029d9971b5aee1a3a0775756e53a2dca` |
| `vendor/tabler/LICENSE` | 1,090 | `4f88a82d13be3c5c63a12c5631eae914aa4381b6dc17641bf1ab85f3f8f6c8a5` |

## 2. 复用的布局与组件

页面骨架来自官方 [tabler/tabler-starter](https://github.com/tabler/tabler-starter) 的 `index.html`
（固定提交 [`cc48a51`](https://github.com/tabler/tabler-starter/blob/cc48a519c3684879761e1a49a1d1017bb47a68cd/index.html)，MIT）。
该模板本体是 HTML 片段，未整体复制；本仓库按其结构使用 `page / page-wrapper / page-header / page-body /
container-xl / row row-cards / card / card-body / card-title` 等类名，并把模板示例中的
`https://cdn.jsdelivr.net/npm/@tabler/core@latest/...` 两处引用替换为上述固定版本本地文件。

从 Tabler core（Bootstrap 派生）实际用到的组件样式/行为：

- 布局与容器：`page`、`page-wrapper`、`page-header`、`page-body`、`container-xl`、`row`、`row-cards`、`col-*`、`g-*`
- 卡片：`card`、`card-header`、`card-body`、`card-title`、`card-actions`、`card-header-tabs`、`card-footer`
- 导航与标签页：`navbar`、`navbar-brand`、`nav nav-tabs`、`nav-link`、`tab-content`、`tab-pane`
  （标签页切换使用 `data-bs-toggle="tab"`，由上述 `tabler.min.js` 提供）
- 表单：`form-label`、`form-control`、`form-text`、`form-check`、`form-check-input`、`form-switch`、`form-select`
- 按钮与提示：`btn`、`btn-primary`、`btn-outline-*`、`btn-sm`、`btn-list`、`spinner-border`
- 状态与文本：`badge`、`bg-*-lt`、`text-secondary`、`text-danger`、`text-success`、`small`、`fw-bold`
- 列表：`list-group`、`list-group-item`、`list-group-item-action`
- 辅助：`table`、`table-vcenter`、`table-sm`、`alert`、`alert-danger`、`alert-warning`、`divide-y`、`d-none`、`hr`

业务专用样式集中在 `css/workbench.css`（Agent 协作画布、节点、连线、领域配色、响应式堆叠），
不是对 Tabler 主题的重写。

## 3. 未引入的内容

- 未引入 `@tabler/icons`、ApexCharts、MapLibre、FullCalendar、Tom Select 等 `dist/libs/**` 插件。
- 未引入 `tabler-vendors.min.css`、`tabler-marketing.min.css`、RTL 变体或任何 `.map` 文件。
- 未引入 Astro/Node 构建链；页面只使用预编译产物。
- 未引入 Langflow 的任何代码或资源。Langflow（MIT）仅作为「任务节点 + 端口 + 有向连线 + 节点详情」
  的视觉组织参考，协作画布的 DOM/SVG/样式为本项目自行编写。

## 4. 图标

页面中的小图标（状态勾选、失败叉、连接线箭头、品牌方块）均为本项目手写的内联 SVG 或纯 CSS 图形，
未复制第三方图标集；不适用第三方图标许可。

## 5. 许可证正文

Tabler 的 MIT 许可证全文见 [`vendor/tabler/LICENSE`](./vendor/tabler/LICENSE)。
