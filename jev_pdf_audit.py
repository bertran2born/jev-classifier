#!/usr/bin/env python3
"""Screen a directory of scientific PDFs with Jev / TypeSafe.

This is a screening tool, not an empirical test of p-hacking or researcher intent.
Input: text excerpts from local PDFs. Output: structured study-level labels.

Usage:
    python jev_pdf_audit.py /path/to/pdfs --limit 20
    python jev_pdf_audit.py /path/to/pdfs
    python jev_pdf_audit.py /path/to/pdfs --dry-run

Environment:
    TYPESAFE_API_KEY=...  (not needed for --dry-run)
Requirements:
    pip install pymupdf requests
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time

try:
    import fitz  # PyMuPDF
except ImportError:
    raise SystemExit("Missing dependency: pip install pymupdf")
try:
    import requests
except ImportError:
    raise SystemExit("Missing dependency: pip install requests")

API_URL = "https://api.typesafe.ai/v1/systemone"
SCHEMA_VERSION = "screening_v1_2026_11"

QUESTIONS = {
    "field": {
        "type": "choice",
        "instructions": "Classify the main scientific field of this study. Only use the supplied article excerpts.",
        "criteria": {
            "genetics": "Genetics, genomics or heritability",
            "psychology": "Psychology, cognition or behavioral science",
            "economics": "Economics or econometrics",
            "sociology_politics": "Sociology, political science or demographic studies",
            "medicine": "Medicine or epidemiology",
            "education": "Educational research",
            "climate": "Climate or environmental science",
            "other_unclear": "Another domain or cannot tell",
        },
    },
    "primary_finding": {
        "type": "choice",
        "instructions": "Compared with the authors' EXPLICIT scientific hypothesis (not political ideology), what do the main findings indicate? If the hypothesis is not stated, choose unclear.",
        "criteria": {
            "supports": "Main findings tend to support the stated hypothesis",
            "contradicts": "Main findings tend to contradict the stated hypothesis",
            "mixed": "Main findings are mixed or heterogeneous",
            "unclear": "Not ascertainable from supplied excerpts",
        },
    },
    "significance": {
        "type": "choice",
        "instructions": "Classify statistical significance of the PRIMARY inferential result, if explicitly reported. Never deduce from a qualitative conclusion.",
        "criteria": {
            "significant": "Primary result reported statistically significant",
            "not_significant": "Primary result reported not statistically significant",
            "mixed": "Several primary tests with mixed significance",
            "unclear": "Unclear, not applicable or not evidenced in the excerpts",
        },
    },
    "preregistration": {
        "type": "choice",
        "instructions": "What do the excerpts EXPLICITLY establish about preregistration or a prospective statistical analysis plan? Do not interpret absence of mention as absence of preregistration.",
        "criteria": {
            "yes_explicit": "The study explicitly describes preregistration or an advance-registered analysis plan",
            "no_explicit": "The study explicitly states it was not preregistered",
            "not_established": "Nothing conclusive about preregistration is shown",
        },
    },
    "choice_timing": {
        "type": "choice",
        "instructions": "When were analytic decisions (model selection, sample exclusions, outcome definitions, covariates) made? Classify post hoc ONLY if explicitly evidenced. Do NOT infer research misconduct or motivation.",
        "criteria": {
            "prespecified": "Analytic decisions explicitly described as prespecified",
            "posthoc_explicit": "Analytic decisions explicitly described as changed or chosen after examining observed results",
            "both": "Both prespecified and expressly post hoc analyses are documented",
            "unknown": "Timing of analytic decisions cannot be established from excerpts",
        },
    },
    "multiple_testing": {
        "type": "choice",
        "instructions": "What do the excerpts establish about correction for multiple hypothesis testing? Treat no mention as unknown, not necessarily uncorrected.",
        "criteria": {
            "corrected": "Explicit control for multiplicity, such as FDR or Bonferroni, reported",
            "uncorrected_explicit": "Multiple tests explicitly reported without correction, or authors explicitly state no adjustment",
            "not_applicable": "Clearly no multiplicity issue in the reported primary analysis",
            "unknown": "Insufficient evidence in excerpts",
        },
    },
    "robustness": {
        "type": "choice",
        "instructions": "Are sensitivity analyses or alternative model specifications explicitly reported? Not mentioning them in excerpts does not mean the paper lacks them.",
        "criteria": {
            "reported": "Explicit sensitivity analyses, replications, or robustness checks reported",
            "absent_explicit": "Authors explicitly acknowledge no such checks were performed",
            "unknown": "Not established from excerpts",
        },
    },
    "exclusions": {
        "type": "choice",
        "instructions": "Classify only explicit information about participant/observation exclusions or data cleaning, without inferring missing information as misconduct.",
        "criteria": {
            "justified": "Explicit operational criteria for exclusions or filtering are described",
            "posthoc_explicit": "Exclusion criteria explicitly changed after examination of results",
            "unknown_or_na": "Insufficient evidence or exclusions not relevant",
        },
    },
    "interpretation": {
        "type": "choice",
        "instructions": "Does the authors' stated interpretation of the main result make stronger statistical or causal claims than the supplied results warrant? Choose unclear if excerpts are insufficient.",
        "criteria": {
            "aligned": "Interpretation appears consistent with the statistics shown",
            "overclaim": "An identifiable claim appears stronger than the shown evidence warrants",
            "unclear": "Insufficient evidence or no comparison possible",
        },
    },
}

METHOD = re.compile(
    r"\b(methods?|methodolog\w*|design|sampling|sample selection|exclusion\w*|"
    r"covariat\w*|controll?ed|controls?|confound\w*|model selection|regression|"
    r"randomi[sz]\w*|analysis plan|analytic plan|preregist\w*|pre-regist\w*|"
    r"data cleaning|imputation|attrition|dropout|inclusion criteria|"
    r"échantillon|méthod\w*|exclu\w*|régression|préenregistr\w*)\b", re.I)
RESULT = re.compile(
    r"\b(results?|findings?|effect size|coefficients?|confidence intervals?|"
    r"statisticall?y significant|p[- ]values?|hypothes\w*|odds ratio|"
    r"hazard ratio|estimate\w*|estimateur\w*|significati\w*|résultat\w*|"
    r"intervalle de confiance|effet\w*)\b|\bp\s*[<=>]\s*\.?\d", re.I)
ROBUST = re.compile(
    r"\b(robustness|sensitivity analysis|multiverse|specification curve|"
    r"specifications?|multiple comparisons?|multiple testing|bonferroni|"
    r"false discovery|fdr|adjusted p|correction|limitations?|"
    r"supplementar\w*|sensitivity|robustesse|sensibilité|analyses complémentaires)\b", re.I)
REFERENCES = re.compile(r"^\s*(references|bibliography|références|bibliographie)\s*$", re.I)


def collect_blocks(pdf: Path, max_pages: int):
    pages = 0
    total = 0
    excerpts = []
    with fitz.open(pdf) as doc:
        n_pages = len(doc)
        for i in range(min(n_pages, max_pages)):
            page = doc[i]
            pages += 1
            text = page.get_text("text", sort=True)
            total += len(text.strip())
            if i > max(2, n_pages // 2) and REFERENCES.search(text[:500]):
                continue
            for item in page.get_text("blocks", sort=True):
                if len(item) < 5 or not isinstance(item[4], str):
                    continue
                block = re.sub(r"[ \t]+", " ", item[4]).strip()
                block = re.sub(r"(?<!\n)\n(?!\n)", " ", block)
                if len(block) < 45:
                    continue
                # Slightly prefer blocks with substantive statistical evidence.
                score = (
                    2 * len(METHOD.findall(block))
                    + 2 * len(RESULT.findall(block))
                    + 3 * len(ROBUST.findall(block))
                )
                excerpts.append((score, i + 1, block[:1900]))
    return n_pages, pages, total, excerpts


def build_packet(excerpts, cap):
    """Build a bounded, provenance-tagged excerpt, not a full-paper representation."""
    if not excerpts:
        return "", []
    preamble = (
        "SCIENTIFIC ARTICLE EXCERPTS ONLY: These are selected fragments, NOT the "
        "full article. Lack of evidence in fragments is NOT evidence of absence. "
        "Do not infer researcher intent or ideological preferences. Use 'unknown' "
        "or equivalent when evidence is incomplete. Page tags refer to PDF pages.\n\n"
    )
    # Header and abstract candidates, then highest-score method/result excerpts.
    beginnings = [(s, p, x) for (s, p, x) in excerpts if p <= 2]
    beginnings = beginnings[:8]
    ranked = sorted(excerpts, key=lambda v: (-v[0], v[1]))
    selected = []
    selected_keys = set()
    budget = max(0, cap - len(preamble))
    for sequence in (beginnings, ranked):
        for score, page, block in sequence:
            key = (page, block[:100])
            if key in selected_keys or budget < 200:
                continue
            chunk = f"[PDF page {page}] {block}\n\n"
            if len(chunk) > budget:
                chunk = chunk[:budget]
            selected.append((page, chunk))
            selected_keys.add(key)
            budget -= len(chunk)
        if budget < 200:
            break
    selected.sort(key=lambda v: v[0])
    pages = sorted({p for p, _ in selected})
    return (preamble + "".join(chunk for _, chunk in selected))[:cap], pages


def study_identity(pdf: Path):
    st = pdf.stat()
    key = hashlib.sha256(str(pdf.resolve()).encode()).hexdigest()[:18]
    return key, st.st_size, st.st_mtime_ns


def ask_jev(packet: str, key: str, max_attempts: int = 6):
    data = {"model": "jev-latest", "state": packet, "questions": QUESTIONS}
    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(max_attempts):
        try:
            resp = requests.post(API_URL, headers=hdr, json=data, timeout=120)
            if resp.status_code in (429, 529, 502, 503, 504):
                if attempt + 1 == max_attempts:
                    resp.raise_for_status()
                wait = min(40, 2 ** attempt + random.random())
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdecimal():
                    wait = min(120, max(wait, float(retry_after)))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            body = resp.json()
            if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
                raise ValueError("Jev API response lacks an answers object")
            for name, question in QUESTIONS.items():
                answer = body["answers"].get(name)
                if not isinstance(answer, dict) or answer.get("choice") not in question["criteria"]:
                    raise ValueError(f"Missing or invalid Jev choice for {name}")
                probabilities = answer.get("probabilities")
                if not isinstance(probabilities, dict) or set(probabilities) != set(question["criteria"]):
                    raise ValueError(f"Missing or invalid Jev probabilities for {name}")
                values = [*probabilities.values(), answer.get("confidence")]
                if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                    raise ValueError(f"Invalid Jev probability/confidence for {name}")
                if not math.isclose(sum(probabilities.values()), 1, abs_tol=0.01):
                    raise ValueError(f"Jev probabilities do not sum to one for {name}")
            return body
        except (requests.Timeout, requests.ConnectionError):
            if attempt + 1 == max_attempts:
                raise
            time.sleep(min(40, 2 ** attempt + random.random()))
    raise RuntimeError("Could not complete Jev request")


def analyze_pdf(pdf: Path, outdir: Path, api_key: str | None, max_pages: int, cap: int, dry_run: bool):
    identity, size, mtime = study_identity(pdf)
    row = {
        "schema_version": SCHEMA_VERSION,
        "id": identity,
        "pdf": str(pdf.resolve()),
        "file_size": size,
        "mtime_ns": mtime,
        "max_pages": max_pages,
        "max_chars": cap,
    }
    try:
        n_pages, read_pages, total_text, excerpts = collect_blocks(pdf, max_pages)
        row.update(pages_total=n_pages, pages_read=read_pages, chars_extracted=total_text)
        if total_text < 600:
            row.update(status="needs_ocr", error="Too little extractable text: likely scanned/image PDF")
            return row
        packet, pages_used = build_packet(excerpts, cap)
        row["pages_used"] = ",".join(map(str, pages_used))
        if len(packet) < 600:
            row.update(status="needs_review", error="Too little usable text extracted")
            return row
        excerpt_path = outdir / "excerpts" / f"{identity}.txt"
        excerpt_path.parent.mkdir(parents=True, exist_ok=True)
        excerpt_path.write_text(packet, encoding="utf-8")
        row["excerpt_file"] = str(excerpt_path.resolve())
        row["chars_sent"] = len(packet)
        row["coverage"] = "selected_excerpts_only"
        if dry_run:
            row["status"] = "dry_run"
            return row
        result = ask_jev(packet, api_key)
        row["status"] = "ok"
        row["model"] = result.get("model", "")
        row["input_tokens"] = result.get("usage", {}).get("input_tokens", "")
        for name, q in QUESTIONS.items():
            answer = result["answers"].get(name, {})
            label = answer.get("choice", "")
            prob = answer.get("probabilities", {})
            row[name] = label
            row[name + "_prob"] = prob.get(label, "")
            row[name + "_confidence"] = answer.get("confidence", "")
            row[name + "_all_probabilities"] = json.dumps(prob, sort_keys=True)
        flags = []
        for name, target in (
            ("choice_timing", "posthoc_explicit"),
            ("exclusions", "posthoc_explicit"),
            ("multiple_testing", "uncorrected_explicit"),
            ("interpretation", "overclaim"),
        ):
            if row.get(name) == target and float(row.get(name + "_prob") or 0) >= 0.8:
                flags.append(f"review_{name}")
        row["review_flags"] = ";".join(flags)
        return row
    except Exception as exc:
        row["status"] = "error"
        # Avoid printing request headers/keys; standard exception messages only.
        row["error"] = f"{type(exc).__name__}: {str(exc)[:350]}"
        return row


def load_previous(journal: Path):
    prev = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            prev[row.get("id")] = row
    return prev


def export_csv(records, csv_path: Path):
    fields = ["id", "pdf", "status", "error", "pages_total", "pages_read", "pages_used",
              "chars_extracted", "chars_sent", "input_tokens", "coverage",
              "review_flags", "excerpt_file", "model", "schema_version", "file_size", "mtime_ns",
              "max_pages", "max_chars"]
    for name in QUESTIONS:
        fields.extend([name, name + "_prob", name + "_confidence", name + "_all_probabilities"])
    temp = csv_path.with_suffix(".csv.tmp")
    with temp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in sorted(records.values(), key=lambda r: r.get("pdf", "")):
            w.writerow(row)
    temp.replace(csv_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf_dir", type=Path, help="Folder containing PDFs, scanned recursively")
    ap.add_argument("--out", type=Path, default=Path("jev-audit-results"), help="Local output directory")
    ap.add_argument("--limit", type=int, default=0, help="Process only the first N matching PDFs (0 = all)")
    ap.add_argument("--workers", type=int, default=4, help="Number of parallel API requests (default: 4)")
    ap.add_argument("--max-pages", type=int, default=100, help="PDF pages read per file (default: 100)")
    ap.add_argument("--max-chars", type=int, default=22000, help="Max excerpt chars sent per file (default: 22000)")
    ap.add_argument("--dry-run", action="store_true", help="Extract excerpts locally only; do not contact Jev")
    ap.add_argument("--force", action="store_true", help="Reprocess existing results, e.g. after changing QUESTIONS (new API calls)")
    args = ap.parse_args()
    if not args.pdf_dir.is_dir():
        ap.error(f"Not a directory: {args.pdf_dir}")
    if args.limit < 0 or args.workers < 1 or args.max_chars < 1000 or args.max_pages < 1:
        ap.error("--limit must be ≥0; --workers ≥1; --max-pages ≥1; --max-chars ≥1000")
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key and not args.dry_run:
        ap.error("Set TYPESAFE_API_KEY first, or pass --dry-run")
    outdir = args.out.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    # Local extraction checks must never overwrite paid classification results.
    journal = outdir / ("dry-run.jsonl" if args.dry_run else "results.jsonl")
    csv_path = outdir / ("dry-run.csv" if args.dry_run else "results.csv")
    records = load_previous(journal)
    pdfs = sorted(p for p in args.pdf_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if args.limit:
        pdfs = pdfs[: args.limit]
    todo = []
    for p in pdfs:
        try:
            identity, size, mtime = study_identity(p)
        except OSError as exc:
            print(f"Could not stat {p}: {exc}", file=sys.stderr)
            continue
        old = records.get(identity)
        if old and old.get("status") in ("ok", "needs_ocr", "needs_review") and not args.dry_run and not args.force \
                and old.get("schema_version") == SCHEMA_VERSION \
                and old.get("max_pages") == args.max_pages and old.get("max_chars") == args.max_chars \
                and old.get("file_size") == size and old.get("mtime_ns") == mtime:
            continue
        todo.append(p)
    print(f"Found {len(pdfs)} PDFs; {len(todo)} to process; results: {outdir}", flush=True)
    finished = 0
    failed = False
    interrupted = False
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(analyze_pdf, p, outdir, key, args.max_pages, args.max_chars, args.dry_run): p for p in todo}
            with journal.open("a", encoding="utf-8") as log:
                for future in as_completed(futures):
                    row = future.result()
                    failed |= row["status"] == "error"
                    records[row["id"]] = row
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                    finished += 1
                    print(f"[{finished}/{len(todo)}] {row['status']:12} {Path(row['pdf']).name}", flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print("Interrupted; completed results have been saved. Rerun to resume.", file=sys.stderr)
    finally:
        export_csv(records, csv_path)
        good = sum(r.get("status") == "ok" for r in records.values())
        print(f"CSV: {csv_path} | classified: {good} | journal: {journal}", flush=True)
    return 130 if interrupted else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
