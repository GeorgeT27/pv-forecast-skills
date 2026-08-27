#!/usr/bin/env bash
# station_analysis_short.py 的跑批脚本。
#
#   ./run_short.sh                 # 默认 mock：现产 mock 数据再跑一遍全链路（不需要模型）
#   ./run_short.sh basic           # 只跑基础分析（input + predict）
#   ./run_short.sh nanwang         # 加 --info-csv：南网口径 + factor 扫描 + city
#   ./run_short.sh cf              # 加 --counterfactual：GHI 换真值的 oracle 归因（需模型）
#   ./run_short.sh kt              # 加 --cf-kt-scale：K_t 乘性扫描（需模型）
#   ./run_short.sh full            # cf + kt 一起
#
# 跑真实数据就改下面 CONFIG 段的路径，或用环境变量覆盖任意一项：
#   INPUT=/data/in.parquet PREDICT=/data/pred.parquet ./run_short.sh nanwang
#
# 模式之后的参数原样透传给 station_analysis_short.py：
#   ./run_short.sh nanwang --drop-night --worst-only 5
set -euo pipefail
cd "$(dirname "$0")"

# ------------------------------------------------------------------ CONFIG
INPUT=${INPUT:-mock_input.parquet}
PREDICT=${PREDICT:-mock_predict.parquet}
INFO=${INFO:-mock_info.csv}
OUT=${OUT:-station_analysis_out}
DATE=${DATE:-}                      # 起报日 YYYY-MM-DD；留空则取 timestamp_win 最早日期

# 反事实 / K_t 三件套，只有 cf、kt、full 模式用得上
CKPT=${CKPT:-}                      # --checkpoints-dir
CONFIG=${CONFIG:-}                  # --config，模型的 yaml
INFER_DIR=${INFER_DIR:-.}           # inference.py 所在目录（连同它的 Base/utils 依赖）
CF_INPUT=${CF_INPUT:-}              # 推理专用输入表；留空回退 --input
KT=${KT:-0.8,0.9,1.1,1.2}           # --cf-kt-scale 的系数表

HIST_ROOT=${HIST_ROOT:-}            # 南网 IN 侧原始可用功率宽表根目录；留空不叠那条线
PY=${PY:-python3}
# ------------------------------------------------------------------

MODE=${1:-mock}
if [ $# -gt 0 ]; then shift; fi

die() { echo "run_short.sh: $*" >&2; exit 1; }
need_file() { [ -e "$1" ] || die "找不到 $2：$1"; }
need_model() {
    [ -n "$CKPT" ]   || die "$MODE 模式需要 CKPT=<checkpoints 目录>"
    [ -n "$CONFIG" ] || die "$MODE 模式需要 CONFIG=<模型 yaml>"
    need_file "$INFER_DIR/inference.py" "inference.py（用 INFER_DIR= 指到它所在目录）"
}

ARGS=()
case "$MODE" in
    mock)
        echo "==> 重建 mock 数据"
        "$PY" make_mocks.py
        INPUT=mock_input.parquet; PREDICT=mock_predict.parquet; INFO=mock_info.csv
        DATE=${DATE:-2026-07-15}
        ARGS+=(--info-csv "$INFO")
        ;;
    basic)   ;;
    nanwang) need_file "$INFO" "info.csv"; ARGS+=(--info-csv "$INFO") ;;
    cf)
        need_file "$INFO" "info.csv"; need_model
        ARGS+=(--info-csv "$INFO" --counterfactual)
        ;;
    kt)
        need_file "$INFO" "info.csv"; need_model
        ARGS+=(--info-csv "$INFO" --cf-kt-scale "$KT")
        ;;
    full)
        need_file "$INFO" "info.csv"; need_model
        ARGS+=(--info-csv "$INFO" --counterfactual --cf-kt-scale "$KT")
        ;;
    *) die "未知模式 '$MODE'；可选 mock / basic / nanwang / cf / kt / full" ;;
esac

need_file "$INPUT" "input 表"
need_file "$PREDICT" "predict 表"

CMD=("$PY" station_analysis_short.py --input "$INPUT" --predict "$PREDICT" --out-dir "$OUT")
if [ -n "$DATE" ];      then CMD+=(--date "$DATE"); fi
if [ -n "$HIST_ROOT" ]; then CMD+=(--hist-root "$HIST_ROOT"); fi
case "$MODE" in
    cf|kt|full)
        CMD+=(--checkpoints-dir "$CKPT" --config "$CONFIG" --inference-dir "$INFER_DIR")
        if [ -n "$CF_INPUT" ]; then CMD+=(--cf-input "$CF_INPUT"); fi
        ;;
esac
# macOS 自带 bash 3.2：set -u 下展开空数组会报 unbound variable，得用 ${arr[@]+...} 兜一层
CMD+=(${ARGS[@]+"${ARGS[@]}"} ${@+"$@"})

echo "==> ${CMD[*]}"
echo
"${CMD[@]}"

# 报告目录名 = 起报日去掉横杠；--date 没给时脚本推不出来，退而找 --out-dir 下最新的那个
if [ -n "$DATE" ]; then
    REPORT="$OUT/${DATE//-/}"
else
    REPORT=$(ls -dt "$OUT"/*/ 2>/dev/null | head -1 || true)
fi
echo
if [ -n "$REPORT" ] && [ -d "$REPORT" ]; then
    echo "==> 产物 $REPORT"
    find "$REPORT" -type f | sort | sed 's/^/    /'
else
    echo "==> 没找到报告目录，翻上面的日志看是不是一站都没打上分"
fi
