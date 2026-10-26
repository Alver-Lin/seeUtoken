# seeUtoken · Cursor 用量悬浮球（Python）

桌面常驻应用（Python + pywebview）：

- **模型额度首页**：新建 / 删除额度面板；Cursor 显示实时剩余额度
- **用量详情**：统计卡、存量环图、模型分布、使用记录、年度热力图
- **置顶悬浮球**：屏幕常驻，点击展开侧边用量；系统托盘控制显隐与退出

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

通过 Cursor 网页同款 Dashboard 接口读取你自己的用量；非官方产品。旧的 Electron 版本已弃用，请使用本 Python 版。
