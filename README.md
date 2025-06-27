# Stalco Product Scraper

A web application for scraping product information from Stalco's website.

## Features
- Web interface for uploading Excel files
- Real-time progress tracking
- Multiple concurrent scraping jobs
- Automatic resume on failure
- Download results directly from web interface
- Progress bars and status updates

## Setup
1. Install requirements:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open http://localhost:5000 in your browser

## Project Structure
```
.
├── app.py              # Main Flask application
├── scraping.py        # Scraping logic
├── templates/         # HTML templates
│   └── index.html    # Web interface
├── uploads/          # Uploaded Excel files
└── results/          # Scraped results
```

## Input Excel Format
The input Excel file should have these columns:
- SKU
- PRODUCT_MASTER
- Search Link

## Output
The scraper will generate:
- Excel file with scraped data
- Failed links report (if any)
- Progress tracking in web interface
