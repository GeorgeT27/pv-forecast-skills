"""adapter 模板 —— 连接你的 FastAPI 预测服务（Stage 4 反事实必需，Stage 0–3 不用）。

为什么需要它：反事实要"把被点名特征的预测序列换成真值，重新预测"，而**你的服务的
payload 结构 / 特征字段名 / 响应格式**只有你的仓库知道。本技能不假设任何 API 契约，
只定义一个薄接口，由你在这里把它接到自己的服务。

用法：
  cp <skill>/scripts/api_adapter_template.py ./adapter.py
  # 编辑 ./adapter.py，填入下面函数的 TODO；然后先跑
  #   python3 <skill>/scripts/counterfactual_api.py --dry-run ...
  # 把打印的 payload 给用户确认无误，才允许打真实 API（config.api.confirmed=true）。
"""
from __future__ import annotations

import numpy as np


# ------------------------------------------------------------- 必填：组请求
def build_payload(row: dict, replaced: dict[str, np.ndarray]) -> dict:
    """把一行样本组装成你的 FastAPI 的请求体。

    row：{"timestamp": <ISO 字符串>, "model": <模型列名或 None>,
         "features": {特征名: {"pred": (192,), "label": (192,)}}}
        —— 来自 feature_true.parquet 的原始行（特征名 = feature_pairs.json 里的 feature）；
        model 供多模型 API 路由用，单模型服务可忽略。
    replaced：{特征名: (192,) 覆盖序列}——本次要覆盖 pred 的数组（真值替换模式下是 label；
        neighbor-swap 模式下是邻行预报的对齐平移）。空 dict = 基线调用（原始预测特征重预测，
        作为反事实对照组，抵消 API 模型与离线 parquet 的版本差）。

    返回 dict（将作为 JSON POST 到 config.api.endpoint）。
    """
    raise NotImplementedError("按你的服务契约组 payload：原始特征 + replaced 覆盖")


# ------------------------------------------------------------- 必填：解响应
def parse_response(resp: dict) -> np.ndarray:
    """从响应 JSON 中取出 192 点功率预测，返回 shape (192,) 的 ndarray。"""
    raise NotImplementedError("如 return np.asarray(resp['prediction'], float)")


# ------------------------------------------------------------- 选填：健康检查 / 月度口径
def healthcheck() -> bool:
    """可选：调用前探活。返回 False 时 runner 直接停。不实现则跳过。"""
    return True


def monthly_metric(cf_rows: list[dict]) -> dict | None:
    """可选（--monthly）：用你的 metric.py 对反事实预测集复算 ds_short/ds_ultra_short 月度口径。

    cf_rows：[{"timestamp", "feature", "mode", "pred": (192,)}, ...]（反事实预测）。
    返回 {口径: 数值} 或 None（不实现则 runner 只报行级误差差）。
    """
    return None
