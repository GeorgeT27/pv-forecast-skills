"""光伏预测结果分析的实现层。

两个 CLI 入口（station_analysis_short.py / station_analysis_ultra_short.py）只留参数解析与主流程编排，
计算、绘图、IO 都在这里。

  timeseries      list 单元格展平、时间掩码、两/多序列对齐
  metrics         全部指标：RMSE / nRMSE / 南网口径（短期+超短期）/ 离群 / 反事实分解
  inputs          info.csv 与命令行 spec 的解析、按模板解析站点列名
  plotting        matplotlib 共用件（字体、时间轴、历史/窗口面板）
  plots_short     短期图：每站 2x2、舰队总览、反事实分解
  plots_ultra     超短期图：每站 2x2（17 线功率）
  solar           晴空辐照 GHI_cs、晴空指数 K_t、K_t 空间缩放、时区/坐标体检
  counterfactual  反事实：oracle 换真值 + K_t 乘性扫描，逐趟推理与逐站分解
  short_analysis  短期：单窗口全流程编排
  ultra_loaders   超短期：时间网格与三个 loader
  history_raw     南网 IN 侧原始可用功率宽表

本文件不做任何 re-export：plots_* 会拉起 matplotlib、counterfactual 会拉起模型栈，
`import pvcore` 保持零成本，各入口按需只导自己那几个模块。
"""
