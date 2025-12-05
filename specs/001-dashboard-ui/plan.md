# 实施计划 - 仪表盘 UI (Dashboard UI)

实现一个简单的 Web 仪表盘，用于上传 Wasm 插件和监控集群状态。

## 用户审查要求

> [!NOTE]
> 本次变更不涉及核心运行时逻辑，仅增加前端页面和 Controller 的 API。

## 拟议变更

### Flash Controller (Go)

#### [MODIFY] [flash-controller/main.go](file:///Users/jiwn2/dev/mascreate/masLambda/flash-controller/main.go)
- **API**:
  - 新增 `GET /status`: 返回集群状态（目前模拟数据，后续对接真实状态）。
  - 新增 `Static FS`: 托管 `flash-dashboard/dist` 目录下的静态文件。

### Flash Dashboard (Frontend)

#### [NEW] [flash-dashboard/index.html](file:///Users/jiwn2/dev/mascreate/masLambda/flash-dashboard/index.html)
- 简单的 HTML 页面，包含：
  - 上传表单 (File Input + Upload Button)。
  - 状态列表 (Table/List)。
  - 使用原生 JS (`fetch` API) 与 Controller 交互。

#### [NEW] [flash-dashboard/style.css](file:///Users/jiwn2/dev/mascreate/masLambda/flash-dashboard/style.css)
- 基本的 CSS 样式，保持简洁黑客风。

## 验证计划

### 手动验证
- 启动 Controller。
- 浏览器访问 `http://localhost:8080`。
- 尝试上传 `test.wat`，验证是否执行成功。
- 查看页面是否显示 Runner 节点状态。
