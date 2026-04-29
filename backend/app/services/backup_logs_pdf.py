"""PDF export for backup execution history (panel list)."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

from app.schemas.tasks import BackupLogOut

_FONT_CANDIDATES = (
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
)


def _ascii_fold(text: str, max_len: int) -> str:
    s = (text or "").replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    norm = unicodedata.normalize("NFKD", s)
    return norm.encode("ascii", "ignore").decode("ascii") or "—"


def _dt_str(v: datetime | None) -> str:
    if v is None:
        return "—"
    return v.isoformat(timespec="seconds", sep=" ")


def render_backup_logs_pdf(
    rows: list[BackupLogOut],
    *,
    filter_note: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(10, 10, 10)

    regular_path: Path | None = None
    bold_path: Path | None = None
    for reg, bold in _FONT_CANDIDATES:
        if reg.is_file():
            regular_path = reg
            bold_path = bold if bold.is_file() else reg
            break

    use_unicode = regular_path is not None
    if use_unicode and regular_path is not None and bold_path is not None:
        pdf.add_font("ExportFont", "", str(regular_path))
        pdf.add_font("ExportFont", "B", str(bold_path))

    def set_font(size: int, bold: bool = False) -> None:
        if use_unicode:
            pdf.set_font("ExportFont", "B" if bold else "", size)
        else:
            pdf.set_font("Helvetica", "B" if bold else "", size)

    def clip_txt(s: str, max_len: int) -> str:
        t = (s or "").replace("\n", " ").strip()
        if len(t) > max_len:
            t = t[: max_len - 1] + "…"
        return t if use_unicode else _ascii_fold(t, max_len + 20)

    pdf.add_page()
    set_font(14, bold=True)
    title = clip_txt("Historial de ejecuciones (backup)", 120)
    pdf.cell(0, 8, title, ln=1)
    set_font(9)
    gen = generated_at or datetime.now(timezone.utc)
    line_meta = (
        f"Generado (UTC): {gen.isoformat(timespec='seconds')}  |  Filas: {len(rows)}"
        + (f"  |  Filtro: {filter_note}" if filter_note else "")
    )
    pdf.multi_cell(0, 5, clip_txt(line_meta, 500))
    pdf.ln(2)

    col_w = [36, 36, 42, 38, 28, 22, 24, 18, 14, 14, 46]
    headers = (
        "Inicio",
        "Fin",
        "Cuenta",
        "Tarea",
        "Alcance",
        "Estado",
        "Bytes",
        "Msg",
        "Err",
        "Lote",
        "Resumen error",
    )

    set_font(8, bold=True)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 6, clip_txt(h, 40), border=1)
    pdf.ln()

    set_font(7)
    for row in rows:
        if pdf.get_y() > 190:
            pdf.add_page()
            set_font(8, bold=True)
            for i, h in enumerate(headers):
                pdf.cell(col_w[i], 6, clip_txt(h, 40), border=1)
            pdf.ln()
            set_font(7)

        acc = row.account_email or f"{str(row.account_id)[:12]}…"
        task = row.task_name or f"{str(row.task_id)[:12]}…"
        batch = f"{str(row.run_batch_id)[:10]}…" if row.run_batch_id else "—"
        err_src = row.error_summary or "—"

        cells = [
            clip_txt(_dt_str(row.started_at), 40),
            clip_txt(_dt_str(row.finished_at), 40),
            clip_txt(acc, 80),
            clip_txt(task, 80),
            clip_txt(f"{row.scope}/{row.mode}", 40),
            clip_txt(row.status, 24),
            str(row.bytes_transferred),
            str(row.messages_count),
            str(row.errors_count),
            clip_txt(batch, 24),
            clip_txt(err_src, 200),
        ]
        for i, text in enumerate(cells):
            pdf.cell(col_w[i], 5, text, border=1)
        pdf.ln()

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()