# -*- coding: utf-8 -*-
"""TimesFM-3 零样本封装模板（2026-09-07 v2，拷去训练机用）。

契约（按你的 pipeline 约定，v2 修订：无 label / 设备自理 / NaN adapter 自己处理）：
  - torch.nn.Module；forward(batch_dict, labels=None)，推理只传一个位置参数；
    labels 仅为接口兼容保留，**传了也忽略**，恒不算 loss；
  - 返回对象 .logits 非 None 且为 [B, pred_len] tensor；
    另带 .predictions（同 logits）、.quantiles [B, pred_len, 9]（供后续 conformal/南网 p* 用）；
  - batch_dict 扁平 dict，key=parquet 列名，value=[B, L]（tensor/ndarray/list 均可，CPU）；
    一行一个样本，timestamp_win=起报时刻，observe_power=纯历史 672，_predict 列=未来 192；
  - **设备自理**：默认 auto（有 cuda 用 cuda），config 可强制 "cuda"/"cpu"；输出 tensor 在该设备上；
  - **NaN 自理**：默认逐行沿时间轴线性内插（端点用最近有效值延伸），整行全 NaN 置 0；
    config 可切 "zero"（一律置 0）或 "raise"（发现即报错，排查数据时用）。

安装（目标机）：
  pip install "timesfm[torch]"
  权重 google/timesfm-3.0-pytorch 首次运行自动从 HF 下载（可先 huggingface-cli download 预热）。
  ⚠️ v3 权重 license 为非商用非生产（timesfm-non-commercial-license-v1.0）——本次仅零样本验证实验。

拷过去后先跑本文件末尾的 __main__ 冒烟测试（随机数据，含 NaN 注入），过了再接真 pipeline。
核对点状态（2026-09-07 已对照 GitHub master 源码 src/timesfm3/evaluator.py 逐项核实）：
  V1 ✅ 参数名 past_only_covariates / past_future_covariates，均为"每样本一项"的 list，
     默认 None 可整体不传，单样本也可为 None；协变量总预算约 31 路（future 优先占槽）；
  V2 ✅ contexts 每项 np.atleast_2d，(1,672) 二维与 1 维皆可；
  V3 ✅ ForecastOutput.forecast=点预报（=中位数分位！南网 p* 提取时记住这点），_pick_target 兼容；
  V4 ForecastOutput.quantiles 标注 Optional，return_quantiles=True 默认开——若为 None 降级点预测即可；
  另：predict_batch 返回 Iterator（代码里已 list() 物化）；make_positive=True 默认钳非负；
     勿开 univariate=True（该模式会丢弃全部协变量）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


@dataclass
class TransformersAdaptedModelOutput:
    """若 pipeline 已有同名输出类，删掉这个定义改为 import 你们自己的。"""
    logits: torch.Tensor = None
    predictions: torch.Tensor = None
    quantiles: Optional[torch.Tensor] = None
    loss: Optional[torch.Tensor] = None          # 恒为 None，字段保留只为兼容


DEFAULT_CFG = {
    "dataset": {"pv_col": "observe_power"},
    "timesfm3": {
        "checkpoint": "google/timesfm-3.0-pytorch",
        "context_len": 672,
        "pred_len": 192,
        "device": "auto",           # "auto" | "cuda" | "cpu"
        # 未来已知协变量：[历史列(672), 未来列(192)] 成对，二者拼成 864 喂 past_future。
        # 按你的 parquet 实际列名改；以后加 spread 就再放一对 ["ssrd_spread","ssrd_spread_predict"]。
        "past_future_cols": [
            ["general_ghi", "general_ghi_predict"],
            ["general_temp", "general_temp_predict"],
            ["GHI_solargis", "ghi_solargis_predict"],
            ["temp_solargis", "temp_solargis_predict"],
        ],
        # 只有历史、未来未知的协变量列（672），暂无就留空。
        "past_only_cols": [],
        "per_core_batch_size": 32,
        "return_quantiles": True,   # V4：报错先改 False
        "nan_policy": "interp",     # "interp"（线性内插，默认）| "zero" | "raise"
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class TransformersAdaptedTimesFM3Model(nn.Module):
    def __init__(self, model_config: Optional[dict] = None, **kwargs):
        super().__init__()
        cfg = _merge(DEFAULT_CFG, model_config or {})
        self.target_col = cfg["dataset"].get("pv_col", "observe_power")
        t = cfg["timesfm3"]
        self.checkpoint = t["checkpoint"]
        self.context_len = int(t["context_len"])
        self.pred_len = int(t["pred_len"])
        self.device_pref = t.get("device", "auto")
        self.past_future_cols = [tuple(p) for p in t["past_future_cols"]]
        self.past_only_cols = list(t["past_only_cols"])
        self.per_core_batch_size = int(t["per_core_batch_size"])
        self.return_quantiles = bool(t["return_quantiles"])
        self.nan_policy = t["nan_policy"]
        self._backbone = None
        self._backbone_device = None

    # ------------------------------------------------------------------ 设备
    def _resolve_device(self) -> str:
        if self.device_pref == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return self.device_pref

    # ------------------------------------------------------------------ backbone
    def _ensure_backbone(self, want: str):
        if self._backbone is not None and self._backbone_device == want:
            return
        from timesfm3 import ModelConfig, TimesFM3Evaluator   # 懒 import：不装包也能 import 本模块
        self._backbone = TimesFM3Evaluator(ModelConfig(
            checkpoint_path=self.checkpoint,
            per_core_batch_size=self.per_core_batch_size,
            device=want,
        ))
        self._backbone_device = want

    # ------------------------------------------------------------------ NaN
    @staticmethod
    def _interp_nan(arr: np.ndarray) -> np.ndarray:
        """逐行沿时间轴线性内插；端点 NaN 用最近有效值延伸（np.interp 的钳位行为）；整行 NaN 置 0。"""
        out = arr.copy()
        idx = np.arange(arr.shape[1])
        for i in range(arr.shape[0]):
            row = out[i]
            m = np.isfinite(row)
            if m.all():
                continue
            if not m.any():
                out[i] = 0.0
                continue
            row[~m] = np.interp(idx[~m], idx[m], row[m])
        return out

    # ------------------------------------------------------------------ 取列
    def _col(self, batch_dict: dict, col: str) -> np.ndarray:
        if col not in batch_dict:
            raise KeyError(f"batch_dict 缺列 {col!r}；现有 keys={sorted(batch_dict)[:20]}...")
        v = batch_dict[col]
        arr = v.detach().cpu().numpy() if isinstance(v, torch.Tensor) else np.asarray(v)
        arr = np.asarray(arr, dtype=np.float32)
        if arr.ndim == 1:                       # 单样本容错 → [1, L]
            arr = arr[None, :]
        if not np.isfinite(arr).all():
            if self.nan_policy == "interp":
                arr = self._interp_nan(arr)
            elif self.nan_policy == "zero":
                arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
            else:
                bad = int((~np.isfinite(arr)).sum())
                raise ValueError(f"列 {col!r} 含 {bad} 个非有限值（nan_policy='raise'）")
        return arr

    @staticmethod
    def _pick_target(o) -> np.ndarray:
        """兼容 forecast 形状 (variates, horizon) 或 (horizon,)（核对点 V3）。"""
        f = np.asarray(o)
        return f[0] if f.ndim == 2 else f

    # ------------------------------------------------------------------ forward
    def forward(self, batch_dict: dict, labels=None) -> TransformersAdaptedModelOutput:
        # labels 仅为接口兼容，忽略。
        want = self._resolve_device()
        self._ensure_backbone(want)
        dev = torch.device(want)

        tgt = self._col(batch_dict, self.target_col)[:, -self.context_len:]      # [B,672]
        B = tgt.shape[0]

        pf = {}
        for hist_c, fut_c in self.past_future_cols:
            h = self._col(batch_dict, hist_c)[:, -self.context_len:]             # [B,672]
            f = self._col(batch_dict, fut_c)[:, : self.pred_len]                 # [B,192]
            pf[(hist_c, fut_c)] = np.concatenate([h, f], axis=1)                 # [B,864]
        po = {c: self._col(batch_dict, c)[:, -self.context_len:] for c in self.past_only_cols}

        inputs, pf_list, po_list = [], [], []
        for i in range(B):
            inputs.append(tgt[i][None, :])                                       # (1,672) 核对点 V2
            if pf:
                pf_list.append(np.stack([pf[k][i] for k in pf]))                 # (C,864)
            if po:
                po_list.append(np.stack([po[c][i] for c in po]))                 # (C,672)

        kwargs = dict(horizon=self.pred_len, return_quantiles=self.return_quantiles)
        if pf_list:
            kwargs["past_future_covariates"] = pf_list                           # 核对点 V1
        if po_list:
            kwargs["past_only_covariates"] = po_list
        outs = list(self._backbone.predict_batch(inputs, **kwargs))  # 返回 Iterator，须物化

        fc = np.stack([self._pick_target(o.forecast) for o in outs])             # [B,192]
        logits = torch.as_tensor(fc, dtype=torch.float32, device=dev)

        quantiles = None
        q0 = getattr(outs[0], "quantiles", None)
        if self.return_quantiles and q0 is not None:
            qs = []
            for o in outs:
                q = np.asarray(o.quantiles)                                      # (variates,H,9) 或 (H,9)
                qs.append(q[0] if q.ndim == 3 else q)
            quantiles = torch.as_tensor(np.stack(qs), dtype=torch.float32, device=dev)  # [B,192,9]

        return TransformersAdaptedModelOutput(logits=logits, predictions=logits,
                                              quantiles=quantiles, loss=None)


# ---------------------------------------------------------------------- 冒烟测试
if __name__ == "__main__":
    np.random.seed(0)
    B = 2
    day = np.clip(np.sin(np.linspace(0, 7 * 2 * np.pi, 672)), 0, None).astype(np.float32)
    batch = {"observe_power": np.tile(day * 50, (B, 1))}
    for h, f in DEFAULT_CFG["timesfm3"]["past_future_cols"]:
        batch[h] = np.tile(day * 800, (B, 1))
        batch[f] = np.tile(day[:192] * 800, (B, 1))
    # NaN 注入：验证 adapter 自理
    batch["observe_power"][0, 100:110] = np.nan
    batch["general_ghi"][1, :5] = np.nan            # 端点 NaN → 最近值延伸
    m = TransformersAdaptedTimesFM3Model()
    out = m(batch)                                   # 推理：单位置参数，无 labels
    print("logits:", tuple(out.logits.shape), out.logits.device)     # 期望 (2, 192)
    if out.quantiles is not None:
        print("quantiles:", tuple(out.quantiles.shape))              # 期望 (2, 192, 9)
    assert out.logits is not None and out.logits.shape == (B, 192)
    print("smoke ok")
