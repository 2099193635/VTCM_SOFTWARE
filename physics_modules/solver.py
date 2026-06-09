import numpy as np
import time
from tqdm import tqdm


class SystemDynamics:
    """系统加速度求解器"""
    
    def __init__(self, veh_params, veh_int, para_subrail, control_mode, para_extra_force):
        """
        初始化时预计算车辆系统质量向量 (恒定不变，只需算一次)
        复刻 MATLAB Subroutine_Acceleration_Output.m
        """
        p = veh_params
        sub = para_subrail
        mode = control_mode
        ep = para_extra_force
        inti = veh_int

        # =======================车辆系统=======================
        # 车体质量向量 (5)
        m_car = [p.Mc, p.Mc, p.Jcx, p.Jcy, p.Jcz]
        # 构架质量向量 (2 x 5 = 10)
        m_bogie = [p.Mt, p.Mt, p.Jtx, p.Jty, p.Jtz] * 2
        # 轮对质量向量 (4 x 5 = 20)
        m_wheelset = [p.Mw, p.Mw, p.Jwx, p.Jwy, p.Jwz] * 4
        # # 轴箱质量向量 (左4 + 右4 = 8)
        # m_axlebox = [ep.Jaxlebox] * 8
        # 组装纯车辆系统的 35 自由度质量向量
        m_vehicle = m_car + m_bogie + m_wheelset
        # =======================钢轨系统=======================
        # 单侧轨道的总模态数量
        rail_dofs = mode.NV + mode.NL + mode.NT
        m_left_rail = np.ones(rail_dofs)
        m_right_rail = np.ones(rail_dofs)
        # =======================轨下结构=======================
        # 轨道节点数量
        num_nodes = inti.Nsub + 1
        # 轨枕 (3 段拼接：沉浮Z, 横移Y, 侧滚Roll)
        m_sleeper = np.full(3 * num_nodes, sub.Ms)
        # 道床块 (2 段拼接：左右侧道床)
        m_ballast = np.full(2 * num_nodes, sub.Mb)
        # 组装整体系统自由度
        self.Mass_FULL = np.concatenate([
            m_vehicle,
            m_left_rail,
            m_right_rail,
            m_sleeper,
            m_ballast
        ])
        self.Mass_VEHICLE = np.array(m_vehicle)
        

    def compute_acceleration(self, GF_SYSTEM: np.ndarray) -> np.ndarray:
        
        # 核心：F = M * A  =>  A = F / M (Element-wise division)
        A_SYSTEM = GF_SYSTEM / self.Mass_FULL
        
        return A_SYSTEM
    
class DynamicSolver:
    """
    车辆-轨道刚柔耦合动力学核心求解器
    采用 翟方法 (Zhai Method / 新型显式积分法) 进行时域步进求解
    """
    @staticmethod
    def _as_bool(value):
        """Robust bool parser for CLI/config values ('On'/'Off', 'true'/'false', etc.)."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ('on', 'true', '1', 'yes', 'y'):
                return True
            if v in ('off', 'false', '0', 'no', 'n', ''):
                return False
        return bool(value)

    def __init__(self, topology, integration_params, switch_lock_veh_non_z, switch_lock_axlebox,
                 switch_lock_substructure, sim_switches=None):
        """
        初始化动态求解器
        :param topology: 系统拓扑对象
        :param integration_params: 积分参数对象
        :param switch_lock_veh_non_z: 车体非垂向自由度锁定开关
        :param switch_lock_axlebox: 轴箱自由度锁定开关
        :param switch_lock_substructure: 轨下结构自由度锁定开关
        :param sim_switches: 仿真功能开关对象 (ExtraforceElementSwitch)
        """
        self.topo = topology
        self.params = integration_params
        self.sim_switches = sim_switches        # 仿真功能开关（含曲线力开关）

        # 自由度锁定
        self.switch_lock_veh_non_z = self._as_bool(switch_lock_veh_non_z)
        self.switch_lock_axlebox = self._as_bool(switch_lock_axlebox)
        self.switch_lock_substructure = self._as_bool(switch_lock_substructure)

        # 锁定掩码
        self._build_freedom_locker()
    
    def _build_freedom_locker(self):
        num_dof = self.topo.Fnum_Total
        lock_mask = np.zeros(num_dof, dtype=bool) # 初始全为 False

        # --- LOCK0: 锁定车体部分自由度 (仅保留 Z 向沉浮运动) ---
        if self.switch_lock_veh_non_z:
            z_dofs = [1, 6, 11, 16, 21, 26, 31]
            all_veh_dofs = list(range(35))
            lock_dofs_veh = [d for d in all_veh_dofs if d not in z_dofs]
            lock_mask[lock_dofs_veh] = True
        # --- LOCK1: 锁定车体轴箱 ---
        if self.switch_lock_axlebox:
            lock_mask[35:43] = True  # 轴箱对应车辆系统的最后 8 个自由度 (索引 35 到 42)
        # --- LOCK2: 锁定轨下结构自由度 ---
        if self.switch_lock_substructure:
            start = self.topo.idx_Sleeper[0]
            end = self.topo.idx_Subgrade_R[1]
            lock_mask[start:end] = True
        
        self.lock_mask = lock_mask
        
    def solve(self, track_excitation, geom_info, engines, track_geometry=None, sim_switches=None,
              progress_callback=None, cancel_event=None):
        """
        执行动力学主循环
        :param track_excitation: 激扰矩阵元组 (bz_L, by_L, dbz_L, ...)
        :param geom_info: 轮轨接触几何前处理数据 (ContactGeometryInfo)
        :param engines: 打包好的物理引擎字典 (suspension, contact, assembler, dynamics)
        :param track_geometry: 预计算的线型参数矩阵字典 {'K','H','G','dK','dH','S'}，每项 (Nt,4)
        :param sim_switches: 仿真功能开关对象（优先使用构造时传入的值）
        """
        # 优先使用外部传入值，否则使用构造时注册的值
        if sim_switches is None:
            sim_switches = self.sim_switches
        Nt = self.topo.Nt
        dt = self.params.Tstep
        alpha = self.params.alpha
        beta = self.params.beta
        vc = self.params.Vc
        omg = self.params.omega  # 名义滚动角速度 rad/s
        
        # 解包物理引擎
        suspension_sys = engines['suspension']
        wr_interaction = engines['contact']
        gf_assembler = engines['assembler']
        sys_dynamics = engines['dynamics']
        
        two_point_switch = 'On'
        if sim_switches is not None and not sim_switches.is_active('Switch_2PointContact'):
            two_point_switch = 'Off'

        # 1. 申请内存：状态矩阵
        X, V, A, PadComp_L1, PadComp_L2, PadComp_R1, PadComp_R2, spy_dict = self.topo.allocate_memory(switch_2point_contact=two_point_switch)
        
        # 解包激扰矩阵 (4个轮对，长度为 Nt)
        bz_L, by_L, dbz_L, dby_L, bz_R, by_R, dbz_R, dby_R, defect_a, defect_L = track_excitation

        print(f" -> [求解器启动] 开始执行时域积分 (翟方法)，总步数: {Nt}，步长: {dt}s")
        start_time = time.time()

        # ==========================================
        # 核心积分大循环 (对应 MATLAB for ii=1:Nt)
        # ==========================================
        if progress_callback:
            progress_callback(0, Nt)

        for i in tqdm(range(Nt), desc="动力学积分进度", unit="步", ncols=100):
            if cancel_event is not None and cancel_event.is_set():
                print(" -> [求解器] 收到取消请求，提前结束积分。")
                X = X[:i + 1, :]
                V = V[:i + 1, :]
                A = A[:i + 1, :]
                for key, value in list(spy_dict.items()):
                    if hasattr(value, 'shape') and len(value.shape) >= 1 and value.shape[0] == Nt:
                        spy_dict[key] = value[:i + 1]
                break

            # ==========================================
            # STEP 1: 积分预测器 (Predictor - 翟方法)
            # ==========================================
            if i == 0:
                # 初始静止状态 (在此可加入落车静承载初始位移 X0)
                pass 
            elif i == 1:
                # 第二步：无 i-2 的历史加速度数据
                X[i, :] = X[i-1, :] + V[i-1, :] * dt + (0.5 + alpha) * A[i-1, :] * (dt**2)
                V[i, :] = V[i-1, :] + (1 + beta) * A[i-1, :] * dt
            else:
                # 第三步及以后：完整预测公式
                X[i, :] = X[i-1, :] + V[i-1, :] * dt + (0.5 + alpha) * A[i-1, :] * (dt**2) - alpha * A[i-2, :] * (dt**2)
                V[i, :] = V[i-1, :] + (1 + beta) * A[i-1, :] * dt - beta * A[i-2, :] * dt

            X[i, self.lock_mask] = 0.0
            V[i, self.lock_mask] = 0.0

            # ==========================================
            # STEP 2: 状态切片提取 (映射给各子结构)
            # ==========================================
            # 将当前步的一维长向量 X[i] 转化为带有各种属性的对象 state
            state = self.topo.extract_state(X[i, :], V[i, :], vc)
            
            # 提取当前步、4个轮对的轨道不平顺 (Irregularity)
            IrreZ_L, VIrreZ_L = bz_L[:, i], dbz_L[:, i]
            IrreZ_R, VIrreZ_R = bz_R[:, i], dbz_R[:, i]
            IrreL_L, VIrreL_L = by_L[:, i], dby_L[:, i]
            IrreL_R, VIrreL_R = by_R[:, i], dby_R[:, i]

            # ==========================================
            # STEP 3: 悬挂力计算 (Force_Pre_Sec)
            # ==========================================
            susp_forces = suspension_sys.compute_forces(state)

            # ==========================================
            # STEP 4: 提取钢轨物理状态
            # ==========================================
            t_current = i * dt
            X0t = self.params.X0 + self.params.Vc * t_current
            Lc = self.params.Lc
            Lt = self.params.Lt
            Xw = np.array([
                X0t + 2 * (Lc + Lt),  # 1位轮对 (前构架前轮)
                X0t + 2 * Lc,         # 2位轮对 (前构架后轮)
                X0t + 2 * Lt,         # 3位轮对 (后构架前轮)
                X0t                   # 4位轮对 (后构架后轮)
            ])
            rail_states = engines['rail_modal'].extract_physical_states(state.__dict__, Xw=Xw)


            # ==========================================
            # STEP 5: 轮轨接触力计算 (Contact_Wheel_Rail_TwoPoints)
            # ==========================================
            # 初始化当前步 4 个轮对的力学容器字典 (数组格式，为了送给 Assembler)
            wr_forces_keys = [
                'FNx_L', 'FNy_L', 'FNz_L', 'FNx_R', 'FNy_R', 'FNz_R', 
                'FNx_L2', 'FNy_L2', 'FNz_L2', 'FNx_R2', 'FNy_R2', 'FNz_R2',
                'MLy', 'MLz', 'MRy', 'MRz', 'rL', 'rR', 'rL2', 'rR2', 'a0', 'a02',
                'CreepForce_L', 'CreepForce_R',
                'hrL', 'eL', 'hrR', 'eR', 'hrL2', 'eL2', 'hrR2', 'eR2'  # <--- 加上这行
            ]
            wr_forces = {k: np.zeros(4) for k in wr_forces_keys}

            # 分别对 4 个轮对执行空间非线性寻优与接触力学计算
            for nw in range(4):
                # 调用我们在 wheel_rail_contact.py 中写好的终极方法
                f_nw = wr_interaction.calculate_two_point_contact(
                    nw=nw, vc=vc, omg=omg,
                    Zw=state.X_ZW[nw], Yw=state.X_YW[nw], phiw=state.X_RollW[nw], psiw=state.X_YawW[nw],
                    LRKX_Y=rail_states['RailW_Ldis_L'][nw], LRKX_Z=rail_states['RailW_Zdis_L'][nw], thetaL=rail_states['RailW_Tdis_L'][nw], 
                    RRKX_Y=rail_states['RailW_Ldis_R'][nw], RRKX_Z=rail_states['RailW_Zdis_R'][nw], thetaR=rail_states['RailW_Tdis_R'][nw],
                    VXwo=vc, VYwo=state.V_YW[nw], VZwo=state.V_ZW[nw],
                    Vwphi=state.V_RollW[nw], Vwbeta=omg, Vwpsi=state.V_YawW[nw],
                    VrkxY_L=rail_states['RailW_Lvel_L'][nw], VrkxZ_L=rail_states['RailW_Zvel_L'][nw], VrkxO_L=rail_states['RailW_Tvel_L'][nw], 
                    VrkxY_R=rail_states['RailW_Lvel_R'][nw], VrkxZ_R=rail_states['RailW_Zvel_R'][nw], VrkxO_R=rail_states['RailW_Tvel_R'][nw],
                    Irrez_L=IrreZ_L[nw], Irrey_L=IrreL_L[nw], VIrrez_L=VIrreZ_L[nw], VIrrey_L=VIrreL_L[nw],
                    Irrez_R=IrreZ_R[nw], Irrey_R=IrreL_R[nw], VIrrez_R=VIrreZ_R[nw], VIrrey_R=VIrreL_R[nw]
                )
                
                # 将第 nw 个轮对的受力组装到数组中
                for k in wr_forces_keys:
                    if k in f_nw:
                        wr_forces[k][nw] = f_nw[k]

            # ==========================================
            # STEP 6: 组装系统广义力向量 (GF_SYSTEM)
            # ==========================================
            

            fastener_forces = engines['substructure'].compute_fastener_forces(rail_states, state.__dict__)
            subrail_forces = engines['substructure'].compute_subrail_forces(state.__dict__, state.__dict__)
            
            # 送入全系统大总装！
            GF_SYSTEM = gf_assembler.assemble_GF_SYSTEM(
                state, susp_forces, wr_forces, 
                fastener_forces=fastener_forces, subrail_forces=subrail_forces, 
                rail_modal_sys=engines['rail_modal'], rail_states=rail_states
            )
            
            # ==========================================
            # STEP 6.5: 曲线等效力叠加 (Equivalent Curve Forces)
            # ==========================================
            # 完整实现 35-DOF 曲线等效力，与 MATLAB Force_EquivalentCurveForce.m 完全对应。
            # track_geometry 列顺序 (Nt,7): [Xw1, Xw2, Xw3, Xw4, Xt1, Xt2, Xc]
            if (track_geometry is not None
                    and sim_switches is not None
                    and sim_switches.is_active('Switch_CurveTrack')
                    and 'veh_params' in engines):

                ECF_35 = self._compute_curve_force(
                    step_i=i,
                    tg=track_geometry,
                    wr_forces=wr_forces,
                    state=state,
                    vc=vc,
                    veh=engines['veh_params'],
                    g=self.params.g
                )
                CF = np.zeros(len(GF_SYSTEM))
                CF[:35] = ECF_35
                GF_SYSTEM = GF_SYSTEM + CF

            # ==========================================
            # STEP 7: 求解当前步加速度 A (A = M^-1 * GF)
            # ==========================================
            # idx_start, idx_end = self.topo.idx_Car
            A[i, :] = sys_dynamics.compute_acceleration(GF_SYSTEM)
            # 自由度锁定
            A[i, self.lock_mask] = 0.0
            # ==========================================
            # STEP 8: 监视数据与结果记录 (SPY)
            # ==========================================
            # 1. 记录一系悬挂力 (将左4个和右4个拼接成长度为8的数组)
            spy_dict['Yixi_Force_x'][i, :] = np.concatenate([susp_forces['Fxf_L'], susp_forces['Fxf_R']])
            spy_dict['Yixi_Force_y'][i, :] = np.concatenate([susp_forces['Fyf_L'], susp_forces['Fyf_R']])
            spy_dict['Yixi_Force_z'][i, :] = np.concatenate([susp_forces['Fzf_L'], susp_forces['Fzf_R']])
            
            # 2. 记录二系悬挂力 (将左2个和右2个拼接成长度为4的数组)
            spy_dict['Erxi_Force_x'][i, :] = np.concatenate([susp_forces['Fxt_L'], susp_forces['Fxt_R']])
            spy_dict['Erxi_Force_y'][i, :] = np.concatenate([susp_forces['Fyt_L'], susp_forces['Fyt_R']])
            spy_dict['Erxi_Force_z'][i, :] = np.concatenate([susp_forces['Fzt_L'], susp_forces['Fzt_R']])

            # 3. 记录踏面接触区(点1)轮轨力 (拼接左4个和右4个，长度为8)
            spy_dict['TotalVerticalForce'][i, :] = np.concatenate([wr_forces['FNz_L'], wr_forces['FNz_R']])
            spy_dict['TotalLateralForce'][i, :] = np.concatenate([wr_forces['FNy_L'], wr_forces['FNy_R']])

            # 4. 记录轮缘接触区(点2)轮轨力 (动态判断是否开启了两点接触监视)
            if 'TotalVerticalForce_Point2' in spy_dict:
                spy_dict['TotalVerticalForce_Point2'][i, :] = np.concatenate([wr_forces['FNz_L2'], wr_forces['FNz_R2']])
                spy_dict['TotalLateralForce_Point2'][i, :] = np.concatenate([wr_forces['FNy_L2'], wr_forces['FNy_R2']])

            if progress_callback:
                progress_callback(i + 1, Nt)
            
        print(f" -> [求解完毕] 总耗时: {time.time()-start_time:.2f} s")
        return X, V, A, spy_dict

    # ------------------------------------------------------------------
    def _compute_curve_force(self, step_i: int, tg: dict, wr_forces: dict,
                              state, vc: float, veh, g: float) -> np.ndarray:
        """
        计算完整 35-DOF 曲线等效力向量。
        完全对应 MATLAB Force_EquivalentCurveForce.m。

        track_geometry (tg) 列顺序 (Nt, 7):
          col 0: Xw1 (1位轮对)  col 1: Xw2 (2位轮对)
          col 2: Xw3 (3位轮对)  col 3: Xw4 (4位轮对 / X0t)
          col 4: Xt1 (1号构架)  col 5: Xt2 (2号构架)
          col 6: Xc  (车体中心)

        返回长度为 35 的 ndarray，对应 GF_VEHICLE DOF 顺序：
          [0-4]   车体  Y, Z, Roll, Spin, Yaw
          [5-9]   构架1 Y, Z, Roll, Spin, Yaw
          [10-14] 构架2 Y, Z, Roll, Spin, Yaw
          [15-34] 轮对1-4 各5个 DOF (Y, Z, Roll, Spin, Yaw)
        """
        # ── 车辆参数 ──────────────────────────────────────────────────
        Mc, Mt, Mw    = veh.Mc, veh.Mt, veh.Mw
        Jcx, Jcz      = veh.Jcx, veh.Jcz
        Jtx, Jtz      = veh.Jtx, veh.Jtz
        Jwx, Jwy, Jwz = veh.Jwx, veh.Jwy, veh.Jwz
        Kpy, Cpy      = veh.Kpy, veh.Cpy
        Kpx, Cpx      = veh.Kpx, veh.Cpx
        Ksx, Ksy      = veh.Ksx, veh.Ksy
        Csx, Csy      = veh.Csx, veh.Csy
        Lc, Lt        = veh.Lc,  veh.Lt
        HcB, HBt, Htw = veh.HcB, veh.HBt, veh.Htw
        dw, ds        = veh.dw, veh.ds
        R_wheel       = veh.R                      # 标称车轮半径
        omg           = vc / R_wheel               # 标称滚动角速度

        # ── 线型参数（7个位置）───────────────────────────────────────
        K_all   = tg['K'][step_i, :]    # 曲率 (7,)
        H_all   = tg['H'][step_i, :]    # 超高角绝对值 (7,)
        dK_all  = tg['dK'][step_i, :]   # d(K)/dt (7,)
        dH_all  = tg['dH'][step_i, :]   # d(H)/dt (7,)
        ddH_all = tg['ddH'][step_i, :]  # d²(H)/dt² (7,)

        # 带符号的超高角及其导数（右转曲线 K<0 时 H 取负，与 MATLAB Theta_mile 一致）
        _eps = 1e-10
        sk      = np.sign(K_all)
        sk[np.abs(K_all) < _eps] = 0.0
        H_s     = H_all   * sk    # Theta_mile(x)    (7,)
        dH_s    = dH_all  * sk    # dTheta_mile(x)   (7,)
        ddH_s   = ddH_all * sk    # ddTheta_mile(x)  (7,)

        # 安全曲率半径（避免除以零）
        R_all = np.where(np.abs(K_all) > _eps, 1.0 / K_all, 1e10)

        # ── 各部件拆包（MATLAB 命名约定）────────────────────────────
        # 轮对 (cols 0-3)
        tsew  = H_s[:4];    dsew  = dH_s[:4];    ddsew = ddH_s[:4]
        dKw   = dK_all[:4]; Rw    = R_all[:4]
        # 构架 (cols 4-5)
        tset1, tset2   = H_s[4],    H_s[5]
        dset1, dset2   = dH_s[4],   dH_s[5]
        ddset1, ddset2 = ddH_s[4],  ddH_s[5]
        dKt1,  dKt2    = dK_all[4], dK_all[5]
        Rt1,   Rt2     = R_all[4],  R_all[5]
        # 车体 (col 6)
        tsec  = H_s[6];   dsec  = dH_s[6];   ddsec = ddH_s[6]
        dKc   = dK_all[6]; Rc   = R_all[6]

        # ── 接触半距 a0 (来自当前步轮轨接触几何) ─────────────────────
        a0_raw = wr_forces.get('a0', 0.0)
        a0_arr = np.asarray(a0_raw, dtype=float).ravel()
        if a0_arr.size == 0:
            a0_arr = np.zeros(4)
        elif a0_arr.size < 4:
            a0_arr = np.full(4, float(a0_arr[0]))
        a0c  = float(np.mean(a0_arr))
        a0t1 = float((a0_arr[0] + a0_arr[1]) / 2.0)
        a0t2 = float((a0_arr[2] + a0_arr[3]) / 2.0)
        a0w  = a0_arr[:4]                               # 各轮对接触半距

        # ── 轮对旋转角速度 Vwb (Spin DOF, Python 0-based 索引 18,23,28,33) ──
        Vwb = state.V_SpinW   # (4,) 来自 topology.py StepState.extract_state()

        # ══════════════════ 计算 35 项等效力 ══════════════════════════
        # ─── 车体 (P1-P5) ───────────────────────────────────────────
        P1  = Mc * a0c * ddsec  +  Mc * vc**2 / Rc * tsec
        P2  = 0.0
        P3  = (Mc*g*tsec - Mc*(vc**2/Rc)
               - Mc*(R_wheel + Htw + HBt + HcB) * ddsec
               + 2*Ksy*(Lc**2/Rc) + 2*Csy*Lc**2*dKc)
        P4  = (-2*HcB*Ksy*(Lc**2/Rc) - 2*HcB*Csy*Lc**2*dKc
               - Jcx * ddsec)
        P5  = -Jcz * vc * dKc

        # ─── 构架1 (P6-P10) ─────────────────────────────────────────
        P6  = Mt * a0t1 * ddset1  +  Mt * (vc**2 / Rt1) * tset1
        P7  = 0.0
        P8  = (2*Kpy*(Lt**2/Rt1) + 2*Cpy*Lt**2*dKt1
               - Ksy*(Lc**2/Rc) - Csy*Lc**2*dKc
               - Mt*(vc**2/Rt1) - Mt*(R_wheel + Htw)*ddset1
               + Mt*g*tset1)
        P9  = (-2*Htw*Kpy*(Lt**2/Rt1) - 2*Htw*Cpy*Lt**2*dKt1
               - HBt*Ksy*(Lc**2/Rc) - HBt*Csy*Lc**2*dKc
               - Jtx * ddset1)
        P10 = (-Jtz*vc*dKt1
               - 2*Ksx*ds**2*(Lc/Rc) - 2*Csx*ds**2*Lc*dKc)

        # ─── 构架2 (P11-P15) ────────────────────────────────────────
        P11 = Mt * a0t2 * ddset2  +  Mt * (vc**2 / Rt2) * tset2
        P12 = 0.0
        P13 = (2*Kpy*(Lt**2/Rt2) + 2*Cpy*Lt**2*dKt2
               - Ksy*(Lc**2/Rc) - Csy*Lc**2*dKc
               - Mt*(vc**2/Rt2) - Mt*(R_wheel + Htw)*ddset2
               + Mt*g*tset2)
        P14 = (-2*Htw*Kpy*(Lt**2/Rt2) - 2*Htw*Cpy*Lt**2*dKt2
               - HBt*Ksy*(Lc**2/Rc) - HBt*Csy*Lc**2*dKc
               - Jtx * ddset2)
        P15 = (-Jtz*vc*dKt2
               + 2*Ksx*ds**2*(Lc/Rc) + 2*Csx*ds**2*Lc*dKc)

        # ─── 轮对1 (P16-P20) ────────────────────────────────────────
        P16 = Mw * a0w[0] * ddsew[0]  +  Mw * (vc**2 / Rw[0]) * tsew[0]
        P17 = 0.0
        P18 = (-Mw*(vc**2/Rw[0]) - Mw*R_wheel*ddsew[0]
               - Kpy*(Lt**2/Rt1) - Cpy*Lt**2*dKt1
               + Mw*g*tsew[0])
        P19 = Jwy * (Vwb[0] - omg) * (vc / Rw[0])  -  Jwx * ddsew[0]
        P20 = (Jwy * dsew[0] * (Vwb[0] - omg)
               - Jwz*vc*dKw[0]
               - 2*Kpx*dw**2*Lt/Rt1 - 2*Cpx*dw**2*Lt*dKt1)

        # ─── 轮对2 (P21-P25) ────────────────────────────────────────
        P21 = Mw * a0w[1] * ddsew[1]  +  Mw * (vc**2 / Rw[1]) * tsew[1]
        P22 = 0.0
        P23 = (-Mw*(vc**2/Rw[1]) - Mw*R_wheel*ddsew[1]
               - Kpy*(Lt**2/Rt1) - Cpy*Lt**2*dKt1
               + Mw*g*tsew[1])
        P24 = Jwy * (Vwb[1] - omg) * (vc / Rw[1])  -  Jwx * ddsew[1]
        P25 = (Jwy * dsew[1] * (Vwb[1] - omg)
               - Jwz*vc*dKw[1]
               + 2*Kpx*dw**2*Lt/Rt1 + 2*Cpx*dw**2*Lt*dKt1)

        # ─── 轮对3 (P26-P30) ────────────────────────────────────────
        P26 = Mw * a0w[2] * ddsew[2]  +  Mw * (vc**2 / Rw[2]) * tsew[2]
        P27 = 0.0
        P28 = (-Mw*(vc**2/Rw[2]) - Mw*R_wheel*ddsew[2]
               - Kpy*(Lt**2/Rt2) - Cpy*Lt**2*dKt2
               + Mw*g*tsew[2])
        P29 = Jwy * (Vwb[2] - omg) * (vc / Rw[2])  -  Jwx * ddsew[2]
        P30 = (Jwy * dsew[2] * (Vwb[2] - omg)
               - Jwz*vc*dKw[2]
               - 2*Kpx*dw**2*Lt/Rt2 - 2*Cpx*dw**2*Lt*dKt2)

        # ─── 轮对4 (P31-P35) ────────────────────────────────────────
        P31 = Mw * a0w[3] * ddsew[3]  +  Mw * (vc**2 / Rw[3]) * tsew[3]
        P32 = 0.0
        P33 = (-Mw*(vc**2/Rw[3]) - Mw*R_wheel*ddsew[3]
               - Kpy*(Lt**2/Rt2) - Cpy*Lt**2*dKt2
               + Mw*g*tsew[3])
        P34 = Jwy * (Vwb[3] - omg) * (vc / Rw[3])  -  Jwx * ddsew[3]
        P35 = (Jwy * dsew[3] * (Vwb[3] - omg)
               - Jwz*vc*dKw[3]
               + 2*Kpx*dw**2*Lt/Rt2 + 2*Cpx*dw**2*Lt*dKt2)

        return np.array([
            P1,  P2,  P3,  P4,  P5,
            P6,  P7,  P8,  P9,  P10,
            P11, P12, P13, P14, P15,
            P16, P17, P18, P19, P20,
            P21, P22, P23, P24, P25,
            P26, P27, P28, P29, P30,
            P31, P32, P33, P34, P35,
        ], dtype=float)
