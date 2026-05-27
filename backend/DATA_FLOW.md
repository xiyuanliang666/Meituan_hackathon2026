# 后端数据流与接口说明

## 1. 当前实现状态

当前后端已经从“纯 mock 接口”推进到“轻量业务数据库驱动”的阶段。

核心链路：

```text
运营侧/命题三美甲评测数据（对外版）.xlsx
        ↓
dataset_loader 解析种子数据
        ↓
SQLite 轻量业务库 backend/storage/nail_ai_demo.db
        ↓
推荐 / 爆款推送 / 用户行为 / 复盘报告
```

## 2. 数据源说明

官方 xlsx 不是完整的 25 组手图和款式图配对。实际结构是：

- `sheet1`：13 组真实手图 + 款式图配对，后半部分存在部分只有款式图的行。
- `sheet2`：25 张款式图，包含原始款式图 URL 和增强后款式图 URL。

因此后端按真实结构导入：

- `hand_templates`：13 张手图模板。
- `styles`：25 个款式。
- `evaluation_pairs`：13 组真实配对样例。

## 3. SQLite 表结构

| 表 | 用途 |
| --- | --- |
| `hand_templates` | 手图模板，来自 xlsx |
| `styles` | 款式图、款式名、热度分、生命周期 |
| `evaluation_pairs` | 官方提供的真实手图/款式图配对 |
| `style_tags` | 款式标签，按产品定义拆成营销维度和工艺维度，例如 `marketing_color`、`marketing_style`、`craft_type`、`craft_complexity` |
| `style_signals` | 搜索热度、UGC 词频、试戴收藏率等运营信号 |
| `ugc_keywords` | UGC 热词和关联标签 |
| `user_events` | 用户行为事件：曝光、试戴、收藏、点赞、下单等 |
| `push_audits` | 商户对爆款推送卡片的审核状态 |

## 4. 数据初始化

启动服务后调用：

```bash
curl -X POST http://127.0.0.1:8000/api/db/init
```

返回示例：

```json
{
  "tables": {
    "hand_templates": 13,
    "styles": 25,
    "evaluation_pairs": 13,
    "style_tags": 150,
    "style_signals": 75,
    "ugc_keywords": 4,
    "user_events": 0,
    "push_audits": 0
  }
}
```

也可以查看：

```bash
curl http://127.0.0.1:8000/api/db/summary
```

## 5. 主要接口

### 5.1 数据集接口

```http
GET /api/evaluation-dataset
```

返回 xlsx 解析后的完整种子数据：

- `hand_templates`
- `styles`
- `pairs`

```http
GET /api/evaluation-pairs
```

只返回真实存在的 13 组手图/款式图配对。

### 5.2 数据库查询接口

```http
GET /api/db/styles
```

查询结构化款式数据。

```http
GET /api/db/events
```

查询用户行为流水。

```http
POST /api/db/tag-seed-styles
```

对官方 25 个款式调用标签提取，并写回 `styles/style_tags`。如果 Gemini/Qwen key 不可用，会回退到稳定标签兜底，响应中的 `analysis_modes` 会显示实际来源。

### 5.3 推荐接口

```http
POST /api/recommendations
```

当前推荐已经读取 SQLite，不再使用静态款式 mock。

推荐使用的数据：

```text
styles
+ style_tags
+ style_signals
```

请求示例：

```json
{
  "user_id": "u1",
  "skin_tone": "暖黄",
  "hand_shape": "短宽",
  "query": "约会显白猫眼",
  "limit": 4
}
```

### 5.4 用户行为接口

```http
POST /api/events
```

写入用户行为事件。

支持的 `event_type`：

- `exposure`
- `try_on`
- `favorite`
- `like`
- `dislike`
- `order`

请求示例：

```json
{
  "user_id": "u1",
  "style_id": "style-seed-021",
  "event_type": "try_on",
  "source": "user_h5"
}
```

```http
GET /api/events/stats
```

按款式聚合用户行为，输出试戴率、收藏率、下单率。

### 5.5 爆款推送接口

```http
GET /api/push-cards
```

当前爆款推送已经读取 SQLite，不再使用 `mock/operations.py`。

生成推送卡片使用的数据：

```text
styles
+ style_tags
+ style_signals
+ user_events
+ push_audits
```

```http
POST /api/push-cards/{push_id}/audit
```

写入商户审核状态。状态会持久化到 `push_audits`。

### 5.6 复盘报告接口

```http
POST /api/report
```

当前报告上下文来自 SQLite：

```text
user_events 聚合统计
+ push_cards 动态爆款卡片
+ styles/style_signals 热度数据
+ push_audits 审核状态
```

如果配置了 Gemini，报告由 Gemini 基于数据库上下文生成；如果没有配置模型，则返回 `generation_mode = "db_mock"` 的规则版报告。

## 6. 模型接口状态

| 能力 | 当前状态 |
| --- | --- |
| 款式标签提取 `/api/extract-tags` | 支持 Gemini，失败回退 mock |
| 手部分析 `/api/analyze-hand` | 支持 Qwen VL，失败回退 mock |
| 推荐 `/api/recommendations` | 读取 SQLite |
| AI 试戴 `/api/try-on` | 可接真实图片模型；未开启时返回本地 SVG 兜底图 |
| 裸手模板合成 `/api/generate-composite` | 可接真实图片模型；未开启时返回本地 SVG 兜底图 |
| 爆款推送 `/api/push-cards` | 读取 SQLite |
| 复盘报告 `/api/report` | 读取 SQLite，可接 Gemini |

## 7. 当前剩余 mock

已经删除：

- `backend/app/mock/styles.py`
- `backend/app/mock/operations.py`

仍然保留 mock/规则兜底的地方：

- `image_generation.py`：未开启真实图片模型时返回本地 SVG 兜底图。
- `tag_extractor.py`：未配置 Gemini 或调用失败时回退 mock。
- `hand_analyzer.py`：未配置 Qwen 或调用失败时回退 mock。
- `operations.py`：未配置 Gemini 时，复盘报告使用数据库规则版 `db_mock`。

这些不是废弃 mock，而是 Demo 稳定性兜底。

## 8. 下一步建议

优先级从高到低：

1. 配置可用的图片生成模型 key，验证 `image_generation.py` 的真实生成路径。
2. 把 `/api/extract-tags` 的真实模型输出写回 `styles/style_tags`，让标签库从 seed 标签升级为模型标签。
3. 增加事件模拟脚本，一键写入曝光、试戴、收藏、下单，方便演示爆款变化。
4. 增加简单数据看板页面或导出接口，方便产品/前端可视化查看 SQLite 数据。
