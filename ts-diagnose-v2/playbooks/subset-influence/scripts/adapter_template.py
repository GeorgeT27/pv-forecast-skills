"""adapter 模板 —— 连接你的训练仓库（Mode B 必需，Mode A 不用）。

为什么需要它：回放分组、评估 checkpoint、算梯度都要调用**你训练代码里的**采样函数、
模型类（M1=FourierMobaTransformer / M2=PatchRegForecast / M3=MoiraiPvForecaster /
M4=PatchTSTPvForecaster）与数据加载。本技能不假设你的目录结构，只定义一个薄接口，
由你在这里把它接到自己的仓库。

用法：
  cp <skill>/scripts/adapter_template.py ./adapter.py
  # 编辑 ./adapter.py，填入下面 5 个函数的 TODO（从 influence_config.json.train_repo 导入；
  # 第 5 个 load_loss_history 可选——只服务 Stage 1 训练动力学的 checkpoint 路径）
本技能脚本会 `import adapter` 并调用这些函数。填不了的函数留 NotImplementedError，
只跑用得到它的阶段（如只做 Stage 3 不做回放，可不填 sample_assignments）。
"""
from __future__ import annotations

import numpy as np

# 建议：把训练仓库根加进 sys.path，从中导入采样器与模型
# import sys, json
# CFG = json.load(open("influence_config.json"))
# sys.path.insert(0, CFG["train_repo"])
# from your_pkg.sampling import assign_stations_to_chunks
# from your_pkg.models import FourierMobaTransformer, PatchRegForecast, ...
# from your_pkg.data import build_station_dataloader


# ---------------------------------------------------------------- Stage 0：回放分组
def sample_assignments(iteration: int, seed) -> list[list[str]]:
    """复现某一迭代的分组：返回 K 个 chunk（见实验线 chunking），每个是站 id 列表。

    必须用与训练**完全相同**的随机流程（同一函数 + 同一 seed 推进方式）。
    若训练里 seed 是「基础种子 + 迭代号」派生，请在此如实复现该派生。
    """
    raise NotImplementedError("接入训练仓库的分组采样函数，返回 [[站,...]×K]")


# ------------------------------------------------- Stage 0 指纹 / Stage 2 补料：评估与模型
def load_model(model_name: str, ckpt_path: str, device: str = "cpu"):
    """按模型名 + checkpoint 路径构建并载入模型，返回可推理/可求梯度的对象（eval 态）。"""
    raise NotImplementedError("按 model_name 选类、load_state_dict(ckpt_path)")


def predict_station(model, station_id: str, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """在某站数据上前向，返回 (pred, true)，形状均 (n_samples, 192)。

    用于 ckpt_eval 重算留出站 RMSE（station_id = 测试站）与 Stage 0 的指纹验证
    （在全部训练站上评估）。数据加载走你训练时同一套 pipeline，保证特征一致。
    """
    raise NotImplementedError("构建该站 dataloader，前向出 (pred,true)")


# ---------------------------------------------------------------- Stage 3：梯度（TracIn）
def loss_gradient(model, station_id: str, cfg: dict,
                  n_windows: int = 200, params_filter=None) -> np.ndarray:
    """在某站一个固定子样本上算训练损失对参数的梯度，展平成 1 维向量返回。

    - station_id = 训练站 => 得 g_s；station_id = 测试站(留出站) => 得 g_test。
    - params_filter：可选，只取部分层（如最后线性头）以降内存；两侧必须一致。
    - 固定子样本（同一 n_windows、同一顺序）保证跨 checkpoint 可比。
    """
    raise NotImplementedError("对训练损失 backward，收集并展平梯度")


# ------------------------------------------- Stage 1（可选）：checkpoint 内的 loss 历史
def load_loss_history(model_name: str, ckpt_path: str):
    """若训练把逐 epoch loss 存进了 checkpoint（如 ckpt["loss_history"]），在此取出。

    返回 [(epoch, loss), ...]；没存则返回 None（Stage 1 训练动力学将只依赖日志路径，
    日志也没有就整段跳过——所以本函数**可不实现**，默认 None 不阻塞任何阶段）。
    只取 dict 里的小标量列表，别把权重张量带出来（上下文纪律）。
    """
    return None
