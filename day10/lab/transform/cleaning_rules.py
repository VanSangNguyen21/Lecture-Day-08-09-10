"""
Cleaning rules — raw export → cleaned rows + quarantine.

Baseline gồm các failure mode mở rộng (allowlist doc_id, parse ngày, HR stale version).
Sinh viên thêm ≥3 rule mới: mỗi rule phải ghi `metric_impact` (xem README — chống trivial).
"""

from __future__ import annotations

import csv
import hashlib
import re
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

# Khớp export hợp lệ trong lab (mở rộng khi nhóm thêm doc mới — phải đồng bộ contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


# Pydantic Model for Schema Validation (Distinction / Bonus Feature)
class CleanedRow(BaseModel):
    chunk_id: str
    doc_id: str
    chunk_text: str = Field(min_length=8)
    effective_date: date
    exported_at: datetime

    @field_validator("doc_id")
    @classmethod
    def validate_doc_id(cls, v: str) -> str:
        if v not in ALLOWED_DOC_IDS:
            raise ValueError(f"doc_id '{v}' is not in allowed list")
        return v


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Trả về (iso_date, error_reason).
    iso_date rỗng nếu không parse được.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def _get_hr_leave_cutoff() -> str:
    """
    [Rule mới 1] Dynamic versioning cutoff: Đọc từ data_contract.yaml hoặc environment variable.
    """
    # Đọc từ environment variable trước
    env_cutoff = os.environ.get("HR_LEAVE_MIN_EFFECTIVE_DATE")
    if env_cutoff:
        return env_cutoff.strip()
    
    # Fallback load từ data_contract.yaml
    try:
        contract_path = Path(__file__).resolve().parent.parent / "contracts" / "data_contract.yaml"
        if contract_path.is_file():
            with contract_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                cutoff = data.get("policy_versioning", {}).get("hr_leave_min_effective_date")
                if cutoff:
                    return str(cutoff).strip()
    except Exception:
        pass
    return "2026-01-01"


def _mask_pii_entities(text: str) -> str:
    """
    [Rule mới 2] PII Masking: Che giấu email và số điện thoại không hợp lệ.
    """
    # Che email không thuộc hệ thống nội bộ (@company.internal)
    def email_repl(match):
        email = match.group(0)
        if email.lower().endswith("@company.internal"):
            return email
        return "[MASKED_EMAIL]"
    
    text = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", email_repl, text)
    
    # Che số điện thoại chung (10 số bắt đầu bằng 0), cho phép ext. 2000
    text = re.sub(r"\b0\d{9}\b", "[MASKED_PHONE]", text)
    return text


def _validate_content_integrity(doc_id: str, text: str) -> Tuple[bool, str]:
    """
    [Rule mới 3] Content Integrity Validation: Đảm bảo nội dung chunk khớp với tài liệu.
    """
    text_lower = text.lower()
    if doc_id == "policy_refund_v4":
        keywords = ["hoàn tiền", "refund", "trả lại", "đơn hàng", "yêu cầu"]
        if not any(k in text_lower for k in keywords):
            return False, "refund_policy_content_mismatch"
    elif doc_id == "sla_p1_2026":
        keywords = ["sla", "phản hồi", "response", "xử lý", "ticket", "sự cố"]
        if not any(k in text_lower for k in keywords):
            return False, "sla_policy_content_mismatch"
    return True, ""


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Trả về (cleaned, quarantine).
    """
    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    hr_cutoff = _get_hr_leave_cutoff()

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        # 1) Quarantine: doc_id check (baseline)
        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        # 2) Normalize effective_date (baseline)
        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # 3) Quarantine: stale HR policy using dynamic cutoff (Rule 1 / baseline)
        if doc_id == "hr_leave_policy" and eff_norm < hr_cutoff:
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                    "cutoff_used": hr_cutoff,
                }
            )
            continue

        # 4) Quarantine: missing text check (baseline)
        if not text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        # 5) Content integrity validation (Rule 3)
        integrity_ok, integrity_reason = _validate_content_integrity(doc_id, text)
        if not integrity_ok:
            quarantine.append({**raw, "reason": integrity_reason})
            continue

        # 6) Text normalization
        norm_text_content = " ".join(text.strip().split())
        
        # 7) PII masking (Rule 2)
        norm_text_content = _mask_pii_entities(norm_text_content)

        # 8) Deduplication check (baseline)
        key = _norm_text(norm_text_content)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        # 9) Fix stale refund window (baseline)
        fixed_text = norm_text_content
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ngày làm việc" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ngày làm việc",
                    "7 ngày làm việc",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        # 10) Pydantic validation gate (Distinction / Bonus Feature)
        try:
            chunk_id_cand = _stable_chunk_id(doc_id, fixed_text, seq + 1)
            
            validated = CleanedRow(
                chunk_id=chunk_id_cand,
                doc_id=doc_id,
                chunk_text=fixed_text,
                effective_date=eff_norm,
                exported_at=exported_at or datetime.now().isoformat()
            )
            
            seq += 1
            cleaned.append({
                "chunk_id": validated.chunk_id,
                "doc_id": validated.doc_id,
                "chunk_text": validated.chunk_text,
                "effective_date": validated.effective_date.isoformat(),
                "exported_at": validated.exported_at.isoformat(),
            })
        except Exception as pyd_err:
            quarantine.append({
                **raw,
                "reason": f"pydantic_schema_validation_failed: {str(pyd_err)}"
            })
            continue

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
