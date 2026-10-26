# -*- coding: utf-8 -*-
"""本地联调：把 .dem 按 4MB 分片传给服务，并轮询解析结果。

用法:
    python test_client.py <dem 文件> [endpoint] [口令]
"""

import json
import os
import sys
import time
import urllib.request

CHUNK = 4 * 1024 * 1024


def post(url, data, headers, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def get(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    path = sys.argv[1]
    endpoint = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8099").rstrip("/")
    code = sys.argv[3] if len(sys.argv) > 3 else "zgnb"
    name = os.path.basename(path)
    size = os.path.getsize(path)
    total = (size + CHUNK - 1) // CHUNK
    upload_id = os.urandom(16).hex()
    force = len(sys.argv) > 4 and sys.argv[4] == "force"

    print(f"上传 {name} ({size/1024/1024:.0f}MB, {total} 片) -> {endpoint}"
          + (" [force]" if force else ""))
    with open(path, "rb") as fp:
        for i in range(total):
            chunk = fp.read(CHUNK)
            headers = {
                "Content-Type": "application/octet-stream",
                "x-upload-code": code,
                "x-upload-id": upload_id,
                "x-chunk-index": str(i),
                "x-chunk-total": str(total),
                "x-file-name": name,
            }
            if force:
                headers["x-force"] = "1"
            status, data = post(endpoint + "/upload", chunk, headers)
            if status != 200:
                print("上传失败", status, data)
                return 1
            print(f"  {i+1}/{total}")

    status, data = post(
        endpoint + "/parse",
        json.dumps({"uploadId": upload_id, "force": force}).encode(),
        {"Content-Type": "application/json", "x-upload-code": code},
    )
    print("开始解析:", status, data)
    if status != 202:
        return 1
    job_id = data["jobId"]

    t0 = time.time()
    last = None
    while True:
        try:
            _, st = get(f"{endpoint}/status?jobId={job_id}")
        except Exception as exc:
            print("查询失败:", exc)
            time.sleep(2)
            continue
        if st.get("stage") != last:
            last = st.get("stage")
            print(f"  [{time.time()-t0:.1f}s] {st.get('state')} · {last}")
        if st.get("state") == "done":
            print(json.dumps(st.get("result"), ensure_ascii=False, indent=2))
            return 0
        if st.get("state") == "error":
            print("失败:", st.get("message"))
            return 1
        time.sleep(1.5)


if __name__ == "__main__":
    raise SystemExit(main())
