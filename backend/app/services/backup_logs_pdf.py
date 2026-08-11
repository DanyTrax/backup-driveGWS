"""PDF export for backup execution history (panel list)."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from app.schemas.tasks import BackupLogOut

_FONT_CANDIDATES = (
    (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ),
)

# A4 landscape usable width with margins 8+8 ≈ 281 mm — anchos deben sumar exactamente.
_PAGE_USABLE_MM = 281.0
_COL_W = (26.0, 26.0, 48.0, 40.0, 30.0, 18.0, 22.0, 14.0, 12.0, 16.0, 29.0)
assert abs(sum(_COL_W) - _PAGE_USABLE_MM) < 0.01


def _ascii_fold(text: str, max_len: int) -> str:
    s = (text or "").replace("\n", " ").strip()
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    norm = unicodedata.normalize("NFKD", s)
    return norm.encode("ascii", "ignore").decode("ascii") or "—"


def _dt_short(v: datetime | None) -> str:
    if v is None:
        return "—"
    # Compacto para caber en columna sin solapar
    return v.strftime("%y-%m-%d %H:%M")


def _fmt_bytes(n: int | None) -> str:
    try:
        v = int(n or 0)
    except (TypeError, ValueError):
        return "—"
    if v < 1000:
        return str(v)
    if v < 1_000_000:
        return f"{v / 1000:.1f}K"
    if v < 1_000_000_000:
        return f"{v / 1_000_000:.1f}M"
    return f"{v / 1_000_000_000:.2f}G"


def _max_chars(width_mm: float, font_size: float = 6.5) -> int:
    """Aprox. caracteres que caben sin desbordar la celda (DejaVu ~0.35*size mm)."""
    return max(3, int(width_mm / max(font_size * 0.32, 1.5)))


def render_backup_logs_pdf(
    rows: list[BackupLogOut],
    *,
    filter_note: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError(
            "Dependencia PDF no instalada: ejecutá pip install fpdf2 en el entorno del API."
        ) from exc

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_margins(8, 10, 8)

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

    def set_font(size: float, bold: bool = False) -> None:
        if use_unicode:
            pdf.set_font("ExportFont", "B" if bold else "", size)
        else:
            pdf.set_font("Helvetica", "B" if bold else "", size)

    def fit(s: str, width_mm: float, font_size: float = 6.5) -> str:
        t = (s or "").replace("\n", " ").replace("\r", " ").strip() or "—"
        max_len = _max_chars(width_mm, font_size)
        if len(t) > max_len:
            t = t[: max(1, max_len - 1)] + "…"
        if not use_unicode:
            t = _ascii_fold(t, max_len)
        # Ajuste fino con get_string_width si la fuente está activa
        try:
            while len(t) > 1 and pdf.get_string_width(t) > width_mm - 1.2:
                t = t[:-2] + "…"
        except Exception:
            pass
        return t

    def draw_header() -> None:
        set_font(6.5, bold=True)
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
            "Resumen",
        )
        for i, h in enumerate(headers):
            pdf.cell(_COL_W[i], 6, fit(h, _COL_W[i], 6.5), border=1, align="C")
        pdf.ln()

    pdf.add_page()
    set_font(12, bold=True)
    pdf.cell(
        0,
        7,
        fit("Historial de ejecuciones (backup)", _PAGE_USABLE_MM, 12),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    set_font(8)
    gen = generated_at or datetime.now(timezone.utc)
    line_meta = (
        f"Generado (UTC): {gen.isoformat(timespec='seconds')}  |  Filas: {len(rows)}"
        + (f"  |  Filtro: {filter_note}" if filter_note else "")
    )
    pdf.multi_cell(0, 4, fit(line_meta, _PAGE_USABLE_MM, 8))
    pdf.ln(1)

    draw_header()
    set_font(6.5)
    row_h = 5.0
    bottom_limit = pdf.h - pdf.b_margin - 8

    for row in rows:
        if pdf.get_y() + row_h > bottom_limit:
            pdf.add_page()
            draw_header()
            set_font(6.5)

        acc = row.account_email or f"{str(row.account_id)[:10]}…"
        task = row.task_name or f"{str(row.task_id)[:10]}…"
        batch = f"{str(row.run_batch_id)[:8]}" if row.run_batch_id else "—"
        err_src = (row.error_summary or "").strip() or "—"
        scope = f"{row.scope}/{row.mode}"

        cells = [
            fit(_dt_short(row.started_at), _COL_W[0]),
            fit(_dt_short(row.finished_at), _COL_W[1]),
            fit(acc, _COL_W[2]),
            fit(task, _COL_W[3]),
            fit(scope, _COL_W[4]),
            fit(row.status, _COL_W[5]),
            fit(_fmt_bytes(row.bytes_transferred), _COL_W[6]),
            fit(str(row.messages_count), _COL_W[7]),
            fit(str(row.errors_count), _COL_W[8]),
            fit(batch, _COL_W[9]),
            fit(err_src, _COL_W[10]),
        ]
        for i, text in enumerate(cells):
            align = "R" if i in (6, 7, 8) else "L"
            pdf.cell(_COL_W[i], row_h, text, border=1, align=align)
        pdf.ln()

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
