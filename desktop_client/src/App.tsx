import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Col,
  Dropdown,
  Form,
  Input,
  InputNumber,
  Layout,
  Modal,
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message
} from "antd";
import {
  BarChartOutlined,
  FolderOpenOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  AlignmentPreview,
  api,
  getBackendUrl,
  IrregularityPreview,
  Metadata,
  ResultPlotGroup,
  ResultSummary,
  SimulationConfig,
  SimulationRecord
} from "./api";
import appIcon from "./assets/vtcm-project-icon.png";
import "./styles.css";

const { Header, Content, Sider } = Layout;
const { Text } = Typography;

const fallbackDefaults: SimulationConfig = {
  vx_set: 215,
  tz: 5,
  tstep: 0.0001,
  start_mileage: 271.82269772001104,
  curve_file_dir: "preprocessing/台账/处理后/curve_parameters.csv",
  gradient_file_dir: "preprocessing/台账/处理后/gradient_parameters.csv",
  cache_file_dir: "configs/track_cache.npz",
  force_rebuild: "Off",
  vehicle_type: "高速客车",
  rail_type: "CHN60",
  fastener_type: "Standard_KV",
  param_profile_dir: "configs/standard",
  irr_type: "外部导入",
  irr_lead_time: 2,
  psd_type: "高铁谱",
  defect_switch: "off",
  input_path: "",
  output_path: "",
  external_mileage_mode: "absolute",
  external_distance_unit: "km",
  Type2: "空间谱",
  external_files: [],
  N_sub: 2000,
  X0: 20,
  alpha: 0.5,
  beta: 0.25,
  g: 9.81,
  switch_curve_track: "On",
  switch_2point_contact: "On",
  switch_extra_force_element: "On",
  switch_pad_zone: "On",
  switch_pad_partition: "On",
  switch_railcant_unsymmetric: "On",
  switch_lock_veh_non_z: "On",
  switch_lock_axlebox: "Off",
  switch_lock_substructure: "Off",
  save_data: "On",
  save_dof_mode: "vehicle",
  project_name: "desktop_workbench",
  run_note: "desktop",
  plot_figs: "Off"
};

const fallbackMetadata: Metadata = {
  defaults: fallbackDefaults,
  vehicle_types: ["高速客车", "提速客车", "普通客车"],
  rail_types: ["CHN60"],
  fastener_types: ["Standard_KV"],
  irr_types: ["外部导入", "随机不平顺", "谐波不平顺", "无不平顺"],
  psd_types: ["高铁谱", "干线谱", "美国谱", "德国低干扰谱"]
};

const helpText: Record<string, string> = {
  vx_set: "车辆运行速度，单位 km/h。",
  tz: "目标仿真时长，单位 s。外部导入或随机不平顺会叠加缓冲时间。",
  irr_lead_time: "缓冲时间：外部导入或随机不平顺开始前的无激励平顺运行时长，单位 s。",
  tstep: "积分时间步长，单位 s。步长越小越精细，计算耗时也越长。",
  start_mileage: "仿真起点绝对里程。建议先导入台账，再从台账里程中选择。",
  vehicle_type: "车辆动力学参数类型。",
  rail_type: "钢轨参数类型。",
  fastener_type: "扣件刚度和阻尼参数类型。",
  irr_type: "轨道激励来源：随机谱、谐波、外部导入或无不平顺。",
  psd_type: "随机不平顺使用的功率谱类型；外部导入时作为记录标签。",
  curve_file_dir: "曲线台账 CSV 文件。",
  gradient_file_dir: "坡度台账 CSV 文件。",
  external_files: "外部不平顺文件，使用 VL/VR/LL/LR 四个通道。",
  N_sub: "轨下结构离散单元数量，影响自由度和计算耗时。",
  save_dof_mode: "vehicle 仅保存车辆自由度，full 保存全系统自由度。",
  switch_curve_track: "是否叠加曲线轨道引起的等效力。",
  switch_2point_contact: "是否记录并计算两点接触相关输出。"
};

type PanelKey = "alignment" | "irregularity" | "result" | "run" | "history";

function statusColor(status: SimulationRecord["status"]) {
  if (status === "completed") return "green";
  if (status === "running") return "blue";
  if (status === "failed") return "red";
  if (status === "cancelled") return "orange";
  return "default";
}

function Label({ id, children }: { id: string; children: string }) {
  return (
    <Space size={4}>
      <span>{children}</span>
      <Tooltip title={helpText[id] || "用于生成本次仿真的参数。"}>
        <QuestionCircleOutlined className="help-icon" />
      </Tooltip>
    </Space>
  );
}

function Panel({
  title,
  panelKey,
  visible,
  onClose,
  children
}: {
  title: string;
  panelKey: PanelKey;
  visible: boolean;
  onClose: (key: PanelKey) => void;
  children: React.ReactNode;
}) {
  if (!visible) return null;
  return (
    <div className="panel">
      <div className="panel-title">
        <span>{title}</span>
        <Button size="small" type="text" onClick={() => onClose(panelKey)}>
          关闭
        </Button>
      </div>
      {children}
    </div>
  );
}

function makeAlignmentOption(preview?: AlignmentPreview) {
  const s = preview?.series;
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 72, right: 30, top: 48, bottom: 56 },
    xAxis: {
      type: "category",
      data: (s?.mileage_km || []).map((v) => v.toFixed(3)),
      name: "里程 (km)",
      nameLocation: "middle",
      nameGap: 34
    },
    yAxis: { type: "value", scale: true, name: "线路参数", nameLocation: "middle", nameGap: 52 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18 }],
    series: [
      { name: "超高 (m)", type: "line", showSymbol: false, data: s?.cant_m || [] },
      { name: "坡度", type: "line", showSymbol: false, data: s?.gradient || [] },
      { name: "纵断面 (m)", type: "line", showSymbol: false, data: s?.vertical_profile_m || [] }
    ]
  };
}

function makeIrregularityOption(preview?: IrregularityPreview) {
  const entries = Object.entries(preview?.series || {});
  const x = entries[0]?.[1].x || [];
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 72, right: 30, top: 48, bottom: 56 },
    xAxis: {
      type: "category",
      data: x.map((v) => Number(v).toFixed(3)),
      name: "距离 (m)",
      nameLocation: "middle",
      nameGap: 34
    },
    yAxis: { type: "value", scale: true, name: "不平顺 (m)", nameLocation: "middle", nameGap: 52 },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18 }],
    series: entries.map(([key, value]) => ({ name: key, type: "line", showSymbol: false, data: value.y }))
  };
}

function makeResultGroups(result?: ResultSummary): ResultPlotGroup[] {
  if (result?.groups?.length) return result.groups;
  const time = result?.series.time || [];
  const series = result?.series || {};
  return [
    {
      key: "acceleration",
      title: "加速度",
      x_name: "时间",
      x_unit: "s",
      y_name: "加速度",
      y_unit: "m/s²",
      series: [
        { key: "carbody_az", name: "车体垂向", x: time, y: series.carbody_az || [] },
        { key: "carbody_ay", name: "车体横向", x: time, y: series.carbody_ay || [] }
      ]
    },
    {
      key: "wheel_rail_force",
      title: "轮轨力",
      x_name: "时间",
      x_unit: "s",
      y_name: "力",
      y_unit: "N",
      series: [
        { key: "wheel_vertical_force", name: "轮轨垂向力", x: time, y: series.wheel_vertical_force || [] },
        { key: "wheel_lateral_force", name: "轮轨横向力", x: time, y: series.wheel_lateral_force || [] }
      ]
    }
  ].filter((group) => group.series.some((item) => item.y.length));
}

function makeResultOption(group?: ResultPlotGroup) {
  const x = group?.series[0]?.x || [];
  return {
    tooltip: { trigger: "axis" },
    legend: { top: 0 },
    grid: { left: 82, right: 34, top: 48, bottom: 58 },
    xAxis: {
      type: "category",
      data: x.map((v) => Number(v).toFixed(3)),
      name: `${group?.x_name || "X"}${group?.x_unit ? ` (${group.x_unit})` : ""}`,
      nameLocation: "middle",
      nameGap: 36
    },
    yAxis: {
      type: "value",
      scale: true,
      name: `${group?.y_name || "Y"}${group?.y_unit ? ` (${group.y_unit})` : ""}`,
      nameLocation: "middle",
      nameGap: 60
    },
    dataZoom: [{ type: "inside" }, { type: "slider", height: 18 }],
    series: (group?.series || []).map((item) => ({
      name: item.name,
      type: "line",
      showSymbol: false,
      data: item.y
    }))
  };
}

export default function App() {
  const [metadata, setMetadata] = useState<Metadata>(fallbackMetadata);
  const [form] = Form.useForm<SimulationConfig>();
  const [records, setRecords] = useState<SimulationRecord[]>([]);
  const [activeRun, setActiveRun] = useState<SimulationRecord>();
  const [result, setResult] = useState<ResultSummary>();
  const [resultGroupKey, setResultGroupKey] = useState<string>();
  const [alignment, setAlignment] = useState<AlignmentPreview>();
  const [irregularity, setIrregularity] = useState<IrregularityPreview>();
  const [irregularityView, setIrregularityView] = useState<"simulation" | "full">("simulation");
  const [logs, setLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [configOpen, setConfigOpen] = useState(true);
  const [panels, setPanels] = useState<Record<PanelKey, boolean>>({
    alignment: true,
    irregularity: true,
    result: true,
    run: true,
    history: true
  });
  const irrType = Form.useWatch("irr_type", form);

  const setPanelVisible = (key: PanelKey, visible: boolean) => {
    setPanels((old) => ({ ...old, [key]: visible }));
  };

  const refreshRecords = async () => {
    const data = await api.listResults();
    setRecords(data);
    return data;
  };

  useEffect(() => {
    form.setFieldsValue(fallbackDefaults);
    api
      .metadata()
      .then((data) => {
        const merged = {
          ...fallbackMetadata,
          ...data,
          defaults: { ...fallbackDefaults, ...data.defaults },
          vehicle_types: data.vehicle_types?.length ? data.vehicle_types : fallbackMetadata.vehicle_types,
          rail_types: data.rail_types?.length ? data.rail_types : fallbackMetadata.rail_types,
          fastener_types: data.fastener_types?.length ? data.fastener_types : fallbackMetadata.fastener_types
        };
        setMetadata(merged);
        form.setFieldsValue(merged.defaults);
      })
      .then(refreshRecords)
      .catch((err) => message.error(`后端连接失败：${err.message}`));
  }, []);

  useEffect(() => {
    if (!activeRun || !["queued", "running"].includes(activeRun.status)) return;
    let socket: WebSocket | undefined;
    let closed = false;

    getBackendUrl().then((base) => {
      if (closed) return;
      socket = new WebSocket(`${base.replace("http", "ws")}/api/simulations/${activeRun.run_id}/events`);
      socket.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "log") setLogs((old) => [...old.slice(-180), payload.message]);
        if (payload.type === "progress") {
          setActiveRun((old) =>
            old
              ? {
                  ...old,
                  status: "running",
                  progress: payload.progress,
                  current_step: payload.current_step,
                  total_steps: payload.total_steps,
                  message: payload.message || old.message
                }
              : old
          );
        }
        if (payload.type === "status") {
          setActiveRun((old) =>
            old
              ? {
                  ...old,
                  status: payload.status || old.status,
                  result_path: payload.result_path || old.result_path,
                  message: payload.message || old.message,
                  progress: payload.status === "completed" ? 1 : old.progress
                }
              : old
          );
          if (payload.status === "completed") {
            const data = await api.getResult(activeRun.run_id);
            setResult(data);
            setResultGroupKey(makeResultGroups(data)[0]?.key);
            setPanelVisible("result", true);
          }
          refreshRecords();
        }
        if (payload.type === "error") {
          setActiveRun((old) => (old ? { ...old, status: "failed", message: payload.message || old.message } : old));
          refreshRecords();
        }
      };
    });

    return () => {
      closed = true;
      socket?.close();
    };
  }, [activeRun?.run_id, activeRun?.status]);

  const previewAlignment = async () => {
    try {
      const values = form.getFieldsValue();
      const data = await api.alignmentPreview({
        curve_file_dir: values.curve_file_dir,
        gradient_file_dir: values.gradient_file_dir,
        start_mileage: values.start_mileage
      });
      setAlignment(data);
      setPanelVisible("alignment", true);
      message.success("台账预览已更新");
    } catch (error) {
      message.error(`台账预览失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const previewIrregularity = async () => {
    try {
      const values = form.getFieldsValue();
      const data = await api.irregularityPreview({
        irr_type: values.irr_type,
        psd_type: values.psd_type,
        files: values.external_files || [],
        start_mileage: values.start_mileage,
        duration_s: values.tz,
        speed_kmh: values.vx_set
      });
      setIrregularity(data);
      setIrregularityView("simulation");
      setPanelVisible("irregularity", true);
      message.success("不平顺预览已更新");
    } catch (error) {
      message.error(`不平顺预览失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const selectPath = async (field: keyof SimulationConfig) => {
    const file = await window.vtcm?.selectFile();
    if (file) form.setFieldValue(field, file);
  };

  const selectExternalFile = async (key: "VL" | "VR" | "LL" | "LR") => {
    const file = await window.vtcm?.selectFile();
    if (!file) return;
    const current = form.getFieldValue("external_files") || [];
    const next = current.filter((item: string) => !item.startsWith(`${key}=`));
    next.push(`${key}=${file}`);
    form.setFieldValue("external_files", next);
    await previewIrregularity();
  };

  const runSimulation = async () => {
    const values = await form.validateFields();
    setLoading(true);
    setLogs([]);
    try {
      const localMissing: string[] = [];
      if (!alignment) localMissing.push("请先导入台账并刷新预览，然后选择起始里程。");
      if (values.irr_type === "外部导入" && !irregularity) {
        localMissing.push("当前为外部导入不平顺，请先选择 VL/VR/LL/LR 文件并预览。");
      }
      const preflight = await api.preflight(values);
      const allMissing = [...localMissing, ...preflight.missing];
      if (allMissing.length) {
        Modal.warning({
          title: "启动前还有工作未完成",
          width: 620,
          content: (
            <div>
              <p>请先处理以下项目，然后再启动仿真：</p>
              <ul>
                {allMissing.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )
        });
        return;
      }
      if (preflight.warnings.length) message.warning(preflight.warnings.join("；"));

      const response = await api.createSimulation(values);
      const record = await api.getSimulation(response.run_id);
      setActiveRun(record);
      setResult(undefined);
      setPanelVisible("run", true);
      await refreshRecords();
      message.success("仿真任务已提交");
    } finally {
      setLoading(false);
    }
  };

  const openResult = async (record: SimulationRecord) => {
    setActiveRun(record);
    setResult(undefined);
    if (record.result_path) {
      const data = await api.getResult(record.run_id);
      setResult(data);
      setResultGroupKey(makeResultGroups(data)[0]?.key);
      setPanelVisible("result", true);
    }
  };

  const alignmentOption = useMemo(() => makeAlignmentOption(alignment), [alignment]);
  const irregularityForChart = useMemo(() => {
    if (!irregularity) return undefined;
    return {
      ...irregularity,
      series: irregularityView === "full" ? irregularity.full_series : irregularity.simulation_series
    };
  }, [irregularity, irregularityView]);
  const irregularityOption = useMemo(() => makeIrregularityOption(irregularityForChart), [irregularityForChart]);
  const resultGroups = useMemo(() => makeResultGroups(result), [result]);
  const activeResultGroup = useMemo(
    () => resultGroups.find((group) => group.key === resultGroupKey) || resultGroups[0],
    [resultGroupKey, resultGroups]
  );
  const resultOption = useMemo(() => makeResultOption(activeResultGroup), [activeResultGroup]);

  const panelMenu = {
    items: (Object.keys(panels) as PanelKey[]).map((key) => ({
      key,
      label: (
        <Checkbox checked={panels[key]} onChange={(event) => setPanelVisible(key, event.target.checked)}>
          {key === "alignment"
            ? "台账/线路面板"
            : key === "irregularity"
              ? "不平顺面板"
              : key === "result"
                ? "结果面板"
                : key === "run"
                  ? "运行面板"
                  : "历史面板"}
        </Checkbox>
      )
    }))
  };

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <div className="brand-block">
          <img className="app-logo" src={appIcon} alt="" />
          <div>
            <strong>VTCM Workbench</strong>
            <Text type="secondary">车辆-轨道耦合仿真桌面工作台</Text>
          </div>
        </div>
        <Space>
          <Dropdown menu={panelMenu} trigger={["click"]}>
            <Button>Alignment</Button>
          </Dropdown>
          <Button icon={configOpen ? <MenuFoldOutlined /> : <MenuUnfoldOutlined />} onClick={() => setConfigOpen(!configOpen)}>
            配置
          </Button>
          <Button icon={<ReloadOutlined />} onClick={refreshRecords}>
            刷新
          </Button>
          <Button type="primary" icon={<PlayCircleOutlined />} loading={loading} onClick={runSimulation}>
            启动仿真
          </Button>
        </Space>
      </Header>

      <Layout>
        {configOpen && (
          <Sider width={430} theme="light" className="config-pane">
            <Form form={form} layout="vertical" initialValues={fallbackDefaults}>
              <Tabs
                defaultActiveKey="basic"
                items={[
                  {
                    key: "basic",
                    label: "仿真配置",
                    children: (
                      <>
                        <Row gutter={12}>
                          <Col span={8}>
                            <Form.Item name="vx_set" label={<Label id="vx_set">速度 km/h</Label>}>
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                          </Col>
                          <Col span={8}>
                            <Form.Item name="tz" label={<Label id="tz">时长 s</Label>}>
                              <InputNumber min={0.01} style={{ width: "100%" }} />
                            </Form.Item>
                          </Col>
                          <Col span={8}>
                            <Form.Item name="tstep" label={<Label id="tstep">步长 s</Label>}>
                              <InputNumber min={0.00001} step={0.0001} style={{ width: "100%" }} />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item name="irr_lead_time" label={<Label id="irr_lead_time">缓冲时间 s</Label>}>
                          <InputNumber min={0} step={0.5} style={{ width: "100%" }} />
                        </Form.Item>
                        <Form.Item name="start_mileage" label={<Label id="start_mileage">起始里程 km</Label>}>
                          <Select
                            showSearch
                            options={(alignment?.mileage_choices || [metadata.defaults.start_mileage]).map((value) => ({
                              value,
                              label: String(value)
                            }))}
                          />
                        </Form.Item>

                        <Row gutter={12}>
                          <Col span={8}>
                            <Form.Item name="vehicle_type" label={<Label id="vehicle_type">车辆</Label>}>
                              <Select options={metadata.vehicle_types.map((value) => ({ value }))} />
                            </Form.Item>
                          </Col>
                          <Col span={8}>
                            <Form.Item name="rail_type" label={<Label id="rail_type">钢轨</Label>}>
                              <Select options={metadata.rail_types.map((value) => ({ value }))} />
                            </Form.Item>
                          </Col>
                          <Col span={8}>
                            <Form.Item name="fastener_type" label={<Label id="fastener_type">扣件</Label>}>
                              <Select options={metadata.fastener_types.map((value) => ({ value }))} />
                            </Form.Item>
                          </Col>
                        </Row>

                        <Form.Item name="param_profile_dir" label="参数目录">
                          <Input />
                        </Form.Item>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Form.Item name="irr_type" label={<Label id="irr_type">不平顺类型</Label>}>
                              <Select options={metadata.irr_types.map((value) => ({ value }))} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="psd_type" label={<Label id="psd_type">功率谱</Label>}>
                              <Select options={metadata.psd_types.map((value) => ({ value }))} />
                            </Form.Item>
                          </Col>
                        </Row>

                        <Form.Item name="curve_file_dir" label={<Label id="curve_file_dir">曲线台账</Label>}>
                          <Input addonAfter={<Button type="text" size="small" icon={<FolderOpenOutlined />} onClick={() => selectPath("curve_file_dir")} />} />
                        </Form.Item>
                        <Form.Item name="gradient_file_dir" label={<Label id="gradient_file_dir">坡度台账</Label>}>
                          <Input addonAfter={<Button type="text" size="small" icon={<FolderOpenOutlined />} onClick={() => selectPath("gradient_file_dir")} />} />
                        </Form.Item>
                        <Button block onClick={previewAlignment}>
                          导入/刷新台账预览
                        </Button>

                        <div className="form-separator" />
                        {irrType === "外部导入" && (
                          <>
                            <Form.Item name="external_files" label={<Label id="external_files">外部不平顺文件</Label>}>
                              <Select mode="tags" open={false} />
                            </Form.Item>
                            <Row gutter={8}>
                              {(["VL", "VR", "LL", "LR"] as const).map((key) => (
                                <Col span={6} key={key}>
                                  <Button block onClick={() => selectExternalFile(key)}>
                                    {key}
                                  </Button>
                                </Col>
                              ))}
                            </Row>
                          </>
                        )}
                        <Button block className="stacked-button" onClick={previewIrregularity}>
                          预览不平顺
                        </Button>
                      </>
                    )
                  },
                  {
                    key: "advanced",
                    label: "高级参数",
                    children: (
                      <>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Form.Item name="N_sub" label={<Label id="N_sub">轨下单元</Label>}>
                              <InputNumber min={1} style={{ width: "100%" }} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="save_dof_mode" label={<Label id="save_dof_mode">保存自由度</Label>}>
                              <Select options={[{ value: "vehicle", label: "车辆" }, { value: "full", label: "全系统" }]} />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Row gutter={12}>
                          <Col span={12}>
                            <Form.Item name="switch_curve_track" label={<Label id="switch_curve_track">曲线等效力</Label>}>
                              <Select options={[{ value: "On" }, { value: "Off" }]} />
                            </Form.Item>
                          </Col>
                          <Col span={12}>
                            <Form.Item name="switch_2point_contact" label={<Label id="switch_2point_contact">两点接触</Label>}>
                              <Select options={[{ value: "On" }, { value: "Off" }]} />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item name="project_name" label="项目名">
                          <Input />
                        </Form.Item>
                        <Form.Item name="run_note" label="运行备注">
                          <Input />
                        </Form.Item>
                      </>
                    )
                  }
                ]}
              />
            </Form>
          </Sider>
        )}

        <Content className="workbench">
          <div className="panel-grid">
            <Panel title="台账/线路" panelKey="alignment" visible={panels.alignment} onClose={(key) => setPanelVisible(key, false)}>
              {alignment ? <ReactECharts option={alignmentOption} style={{ height: 300 }} /> : <Alert type="info" message="先导入台账文件并刷新预览" />}
            </Panel>

            <Panel title="不平顺预览" panelKey="irregularity" visible={panels.irregularity} onClose={(key) => setPanelVisible(key, false)}>
              {irregularity ? (
                <>
                  <Tabs
                    size="small"
                    activeKey={irregularityView}
                    onChange={(key) => setIrregularityView(key as "simulation" | "full")}
                    items={[
                      { key: "simulation", label: "仿真区段" },
                      { key: "full", label: "全长", disabled: !irregularity.full_available }
                    ]}
                  />
                  <ReactECharts option={irregularityOption} style={{ height: 300 }} />
                </>
              ) : (
                <Alert type="info" message="选择不平顺类型和文件后预览" />
              )}
            </Panel>

            <Panel title="运行状态" panelKey="run" visible={panels.run} onClose={(key) => setPanelVisible(key, false)}>
              {activeRun ? (
                <>
                  <Space>
                    <Tag color={statusColor(activeRun.status)}>{activeRun.status}</Tag>
                    <Text copyable>{activeRun.run_id}</Text>
                  </Space>
                  <Progress
                    percent={Math.round((activeRun.progress || 0) * 100)}
                    status={activeRun.status === "failed" ? "exception" : activeRun.status === "completed" ? "success" : "active"}
                  />
                  <Text type="secondary">
                    {activeRun.current_step}/{activeRun.total_steps} {activeRun.message}
                  </Text>
                  <div className="actions-row">
                    <Button icon={<PauseCircleOutlined />} disabled={activeRun.status !== "running"} onClick={() => api.cancelSimulation(activeRun.run_id)}>
                      取消
                    </Button>
                    <Button icon={<BarChartOutlined />} disabled={!activeRun.result_path} onClick={() => openResult(activeRun)}>
                      打开结果
                    </Button>
                  </div>
                  <div className="log-box">
                    {logs.map((line, i) => (
                      <div key={i}>{line}</div>
                    ))}
                  </div>
                </>
              ) : (
                <Alert type="info" message="尚未选择运行任务" />
              )}
            </Panel>

            <Panel title="结果曲线" panelKey="result" visible={panels.result} onClose={(key) => setPanelVisible(key, false)}>
              {result ? (
                <>
                  <Tabs
                    size="small"
                    activeKey={activeResultGroup?.key}
                    onChange={setResultGroupKey}
                    items={resultGroups.map((group) => ({ key: group.key, label: group.title }))}
                  />
                  <ReactECharts option={resultOption} style={{ height: 380 }} />
                </>
              ) : (
                <Alert type="info" message="选择一个已完成任务后查看曲线" />
              )}
            </Panel>
          </div>

          <Panel title="历史记录" panelKey="history" visible={panels.history} onClose={(key) => setPanelVisible(key, false)}>
            <Table
              size="small"
              rowKey="run_id"
              dataSource={records}
              pagination={{ pageSize: 8 }}
              onRow={(record) => ({ onClick: () => openResult(record) })}
              columns={[
                {
                  title: "状态",
                  dataIndex: "status",
                  width: 100,
                  render: (status) => <Tag color={statusColor(status)}>{status}</Tag>
                },
                { title: "创建时间", dataIndex: "created_at", width: 180 },
                { title: "进度", dataIndex: "progress", width: 100, render: (value) => `${Math.round(value * 100)}%` },
                { title: "信息", dataIndex: "message" },
                { title: "结果文件", dataIndex: "result_path", ellipsis: true }
              ]}
            />
          </Panel>
        </Content>
      </Layout>
    </Layout>
  );
}
