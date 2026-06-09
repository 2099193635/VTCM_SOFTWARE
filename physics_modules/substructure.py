'''
FilePath: \VTCM_PYTHON\physics_modules\substructure.py
Description: 轨道下部结构 (扣件、轨枕、道床、路基) 相互作用力计算模块
'''
import numpy as np

class SubstructureDynamics:
    def __init__(self, fastener_params, rail_params, subrail_params):
        self.fp = fastener_params
        self.rp = rail_params
        self.sp = subrail_params

    def compute_fastener_forces(self, rs, ss):
        """计算扣件弹簧阻尼力 (对应 Force_Fastener.m)"""
        # 结构参数简化引用
        bb, aa, d = self.rp.bb, self.rp.aa, self.sp.d
        Kkjv, Ckjv, Kkjh, Ckjh = self.fp.Kkjv, self.fp.Ckjv, self.fp.Kkjh, self.fp.Ckjh
        
        # 轨枕状态切片
        Zs, Ys, Rolls = ss['XSleeper_Z'], ss['XSleeper_Y'], ss['XSleeper_Roll']
        VZs, VYs, VRolls = ss['VSleeper_Z'], ss['VSleeper_Y'], ss['VSleeper_Roll']

        # --- 左侧钢轨扣件 ---
        FV1_L = 0.5 * Kkjv * (rs['RailF_Zdis_L'] - bb * rs['RailF_Tdis_L'] - Zs + (d + bb) * Rolls) + \
                0.5 * Ckjv * (rs['RailF_Zvel_L'] - bb * rs['RailF_Tvel_L'] - VZs + (d + bb) * VRolls)
                
        FV2_L = 0.5 * Kkjv * (rs['RailF_Zdis_L'] + bb * rs['RailF_Tdis_L'] - Zs + (d - bb) * Rolls) + \
                0.5 * Ckjv * (rs['RailF_Zvel_L'] + bb * rs['RailF_Tvel_L'] - VZs + (d - bb) * VRolls)
                
        FV_L = FV1_L + FV2_L 
        
        FL_L = Kkjh * (rs['RailF_Ldis_L'] - Ys - aa * rs['RailF_Tdis_L']) + \
               Ckjh * (rs['RailF_Lvel_L'] - VYs - aa * rs['RailF_Tvel_L'])

        # --- 右侧钢轨扣件 ---
        FV1_R = 0.5 * Kkjv * (rs['RailF_Zdis_R'] - bb * rs['RailF_Tdis_R'] - Zs - (d - bb) * Rolls) + \
                0.5 * Ckjv * (rs['RailF_Zvel_R'] - bb * rs['RailF_Tvel_R'] - VZs - (d - bb) * VRolls)
                
        FV2_R = 0.5 * Kkjv * (rs['RailF_Zdis_R'] + bb * rs['RailF_Tdis_R'] - Zs - (d + bb) * Rolls) + \
                0.5 * Ckjv * (rs['RailF_Zvel_R'] + bb * rs['RailF_Tvel_R'] - VZs - (d + bb) * VRolls)
                
        FV_R = FV1_R + FV2_R
        
        FL_R = Kkjh * (rs['RailF_Ldis_R'] - Ys - aa * rs['RailF_Tdis_R']) + \
               Ckjh * (rs['RailF_Lvel_R'] - VYs - aa * rs['RailF_Tvel_R'])

        return {'FV1_L': FV1_L, 'FV2_L': FV2_L, 'FV_L': FV_L, 'FL_L': FL_L,
                'FV1_R': FV1_R, 'FV2_R': FV2_R, 'FV_R': FV_R, 'FL_R': FL_R}

    def compute_subrail_forces(self, ss, bs):
        """计算轨枕-道床-路基力学响应 (对应 Force_SubRail.m)"""
        d, Kbv, Cbv, Kbh, Cbh = self.sp.d, self.sp.Kbv, self.sp.Cbv, self.sp.Kbh, self.sp.Cbh
        Kw, Cw, Kfv, Cfv = self.sp.Kw, self.sp.Cw, self.sp.Kfv, self.sp.Cfv

        Zs, Ys, Rolls = ss['XSleeper_Z'], ss['XSleeper_Y'], ss['XSleeper_Roll']
        VZs, VYs, VRolls = ss['VSleeper_Z'], ss['VSleeper_Y'], ss['VSleeper_Roll']
        
        XSub_L, VSub_L = bs['XSubgrade_L'], bs['VSubgrade_L']
        XSub_R, VSub_R = bs['XSubgrade_R'], bs['VSubgrade_R']

        # PART1: 轨枕-道床块力元力
        FLsV = Kbv * (Zs - XSub_L - d * Rolls) + Cbv * (VZs - VSub_L - d * VRolls)
        FLsL = Kbh * Ys + Cbh * VYs
        
        FRsV = Kbv * (Zs - XSub_R + d * Rolls) + Cbv * (VZs - VSub_R + d * VRolls)
        FRsL = Kbh * Ys + Cbh * VYs

        # PART2: 道床-路基力元力 (基于 NumPy 的一维切片移位，模拟道床块纵向剪切力)
        # XSubL_1 = [XSubgrade_L(2:end), 0]
        XSubL_1 = np.append(XSub_L[1:], 0)
        XSubL_2 = np.append(0, XSub_L[:-1])
        VSubL_1 = np.append(VSub_L[1:], 0)
        VSubL_2 = np.append(0, VSub_L[:-1])

        XSubR_1 = np.append(XSub_R[1:], 0)
        XSubR_2 = np.append(0, XSub_R[:-1])
        VSubR_1 = np.append(VSub_R[1:], 0)
        VSubR_2 = np.append(0, VSub_R[:-1])

        # 左侧道床力元
        FLb1 = Kw * (XSub_L - XSubL_1) + Cw * (VSub_L - VSubL_1)
        FLb2 = Kw * (XSub_L - XSubL_2) + Cw * (VSub_L - VSubL_2)
        FLbR = Kw * (XSub_L - XSub_R) + Cw * (VSub_L - VSub_R)
        FLbf = Kfv * XSub_L + Cfv * VSub_L

        # 右侧道床力元
        FRb1 = Kw * (XSub_R - XSubR_1) + Cw * (VSub_R - VSubR_1)
        FRb2 = Kw * (XSub_R - XSubR_2) + Cw * (VSub_R - VSubR_2)
        FRbL = -FLbR
        FRbf = Kfv * XSub_R + Cfv * VSub_R

        return {'FLsV': FLsV, 'FLsL': FLsL, 'FRsV': FRsV, 'FRsL': FRsL,
                'FLb1': FLb1, 'FLb2': FLb2, 'FLbR': FLbR, 'FLbf': FLbf,
                'FRb1': FRb1, 'FRb2': FRb2, 'FRbL': FRbL, 'FRbf': FRbf}