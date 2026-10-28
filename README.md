# Dota 2 对黑助手

本地解析 Dota 2 重放（`.dem`），统计玩家数据、计算评分，并按规则生成 5v5 对黑阵容。
也可以在网页上直接上传 `.dem`，由云端自动解析并发布。

本地开发版本已加入玩家个人资料、账号身份修正、缺失数据处理、七种单场称号和 Steam 头像。完整变更、数据口径和验收方式见 [本轮改动说明](CHANGELOG.md)。当前仍处于本地验收阶段，尚未推送或发布。

本机工具已准备为项目内安装；交接内容、只读预检和正式发布前的顺序见 [发布准备与交接](PREPARE_RELEASE.md)。可双击 `一键发布预检.bat` 查看就绪状态，该入口不会登录或发布。

也可双击 `一键本地验收.bat` 运行测试并生成两场样例预览，不依赖全局 npm/tcb，不会连接腾讯云或刷新 Steam 头像。

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

网页「上传录像」→ 云托管 dota-upload（分片上传 + Linux 解析器）
                            │
                            ├── state/（比赛数据持久化，含 SteamID）
                            └── 重建 docs/ → 自动发布静态托管
```

## 目录

以下结构以仓库根目录为基准；本地路径可以自行选择。

```
replay/
├── stats.py / balance.py / roll.py / make_web.py / make_match_data.py
├── player_data.py             # 共享身份识别与缺失感知统计
├── match_titles.py / web_safety.py  # 单场称号与页面序列化
├── steam_profiles.py          # 随录像变化刷新头像，公开缓存
├── steam.secret.example.json  # Steam Key 配置模板，真实配置忽略
├── legacy_identities.json     # 人工确认旧昵称对应的账号
├── CHANGELOG.md / tests/      # 本轮变更说明与回归测试
├── PREPARE_RELEASE.md / release_preflight.py  # 交接清单与离线发布预检
├── tcb.cmd / npm.cmd / tools/ # 项目内工具入口与安装脚本
├── reparse_known.py           # 安全重解析已有比赛
├── make_name_maps.py          # 中文装备/技能名映射
├── item_names_zh.json / item_aliases.json / item_ids.json
├── deploy_tcb.py              # 腾讯云静态发布（发布前自动扫描新录像）
├── scan_new.py                # 扫描 replays 目录，解析新增练习赛
├── deploy_ai.py               # 部署 AI 云函数
├── build_cloudrun.py          # 组装并部署上传/解析服务（云托管）
├── sync_cloud.py              # 把网页上传的比赛同步回本地（不发布）
├── upload_service/            # 上传/解析服务源码（Node + Dockerfile）
├── state/                     # 云端解析服务持久化（含 SteamID，公开可读，git 忽略）
├── cloudfunctions/roll-ai/    # DeepSeek 代理云函数
├── cloudbaserc.example.json   # 云函数配置模板（真实配置不入库）
├── cloudbase.json             # 环境 ID、访问域名、AI 端点
├── aliases.json               # 多账号合并（名字与 SteamID 映射）
├── baselines.json             # 核心/酱油表现分基准
├── hero_names_zh.json         # 英雄英文 key → 中文名
├── mmr.json                   # 玩家 MMR 登记（默认空 = 未登记）
├── docs/index.html            # 公开网页
├── docs/player_profiles.js / .css  # 玩家资料页源码
├── docs/hero_portraits.json / item_icons.json  # 在线图片地址映射
├── docs/vendor/               # marked + DOMPurify（本地托管）
├── docs/data/matches.js       # 比赛明细数据（公开，无 SteamID）
├── mantatool/                 # Go 解析器源码与 parse.exe
├── dem/                       # .dem 重放（git 忽略）
├── json/                      # 解析结果（含 SteamID，git 忽略）
├── player_stats.csv / .html   # 本地汇总表（git 忽略）
├── manta/                     # 上游解析库（git 忽略）
└── 五个一键 bat
```

| 路径 | 说明 |
|---|---|
| `stats.py` | 汇总玩家数据（胜率、KDA、GPM/XPM、伤害/经济等） |
| `balance.py` | 计算 Elo + 表现分，枚举并排序 5v5 分法 |
| `roll.py` | 规则化 roll（R1–R5），只在合格方案里随机 |
| `make_web.py` | 生成统计、玩家资料、比赛明细等六 Tab 网页到 `docs/index.html` |
| `sync_cloud.py` | 补回网页上传的比赛到本地 `json/`，不发布 |
| `make_match_data.py` | 从比赛 JSON 生成 `docs/data/matches.js` |
| `reparse_known.py` | 只重解析已有比赛，补齐事件/经济/装备时间线 |
| `make_name_maps.py` | 从本地 VPK 生成中文装备/技能名 |
| `deploy_tcb.py` | 扫描新录像 → 生成 → 上传到腾讯云 CloudBase |
| `scan_new.py` | 扫描 `replays` 目录，解析新增练习赛并写入 `json/` |
| `deploy_ai.py` | 部署 `roll-ai` 云函数，写入 AI 端点并重新发布网页 |
| `cloudfunctions/roll-ai/` | DeepSeek 代理：对话、工具调用、限流 |
| `cloudbase.json` | 环境 ID、访问域名、AI/上传端点，可选 `upload_service_name` |
| `aliases.json` | 同一玩家多账号合并配置 |
| `baselines.json` | 核心 / 酱油的表现分基准值，可分别调整 |
| `mmr.json` | 玩家 MMR 登记，默认空（全部显示 `-`） |
| `mantatool/parse.go` | 重放解析器（Go + manta），输出 JSON |
| `一键统计.bat` | 重新生成汇总表 |
| `一键打开网页.bat` | 重新生成并打开网页 |
| `一键发布到腾讯云.bat` | 生成网页并上传到腾讯云 CloudBase |
| `一键部署AI.bat` | 部署云函数、配置 Key、更新 AI 端点 |
| `一键同步.bat` | 补回网页上传的比赛到本地（不发布） |

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

重放目录默认是 `C:/Users/admin/Desktop/replay/dem`（唯一解析来源），可用环境变量 `DOTA_REPLAY_DIR` 覆盖。

前置条件：

- 已执行过 `tcb login`，或配置了 `cloudbase.secret.json` 自动登录
- CloudBase 环境已开通静态网站托管
- `cloudbase.json` 中的 `env_id` 对应环境

当前访问地址：

```
https://unhappy-grouse-d3gsbs7inb2cb10d6-1514393073.tcloudbaseapp.com/
```

默认域名不需要备案；绑定自己的域名需要 ICP 备案。

## 比赛明细

「比赛明细」提供单场详情：

- 比赛列表 + 详情：胜负、比分、时长、模式
- 总览：双方 KPI、记分板、英雄中文名、KDA、净资产、GPM/XPM、正反补、装备
- 经济：团队经济差/经验差、双方玩家净资产曲线
- 战斗：造成/承受伤害、伤害类型构成、推塔、眩晕、治疗、眼位
- 装备：终局装备 + 购买时间线，可过滤消耗品/只看成装
- 事件：击杀、推塔、兵营、肉山、不朽盾时间线

数据由 `make_match_data.py` 生成到 `docs/data/matches.js`，发布时自动上传。页面只包含公开字段，**不包含 SteamID**。

扩展解析器或修改事件口径后，可重解析已有比赛：

```bash
python reparse_known.py --all-known
```

## 玩家资料

在“玩家资料”搜索昵称并选择玩家，或点击统计表、对局记分板中的玩家名进入。选人区的“资料”链接不会改变已选名单。

资料页分为五个栏目：

| 栏目 | 内容 |
|---|---|
| 概览 | Steam 头像、最新录像昵称/固定别名、定位、登记 MMR、综合分、胜负、KDA、GPM/XPM、伤害、近期状态、常用英雄、称号累计 |
| 比赛记录 | 按英雄及结果筛选，每页 10 场，展示终局装备和称号，可进入比赛详情 |
| 英雄统计 | 出场次数、胜率、KDA、GPM/XPM、最近使用时间 |
| 队友 | 同队场次、胜负、同队胜率、最近同队时间，可进入队友资料 |
| 对手 | 交手场次、胜负、对抗胜率、最近交手时间，可进入对手资料 |

队友和对手的胜负均以当前资料页玩家为视角；未知结果不计入胜率分母，阵营缺失时不推断队友/对手关系。缺失数值不当成 0，平均值附有效样本数。所有数据仅覆盖本项目录入的练习赛，不代表完整天梯战绩。

MMR 仍通过 `mmr.json` 手动登记。本轮没有加入段位查询或自动估计 MMR；评分权重维持原有规则。

资料链接格式为 `#player=p_…&view=overview`，其余栏目为 `matches`、`heroes`、`peers`、`opponents`。链接使用公开玩家标识，支持直接打开和浏览器返回。

英雄和物品图片来自 Steam CDN，本地只保存地址映射（`docs/hero_portraits.json`、`docs/item_icons.json`），不下载图片文件。图片加载失败时保留文字或占位。人物头像、英雄及物品图片分别处理，后两者不需要 Steam API Key。界面结构参考及实现细节见 [本轮改动说明](CHANGELOG.md)。

## 本地身份修正与单场称号（v1）

内部按有效 SteamID 识别账号，昵称只用于展示。同账号改名会合并；重名的不同账号分别统计，并以公开标识后缀区分。公开页面只输出散列后的玩家标识，不输出 SteamID；该标识用于关联记录，不承诺匿名性。

`aliases.json` 中的昵称映射只修改显示名；需要合并多个账号时，为这些 **SteamID** 配置相同的名称。只有昵称的历史数据会标记“身份待确认”，不会凭重名自动归并。人工确认后可在 `legacy_identities.json` 写入 `{"旧昵称": "SteamID64"}`；这个配置会作用于所有同名旧记录，存在重名时应先逐场核实。

Go 解析器输出 schema 3：未读到的数值保留 `null`，并记录 `data_quality.missing_fields`；真实零值保留为 0。旧版结果的字段来源无法凭输出核实，建议重解析。统计使用每项指标的有效场次，网页悬停 GPM/XPM/KDA/伤害经济比可查看样本数。评分核心指标不完整或身份待确认时，综合分暂按 1000 标为暂定；不使用缺失值充当零分。

比赛总览新增七种称号：MVP、富豪、破敌、破军、偏将、补王、英魂。点击徽章可查看本场依据，展开“称号规则与数据说明”可查看公式和停评原因。

- 仅评选双方各 5 人、时长超过 3 分钟、胜负已知的比赛；一人可多称号。
- 富豪取全场净资产最高；破敌取胜方击杀最高；补王取全场反补最高；偏将取全场辅助分最高。辅助分 = 助攻 + 2×插眼 + 3×排眼。
- 破军取全场敌方塔最后一击数最高。排除小兵击塔和反补；可唯一归属的蛇棒计给暗影萨满，未知召唤物使该项暂不评选。正补塔数全员相同时不颁发。
- 综合分 = 100×（30% KDA + 25% 英雄伤害 + 15% 推塔伤害 + 10% 眩晕 + 10% 治疗 + 10% 辅助分），KDA = (击杀+助攻)/(死亡+1)。各项除以全场最高值，最高为零时该项记零。
- 胜方综合分第一为 MVP，败方第一为英魂，各一人；使用未舍入分数，同分依次比较 KDA、击杀、较少死亡、较小比赛内编号。
- 基础称号允许并列，最高为零不颁发。依赖数据不完整时，暂停对应称号；不影响独立指标的称号。

称号名称参考 11 平台经典体系；上述综合分、辅助分、并列处理和适用阵营是 **本项目自拟 v1 规则**，不代表 11 平台原始算法。称号分与对黑匹配评分相互独立，当前只展示单场称号。

两份验证录像位于 `replay/` 时，只在本地解析与预览：

```powershell
.\mantatool\parse.exe --out .\json\feature_validation .\replay\9064327315.dem .\replay\9064411460.dem
python make_web.py --matches-dir json/feature_validation --output-dir cloudrun_test/preview --local-preview
python -m http.server 8765 --bind 127.0.0.1 --directory cloudrun_test/preview
```

浏览器访问 `http://127.0.0.1:8765/#match=9064411460`。`--local-preview` 清空云端上传和 AI 接口，仅生成本地静态文件；不会推送、发布，也不会覆盖已跟踪的 `docs/` 历史数据。无有效比赛时生成器会保留现有页面并退出。解析器需先按 `mantatool/go.mod` 的本地 manta 依赖完成构建。

验证命令：`python -B -m unittest discover -s tests -v`、`node --test tests/player_profiles.test.cjs`；在 `mantatool/` 中运行 `go test .`。

## Steam 头像

在 [Steam 官方页面](https://steamcommunity.com/dev/apikey)申请普通用户 Web API Key；域名填写本项目实际网站的主机名（不含 `https://` 和路径）。本地复制 `steam.secret.example.json` 为 `steam.secret.json`，将 Key 填入 `api_key`；也支持环境变量 `STEAM_WEB_API_KEY`，环境变量优先。`steam.secret.json` 已被 Git 忽略，Key 不会进入网页或头像缓存。

头像在成功录入新录像、或某场录像解析数据变化后的页面生成阶段更新，仅查询相关选手；普通页面重建使用缓存，不会按打开页面次数请求 Steam。Steam 昵称不覆盖录像昵称或人工别名。一个玩家有多个合并账号时，使用其比赛时间最新的账号查询头像。

`state/steam_profiles.json` 保存公开玩家标识、Steam CDN 头像 URL、同步时间和录像内容指纹，不保存 Key、SteamID 或 Steam 返回的其他个人资料。同步失败时保留原缓存，不阻断比赛处理；没有头像或图片加载失败时显示昵称首字。部分账号未返回头像时会保留已有头像，并在下次页面生成时重试未完成的同步。

本地与云端同步会保留头像缓存。将来部署上传服务时，可设置服务端环境变量 `STEAM_WEB_API_KEY`；现有构建脚本也支持从本地配置读取 Key 写入私有镜像的 `secrets.json`。当前只进行本地验证，不会自动部署。

如需在生成页面时禁止查询 Steam 头像 API，添加 `--no-avatar-refresh`；浏览器仍按需加载在线图片。`--local-preview` 关闭云端上传和 AI 接口，头像同步仍遵循录像变化规则。

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

## 发布路径

两条路径都会更新同一份线上数据，可以混用：

| 路径 | 入口 | 做什么 |
|---|---|---|
| 本地发布 | `一键发布到腾讯云.bat`（`deploy_tcb.py`） | 扫描 `dem/` → 解析新练习赛 → 先从云端补回网页上传的比赛 → 生成统计/网页 → 上传 `state/` + `docs/` |
| 网页上传 | 网页「上传录像」Tab | 分片上传 → 云端解析 → 自动生成并发布，同时更新云端 `state/` |

- 网页上传过的比赛只存在云端 `state/`；本地发布前会自动把它们补回 `json/`（不覆盖本地原始文件），所以不会把线上数据覆盖丢。
- 改了 `make_web.py` / `stats.py` 后，除了本地发布，还要执行 `python build_cloudrun.py --deploy`
  更新云托管镜像——网页上传是用镜像里的脚本重新生成页面的，否则会发布回旧逻辑。
- 改了 `mmr.json` / `aliases.json` / `baselines.json` / 英雄物品映射等配置也一样：本地发布后，
  云端会检测到配置哈希与镜像不一致，**拒绝网页上传发布**并提示先更新镜像。
  这是防止网页上传用旧配置覆盖你的修改；更新镜像后自动恢复。
- 两边发布前都会重新读取云端 `state/index.json`；如果对方刚发布了新比赛，会中止并要求重试，
  避免旧数据后写入覆盖新比赛。
- 本地发布和网页上传都只接收练习赛，并按比赛 ID 去重。
- 只生成不发布：`一键统计.bat`、`一键打开网页.bat`；只部署 AI：`一键部署AI.bat`（它最后也会走一次 `deploy_tcb.py`）。

### 本地同步

网页上传只写云端 `state/`。以下时机会自动补回本地 `json/`：

- `一键发布到腾讯云.bat`：发布前同步
- `一键统计.bat` / `一键打开网页.bat`：先生成统计，同步失败会跳过并继续
- 手动：`python sync_cloud.py` 或 `一键同步.bat`

同步只补本地缺失的比赛，不覆盖本地已有的原始 JSON，也不会自动发布。

## 上传录像（网页）

统计页顶部新增「上传录像」Tab：

1. 从 Dota 2 客户端下载重放，文件名为比赛 ID（如 `9061520546.dem`）
2. 输入上传口令（见群公告），可勾选「记住」下次自动填
3. 点击选择或把文件拖进上传区；选中后会先查重，已存在会直接提示
4. 分片上传（4MB/片，失败自动重试 3 次），可随时取消
5. 渲染完成后显示比赛卡片，可直接跳到本场明细

口令提示文字在 `cloudbase.json` 的 `upload_hint` 配置；默认只写「口令见群公告」，
不要直接把口令写进公开页面，否则口令就失去作用了。

构建上传服务前必须明确设置 `UPLOAD_CODE` 或填写本地 `upload_code.txt`，不再回退到默认口令。构建前也会核对完整原始数据，避免打包两场验证数据或其他电脑的旧目录。

限制与行为：

- 只接受练习赛（`lobby_type=1`、10 人、时长 > 0）
- 单文件上限 300MB，口令错误直接拒绝
- 解析成功后删除云端录像分片，只保留比赛数据（`state/`，含 SteamID）
- 失败不会写入统计，也不会发布

服务端代码在 `upload_service/server.js`，镜像由云端构建：

```bash
python build_cloudrun.py --deploy   # 组装 + 提交云端构建部署
```

首次启动时服务会把自己的公网域名写进 `cloudbase.json` 的 `upload_endpoint`，
`make_web.py` 生成页面时注入该地址。

安全说明：`cloudbase.apikey`、上传口令和密钥都在 `cloudrun_build/app/secrets.json`，
只进入私有镜像，不提交 git。若泄露，请重新生成 CloudBase API Key 后重新部署。

## 手动运行（调试用）

```bash
python stats.py          # 汇总统计
python make_web.py       # 生成 docs/index.html
python scan_new.py       # 手动扫描新录像
python reparse_known.py --all-known  # 重解析已有比赛
python make_name_maps.py # 更新中文装备/技能名
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
- `aliases.json` / `mmr.json` / `stats.py` 含少量 SteamID（多账号与 MMR 登记用）

公开可读的有三类：

- `docs/index.html`、`docs/data/matches.js`：玩家名、评分、比赛事件和统计，**不含 SteamID**
- `state/match_*.json`：云端解析服务的完整比赛数据，**含 SteamID**（按当前配置不脱敏）
- CloudBase 环境 ID 与公开接口地址

发布脚本会在上传前检查 `matches.js`，发现 SteamID 会终止发布；`state/` 不在该检查范围内。

AI 对话时，当前 10 人的玩家名、评分和统计会发送给 DeepSeek；不会发送 SteamID。DeepSeek Key 只保存在 CloudBase 云函数环境变量中，不进入页面和 git。

## 已知限制

- 样本较少时，评分、英雄胜率及对抗胜率仅供已录入练习赛内参考
- 位置（核心/酱油）按每场净资产排名推断，非人工标注
- 玩家名含特殊字符时，脚本支持模糊匹配
