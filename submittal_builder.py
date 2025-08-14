# submittal_builder.py — Streamlit Cloud–ready

import streamlit as st
from PyPDF2 import PdfMerger
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
import textwrap
import tempfile
import io
import os
import re
import datetime

# ---------- Page config ----------
st.set_page_config(page_title="Wiljo Submittal Builder", layout="centered")

# ---------- Helpers ----------
def resource_path(*parts):
    """Repo-relative path (works on Streamlit Cloud and locally)."""
    base = os.path.dirname(__file__)
    return os.path.join(base, *parts)

# Optional custom fonts; fall back to Times if not present
FONT_REG = "Times-Roman"
FONT_BOLD = "Times-Bold"
try:
    pdfmetrics.registerFont(TTFont("WILJO-SERIF", resource_path("fonts", "LiberationSerif-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("WILJO-SERIF-BOLD", resource_path("fonts", "LiberationSerif-Bold.ttf")))
    FONT_REG = "WILJO-SERIF"
    FONT_BOLD = "WILJO-SERIF-BOLD"
except Exception:
    pass

LETTER_W, LETTER_H = LETTER

def load_logo_imagereader(filename="wiljo_logo.png"):
    """Load a bundled logo as ImageReader (repo root)."""
    p = resource_path(filename)
    if os.path.exists(p):
        try:
            return ImageReader(p)
        except Exception:
            pass
    if os.path.exists(filename):
        try:
            return ImageReader(filename)
        except Exception:
            pass
    return None

def draw_logo_fit_box(c, logo_filename, left_x, top_y, max_width_in=1.6, max_height_in=0.75):
    """
    Draw the logo scaled to fit inside a box (inches). Returns drawn height in inches.
    """
    ir = load_logo_imagereader(logo_filename)
    if ir is None:
        try:
            st.info(f"Logo not found (looking for '{logo_filename}').")
        except Exception:
            pass
        return 0.0

    try:
        ow, oh = ir.getSize()
    except Exception:
        ow, oh = (400, 200)

    if ow <= 0 or oh <= 0:
        return 0.0

    box_w = float(max_width_in) * inch
    box_h = float(max_height_in) * inch
    scale = min(box_w / ow, box_h / oh)
    draw_w = ow * scale
    draw_h = oh * scale

    c.drawImage(
        ir,
        left_x,
        top_y - draw_h,  # ReportLab y is bottom-left
        width=draw_w,
        height=draw_h,
        preserveAspectRatio=True,
        mask="auto",
    )
    return draw_h / inch

def draw_wrapped_text(c, text, x, y, max_width, font=FONT_REG, size=12, leading=16):
    """Left-aligned wrapped text."""
    c.setFont(font, size)
    chars = max(1, int(max_width / (size * 0.5)))
    for line in textwrap.wrap(text or "", width=chars):
        c.drawString(x, y, line)
        y -= leading
    return y

# ---- centered wrap + auto-fit for section covers ----
def wrap_centered_text(c, text, center_x, top_y, max_width, font, size, leading):
    """
    Wrap text to fit max_width (approx), draw each line centered,
    and return the y after drawing along with the list of lines.
    """
    s = (text or "").strip()
    c.setFont(font, size)
    chars = max(1, int(max_width / (size * 0.5)))
    lines = textwrap.wrap(s, width=chars) if s else [""]
    y = top_y
    for line in lines:
        c.drawCentredString(center_x, y, line)
        y -= leading
    return y, lines

def draw_autofit_centered(
    c, text, center_x, box_top_y, box_height, max_width,
    font, max_size=48, min_size=14, target_lines=2, line_gap=6
):
    """
    Auto-shrinks text to fit within (max_width x box_height), centered.
    Tries from max_size down to min_size until it fits target_lines (or fewer),
    horizontal width, and vertical space. Draws and returns the final y.
    """
    s = (text or "").strip()
    if not s:
        return box_top_y

    for size in range(int(max_size), int(min_size) - 1, -1):
        leading = size + line_gap
        chars = max(1, int(max_width / (size * 0.5)))
        lines = textwrap.wrap(s, width=chars) or [""]
        needed_h = len(lines) * leading
        too_wide = any(stringWidth(line, font, size) > max_width for line in lines)

        if (len(lines) <= target_lines) and (needed_h <= box_height) and not too_wide:
            y = box_top_y - (box_height - leading) / 2
            c.setFont(font, size)
            for line in lines:
                c.drawCentredString(center_x, y, line)
                y -= leading
            return y

    # Fallback at min_size
    size = min_size
    leading = size + line_gap
    _, _ = wrap_centered_text(c, s, center_x, box_top_y - leading / 2, max_width, font, size, leading)
    return box_top_y - leading

# ---------- PDF Generators ----------
def generate_binder_cover(date_str, to_name, to_company, to_addr1, to_addr2, project, submitter_name):
    """
    Letter-style binder cover with logo between two full-width lines, then body.
    Returns a temporary file path to the PDF page.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp.name, pagesize=LETTER)
    margin = 0.9 * inch
    x = margin
    y = LETTER_H - margin
    page_w, _ = LETTER

    # Top break line (slightly above logo)
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    top_line_y = y + 0.20 * inch
    c.line(x, top_line_y, page_w - x, top_line_y)

    # Logo
    drawn_h_in = draw_logo_fit_box(
        c,
        "wiljo_logo.png",
        left_x=x,
        top_y=y,
        max_width_in=1.6,
        max_height_in=0.75,
    )

    # Bottom break line (below logo)
    header_gap_in = 0.20
    bottom_line_y = y - (drawn_h_in + header_gap_in) * inch
    c.line(x, bottom_line_y, page_w - x, bottom_line_y)

    # Body start
    body_gap_in = 0.25
    body_top_y = bottom_line_y - (body_gap_in * inch)

    # Date
    c.setFont(FONT_REG, 12)
    c.drawString(x, body_top_y, date_str)
    text_y = body_top_y - 28

    # Recipient block
    c.setFont(FONT_REG, 12)
    for line in [to_name, to_company, to_addr1, to_addr2]:
        if line and line.strip():
            c.drawString(x, text_y, line.strip())
            text_y -= 18
    text_y -= 10

    # Re: Project
    c.setFont(FONT_BOLD, 12)
    c.drawString(x, text_y, f"Re: {project}")
    text_y -= 28

    # Approval sentence
    text_y = draw_wrapped_text(
        c,
        "We are submitting the following materials for the architect’s review and approval:",
        x,
        text_y,
        max_width=(LETTER_W - 2 * margin),
        font=FONT_REG,
        size=12,
        leading=16,
    )
    text_y -= 10

    # Bulleted Spec Sections
    bullet = u"\u2022"
    c.setFont(FONT_REG, 12)
    max_width = LETTER_W - 2 * margin
    sections = st.session_state.get("spec_data") or []
    for entry in sections:
        spec_label = (entry.get("spec") or "").strip()
        if not spec_label:
            continue
        line = f"{bullet}  Spec Section {spec_label}"
        for i_line, l in enumerate(textwrap.wrap(line, width=int(max_width / (12 * 0.5)))):
            c.drawString(x + (0 if i_line == 0 else 18), text_y, l)
            text_y -= 16
        text_y -= 2

        # Overflow safety
        if text_y < 120:
            footer_text = "Wiljo Interiors, Inc.   |   109 NE 38th Street, Oklahoma City, OK 73105"
            c.setFont(FONT_REG, 10)
            c.drawCentredString(LETTER_W / 2, 0.5 * inch, footer_text)
            c.showPage()
            c.setFont(FONT_REG, 12)
            text_y = LETTER_H - margin

    text_y -= 40

    # Signature
    c.setFont(FONT_REG, 12)
    c.drawString(x, text_y, "Respectfully Submitted,")
    text_y -= 36
    c.drawString(x, text_y, submitter_name)

    # Footer
    footer_text = "Wiljo Interiors, Inc.   |   109 NE 38th Street, Oklahoma City, OK 73105"
    c.setFont(FONT_REG, 10)
    c.drawCentredString(LETTER_W / 2, 0.5 * inch, footer_text)

    c.showPage()
    c.save()
    return tmp.name

def generate_section_cover(spec_section, product_name):
    """
    Returns a BytesIO containing a one-page section cover PDF.
    - Spec Section (bold, large) auto-wraps/auto-shrinks to fit 2 lines.
    - Product Name (bold, medium) wraps below it (up to 3 lines).
    - Footer centered at bottom.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    page_w, page_h = LETTER

    # Background
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, page_w, page_h, fill=1)
    c.setFillColorRGB(0, 0, 0)

    # Layout
    margin_x = 0.85 * inch
    center_x = page_w / 2
    max_width = page_w - 2 * margin_x

    # Spec Section title (above center)
    title_box_top = page_h * 0.62
    title_box_h   = 1.8 * inch
    draw_autofit_centered(
        c,
        text=spec_section,
        center_x=center_x,
        box_top_y=title_box_top,
        box_height=title_box_h,
        max_width=max_width,
        font=FONT_BOLD,
        max_size=48,
        min_size=18,
        target_lines=2,
        line_gap=6,
    )

    # Product name below
    product_box_top = title_box_top - title_box_h - 0.25 * inch
    product_box_h   = 1.2 * inch
    draw_autofit_centered(
        c,
        text=product_name,
        center_x=center_x,
        box_top_y=product_box_top,
        box_height=product_box_h,
        max_width=max_width,
        font=FONT_BOLD,
        max_size=32,
        min_size=14,
        target_lines=3,
        line_gap=4,
    )

    # Footer
    footer_text = "Wiljo Interiors, Inc.   |   109 NE 38th Street, Oklahoma City, OK 73105"
    c.setFont(FONT_REG, 10)
    c.drawCentredString(page_w / 2, 0.5 * inch, footer_text)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

def sanitize_filename(name: str, fallback: str = "Submittal_Binder.pdf") -> str:
    """Remove illegal filename chars and ensure .pdf extension."""
    name = (name or "").strip()
    if not name:
        return fallback
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name

# ---------- UI ----------
st.title("Wiljo Submittal Builder")

# ---- Step 1: Binder Cover Information ----
st.header("1) Binder Cover Information")
col1, col2 = st.columns(2)
with col1:
    project = st.text_input("Project (for Re: line)", value="", placeholder="e.g., Project Name")
    submitter_name = st.text_input("Submitted By (PM Name)", value="", placeholder="e.g., PM Name")
    date_value = st.date_input("Date", value=datetime.date.today(), format="MM/DD/YYYY")
with col2:
    to_name = st.text_input("To: Name", value="", placeholder="e.g., CM/GC Contact")
    to_company = st.text_input("To: Company", value="", placeholder="e.g., CM/GC")
    to_addr1 = st.text_input("To: CM/GC Street", value="", placeholder="e.g., Street")
    to_addr2 = st.text_input("To: CITY/STATE/ZIP", value="", placeholder="e.g., City, State, Zip")

# ---- Step 2: Upload PDFs ----
st.header("2) Upload Product PDFs")
uploaded_pdfs = st.file_uploader(
    "Upload one or more product submittal PDFs",
    type=["pdf"],
    accept_multiple_files=True
)

# ---- Step 3: Add Spec Sections & Products ----
st.header("3) Add Spec Sections & Products")
if "spec_data" not in st.session_state:
    st.session_state.spec_data = []
if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

with st.form("spec_form", clear_on_submit=True):
    spec = st.text_input("Spec Section (e.g., 054000 Cold Formed Metal Framing)")
    product = st.text_input("Product Name (for the section cover page)")
    pdf_files = st.multiselect(
        "Select attached PDFs for this section",
        uploaded_pdfs,
        format_func=lambda f: getattr(f, "name", "PDF")
    )
    add_section = st.form_submit_button("Add Section")
    if add_section:
        pdf_payloads = [{"name": f.name, "data": f.getvalue()} for f in pdf_files]
        st.session_state.spec_data.append({
            "spec": (spec or "").strip(),
            "product": (product or "").strip(),
            "pdfs": pdf_payloads
        })

# Show current list and Clear All (with confirm)
if st.session_state.spec_data:
    st.subheader("Sections Added (in order)")

    if st.session_state.confirm_clear:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Yes, Clear All"):
                st.session_state.spec_data.clear()
                st.session_state.confirm_clear = False
                st.rerun()
        with c2:
            if st.button("❌ Cancel"):
                st.session_state.confirm_clear = False
                st.rerun()
    else:
        if st.button("🗑️ Clear All Sections"):
            st.session_state.confirm_clear = True
            st.rerun()

    for i, entry in enumerate(st.session_state.spec_data, start=1):
        with st.expander(f"{i}. Spec Section: {entry['spec']} — {entry['product']}  ({len(entry.get('pdfs', []))} file(s))", expanded=True):
            if entry.get("pdfs"):
                for p in entry["pdfs"]:
                    st.caption(f"- {p['name']}")
            else:
                st.caption("No PDFs attached.")

# ---- Step 4: Generate Submittal Binder ----
st.header("4) Generate Submittal Binder")
required_missing = []
if not (st.session_state.get("spec_data")):
    required_missing.append("Add at least one Spec Section in step 3")
if not (project or "").strip():
    required_missing.append("Project (step 1)")
if not (to_name or "").strip():
    required_missing.append("To: Name (step 1)")

if required_missing:
    st.error("Please complete the following before generating:\n- " + "\n- ".join(required_missing))
    disabled = True
else:
    disabled = False

# Custom file name (suggest Project + date)
default_filename = "Submittal_Binder.pdf"
suggested_name = (project.strip() or "Submittal_Binder")
try:
    try:
        date_tag = date_value.strftime("%Y-%m-%d")
    except Exception:
        date_tag = date_value.strftime("%m-%d-%Y")
    suggested_name = f"{suggested_name}_{date_tag}.pdf"
except Exception:
    suggested_name = f"{suggested_name}.pdf"

custom_filename_input = st.text_input('File name (include ".pdf" or leave as suggested)', value=suggested_name)

if st.button("📎 Generate Submittal Binder", disabled=disabled):
    # Use the calendar-selected date (cover wants M/D/YYYY, cross-platform)
    try:
        date_str = date_value.strftime("%-m/%-d/%Y")  # POSIX
    except Exception:
        date_str = date_value.strftime("%#m/%#d/%Y")  # Windows

    from io import BytesIO
    output_buf = BytesIO()
    temp_paths = []
    binder_cover_path = None

    try:
        with PdfMerger() as merger:
            # Binder cover
            binder_cover_path = generate_binder_cover(
                date_str=date_str,
                to_name=to_name,
                to_company=to_company,
                to_addr1=to_addr1,
                to_addr2=to_addr2,
                project=project,
                submitter_name=submitter_name,
            )
            merger.append(binder_cover_path)

            # Section covers + PDFs
            for entry in st.session_state.spec_data:
                sec_cover = generate_section_cover(entry["spec"], entry["product"])
                try:
                    sec_cover.seek(0)
                except Exception:
                    pass
                merger.append(sec_cover)

                for p in entry.get("pdfs", []):
                    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    tmp_pdf.write(p["data"])
                    tmp_pdf.flush()
                    tmp_pdf.close()
                    temp_paths.append(tmp_pdf.name)
                    merger.append(tmp_pdf.name)

            merger.write(output_buf)

        # Download
        output_buf.seek(0)
        final_name = sanitize_filename(custom_filename_input, fallback=default_filename)
        st.download_button(
            label="⬇️ Download Submittal Binder",
            data=output_buf.getvalue(),
            file_name=final_name,
            mime="application/pdf",
        )

        st.success("✅ Submittal Binder created.")
        st.warning(
            "REMINDER: Please highlight specific items used on the product data sheet. "
            "(e.g., 5/8\" Fire code, or Tile number, etc.)"
        )

    finally:
        # Cleanup temp files
        for pth in temp_paths:
            try:
                os.remove(pth)
            except Exception:
                pass
        if binder_cover_path:
            try:
                os.remove(binder_cover_path)
            except Exception:
                pass
