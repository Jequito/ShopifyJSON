import streamlit as st
import requests
import pandas as pd
import html
import re
import io
import time
from urllib.parse import urlparse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Shopify Product Scraper",
    page_icon="🛍️",
    layout="wide",
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def clean_url(raw: str) -> str:
    """Normalise a Shopify store URL to https://domain.com"""
    raw = raw.strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    return f"{parsed.scheme}://{parsed.netloc}"


def decode_description(text: str) -> str:
    """
    Shopify descriptions often contain:
      • HTML entities  (&amp; &lt; &#39; etc.)
      • Unicode escape sequences  (\u003e \u0026 etc.)
    Convert everything back to readable text and strip HTML tags.
    """
    if not text:
        return ""

    # 1. Decode JSON-style unicode escapes  \uXXXX  →  real character
    try:
        text = text.encode("utf-8").decode("unicode_escape")
    except (UnicodeDecodeError, ValueError):
        pass

    # 2. Decode HTML entities  &amp; → &,  &#39; → '  etc.
    text = html.unescape(text)

    # 3. Strip HTML tags, preserving newlines for block elements
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    # 4. Collapse excessive whitespace / blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_page(session: requests.Session, base_url: str, page: int, limit: int = 250) -> list:
    """Fetch one page of products.json; returns list of product dicts."""
    url = f"{base_url}/products.json?limit={limit}&page={page}"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("products", [])
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 430 or resp.status_code == 429:
            st.warning("Rate limited – waiting 5 seconds before retrying…")
            time.sleep(5)
            return fetch_page(session, base_url, page, limit)
        raise e


def scrape_all_products(base_url: str, progress_bar, status_text) -> list[dict]:
    """Page through products.json until an empty page is returned."""
    all_rows = []
    page = 1

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    with requests.Session() as session:
        session.headers.update(headers)

        while True:
            status_text.text(f"Fetching page {page}…  ({len(all_rows)} products so far)")
            products = fetch_page(session, base_url, page)

            if not products:
                break

            for p in products:
                # Build one row per variant so every variant is its own Excel row
                description = decode_description(p.get("body_html", ""))
                base_info = {
                    "Product ID":    p.get("id", ""),
                    "Title":         p.get("title", ""),
                    "Vendor":        p.get("vendor", ""),
                    "Product Type":  p.get("product_type", ""),
                    "Tags":          ", ".join(p.get("tags", [])),
                    "Description":   description,
                    "Handle":        p.get("handle", ""),
                    "Published At":  p.get("published_at", ""),
                    "Created At":    p.get("created_at", ""),
                    "Updated At":    p.get("updated_at", ""),
                }

                variants = p.get("variants", [])
                images = p.get("images", [])
                first_image = images[0].get("src", "") if images else ""

                if variants:
                    for v in variants:
                        row = {**base_info}
                        row.update({
                            "Variant ID":         v.get("id", ""),
                            "Variant Title":       v.get("title", ""),
                            "SKU":                v.get("sku", ""),
                            "Price":              v.get("price", ""),
                            "Compare At Price":   v.get("compare_at_price", ""),
                            "Available":          v.get("available", ""),
                            "Inventory Quantity": v.get("inventory_quantity", ""),
                            "Weight":             v.get("grams", ""),
                            "Requires Shipping":  v.get("requires_shipping", ""),
                            "Taxable":            v.get("taxable", ""),
                            "Option1 Name":       p.get("options", [{}])[0].get("name", "") if p.get("options") else "",
                            "Option1 Value":      v.get("option1", ""),
                            "Option2 Name":       p.get("options", [{}])[1].get("name", "") if len(p.get("options", [])) > 1 else "",
                            "Option2 Value":      v.get("option2", ""),
                            "Option3 Name":       p.get("options", [{}])[2].get("name", "") if len(p.get("options", [])) > 2 else "",
                            "Option3 Value":      v.get("option3", ""),
                            "Image URL":          v.get("featured_image", {}).get("src", "") if v.get("featured_image") else first_image,
                            "Product URL":        f"{base_url}/products/{p.get('handle', '')}",
                        })
                        all_rows.append(row)
                else:
                    # No variants – still add the product
                    base_info.update({
                        "Variant ID": "", "Variant Title": "", "SKU": "",
                        "Price": "", "Compare At Price": "", "Available": "",
                        "Inventory Quantity": "", "Weight": "",
                        "Requires Shipping": "", "Taxable": "",
                        "Option1 Name": "", "Option1 Value": "",
                        "Option2 Name": "", "Option2 Value": "",
                        "Option3 Name": "", "Option3 Value": "",
                        "Image URL": first_image,
                        "Product URL": f"{base_url}/products/{p.get('handle', '')}",
                    })
                    all_rows.append(base_info)

            progress_bar.progress(min(page / 50, 0.95))  # rough progress
            page += 1
            time.sleep(0.3)  # polite delay

    progress_bar.progress(1.0)
    return all_rows


def build_xlsx(df: pd.DataFrame) -> bytes:
    """Return a polished XLSX as bytes."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"

    header_font  = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    header_fill  = PatternFill("solid", start_color="1E3A5F")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cell_font    = Font(name="Arial", size=10)
    alt_fill     = PatternFill("solid", start_color="EBF1F8")

    # Write headers
    for col_idx, col_name in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font  = header_font
        cell.fill  = header_fill
        cell.alignment = header_align

    # Write data rows
    for row_idx, row in enumerate(df.itertuples(index=False), start=2):
        fill = alt_fill if row_idx % 2 == 0 else None
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = cell_font
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            if fill:
                cell.fill = fill

    # Auto-fit column widths (capped)
    for col_idx, col_name in enumerate(df.columns, start=1):
        max_len = max(
            len(str(col_name)),
            df.iloc[:, col_idx - 1].astype(str).str.len().max() if len(df) > 0 else 0
        )
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 60)

    # Freeze header row
    ws.freeze_panes = "A2"

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ─── UI ────────────────────────────────────────────────────────────────────────

st.title("🛍️ Shopify Product Scraper")
st.caption(
    "Enter any public Shopify store URL to pull every product via the "
    "`/products.json` endpoint — then filter & export to Excel."
)

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Settings")
    limit = st.slider("Products per page (max 250)", 50, 250, 250, step=50)
    st.divider()
    st.markdown(
        "**How it works**\n\n"
        "1. Enters `/products.json?limit=N&page=P`\n"
        "2. Increments pages until an empty array is returned\n"
        "3. Decodes HTML entities & unicode sequences in descriptions\n"
        "4. Exports clean data to `.xlsx`"
    )

# Main input
store_url = st.text_input(
    "Shopify Store URL",
    placeholder="https://example.myshopify.com",
    help="Enter the full store URL. The `/products.json` path will be appended automatically.",
)

scrape_btn = st.button("🔍 Scrape Products", type="primary", use_container_width=True)

# ─── Session state ─────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = None
if "store" not in st.session_state:
    st.session_state.store = ""

# ─── Scraping ──────────────────────────────────────────────────────────────────
if scrape_btn and store_url:
    cleaned = clean_url(store_url)
    st.session_state.store = cleaned

    with st.spinner("Connecting to store…"):
        # Quick reachability check
        try:
            test = requests.get(f"{cleaned}/products.json?limit=1&page=1", timeout=10)
            test.raise_for_status()
        except Exception as e:
            st.error(f"❌ Could not reach `{cleaned}/products.json` — is this a public Shopify store?\n\n`{e}`")
            st.stop()

    st.info(f"✅ Connected to **{cleaned}** — scraping now…")
    progress = st.progress(0)
    status   = st.empty()

    try:
        rows = scrape_all_products(cleaned, progress, status)
    except Exception as e:
        st.error(f"Scraping failed: {e}")
        st.stop()

    st.session_state.df = pd.DataFrame(rows)
    status.text(f"✅ Done — {len(rows)} variants across {st.session_state.df['Product ID'].nunique()} products")

elif scrape_btn and not store_url:
    st.warning("Please enter a store URL first.")

# ─── Results ──────────────────────────────────────────────────────────────────
if st.session_state.df is not None and not st.session_state.df.empty:
    df = st.session_state.df

    st.divider()
    st.subheader(f"📦 Results — {df['Product ID'].nunique():,} products · {len(df):,} variants")

    # ── Filter bar ──────────────────────────────────────────────────────────
    with st.expander("🔎 Filter results", expanded=False):
        col1, col2, col3 = st.columns(3)

        search_title = col1.text_input("Search title / description")
        vendors = ["All"] + sorted(df["Vendor"].dropna().unique().tolist())
        sel_vendor = col2.selectbox("Vendor", vendors)
        types = ["All"] + sorted(df["Product Type"].dropna().unique().tolist())
        sel_type = col3.selectbox("Product Type", types)

        col4, col5 = st.columns(2)
        show_unavailable = col4.checkbox("Show unavailable variants", value=True)
        min_price_str, max_price_str = col5.columns(2)[0].text_input("Min price", ""), col5.columns(2)[1].text_input("Max price", "")

    filtered = df.copy()

    if search_title:
        mask = (
            filtered["Title"].str.contains(search_title, case=False, na=False) |
            filtered["Description"].str.contains(search_title, case=False, na=False)
        )
        filtered = filtered[mask]

    if sel_vendor != "All":
        filtered = filtered[filtered["Vendor"] == sel_vendor]

    if sel_type != "All":
        filtered = filtered[filtered["Product Type"] == sel_type]

    if not show_unavailable:
        filtered = filtered[filtered["Available"] != False]

    # ── Metrics ─────────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Products shown",  filtered["Product ID"].nunique())
    m2.metric("Variants shown",  len(filtered))
    m3.metric("Unique vendors",  filtered["Vendor"].nunique())
    m4.metric("Product types",   filtered["Product Type"].nunique())

    # ── Table (exclude long description column for display) ─────────────────
    display_cols = [c for c in filtered.columns if c != "Description"]
    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        height=500,
        column_config={
            "Product URL": st.column_config.LinkColumn("Product URL"),
            "Image URL":   st.column_config.ImageColumn("Image", width="small"),
            "Available":   st.column_config.CheckboxColumn("Available"),
            "Price":       st.column_config.TextColumn("Price ($)"),
        },
    )

    # ── Export ──────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("📥 Export")

    col_a, col_b = st.columns(2)

    xlsx_bytes = build_xlsx(filtered)
    store_slug = urlparse(st.session_state.store).netloc.replace(".", "_")
    col_a.download_button(
        label="⬇️ Download Excel (.xlsx)",
        data=xlsx_bytes,
        file_name=f"{store_slug}_products.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    col_b.download_button(
        label="⬇️ Download CSV (.csv)",
        data=csv_bytes,
        file_name=f"{store_slug}_products.csv",
        mime="text/csv",
        use_container_width=True,
    )

elif st.session_state.df is not None and st.session_state.df.empty:
    st.warning("No products were found at that URL. Make sure the store is public and uses Shopify.")
