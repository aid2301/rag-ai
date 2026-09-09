#!/usr/bin/env python
"""评估脚本：对测试集逐题运行 RAG Pipeline，统计检索/回答指标。

用法：
    python evaluate.py                 # 使用真实 LLM（需先在设置中配置）
    python evaluate.py --dataset eval_dataset.json
    python evaluate.py --mode fast     # 强制使用 fast 模式

输出：
    - 控制台逐题结果 + 汇总表
    - eval_report.json（机器可读报告）

指标说明：
    retrieval_hit_rate    候选文档命中 expected_sources 的比例
    doc_selection_accuracy 最终选中文档命中 expected_sources 的比例
    answer_correctness    答案包含 expected_answer 关键内容的比例
    forbidden_rate        答案出现 forbidden_answer 禁词的比例（越低越好，视为幻觉风险）
    citation_accuracy     引用来源命中 expected_sources 的比例
    avg_latency_s         平均耗时
    avg_tokens            平均 token 消耗
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.database import close_db, init_db  # noqa: E402
from app.services.rag.pipeline import RAGPipeline, NoDocumentsError  # noqa: E402


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").replace("\n", "").lower()


def _contains(answer: str, needle: str) -> bool:
    if not needle:
        return True
    return _norm(needle) in _norm(answer)


def evaluate_answer(item: dict, answer: str, citations: list[dict], trace: list[dict]) -> dict:
    expected = item.get("expected_answer", "")
    forbidden = item.get("forbidden_answer", [])
    expected_sources = [s.lower() for s in item.get("expected_sources", [])]

    # 从 trace 提取候选文档与选中文档
    candidate_titles = []
    selected_titles = []
    for step in trace:
        if step["name"] == "retrieval":
            candidate_titles = [c.get("title", "") for c in step["data"].get("candidate_documents", [])]
        if step["name"] == "document_selector":
            selected_titles = [s.get("title", "") for s in step["data"].get("selected_documents", [])]

    cited_titles = [c.get("document_title", "") for c in citations]

    def hit(titles) -> bool:
        if not expected_sources:
            return True  # 无期望来源时不判失败
        joined = " ".join(titles).lower()
        return any(s in joined for s in expected_sources)

    answer_ok = _contains(answer, expected) if expected else True
    forbidden_hit = any(_contains(answer, f) for f in forbidden if f)

    return {
        "answer_correct": answer_ok,
        "forbidden_hit": forbidden_hit,
        "retrieval_hit": hit(candidate_titles),
        "selection_hit": hit(selected_titles) if selected_titles else hit(candidate_titles),
        "citation_hit": hit(cited_titles) if cited_titles else (not expected_sources),
    }


async def _run(dataset_path: str, mode: str | None, limit: int | None) -> dict:
    await init_db()
    pipeline = RAGPipeline()
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    if limit:
        dataset = dataset[:limit]

    results = []
    for item in dataset:
        q = item["question"]
        t0 = time.time()
        try:
            out = await pipeline.answer(q, conversation_id=None, mode=mode)
            latency = time.time() - t0
            metrics = evaluate_answer(
                item, out["answer"], out.get("citations", []), out.get("trace", [])
            )
            tokens = sum(u.get("total_tokens", 0) for u in out.get("token_usage", []))
            results.append(
                {
                    "id": item.get("id", q),
                    "question": q,
                    "answer": out["answer"],
                    "citations": [c["document_title"] for c in out.get("citations", [])],
                    "mode": out.get("mode"),
                    "latency_s": round(latency, 2),
                    "tokens": tokens,
                    **metrics,
                }
            )
        except NoDocumentsError as exc:
            results.append(
                {
                    "id": item.get("id", q),
                    "question": q,
                    "error": str(exc),
                    "answer_correct": False,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": item.get("id", q),
                    "question": q,
                    "error": str(exc),
                    "answer_correct": False,
                }
            )

    n = len(results)
    valid = [r for r in results if "error" not in r]
    nv = len(valid) or 1

    summary = {
        "total": n,
        "evaluated": len(valid),
        "failed": n - len(valid),
        "answer_correctness": round(sum(r["answer_correct"] for r in valid) / nv, 3),
        "retrieval_hit_rate": round(sum(r["retrieval_hit"] for r in valid) / nv, 3),
        "doc_selection_accuracy": round(sum(r["selection_hit"] for r in valid) / nv, 3),
        "citation_accuracy": round(sum(r["citation_hit"] for r in valid) / nv, 3),
        "hallucination_rate": round(sum(r["forbidden_hit"] for r in valid) / nv, 3),
        "avg_latency_s": round(sum(r.get("latency_s", 0) for r in valid) / nv, 2),
        "avg_tokens": round(sum(r.get("tokens", 0) for r in valid) / nv, 1),
    }
    return {"summary": summary, "results": results}


async def run(dataset_path: str, mode: str | None, limit: int | None) -> dict:
    await init_db()
    try:
        return await _run(dataset_path, mode, limit)
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description="企业知识库评估脚本")
    parser.add_argument("--dataset", default=str(ROOT / "examples" / "evaluation.json"))
    parser.add_argument("--mode", choices=["fast", "standard", "deep"], default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=str(ROOT / "eval_report.json"))
    args = parser.parse_args()

    report = asyncio.run(run(args.dataset, args.mode, args.limit))
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    s = report["summary"]
    print("\n==================== 评估汇总 ====================")
    print(f"题目总数:            {s['total']}")
    print(f"成功评估:            {s['evaluated']}")
    print(f"回答正确率:          {s['answer_correctness']:.1%}")
    print(f"检索命中率:          {s['retrieval_hit_rate']:.1%}")
    print(f"文档选择准确率:      {s['doc_selection_accuracy']:.1%}")
    print(f"引用准确率:          {s['citation_accuracy']:.1%}")
    print(f"幻觉风险率(禁词):    {s['hallucination_rate']:.1%}")
    print(f"平均耗时:            {s['avg_latency_s']}s")
    print(f"平均 Token:          {s['avg_tokens']}")
    print("================================================\n")

    print("逐题结果：")
    for r in report["results"]:
        flag = "OK " if r.get("answer_correct") else "FAIL"
        err = r.get("error", "")
        ans_preview = (r.get("answer") or "")[:60].replace("\n", " ")
        print(f"[{flag}] {r['id']} {r['question'][:30]}")
        if err:
            print(f"      错误: {err}")
        else:
            print(f"      引用: {r.get('citations')}  | {ans_preview}")

    print(f"\n报告已写入: {args.out}")


if __name__ == "__main__":
    main()
