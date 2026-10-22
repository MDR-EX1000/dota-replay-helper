# Dota 2 对黑助手

本地解析 Dota 2 重放（`.dem`），统计玩家数据、计算评分，并按规则生成 5v5 对黑阵容。

## 数据流

```
dem/*.dem
   │  （manta 本地解析）
   ▼
json/match_*.json
   │
   ├── stats.py      → player_stats.csv / .html
   ├── balance.py    → 每人综合评分与分队建议
   ├── roll.py       → 规则化 roll，终端输出
   └── make_web.py   → index.html（三 Tab 动态网页）
```

## 目录

仓库根目录就是 `C:\Users\admin\Desktop\replay`。

```
replay/
├── stats.py / balance.py / roll.py / make_web.py
├── aliases.json               # 多账号合并
├── baselines.json             # 核心/酱油表现分基准
├── mantatool/                 # Go 解析器源码与 parse.exe
├── dem/                       # .dem 重放（git 忽略）
├── json/
│   ├── match_*.json           # 结构化结果（入库）
│   └── match_*_raw.json       # 原始实体转储（git 忽略）
├── index.html                 # 生成的三 Tab 网页
├── player_stats.csv / .html   # 生成的汇总表
├── manta/                     # 上游解析库（git 忽略，按需 git clone）
└── 一键统计.bat / 一键打开网页.bat
```

| 路径 | 说明 |
|---|---|
| `stats.py` | 汇总玩家数据（胜率、KDA、GPM/XPM、伤害/经济等） |
| `balance.py` | 计算 Elo + 表现分，枚举并排序 5v5 分法 |
| `roll.py` | 规则化 roll（R1–R5），只在合格方案里随机 |
| `make_web.py` | 生成三 Tab 网页：数据统计 / Roll 阵容 / 规则说明 |
| `aliases.json` | 同一玩家多账号合并配置 |
| `baselines.json` | 核心 / 酱油的表现分基准值，可分别调整 |
| `mantatool/parse.go` | 重放解析器（Go + manta），输出 JSON |
| `一键统计.bat` | 重新生成汇总表 |
| `一键打开网页.bat` | 重新生成并打开网页 |

## 常用命令

```bash
# 汇总统计
python stats.py

# 查看评分
python balance.py

# 规则化 roll（10 个玩家名）
python roll.py "玩家1" "玩家2" ... "玩家10"

# 生成网页
python make_web.py
```

## 评分口径

```
综合分 = 0.6 × Elo + 0.4 × 表现分
表现分 = KDA 40% + GPM 15% + XPM 15% + 伤害/经济 30%
基准：1000（Elo 初始分、表现分中心、场次收缩目标一致）
```

表现分按位置设基准（核心 / 酱油，见 `baselines.json`，可直接改），并按场次 `n/(n+4)` 收缩。胜率只展示，不参与评分，避免与 Elo 重复计算。

## 为什么 `.dem` 不进 git

- 单个重放 30–140 MB，8 场就约 550 MB；100 场会到 8 GB 以上
- git 对二进制文件按完整副本存储，历史会迅速膨胀
- 重放可重新下载，不需要版本化

本仓库只跟踪代码、配置和小体积汇总产物。如需长期归档重放，建议单独备份到网盘/对象存储；确需纳入 git 时再改用 Git LFS（并准备支持 LFS 的远端）。

## 已知限制

- 目前样本较少（8 场），评分区分度有限
- 位置（核心/酱油）按每场净资产排名推断，非人工标注
- 玩家名含特殊字符时，脚本支持模糊匹配
