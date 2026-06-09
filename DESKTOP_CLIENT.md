# VTCM Desktop Workbench

本目录提供车辆-轨道耦合仿真的桌面客户端首版骨架：

- `desktop_backend/`：FastAPI 本地服务，负责仿真任务、进度、SQLite 记录和结果读取。
- `desktop_client/`：Electron + React + TypeScript 工作台界面。

## 开发启动

1. 安装 Python 依赖：

```powershell
pip install -r requirements-desktop.txt
```

2. 启动后端：

```powershell
python -m desktop_backend.main
```

3. 安装并启动前端：

```powershell
cd desktop_client
npm install
npm run dev
```

## API

- 默认后端地址：`http://127.0.0.1:18765`
- `GET /api/metadata`
- `POST /api/simulations`
- `GET /api/simulations/{run_id}`
- `POST /api/simulations/{run_id}/cancel`
- `GET /api/results`
- `GET /api/results/{run_id}`
- `WS /api/simulations/{run_id}/events`

## 打包方向

后端用 PyInstaller 生成 `vtcm-backend.exe`，再通过 Electron Builder 作为 `extraResources` 随客户端发布。当前提交先保证开发模式和工程结构清晰，正式安装包需要在依赖安装完成后执行打包联调。
