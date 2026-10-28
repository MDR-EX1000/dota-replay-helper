# 发布准备与交接

本文只说明准备和验收，不代表已取得腾讯云权限或已经发布。

## 分支交付与新环境复现

本次只提交功能源码、测试和文档。合并分支不会自动替换正式网页；维护者需要在自己的环境使用完整原始数据重新生成 `docs/`，并更新上传服务镜像。

下文“已完成”记录的是开发机验收状态。新克隆的仓库不包含录像、原始比赛 JSON、Steam Key、头像缓存、解析器二进制、manta 源码或 `.local-tools/`。请按 README 准备解析器和依赖，按需运行工具安装脚本，并在本机配置自己的密钥。空的私有配置文件也不会随 Git 交付。

无需私有数据即可运行逻辑测试：`python -B -m unittest discover -s tests -v` 和 `node --test tests/player_profiles.test.cjs`（需安装 Python 和 Node）。两场录像预览及 `一键本地验收.bat` 还要求开发机所用的私有样例数据与工具就位；其他环境可用自己的解析结果替换 `--matches-dir` 路径。

## 已完成的本机准备

- 已编译的 Windows 录像解析器和 manta 源码已就位。
- 已安装项目内 Node、npm 11.6.2、CloudBase CLI 3.8.8；不改变系统 PATH。
- Steam Key 已在本地配置，并已验证两场录像中 11 个账号的头像。
- 身份、缺失值、称号、个人资料、队友/对手、在线图标已完成本地验证。
- 已准备发布预检入口；预检不执行登录、云端查询、构建或上传。
- 正式 `docs/` 的旧版 18 场产物保留；新版预览与测试数据均在忽略目录中。

工具和缓存存放在 `.local-tools/`，不会提交 Git。以后需要重装时运行：

```powershell
python tools/setup_local_tools.py
.\tcb.cmd --version
.\npm.cmd --version
```

项目的发布、同步和构建脚本会优先使用项目内 CLI。普通 PowerShell 中直接调用时用 `./tcb.cmd`，不依赖全局 `tcb` 命令。

## 现在可以运行的检查

双击 `一键发布预检.bat`，或执行：

```powershell
python -B release_preflight.py --local-only
```

`--local-only` 只按本机准备情况返回退出码，但仍列出等待交接的项目。完整检查为 `python -B release_preflight.py`；交接项缺失时退出码为 2，这是“尚未就绪”，不是程序异常。

报告写入 `cloudrun_test/release_readiness.json`，只记录状态和比赛文件信息，不记录 Key 或上传口令。检查通过只能说明本地前提满足，不能代替云端权限验证及线上最新数据核验。

双击 `一键本地验收.bat` 可连续运行本机检查、Python/前端测试，并重建两场样例预览。该入口仅在当前进程中加入项目内 Node 路径，不改系统设置，也不请求 Steam 头像接口。

## 请朋友提供

| 内容 | 要求与本地位置 |
|---|---|
| 完整比赛 JSON | 含 SteamID 的原始 `match_*.json`，放仓库根目录下的 `json/`；不能只给公开的 `matches.js` |
| 数据清单 | 最好同时提供当前 `state/index.json`，用于与本地公开基线一起核对遗漏比赛 |
| 可用录像 | 有的话保留在 `replay/` 或指定目录；用于 schema 3 重解析，不要求为了界面先找齐全部录像 |
| 最新玩家配置 | `aliases.json`、`mmr.json`、`baselines.json`、`legacy_identities.json`，以及存在的话 `roles.json` |
| 环境信息 | 环境 ID、地域、网站域名、上传服务名；核对 `cloudbase.json`，上传服务名可用 `upload_service_name` 指定，默认 `dota-upload` |
| 项目 CloudBase API Key | 填入 `cloudbase.apikey`；现有上传服务使用它自动发布，构建部署时也使用它登录 |
| 腾讯云 SecretId/SecretKey | 若使用这种登录方式，填入 `cloudbase.secret.json`。仅使用项目 CloudBase Key 时可以留空，脚本支持该 Key 登录 |
| 当前上传口令 | 填入 `upload_code.txt`，或设置 `UPLOAD_CODE`；必须与朋友确认，构建不再使用默认口令 |

三个凭据/口令文件已经准备为空文件或空配置，均被 Git 忽略。不要将实际值写入 README、提交记录或聊天。Steam Key 已有，无需重复提供；这次没有修改 AI 云函数，不需要为本轮更新重新提供 DeepSeek Key。

## 拿到资料后的顺序

1. 先核对环境及服务名，确认 Key 类型和授权范围；由操作者在本机完成登录。再只读核对线上最新比赛清单，并备份线上 `state/`、`docs/` 和当前服务版本。
2. 将全部原始 JSON 和最新配置放到正确位置。不要把 `json/feature_validation/` 中的两场验证数据当成全部数据；预检会发现相对公开基线的缺失。
3. 运行 `python -B release_preflight.py`，先解决原始数据和配置问题。只有旧 schema 2 的字段来源会提示，原始数字 ID、比赛结构或文件 ID 有问题则不能通过数据检查。
4. 用全量数据重新生成正式 `docs/`（不加 `--local-preview`），验收比赛数、玩家归并、评分、个人资料和称号。正式产物不能直接复制两场预览，预览关闭了上传和 AI。
5. 运行测试并再次预检。约定发布窗口，期间避免朋友同时发布和上传。
6. 在明确批准发布后，更新云端上传服务镜像与静态页面，再验证真实上传、解析、去重、头像更新、页面路由和最终比赛数。

构建器默认数据根目录已改为当前项目，仍建议首次显式指定：

```powershell
# 只组装本地构建目录；要求全量数据和明确上传口令，不会部署。
python build_cloudrun.py --data-root .
```

构建目录包含私有服务配置，已被 Git 忽略。空数据、不完整基线、错误比赛结构或未配置上传口令时，构建会在删除旧构建目录前停止。实际云端部署需要额外的 `--deploy`，本轮没有执行。

## 本轮验证命令

```powershell
python -B -m unittest discover -s tests -v
.\.local-tools\node.exe --test tests/player_profiles.test.cjs
python -B make_web.py --matches-dir json/feature_validation --output-dir cloudrun_test/preview --local-preview --no-avatar-refresh
```

当前本地原始数据根目录仍为空，等待完整数据、腾讯云凭据及线上上传口令。功能测试通过不等同于已完成云端联调。
