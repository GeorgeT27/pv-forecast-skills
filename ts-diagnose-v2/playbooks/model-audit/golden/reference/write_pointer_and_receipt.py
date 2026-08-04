"""Stage 3 参考实现：reconcile 之后的落盘收尾——写 pointer + 写工作目录回执。
钉住「两步缺一不可」的回执纪律（playbook.md §7）：pointer.py 的 write_pointer
（.modelmap 供消费方定位）与 write_receipt（诊断工作目录，供 orient 判完成/新鲜度）
必须都落盘，且两者的 commit/modelmap 路径字段必须一致（同一次 reconcile 的产物）。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "scripts"))
import pointer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelmap-dir", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--models", required=True, help="逗号分隔的模型 ID 列表")
    ap.add_argument("--date", required=True)
    ap.add_argument("--pointer-out", required=True)
    ap.add_argument("--receipt-out", default="MODELMAP_RECEIPT.json")
    ap.add_argument("--out", required=True, help="汇总产物（供 expect 断言读取）")
    a = ap.parse_args()

    models = [m.strip() for m in a.models.split(",") if m.strip()]
    pointer.write_pointer(a.pointer_out, docs_path=a.modelmap_dir, repo=a.repo,
                           commit=a.commit, models=models, date=a.date)
    rec = pointer.write_receipt(modelmap_dir=a.modelmap_dir, commit=a.commit,
                                 path=a.receipt_out)
    read_back = pointer.read_pointer(a.pointer_out)

    summary = {
        "pointer": read_back,
        "receipt": rec,
        "consistent": (read_back["commit"] == rec["commit"]
                        and read_back["path"] == rec["modelmap_dir"]),
    }
    json.dump(summary, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
