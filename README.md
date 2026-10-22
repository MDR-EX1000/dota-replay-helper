# Dota 2 对黑助手

本地解析 Dota 2 重放（`.dem`），统计玩家数据、计算评分，并按规则生成 5v5 对黑阵容。

## 数据流

```
dem/*.dem
   │  manta 本地解析
   ▼
json/match_*.json          （本地，含 SteamID，git 忽略）
   │
   ├── stats.py      → player_stats.csv / .html（本地，git 忽略）
   ├── balance.py    → 每人评分与分队建议
   ├── roll.py       → 规则化 roll，终端输出
   └── make_web.py   → docs/index.html（公开网页）
                            │
                            ▼
                     GitHub Pages
```

## 目录

仓库根目录就是 `C:\Users\admin\Desktop\replay`。

```
replay/
├── cli.py                     # 统一 CLI（stats/web/deploy/roll/parse）
├── stats.py / balance.py / roll.py / make_web.py
├── aliases.json               # 多账号合并（仅名字，不含 SteamID）
├── baselines.json             # 核心/酱油表现分基准
├── docs/index.html            # 公开网页（GitHub Pages 源）
├── mantatool/                 # Go 解析器源码与 parse.exe
├── dem/                       # .dem 重放（git 忽略）
├── json/                      # 解析结果（含 SteamID，git 忽略）
├── player_stats.csv / .html   # 本地汇总表（git 忽略）
├── manta/                     # 上游解析库（git 忽略）
└── 一键统计.bat / 一键打开网页.bat / 一键发布到GitHub.bat
```

| 路径 | 说明 |
|---|---|
| `cli.py` | 统一入口：`stats` / `ratings` / `web` / `publish` / `deploy` / `roll` / `parse` |
| `stats.py` | 汇总玩家数据（胜率、KDA、GPM/XPM、伤害/经济等） |
| `balance.py` | 计算 Elo + 表现分，枚举并排序 5v5 分法 |
| `roll.py` | 规则化 roll（R1–R5），只在合格方案里随机 |
| `make_web.py` | 生成三 Tab 网页到 `docs/index.html` |
| `aliases.json` | 同一玩家多账号合并配置 |
| `baselines.json` | 核心 / 酱油的表现分基准值，可分别调整 |
| `mantatool/parse.go` | 重放解析器（Go + manta），输出 JSON |
| `一键发布到GitHub.bat` | 一键生成网页并发布到 GitHub Pages |

## 一键发布

双击：

```
一键发布到GitHub.bat
```

它会依次执行：

1. 重新统计并生成 `docs/index.html`
2. `git add/commit`
3. `git push` 到 origin
4. 通过 `gh` 启用或更新 GitHub Pages（`main` / `docs`）

首次使用需要：

```bash
gh auth login -h github.com
git remote add origin git@github.com:用户名/仓库.git
```

发布后地址：

```
https://用户名.github.io/仓库名/
```

## 常用命令（可选）

```bash
python cli.py stats          # 汇总统计
python cli.py ratings        # 查看评分
python cli.py web            # 生成并打开网页
python cli.py publish        # 生成并起局域网服务器（只服务 docs/）
python cli.py deploy         # 生成 + 提交 + 推送 + Pages
python cli.py roll "A" ... "J"
python cli.py parse path\to\x.dem
```

## 评分口径

```
综合分 = 0.6 × Elo + 0.4 × 表现分
表现分 = KDA 40% + GPM 15% + XPM 15% + 伤害/经济 30%
基准：1000（Elo 初始分、表现分中心、场次收缩目标一致）
```

表现分按位置设基准（核心 / 酱油，见 `baselines.json`，可直接改），并按场次 `n/(n+5)` 收缩。胜率只展示，不参与评分，避免与 Elo 重复计算。

## 为什么 `.dem` 不进 git

- 单个重放 30–140 MB，8 场就约 550 MB；100 场会到 8 GB 以上
- git 对二进制文件按完整副本存储，历史会迅速膨胀
- 重放可重新下载，不需要版本化

本仓库只跟踪代码、配置和公开网页。如需长期归档重放，建议单独备份到网盘/对象存储；确需纳入 git 时再改用 Git LFS（并准备支持 LFS 的远端）。

## 公开仓库与隐私

仓库公开，但以下内容**不会进入 git**：

- `dem/`：比赛重放
- `json/`：解析结果，含 SteamID
- `player_stats.csv`：含 SteamID
- `manta/`：上游解析库
- `aliases.json` 中只保留玩家名映射，不含 SteamID

公开的只有 `docs/index.html`，其中是玩家名、评分和统计，不含 SteamID。

## 已知限制

- 目前样本较少（8 场），评分区分度有限
- 位置（核心/酱油）按每场净资产排名推断，非人工标注
- 玩家名含特殊字符时，脚本支持模糊匹配
