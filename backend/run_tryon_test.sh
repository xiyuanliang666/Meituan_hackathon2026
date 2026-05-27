#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== 1. 重启后端服务 ==="
kill $(lsof -t -i :8000) 2>/dev/null || true
sleep 1
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/nail_backend.log 2>&1 &
sleep 3

echo "=== 2. 健康检查 ==="
curl -s http://127.0.0.1:8000/health
echo ""

echo "=== 3. 正在生成试戴图（等待中...） ==="
curl -s -X POST http://127.0.0.1:8000/api/try-on \
  -H "Content-Type: application/json" \
  -d '{
    "hand_image_url": "http://p0.meituan.net/pilotimages/3cd4bc446f321574df68ce0a749b16b62603765.png",
    "style_image_url": "http://p1.meituan.net/pilotimages/7bb5bc0c2c741f9f0aa63787a601d7ad2604877.png"
  }' | python3 -m json.tool

echo ""
echo "=== 4. 结果文件 ==="
RESULT="storage/generated/try-on/b83b523ad9.png"
if [ -f "$RESULT" ]; then
    sips -g pixelWidth -g pixelHeight "$RESULT" 2>/dev/null
    ls -lh "$RESULT"
    echo ""
    echo "浏览器打开: http://127.0.0.1:8000/static/generated/try-on/b83b523ad9.png"
else
    echo "未找到结果文件"
fi

echo ""
echo "=== 5. 查看错误日志（如失败） ==="
echo "tail -20 /tmp/nail_backend.log"
