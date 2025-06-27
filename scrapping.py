import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
import os

# CONFIG
INPUT_FILE = 'products.xlsx'
OUTPUT_FILE = 'stalco_scraped_results.xlsx'
FAILED_FILE = 'stalco_failed_links.xlsx'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
RETRY_LIMIT = 2
SLEEP_BETWEEN = 0.4  # seconds

# Load Excel
print("📚 Loading Excel file...")
df = pd.read_excel(INPUT_FILE)
df['PRODUCT_MASTER'] = df['PRODUCT_MASTER'].astype(str)
df['Search Link'] = df['Search Link'].astype(str)

# Unique Search Links
search_links = []

for master in df['PRODUCT_MASTER'].unique():
    subset = df[df['PRODUCT_MASTER'] == master]
    if master == '0':
        search_links.extend(subset['Search Link'].tolist())
    else:
        search_links.append(subset.iloc[0]['Search Link'])

search_links = list(set(search_links))  # deduplicate

def clean_url(url):
    """Clean and validate URL"""
    if not url.startswith('http'):
        url = 'https://stalco.pl' + url
    # Remove duplicate domains
    url = re.sub(r'https://stalco\.pl(https://stalco\.pl)+', 'https://stalco.pl', url)
    
    # Split URL and fragment
    base_url, _, fragment = url.partition('#')
    
    # Keep the fragment if it contains product variation/size
    if fragment and ('rozmiar' in fragment or 'typ' in fragment):
        url = f"{base_url}#{fragment}"
    
    return url

def extract_media_urls(soup):
    """Extract image and video URLs from the product page"""
    images = []
    videos = []
    
    # Find all image URLs in the gallery
    gallery_items = soup.select('li.orbitvu-gallery-item a.orbitvu-gallery-item-link')
    for item in gallery_items:
        if 'data-big_src' in item.attrs:
            if item.get('data-src', '').endswith('.mp4'):
                videos.append(item['data-src'])
            else:
                images.append(item['data-big_src'])
    
    # Also check for main product image
    main_image = soup.select_one('#ovgallery-main-image')
    if main_image and main_image.get('src'):
        if main_image['src'] not in images:
            images.append(main_image['src'])
    
    # Check for video in the gallery
    video_gallery = soup.select_one('video.video-gallery')
    if video_gallery and video_gallery.get('src'):
        if video_gallery['src'] not in videos:
            videos.append(video_gallery['src'])
    
    return images, videos

def extract_product_data(product_url):
    try:
        product_url = clean_url(product_url)
        res = requests.get(product_url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            raise Exception(f"HTTP {res.status_code}")
            
        soup = BeautifulSoup(res.text, 'html.parser')

        title = soup.select_one('h1.product-page__title .js-product-name-with-details')
        short_desc = soup.select_one('div.product-page__short-description')
        full_desc = soup.select_one('div.product-tabs__description')
        details = soup.select('ul.product-details-top__reference-list li')

        if not title:
            raise Exception("Could not find product title")

        # Extract images and videos
        images, videos = extract_media_urls(soup)

        # Extract prices
        price_gross = price_net = "N/A"
        price_div = soup.select_one('div.product-price')
        if price_div:
            # Get gross price (tax included)
            price_gross_elem = price_div.select_one('div.price-tax-excluded')
            if price_gross_elem:
                price_gross = price_gross_elem.get_text(strip=True).replace('zł', '').strip()
            
            # Get net price (tax excluded)
            price_net_elem = price_div.select_one('div.price-tax-included')
            if price_net_elem:
                price_net = price_net_elem.get_text(strip=True).split('Netto')[0].replace('zł', '').strip()

        brand = sku = ean = ''
        for li in details:
            text = li.get_text(strip=True)
            if 'Marka' in text:
                brand = text.replace('Marka', '').strip()
            elif 'Numer katalogowy' in text:
                sku = text.replace('Numer katalogowy:', '').strip()
            elif 'EAN:' in text:
                ean = text.replace('EAN:', '').strip()

        return {
            'Product URL': product_url,
            'Title': title.text.strip() if title else '',
            'Short Description': short_desc.decode_contents() if short_desc else '',
            'Full Description': full_desc.decode_contents() if full_desc else '',
            'Brand': brand,
            'SKU': sku,
            'EAN': ean,
            'Price Gross': price_gross,
            'Price Net': price_net,
            'Images': ','.join(images) if images else '',
            'Videos': ','.join(videos) if videos else ''
        }
    except Exception as e:
        print(f"❌ Error extracting data from {product_url}: {str(e)}")
        return None

# Setup for incremental saving
print(f"🔄 Starting to scrape {len(search_links)} unique links...")
results = []
failed = []

# Load existing results if any
temp_file = 'temp_results.xlsx'
failed_temp = 'temp_failed.xlsx'
try:
    if os.path.exists(temp_file):
        print("📂 Loading existing temporary results...")
        temp_df = pd.read_excel(temp_file)
        results = temp_df.to_dict('records')
        processed_links = set(temp_df['Search Link'])
        # Filter out already processed links
        search_links = [link for link in search_links if link not in processed_links]
        print(f"✅ Loaded {len(results)} existing results")
    
    if os.path.exists(failed_temp):
        failed_df = pd.read_excel(failed_temp)
        failed = failed_df.to_dict('records')
except Exception as e:
    print(f"⚠️ Could not load temporary files: {str(e)}")

def save_progress():
    """Save current progress to temporary files"""
    try:
        if results:
            temp_results_df = pd.DataFrame(results)
            temp_results_df.to_excel(temp_file, index=False)
        if failed:
            temp_failed_df = pd.DataFrame(failed)
            temp_failed_df.to_excel(failed_temp, index=False)
    except Exception as e:
        print(f"⚠️ Error saving progress: {str(e)}")

# Main Loop
for idx, link in enumerate(search_links, 1):
    print(f"🔍 [{idx}/{len(search_links)}] Searching: {link}")
    retry_count = 0
    while retry_count <= RETRY_LIMIT:
        try:
            r = requests.get(link, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                raise Exception(f"Search page returned HTTP {r.status_code}")
                
            soup = BeautifulSoup(r.text, 'html.parser')
            product_link_el = soup.select_one('h2.product-miniature__title a')
            
            if not product_link_el or not product_link_el.get('href'):
                print(f"⚠️ No product found on search page: {link}")
                failed.append({'Search Link': link, 'Reason': 'No product found'})
                break

            product_url = clean_url(product_link_el['href'])
            print(f" → Found product: {product_url}")
            
            data = extract_product_data(product_url)
            if data:
                data['Search Link'] = link
                results.append(data)
                # Save progress after each successful scrape
                save_progress()
                print(f"✅ Successfully scraped: {data['Title']}")
                break  # Success, move to next link
            else:
                raise Exception("Failed to extract product data")

        except Exception as err:
            retry_count += 1
            print(f"❌ Error: {str(err)} | Retry {retry_count}/{RETRY_LIMIT}")
            time.sleep(1)
            if retry_count > RETRY_LIMIT:
                failed.append({'Search Link': link, 'Reason': str(err)})
    
    time.sleep(SLEEP_BETWEEN)

# Save Final Results
print("\n💾 Saving final results...")
results_df = pd.DataFrame(results)

# Clean up temporary files
try:
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(failed_temp):
        os.remove(failed_temp)
except Exception as e:
    print(f"⚠️ Error removing temporary files: {str(e)}")

# Ensure all columns are included in the final output
columns_order = [
    'Search Link',
    'Product URL',
    'PRODUCT_MASTER',
    'EAN',
    'SKU',
    'Title',
    'Brand',
    'Price Gross',
    'Price Net',
    'Images',
    'Videos',
    'Short Description',
    'Full Description'
]

# Merge and organize columns
merged_df = pd.merge(df, results_df, how='left', on='Search Link')
# Ensure Product URL is preserved in the output
final_columns = [col for col in columns_order if col in merged_df.columns] + \
                [col for col in merged_df.columns if col not in columns_order]
merged_df = merged_df[final_columns]

# Save to Excel
merged_df.to_excel(OUTPUT_FILE, index=False)

if failed:
    pd.DataFrame(failed).to_excel(FAILED_FILE, index=False)
    print(f"⚠️ {len(failed)} failed links saved to: {FAILED_FILE}")

print(f"✅ Successfully scraped {len(results)} products")
print(f"✅ Results saved to: {OUTPUT_FILE}")
