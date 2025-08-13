# submittal_builder.py (cloud-ready for Streamlit Community Cloud)
import streamlit as st
from PyPDF2 import PdfMerger
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import textwrap
import tempfile
import io
import os
import sys
import datetime

# ---------- Page config ----------
st.set_page_config(page_title="Wiljo Submittal Builder", layout="centered")

# ---------- Helpers ----------
def resource_path(*parts):
    # On Streamlit Cloud, use repo-relative paths
    base = os.path.dirname(__file__)
    return os.path.join(base, *parts)

# Fonts (optional). If fonts not present, fall back to Times.
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

try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

def draw_wrapped_text(c, text, x, y, max_width, font=FONT_REG, size=12, leading=16):
    c.setFont(font, size)
    chars = max(1, int(max_width / (size * 0.5)))
    for line in textwrap.wrap(text, width=chars):
        c.drawString(x, y, line)
        y -= leading
    return y

def draw_logo_fit_box(c, logo_filename, left_x, top_y, max_width_in=1.6, max_height_in=0.75):
    logo_path = resource_path(logo_filename)
    if not os.path.exists(logo_path):
        return 0.0
    try:
        if PIL_OK:
            img = Image.open(logo_path)
            ow, oh = img.size if img else (0, 0)
        else:
            ow, oh = (400, 200)
        if ow <= 0 or oh <= 0:
            return 0.0
        box_w = float(max_width_in) * inch
        box_h = float(max_height_in) * inch
        scale = min(box_w / ow, box_h / oh)
        draw_w = ow * scale
        draw_h = oh * scale
        c.drawImage(
            ImageReader(logo_path),
            left_x,
            top_y - draw_h,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        return draw_h / inch
    except Exception:
        safe_w = min(max_width_in, 1.2)
        safe_h = min(max_height_in, 0.6)
        c.drawImage(
            ImageReader(logo_path),
            left_x,
            top_y - safe_h * inch,
            width=safe_w * inch,
            height=safe_h * inch,
            preserveAspectRatio=True,
            mask="auto",
        )
        return safe_h

def generate_binder_cover(date_str, to_name, to_company, to_addr1, to_addr2, project, submitter_name):
    """
    Letter-style binder cover with logo between two full-width lines, then body.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp.name, pagesize=LETTER)
    margin = 0.9 * inch
    x = margin
    y = LETTER_H - margin
    page_w, _ = LETTER

    # --- Top full-width break line (slightly above logo) ---
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1)
    top_line_y = y + 0.20 * inch
    c.line(x, top_line_y, page_w - x, top_line_y)

    # --- Logo (fit inside header box) ---
    drawn_h_in = draw_logo_fit_box(
        c,
        "wiljo_logo.png",
        left_x=x,
        top_y=y,
        max_width_in=1.6,
        max_height_in=0.75,
    )

    # --- Bottom full-width break line (just below logo) ---
    header_gap_in = 0.20
    bottom_line_y = y - (drawn_h_in + header_gap_in) * inch
    c.line(x, bottom_line_y, page_w - x, bottom_line_y)

    # --- Body starts below line ---
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
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_BOLD, 48)
    c.drawCentredString(width / 2, height / 2 + 40, (spec_section or "").strip())
    if product_name and product_name.strip():
        c.setFont(FONT_BOLD, 32)
        c.drawCentredString(width / 2, height / 2 - 40, product_name.strip())
    footer_text = "Wiljo Interiors, Inc.   |   109 NE 38th Street, Oklahoma City, OK 73105"
    c.setFont(FONT_REG, 10)
    c.drawCentredString(width / 2, 0.5 * inch, footer_text)
    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# ---------- UI ----------
st.title("Wiljo Submittal Builder")

# Binder info
st.header("1) Binder Cover Information")
col1, col2 = st.columns(2)
import datetime
with col1:
    project = st.text_input("Project (for Re:)", value="", placeholder="e.g., Project Name")
    submitter_name = st.text_input("Submitted By (signature name)", value="", placeholder="e.g., PM Name")
    date_text = st.date_input("Date", value=datetime.date.today(), format="MM/DD/YYYY")
with col2:
    to_name = st.text_input("To: Name", value="", placeholder="e.g., Project PM or PE")
    to_company = st.text_input("To: Company", value="", placeholder="e.g., General Contractor or CM")
    to_addr1 = st.text_input("To: Street", value="", placeholder="e.g., GC or CM Address Street")
    to_addr2 = st.text_input("To: City/State/Zip", value="", placeholder="e.g., City, State, Zip")

st.header("2) Upload Product PDFs")
uploaded_pdfs = st.file_uploader("Upload one or more product submittal PDFs", type=["pdf"], accept_multiple_files=True)

st.header("3) Add Spec Sections & Products")
if "spec_data" not in st.session_state:
    st.session_state.spec_data = []
if "confirm_clear" not in st.session_state:
    st.session_state.confirm_clear = False

with st.form("spec_form", clear_on_submit=True):
    spec = st.text_input("Spec Section (e.g., 054000 Cold Formed Metal Framing)")
    product = st.text_input("Product Name (for the section cover page)")
    pdf_files = st.multiselect("Select attached PDFs for this section", uploaded_pdfs, format_func=lambda f: getattr(f, "name", "PDF"))
    add_section = st.form_submit_button("Add Section")
    if add_section:
        pdf_payloads = [{"name": f.name, "data": f.getvalue()} for f in pdf_files]
        st.session_state.spec_data.append({"spec": (spec or "").strip(), "product": (product or "").strip(), "pdfs": pdf_payloads})

if st.session_state.spec_data:
    st.subheader("Sections Added (in order)")

    # Clear all with confirm
    if st.session_state.confirm_clear:
        col_confirm = st.columns([1, 1])
        with col_confirm[0]:
            if st.button("✅ Yes, Clear All"):
                st.session_state.spec_data.clear()
                st.session_state.confirm_clear = False
                st.rerun()
        with col_confirm[1]:
            if st.button("❌ Cancel"):
                st.session_state.confirm_clear = False
                st.rerun()
    else:
        if st.button("🗑️ Clear All Sections"):
            st.session_state.confirm_clear = True
            st.rerun()

    # Display current list
    for i, entry in enumerate(st.session_state.spec_data, start=1):
        with st.expander(f"{i}. Spec Section: {entry['spec']} — {entry['product']}  ({len(entry.get('pdfs', []))} file(s))", expanded=True):
            if entry.get("pdfs"):
                for p in entry["pdfs"]:
                    st.caption(f"- {p['name']}")
            else:
                st.caption("No PDFs attached.")

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

if st.button("📎 Generate Submittal Binder", disabled=disabled):
    # Date
    if date_text.strip():
        date_str = date_text.strip()
    else:
        today = datetime.date.today()
        try:
            date_str = today.strftime("%-m/%-d/%Y")
        except Exception:
            date_str = today.strftime("%#m/%#d/%Y")

    merger = PdfMerger()

    # Binder cover
    binder_cover = generate_binder_cover(
        date_str=date_str,
        to_name=to_name,
        to_company=to_company,
        to_addr1=to_addr1,
        to_addr2=to_addr2,
        project=project,
        submitter_name=submitter_name,
    )
    merger.append(binder_cover)

    # Sections
    for entry in st.session_state.spec_data:
        sec_cover = generate_section_cover(entry["spec"], entry["product"])
        merger.append(sec_cover)
        for p in entry.get("pdfs", []):
            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp_pdf.write(p["data"])
            tmp_pdf.flush()
            merger.append(tmp_pdf.name)

    final_output = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    merger.write(final_output.name)
    merger.close()

    st.success("✅ Submittal Binder Created")

    st.warning(
    'REMINDER: Please highlight specific items used on the product data sheet. '
    '(e.g., 5/8" Fire code, or Tile number, etc.)'
)
    with open(final_output.name, "rb") as f:
        st.download_button("⬇️ Download Submittal Binder", data=f.read(), file_name="Submittal_Binder.pdf", mime="application/pdf")
