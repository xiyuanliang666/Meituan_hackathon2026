# 美甲 AI 后端与算法服务

黑客松阶段后端采用 Python + FastAPI，先提供稳定 JSON API 给用户侧移动 H5/WebView 和运营侧 Web 后台调用。当前版本以 mock 和规则算法为主，真实多模态模型、图像生成、平台数据接入均封装在 service 层，后续可替换实现。

## 快速启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问：

- 健康检查：`http://localhost:8000/health`
- Swagger：`http://localhost:8000/docs`
- 数据流说明：[DATA_FLOW.md](./DATA_FLOW.md)

## 接入真实模型

当前按任务拆成三类模型配置：

| 任务 | 模型 | 配置项 |
| --- | --- | --- |
| 标签提取 | `gemini-2.5-flash` | `GEMINI_API_KEY` / `GEMINI_BASE_URL` / `GEMINI_MODEL_NAME` |
| 运营文案/复盘报告 | `gemini-2.5-flash` | 同上 |
| 图片理解、手部肤色/手型分析 | `qwen-vl-plus` | `QWEN_API_KEY` / `QWEN_BASE_URL` / `QWEN_VL_MODEL_NAME` |
| AI 试戴/合成图 | `gpt-image-1`（自动回退 `gpt-image-1-mini` / `gpt-image-1.5`） | `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `IMAGE_MODEL_NAME` / `IMAGE_GENERATION_ENABLED` |

配置方式：

```bash
cd backend
cp .env.example .env
```

编辑 `.env`：

```bash
MODEL_REAL_ENABLED=true
MODEL_TIMEOUT_SECONDS=30

GEMINI_API_KEY=你自己贴
GEMINI_BASE_URL=https://api.gpt.ge/v1
GEMINI_MODEL_NAME=gemini-2.5-flash

QWEN_API_KEY=你自己贴
QWEN_BASE_URL=https://api.gpt.ge/v1
QWEN_VL_MODEL_NAME=qwen-vl-plus

OPENAI_API_KEY=你自己贴
OPENAI_BASE_URL=https://api.gpt.ge/v1
IMAGE_MODEL_NAME=gpt-image-1
IMAGE_GENERATION_ENABLED=false
```

如果未配置对应 API Key，或模型调用失败，接口会自动回退到稳定 mock 结果，保证 Demo 不被外部模型波动阻断。响应里的 `analysis_mode` / `generation_mode` 会标记当前使用的是具体模型还是 mock。

当前默认走 OpenAI-compatible 协议：`BASE_URL + /chat/completions`。如果使用 `https://api.gpt.ge/v1`，最终请求地址会是 `https://api.gpt.ge/v1/chat/completions`。如果后续供应商网关协议不同，只需要替换 `app/services/multimodal_client.py`，业务接口不用改。

## 已实现接口

| 接口 | 说明 |
| --- | --- |
| `POST /api/upload-image` | 上传手图/款式图/模板图，返回本地可访问 URL |
| `POST /api/extract-tags` | 款式图标签提取（v2 十二字段，值域从数据库加载） |
| `GET /api/taxonomy` | 标签体系字段与可选值（审核页/打标页下拉） |
| `POST /api/taxonomy/submissions` | 用户提交新标签（待审核，`is_approved=false`） |
| `GET /api/taxonomy/submissions` | 查询待审核标签提交 |
| `PATCH /api/taxonomy/submissions/{id}` | 审核通过/驳回（仅更新 `is_approved` 字段） |
| `GET /api/styles/{style_id}/tags` | 读取款式已存标签 |
| `PUT /api/styles/{style_id}/tags` | 商户审核/修改打标结果 |
| `POST /api/analyze-hand` | 用户手图分析 |
| `POST /api/recommendations` | 个性化款式推荐 |
| `POST /api/generate-composite` | 裸手模板合成图生成 |
| `POST /api/try-on` | 用户 AI 试戴 |
| `GET /api/evaluation-pairs` | 读取赛题 xlsx 中真实存在的手图/款式图配对 |
| `GET /api/evaluation-dataset` | 读取赛题 xlsx 中的手图模板、款式图和配对样例 |
| `POST /api/db/init` | 从 xlsx 初始化轻量 SQLite 业务库 |
| `POST /api/db/tag-seed-styles` | 对官方款式图批量提取标签并写回 SQLite |
| `GET /api/db/summary` | 查看业务库表统计 |
| `GET /api/db/styles` | 查询结构化款式表 |
| `GET /api/db/events` | 查询用户行为事件表 |
| `POST /api/events` | 写入曝光、试戴、收藏、点赞、下单等用户行为 |
| `GET /api/events` | 查询用户行为流水 |
| `GET /api/events/stats` | 按款式聚合用户行为指标 |
| `GET /api/push-cards` | 爆款推送卡片列表 |
| `POST /api/push-cards/{push_id}/audit` | 商户审核上架/拒绝 |
| `POST /api/report` | 运营复盘报告 |
| `POST /api/skills/execute` | Skills 动作执行模拟 |

## 当前边界

- 图片生成接口优先尝试真实图片模型；未开启或失败时返回本地 SVG 兜底图，前端仍可直接展示。
- 赛题 xlsx 作为种子数据源，后端通过 `POST /api/db/init` 导入轻量 SQLite 业务库，默认路径 `backend/storage/nail_ai_demo.db`。
- SQLite 表覆盖手图模板、款式、配对、标签、热度信号、UGC 关键词和用户行为，方便后续 embedding 检索、趋势统计、热门分析、Agent 查询和推荐逻辑。
- 爆款识别使用 mock 信号和规则评分。
- 商户上架、下架、预算调整只做状态模拟，不调用真实美团平台接口。
- 模型 API Key 不应放在前端；真实模型调用统一放在 `services/`。
