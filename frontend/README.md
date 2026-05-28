# 美甲AI智能运营 - 前端

## 目录结构

```
frontend/
├── index.html          # 入口页（选择用户端/运营端）
├── api-config.js       # 公共 API 配置（后端地址、请求封装）
├── user/               # C端用户侧（移动端）
│   ├── index.html
│   ├── styles.css
│   └── app.js          # 已对接后端 API
├── admin/              # B端运营侧（PC端）
│   ├── index.html
│   ├── admin-styles.css
│   └── admin-app.js    # 已对接后端 API
└── mock/               # 静态 mock 数据（兜底用）
```

## 前后端联调

### 1. 启动后端

```bash
cd /Users/asa/lab_job/Meituan_hackathon2026/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

首次运行需初始化数据库：
```bash
curl -X POST http://127.0.0.1:8000/api/db/init
```

### 2. 启动前端

前端是纯静态文件，可以用任何方式打开。推荐使用 Python 自带的 HTTP 服务器：

```bash
cd /Users/asa/lab_job/Meituan_hackathon2026/frontend
python -m http.server 3000
```

然后访问：
- 入口页：http://localhost:3000
- 用户端：http://localhost:3000/user/
- 运营端：http://localhost:3000/admin/

### 3. 联调模式说明

前端代码采用 **优雅降级** 策略：

- **后端可用时**：自动调用真实 API，获取 AI 生成的数据
- **后端不可用时**：自动回退到本地 mock 数据，页面仍可正常浏览

前端启动时会自动检测后端健康状态（`GET /health`），无需额外配置。

### 4. API 对接映射

| 前端功能 | 后端 API | 说明 |
|---------|----------|------|
| AI 对话推荐 | `POST /api/chat` | 基于 Gemini 生成回复 |
| 手图上传 | `POST /api/upload-image` | 支持真实文件上传 |
| 手型分析 | `POST /api/analyze-hand` | Qwen VL 分析肤色/手型 |
| 款式推荐 | `POST /api/recommendations` | 基于手型标签匹配 |
| AI 试戴 | `POST /api/try-on` | GPT-Image-1 生成试戴图 |
| 款式列表 | `GET /api/db/styles` | 获取所有款式数据 |
| 数据统计 | `GET /api/events/stats` | 用户行为聚合 |
| 爆款推送 | `GET /api/push-cards` | 推送卡片列表 |
| 审核上架 | `POST /api/push-cards/{id}/audit` | 商户确认上架 |
| 复盘报告 | `POST /api/report` | AI 生成运营报告 |
| Skills 执行 | `POST /api/skills/execute` | 运营建议执行 |
| 标签提取 | `POST /api/extract-tags` | 款式图 AI 标签识别 |

### 5. 修改后端地址

如果后端不在 `localhost:8000`，修改 `api-config.js` 中的：

```js
const API_BASE = 'http://localhost:8000';
```

### 6. CORS 说明

后端已配置 `allow_origins=["*"]`，允许任何来源的前端访问，开发阶段无需配置代理。
