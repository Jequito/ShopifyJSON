# 🛍️ Shopify Product Scraper

A Streamlit web app that scrapes **any public Shopify store** via the `/products.json` endpoint, displays the products in an interactive table, and exports clean data to Excel (`.xlsx`) or CSV.

## Features

- 🔁 **Auto-pagination** — cycles through pages with `limit=250` until an empty array is returned
- 🧹 **Unicode/HTML cleaning** — decodes HTML entities (`&amp;`, `&#39;`) and unicode escapes (`\u003e`) in product descriptions
- 🔎 **Live filtering** — filter by title, vendor, product type, availability, price
- 📊 **Image previews** in the data table
- 📥 **Export** to `.xlsx` (styled) or `.csv`

---

## Running Locally

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/shopify-scraper.git
cd shopify-scraper
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Deploying to GitHub

### Step-by-step

1. **Create a new GitHub repository**
   - Go to [github.com/new](https://github.com/new)
   - Name it `shopify-scraper` (or anything you like)
   - Leave it **Public** (required for free Streamlit Cloud)
   - Click **Create repository**

2. **Push your code**

```bash
git init
git add .
git commit -m "Initial commit: Shopify product scraper"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/shopify-scraper.git
git push -u origin main
```

---

## Deploying to Streamlit Cloud (free)

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
2. Click **New app**
3. Select your repository (`shopify-scraper`), branch (`main`), and main file (`app.py`)
4. Click **Deploy**

Your app will be live at `https://YOUR_USERNAME-shopify-scraper-app-XXXX.streamlit.app` within a minute or two.

> **No secrets needed** — the app only makes public GET requests, so no API keys are required.

---

## Usage

1. Paste any Shopify store URL (e.g. `https://gymshark.com` or `https://yourstore.myshopify.com`)
2. Adjust the **Products per page** slider in the sidebar if needed (default 250 = maximum)
3. Click **🔍 Scrape Products**
4. Filter results using the filter panel
5. Download as `.xlsx` or `.csv`

---

## How the scraper works

```
GET /products.json?limit=250&page=1
GET /products.json?limit=250&page=2
...
GET /products.json?limit=250&page=N  ← returns [] → stop
```

Each product's `body_html` description is cleaned with:
- `unicode_escape` decoding for `\uXXXX` sequences
- `html.unescape()` for HTML entities (`&amp;`, `&#39;`, `&lt;`, etc.)
- HTML tag stripping to plain text

---

## Project structure

```
shopify-scraper/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

---

## Notes

- Some Shopify stores disable the public `/products.json` endpoint — the app will show a clear error if this happens
- The scraper adds a small 300 ms delay between pages to be polite to store servers
- Very large stores (10 000+ products) may take 1–2 minutes to scrape
