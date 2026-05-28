#!/bin/bash
# 美甲AI智能运营 - 一键启动脚本
# 同时启动后端 API 和前端静态服务器

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "🦘 美甲AI智能运营 - 启动中..."
echo "================================"

# 检查 Python 版本
PYTHON_BIN=""
if command -v python3.14 &>/dev/null; then
    PYTHON_BIN="python3.14"
elif [ -f "$HOME/.workbuddy/binaries/python/versions/3.14.3/bin/python3" ]; then
    PYTHON_BIN="$HOME/.workbuddy/binaries/python/versions/3.14.3/bin/python3"
elif command -v python3.12 &>/dev/null; then
    PYTHON_BIN="python3.12"
elif command -v python3.11 &>/dev/null; then
    PYTHON_BIN="python3.11"
elif command -v python3.10 &>/dev/null; then
    PYTHON_BIN="python3.10"
else
    echo "❌ 需要 Python 3.10+（当前代码使用了 str | None 语法）"
    echo "   请安装 Python 3.10+ 后重试"
    exit 1
fi

echo "✅ 使用 Python: $($PYTHON_BIN --version)"

# 设置后端虚拟环境
if [ ! -d "$BACKEND_DIR/.venv" ]; then
    echo "📦 创建虚拟环境..."
    $PYTHON_BIN -m venv "$BACKEND_DIR/.venv"
fi

echo "📦 安装后端依赖..."
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" -q

# 检查 .env
if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$BACKEND_DIR/.env.example" ]; then
        cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
        echo "⚠️  已从 .env.example 复制 .env，请配置 API Key"
    fi
fi

# 启动后端
echo ""
echo "🚀 启动后端 API (http://localhost:8000)..."
cd "$BACKEND_DIR"
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 等待后端就绪（最多等 10 秒）
echo -n "  等待后端就绪"
for i in $(seq 1 10); do
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo ""
        echo "✅ 后端启动成功"
        # 初始化数据库
        echo "📊 初始化数据库..."
        curl -s -X POST http://localhost:8000/api/db/init >/dev/null 2>&1 || true
        echo "✅ 数据库初始化完成"
        break
    fi
    echo -n "."
    sleep 1
done
if ! curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo ""
    echo "⚠️  后端可能还在启动中，请手动执行: curl -X POST http://localhost:8000/api/db/init"
fi

# 启动前端
echo ""
echo "🌐 启动前端服务 (http://localhost:3000)..."
cd "$FRONTEND_DIR"
$PYTHON_BIN -m http.server 3000 &
FRONTEND_PID=$!

echo ""
echo "================================"
echo "🎉 启动完成！"
echo ""
echo "  📱 入口页: http://localhost:3000"
echo "  📱 用户端: http://localhost:3000/user/"
echo "  💻 运营端: http://localhost:3000/admin/"
echo "  📡 API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo "================================"

# 优雅退出
cleanup() {
    echo ""
    echo "🛑 停止服务..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

# 保持脚本运行
wait
