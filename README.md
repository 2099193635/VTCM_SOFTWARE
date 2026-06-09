# VTCM_SOFTWARE

VTCM_SOFTWARE 是车辆-轨道耦合动力学仿真的桌面工作台。软件使用 Electron + React/TypeScript 构建桌面界面，使用 FastAPI 封装 Python 仿真核心，保留现有 `generate_main.py` 求解流程。

首版目标是让仿真流程从命令行进入桌面客户端：配置工况、导入台账和不平顺文件、启动仿真、查看实时进度、管理历史结果，并用交互式曲线查看关键输出。

## 主要功能

- 仿真配置：速度、时长、步长、缓冲时间、起始里程、车辆/钢轨/扣件类型、不平顺类型、功率谱和开关项。
- 台账预览：导入曲线/坡度台账后，预览超高、坡度、纵断面，并从台账里程选择仿真起点。
- 不平顺预览：支持仿真区段预览和全长预览；轨道谱生成时全长页签不可用，外部导入时可查看全长。
- 运行监控：提交任务前进行前置条件检查，运行中显示实时进度条、步数、状态和日志。
- 结果曲线：按加速度、轮轨力、一二系悬挂力、不平顺、线路几何分组显示，并标注横纵坐标名称和单位。
- 历史记录：保存运行记录、参数快照和结果路径。

## 技术栈

- 桌面客户端：Electron、React、TypeScript、Vite
- UI 与图表：Ant Design、ECharts
- 本地后端：FastAPI、Pydantic、Uvicorn、SQLite
- 仿真核心：Python 数值求解程序，入口为 `generate_main.py`
- 打包：Electron Builder、PyInstaller

## 目录结构

```text
VTCM_SOFTWARE/
├─ desktop_client/          # Electron + React 桌面客户端
│  ├─ electron/             # Electron 主进程和预加载脚本
│  ├─ src/                  # 前端界面源码
│  ├─ public/               # 前端公共资源
│  └─ build/                # Windows 图标资源
├─ desktop_backend/         # FastAPI 本地仿真服务
├─ physics_modules/         # 车辆-轨道耦合动力学核心模块
├─ solver/                  # 积分与环境封装
├─ configs/                 # 标准车辆、钢轨、扣件和轨道参数
├─ Profile_file/            # 车轮/钢轨廓形文件
├─ power_spectrum/          # 不平顺功率谱
├─ preprocessing/           # 台账和不平顺预处理脚本及小型模板
├─ track_geometry/          # 线路几何处理
├─ utils/                   # 后处理和辅助脚本
├─ generate_main.py         # 仿真主入口
├─ requirements-desktop.txt # Python 后端依赖
└─ package.json             # 根目录快捷脚本
```

## Windows 开发启动

建议在 Windows PowerShell 中从仓库根目录执行。

### 1. 安装 Python 依赖

```powershell
pip install -r requirements-desktop.txt
```

### 2. 安装前端依赖

```powershell
npm run install-client
```

### 3. 启动桌面客户端

```powershell
npm run dev
```

启动后会同时运行：

- Python 本地后端：`http://127.0.0.1:18765`
- Vite 前端服务：`http://127.0.0.1:5173`
- Electron 桌面窗口

如果端口被占用，请先关闭之前的客户端或占用 `18765` 的 Python 服务。

## 常用命令

```powershell
# 启动开发版桌面客户端
npm run dev

# 仅构建前端和 Electron 主进程
npm run build-client

# 打包桌面客户端
npm run dist-client

# 单独启动后端服务
python -m desktop_backend.main
```

## 本地 API

默认后端地址：`http://127.0.0.1:18765`

- `GET /api/health`：健康检查
- `GET /api/metadata`：读取车辆、钢轨、扣件、不平顺类型和默认参数
- `POST /api/preflight`：启动前置条件检查
- `POST /api/simulations`：提交仿真任务
- `GET /api/simulations/{run_id}`：查询任务状态
- `POST /api/simulations/{run_id}/cancel`：取消任务
- `GET /api/results`：列出历史结果
- `GET /api/results/{run_id}`：读取结果摘要和曲线
- `WS /api/simulations/{run_id}/events`：实时进度、日志和状态推送

## 打包说明

后端打包方向：

```powershell
pyinstaller desktop_backend.spec
```

客户端打包方向：

```powershell
npm run dist-client
```

正式安装包需要确保 `dist-backend/` 中存在后端可执行文件，Electron Builder 会把它作为 `extraResources` 一起发布。

## 数据说明

本仓库不包含大型动检/静检原始数据、仿真结果和构建产物。默认 `.gitignore` 已排除：

- `node_modules/`
- `dist/`、`dist-electron/`、`dist-backend/`
- `results/`、`outputs/`
- `*.npz`、`*.npy`
- 压缩包和临时缓存

如需运行外部导入不平顺工况，请在客户端中选择本机已有的 VL/VR/LL/LR 文件。

## 当前状态

这是桌面客户端首版工程快照。已实现本地服务化、参数配置、台账/不平顺预览、实时进度、结果分组曲线和基础历史记录。后续可继续扩展批量工况、参数扫描、结果导出和 Windows 安装包自动化。
