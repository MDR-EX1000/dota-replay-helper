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
                     腾讯云 CloudBase
```

## 目录

仓库根目录就是 `C:\Users\admin\Desktop\replay`。

```
replay/
├── stats.py / balance.py / roll.py / make_web.py
├── deploy_tcb.py              # 腾讯云发布
├── cloudbase.json             # 腾讯云环境 ID 与访问域名
├── aliases.json               # 多账号合并（仅名字，不含 SteamID）
├── baselines.json             # 核心/酱油表现分基准
├── hero_names_zh.json         # 英雄英文 key → 中文名
├── docs/index.html            # 公开网页
├── mantatool/                 # Go 解析器源码与 parse.exe
├── dem/                       # .dem 重放（git 忽略）
├── json/                      # 解析结果（含 SteamID，git 忽略）
├── player_stats.csv / .html   # 本地汇总表（git 忽略）
├── manta/                     # 上游解析库（git 忽略）
└── 三个一键 bat
```

| 路径 | 说明 |
|---|---|
| `stats.py` | 汇总玩家数据（胜率、KDA、GPM/XPM、伤害/经济等） |
| `balance.py` | 计算 Elo + 表现分，枚举并排序 5v5 分法 |
| `roll.py` | 规则化 roll（R1–R5），只在合格方案里随机 |
| `make_web.py` | 生成三 Tab 网页到 `docs/index.html` |
| `deploy_tcb.py` | 生成 → 上传到腾讯云 CloudBase 静态托管 |
| `cloudbase.json` | 腾讯云环境 ID 与默认访问域名 |
| `aliases.json` | 同一玩家多账号合并配置 |
| `baselines.json` | 核心 / 酱油的表现分基准值，可分别调整 |
| `mantatool/parse.go` | 重放解析器（Go + manta），输出 JSON |
| `一键统计.bat` | 重新生成汇总表 |
| `一键打开网页.bat` | 重新生成并打开网页 |
| `一键发布到腾讯云.bat` | 生成网页并上传到腾讯云 CloudBase |

## 一键发布到腾讯云

双击：

```
一键发布到腾讯云.bat
```

它会重新生成网页，然后上传到 CloudBase 静态托管。

前置条件：

- 已执行过 `tcb login`，或配置了 `cloudbase.secret.json` 自动登录
- CloudBase 环境已开通静态网站托管
- `cloudbase.json` 中的 `env_id` 对应环境

当前访问地址：

```
https://unhappy-grouse-d3gsbs7inb2cb10d6-1514393073.tcloudbaseapp.com/
```

默认域名不需要备案；绑定自己的域名需要 ICP 备案。

## 手动运行（调试用）

```bash
python stats.py          # 汇总统计
python make_web.py       # 生成 docs/index.html
python deploy_tcb.py     # 发布到腾讯云
python roll.py "A" ... "J"
```

## 评分口径

```
综合分 = 0.6 × Elo + 0.4 × 表现分
表现分 = KDA 40% + GPM 15% + XPM 15% + 伤害/经济 30%
基准：1000（Elo 初始分、表现分中心、场次收缩目标一致）
```

表现分按位置设基准（核心 / 酱油，见 `baselines.json`，可直接改），并按场次 `n/(n+5)` 收缩。胜率只展示，不参与评分，避免与 Elo 重复计算。

## 数据统计口径

- 统计表默认按**胜率降序**，点击任意表头可切换排序（再点一次反向）
- **造成英雄伤害** = `m_flHeroDamage`，对敌方英雄造成的伤害，不含小兵/建筑
- **承受英雄伤害** = 战斗日志中敌方英雄对你造成的伤害，不含小兵/建筑
- **伤害/经济**、**承伤/经济** = 对应伤害 ÷ 净资产
- **常用英雄**显示中文名，映射来自 `hero_names_zh.json`

新增比赛时先解析重放：

```bash
mantatool\parse.exe "D:\...\replays\905xxxxxxx.dem"
```

然后双击 `一键统计.bat` 或 `一键发布到腾讯云.bat`。

## 为什么 `.dem` 不进 git

- 单个重放 30–140 MB，8 场就约 550 MB；100 场会到 8 GB 以上
- git 对二进制文件按完整副本存储，历史会迅速膨胀
- 重放可重新下载，不需要版本化

本仓库只跟踪代码、配置和公开网页。如需长期归档重放，建议单独备份到网盘/对象存储；确需纳入 git 时再改用 Git LFS（并准备支持 LFS 的远端）。

## 隐私与公开内容

即使仓库公开，以下内容也**不会进入 git**：

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
