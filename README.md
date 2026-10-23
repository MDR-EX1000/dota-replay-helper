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
                            │
              浏览器 AI 对话 → CloudBase 云函数 roll-ai
                            │
                            ▼
                 DeepSeek（deepseek-flash）
```

## 目录

仓库根目录就是 `C:\Users\admin\Desktop\replay`。

```
replay/
├── stats.py / balance.py / roll.py / make_web.py
├── deploy_tcb.py              # 腾讯云静态发布（发布前自动扫描新录像）
├── scan_new.py                # 扫描 replays 目录，解析新增练习赛
├── deploy_ai.py               # 部署 AI 云函数
├── cloudfunctions/roll-ai/    # DeepSeek 代理云函数
├── cloudbaserc.example.json   # 云函数配置模板（真实配置不入库）
├── cloudbase.json             # 环境 ID、访问域名、AI 端点
├── aliases.json               # 多账号合并（仅名字，不含 SteamID）
├── baselines.json             # 核心/酱油表现分基准
├── hero_names_zh.json         # 英雄英文 key → 中文名
├── mmr.json                   # 玩家 MMR 登记（默认空 = 未登记）
├── docs/index.html            # 公开网页
├── docs/vendor/               # marked + DOMPurify（本地托管）
├── mantatool/                 # Go 解析器源码与 parse.exe
├── dem/                       # .dem 重放（git 忽略）
├── json/                      # 解析结果（含 SteamID，git 忽略）
├── player_stats.csv / .html   # 本地汇总表（git 忽略）
├── manta/                     # 上游解析库（git 忽略）
└── 四个一键 bat
```

| 路径 | 说明 |
|---|---|
| `stats.py` | 汇总玩家数据（胜率、KDA、GPM/XPM、伤害/经济等） |
| `balance.py` | 计算 Elo + 表现分，枚举并排序 5v5 分法 |
| `roll.py` | 规则化 roll（R1–R5），只在合格方案里随机 |
| `make_web.py` | 生成三 Tab 网页到 `docs/index.html` |
| `deploy_tcb.py` | 扫描新录像 → 生成 → 上传到腾讯云 CloudBase |
| `scan_new.py` | 扫描 `replays` 目录，解析新增练习赛并写入 `json/` |
| `deploy_ai.py` | 部署 `roll-ai` 云函数，写入 AI 端点并重新发布网页 |
| `cloudfunctions/roll-ai/` | DeepSeek 代理：对话、工具调用、限流 |
| `cloudbase.json` | 环境 ID、默认访问域名、`ai_endpoint` |
| `aliases.json` | 同一玩家多账号合并配置 |
| `baselines.json` | 核心 / 酱油的表现分基准值，可分别调整 |
| `mmr.json` | 玩家 MMR 登记，默认空（全部显示 `-`） |
| `mantatool/parse.go` | 重放解析器（Go + manta），输出 JSON |
| `一键统计.bat` | 重新生成汇总表 |
| `一键打开网页.bat` | 重新生成并打开网页 |
| `一键发布到腾讯云.bat` | 生成网页并上传到腾讯云 CloudBase |
| `一键部署AI.bat` | 部署云函数、配置 Key、更新 AI 端点 |

## 一键发布到腾讯云

双击：

```
一键发布到腾讯云.bat
```

它会：

1. 扫描 Dota `replays` 目录最近 7 天的新 `.dem`
2. 只解析新增的练习赛；**已经解析过的会跳过**
   - `scan_state.json` 记录文件大小/修改时间
   - 即使状态文件丢失，只要 `json/match_*.json` 已存在也不会重复解析
3. 重新生成统计和网页
4. 上传到 CloudBase 静态托管

重放目录默认是 `D:\Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\replays`，可用环境变量 `DOTA_REPLAY_DIR` 覆盖。

前置条件：

- 已执行过 `tcb login`，或配置了 `cloudbase.secret.json` 自动登录
- CloudBase 环境已开通静态网站托管
- `cloudbase.json` 中的 `env_id` 对应环境

当前访问地址：

```
https://unhappy-grouse-d3gsbs7inb2cb10d6-1514393073.tcloudbaseapp.com/
```

默认域名不需要备案；绑定自己的域名需要 ICP 备案。

## AI 匹配助手

Roll 出结果后，页面底部会出现「交互式匹配改进」。打开后可以：

- 和 DeepSeek 流式对话，回复逐字出现
- 助手回复按 Markdown 渲染（列表、粗体、代码块、表格），并用 DOMPurify 过滤 HTML
- AI 提出具体阵容时调用 `display_match`，聊天中弹出对局卡片
- 卡片上点「采用此阵容」可更新主结果区

约束：

- 只调整当前已选的 10 人，不换人
- 模型 `deepseek-flash`，通过 CloudBase 云函数 `roll-ai` 代理调用
- DeepSeek Key 只存在云函数环境变量，网页和 git 中都看不到
- 页面公开，任何人拿到链接都能使用；云函数有限流（每 IP 6 次/秒）和 3000 token 上限

部署 / 更新 AI 后端：

```
一键部署AI.bat
```

它会从 `~/.claude/settings.json` 读取当前 DeepSeek Key，部署云函数，更新 `ai_endpoint` 并重新发布网页。真实配置写入本地的 `cloudbaserc.json`（已在 `.gitignore`）。

## 手动运行（调试用）

```bash
python stats.py          # 汇总统计
python make_web.py       # 生成 docs/index.html
python scan_new.py       # 手动扫描新录像
python deploy_tcb.py     # 发布到腾讯云（会先自动扫描）
python deploy_ai.py      # 部署/更新 AI 云函数并重新发布
python roll.py "A" ... "J"
```

## 评分口径

```
综合分 = 0.4 × Elo + 0.3 × 表现分 + 0.3 × MMR分

MMR分 = 1000 + (MMR − 3000) / 30（未登记默认按 2000 计算）
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
- **MMR** 来自 `mmr.json`，未登记的玩家显示 `-`。登记格式：

```json
{
  "玩家名或SteamID": 4500
}
```

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

AI 对话时，当前 10 人的玩家名、评分和统计会发送给 DeepSeek；不会发送 SteamID。DeepSeek Key 只保存在 CloudBase 云函数环境变量中，不进入页面和 git。

## 已知限制

- 目前样本较少（8 场），评分区分度有限
- 位置（核心/酱油）按每场净资产排名推断，非人工标注
- 玩家名含特殊字符时，脚本支持模糊匹配
