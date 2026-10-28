# seeUtoken · Cursor 用量悬浮球（Python）

桌面常驻应用（Python + pywebview）：

- **模型额度首页**：新建 / 删除额度面板；每个软件只允许一个面板，已添加的软件不可重复添加，删除后可重新添加；Cursor 显示实时剩余额度
- **用量详情**：统计卡、存量环图、模型分布、使用记录、年度热力图
- **Codex 接入**：自动识别本机 Codex 登录，通过官方 app-server 读取账户额度；首页卡片和悬浮栏展示各额度窗口，点击卡片或双击悬浮栏 Codex 图标进入详情大屏
- **置顶悬浮球**：屏幕常驻，点击展开侧边用量；系统托盘控制显隐与退出
- **macOS 贴边收起**：将侧边用量栏拖到屏幕左、右边缘，移出后收成窄条；悬停窄条展开，拖离边缘后保持展开。设置中可关闭「贴边自动缩进」
- **悬浮栏置顶设置**：设置中可切换「始终置顶」，与贴边自动缩进独立保存，重启后保留；两项默认开启，修改后立即应用
- **全局外观**：「外观模式」统一提供白天模式、黑夜模式、Liquid Glass（标准）、Liquid Glass（通透）四个选项，统一作用于模型额度首页、Cursor / Codex 详情大屏、侧边栏与弹窗，切换后自动保存。macOS 主窗口同时适配原生 Liquid Glass（旧版系统回退到 Vibrancy），标题栏随外观切换；系统开启「降低透明度」时使用不透明背景

首次使用默认：Token 统计不包含缓存、白天模式、显示侧边用量栏、开启贴边自动缩进、开启始终置顶；之后按用户保存的设置启动。

主窗口点红叉会完整退出应用，同时关闭侧边栏和托盘。最小化或隐藏主窗口后，点击 Dock 图标（或再次打开应用）恢复主窗口并置前；双击侧边栏 Cursor / Codex 图标打开对应详情大屏，未接入的软件图标打开模型额度首页。拖动侧边栏不会触发双击打开。

## 环境

- Python 3.10+
- Windows 推荐（使用 Edge WebView2）

## 安装与启动

```bash
cd seeUtoken
python -m pip install -r requirements.txt

# 前端（Vue3 + Ant Design Vue）
cd frontend
npm install
npm run build
cd ..

python run.py
```

开发时也可在 `frontend` 目录执行 `npm run dev` 单独预览页面。

或：

```bash
python -m seeutoken
```

## 数据来源

1. **自动**：读取本机 Cursor 登录库  
   `%APPDATA%\Cursor\User\globalStorage\state.vscdb`
2. **手动**：详情页「设置 Token」，粘贴 cursor.com 的 `WorkosCursorSessionToken`
3. 未登录时显示演示数据

## 目录

```
seeutoken/     # Python 后端（鉴权、API、热力图、窗口）
frontend/      # Vue3 + Ant Design Vue 源码
ui/            # 前端构建产物（npm run build 生成）
assets/        # 图标
run.py         # 启动入口
requirements.txt
```

## 说明

Codex 账户额度默认每分钟同步一次；详情页可选择手动、1、5、15、30 分钟，设置会保存，独立于 Cursor。首次读取会同步账户；手动模式之后仅点击「立即刷新」才重新同步。未联网时保留最近的本机额度快照；额度窗口过期后显示未知，等待下一次确认。
Token、模型和项目明细来自 `CODEX_HOME`（默认 `~/.codex`）中的本机会话与归档记录，每 15 秒更新；按累计计数的差值统计，忽略重复额度快照及会话归档副本，排除内部自动审核模型。本机统计不代表所有设备的云端账单。除用量、模型和项目元数据外，详情页的使用记录会显示对应提问的文字；不显示系统指令、助手回复、工具输出或登录凭据。

Codex「使用记录」按每次提问汇总一条，合并该次提问中所有模型调用的输入、输出和缓存用量，时间显示最近一次调用时间；正在回答的问题随本机记录刷新累计。「会话内容」列显示提问原文，去除自动附带的附件清单和环境信息，长内容省略显示，悬停可查看原文。模型分布、调用次数和每日统计仍按原始调用计算。缺少提问编号及开始标记的旧记录保留各次调用，避免误合并；缺少提问文字时显示「—」。

Cursor 使用记录同样显示「会话内容」，按 conversationId 和调用时间匹配本机 Cursor 中对应的用户提问；仅详情页读取用户消息，不读取助手回复或认证记录。本机历史缺失时显示「—」。两种详情页均采用紧凑列宽，长提问悬停可查看全文，窄窗口中的 Token 明细分两行完整显示。

设置中的「Token 统计口径」可选择是否包含缓存，默认关闭：主数字为 **不含缓存读写的输入 + 输出**；开启后主数字再加缓存读写。偏好自动保存，首页、悬浮栏、模型分布、热力图和趋势图同步切换。详情始终保留输入、输出、缓存及含缓存总量的明细。此设置只改变 Token 统计，不改变账户额度百分比或账单。

- Cursor Dashboard 的 `inputTokens` 与缓存读写分列：不含缓存 = `inputTokens + outputTokens`，含缓存总量再加 `cacheReadTokens + cacheWriteTokens`。
- Codex 会话的 `input_tokens` 已包含缓存输入：不含缓存 = `input_tokens - cached_input_tokens - cache_write_input_tokens + output_tokens`，含缓存总量 = `input_tokens + output_tokens`。输出已含推理 Token，不重复累加。
- 今日按本机时区零点起算；Cursor「本周期」指订阅账期，Codex「本周」指本地时间周一至今，均与账户的滚动额度窗口分别统计。

通过 Cursor 网页同款 Dashboard 接口读取你自己的用量；非官方产品。旧的 Electron 版本已弃用，请使用本 Python 版。

## macOS DMG 打包

在 Apple Silicon Mac 安装项目的 Python 和前端依赖后，执行：

```bash
bash packaging/macos/build.sh
```

生成 `dist/seeUtoken-V1.0.0.dmg`，包含独立的 `seeUtoken.app`、Applications 拖拽安装入口及安装说明。当前构建目标为 Apple Silicon、macOS 14 及以上；不支持 Intel Mac。可通过 `SEEU_BUILD_PYTHON` 和 `SEEU_BUILD_NODE` 指定构建工具路径。

构建会剔除页面中本机注入的启动数据，运行时把可写页面复制到临时目录，避免改写签名后的应用包。当前版本使用 ad-hoc 签名，未使用 Developer ID 签名及 Apple 公证；首次打开方法见 `packaging/macos/INSTALL.txt`。
