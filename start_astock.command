#!/bin/bash
# AStock 启动脚本：双击即可同时启动后端和前端开发服务器
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
WEB_DIR="$ROOT_DIR/web_version"
BACKEND_DIR="$WEB_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/web_version/frontend"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    log "停止后端 (PID $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    log "停止前端 (PID $FRONTEND_PID)"
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup INT TERM

if command -v conda >/dev/null 2>&1; then
  # 尝试激活 astock_tk 环境以使用安装在其中的 akshare
  CONDA_BASE="$(conda info --base)"
  if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    # shellcheck source=/dev/null
    source "$CONDA_BASE/etc/profile.d/conda.sh"
    if conda env list | grep -q "^astock_tk"; then
      log "检测到 conda，正在激活环境 astock_tk"
      conda activate astock_tk >/dev/null 2>&1 || log "conda 激活 astock_tk 失败，改用系统 Python"
    else
      log "未找到 astock_tk 环境，改用系统 Python"
    fi
  fi
fi

log "切换目录到 $WEB_DIR"
cd "$WEB_DIR"

log "启动后端 uvicorn (端口 8000)"
uvicorn backend.app.main:app --reload --port 8000 &
BACKEND_PID=$!
sleep 1

log "切换目录到 $FRONTEND_DIR"
cd "$FRONTEND_DIR"

log "启动前端 npm run dev (端口 5173)"
npm run dev &
FRONTEND_PID=$!

log "后端 PID: $BACKEND_PID"
log "前端 PID: $FRONTEND_PID"
sleep 2
if command -v open >/dev/null 2>&1; then
  open "http://localhost:5173" >/dev/null 2>&1 || log "浏览器自动打开失败，请手动访问 http://localhost:5173"
else
  log "请手动打开浏览器访问 http://localhost:5173"
fi
log "按 Ctrl+C 可同时停止两个进程。"

wait $FRONTEND_PID
