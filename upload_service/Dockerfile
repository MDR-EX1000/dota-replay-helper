# Dota 2 对黑助手 —— 上传/解析/发布服务
#
# 由 build_cloudrun.py 组装上下文后部署：
#   python build_cloudrun.py --deploy
#
# 构建分两段：
#   1. golang：把 mantatool + manta 编成 Linux 解析器
#   2. node：运行 Web 服务，并带上 Python 脚本与 tcb CLI

FROM golang:1.23-bookworm AS parser
ENV CGO_ENABLED=0 \
    GO111MODULE=on \
    GOPROXY=https://goproxy.cn,direct \
    GOSUMDB=off
WORKDIR /src/mantatool
COPY app/manta /src/manta
COPY app/mantatool/go.mod app/mantatool/go.sum ./
RUN go mod download
COPY app/mantatool/ ./
RUN go build -trimpath -ldflags="-s -w" -o /out/parse .

FROM node:20-bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @cloudbase/cli@3.8.8 --no-audit --no-fund \
 && npm cache clean --force

WORKDIR /app
COPY app/ /app/
COPY service/server.js /app/server.js
COPY --from=parser /out/parse /app/mantatool/parse
RUN chmod +x /app/mantatool/parse

ENV PORT=8080 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    LANG=C.UTF-8
EXPOSE 8080
CMD ["node", "/app/server.js"]
