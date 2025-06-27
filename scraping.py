import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
RETRY_LIMIT = 2
SLEEP_BETWEEN = 0.4

def clean_url(url):
    """Clean and validate URL"""
    if not url.startswith('http'):
        url = 'https://stalco.pl' + url
    url = re.sub(r'https://stalco\.pl(https://stalco\.pl)+', 'https://stalco.pl', url)
    base_url, _, fragment = url.partition('#')
    if fragment and ('rozmiar' in fragment or 'typ' in fragment):
        url = f"{base_url}#{fragment}"
    return url

def extract_media_urls(soup):
    """Extract image and video URLs from the product page"""
    images = []
    videos = []
    
    gallery_items = soup.select('li.orbitvu-gallery-item a.orbitvu-gallery-item-link')
    for item in gallery_items:
        if 'data-big_src' in item.attrs:
            if item.get('data-src', '').endswith('.mp4'):
                videos.append(item['data-src'])
            else:
                images.append(item['data-big_src'])
    
    main_image = soup.select_one('#ovgallery-main-image')
    if main_image and main_image.get('src'):
        if main_image['src'] not in images:
            images.append(main_image['src'])
    
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
        if not title:
            raise Exception("Could not find product title")
            
        short_desc = soup.select_one('div.product-page__short-description')
        full_desc = soup.select_one('div.product-tabs__description')
        details = soup.select('ul.product-details-top__reference-list li')
        
        images, videos = extract_media_urls(soup)
        
        # Extract prices
        price_gross = price_net = "N/A"
        price_div = soup.select_one('div.product-price')
        if price_div:
            price_gross_elem = price_div.select_one('div.price-tax-excluded')
            if price_gross_elem:
                price_gross = price_gross_elem.get_text(strip=True).replace('zł', '').strip()
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

def start_scraping(job_id, input_file, results_folder, jobs):
    """Main scraping function that updates job status"""
    try:
        # Update job status
        jobs[job_id]['status'] = 'processing'
        
        # Load Excel
        df = pd.read_excel(input_file)
        df['PRODUCT_MASTER'] = df['PRODUCT_MASTER'].astype(str)
        df['Search Link'] = df['Search Link'].astype(str)
        
        # Get unique search links
        search_links = []
        for master in df['PRODUCT_MASTER'].unique():
            subset = df[df['PRODUCT_MASTER'] == master]
            if master == '0':
                search_links.extend(subset['Search Link'].tolist())
            else:
                search_links.append(subset.iloc[0]['Search Link'])
        search_links = list(set(search_links))
        
        # Update job info
        jobs[job_id]['total_links'] = len(search_links)
        
        results = []
        failed = []
        
        # Main scraping loop
        for idx, link in enumerate(search_links, 1):
            try:
                r = requests.get(link, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(r.text, 'html.parser')
                product_link_el = soup.select_one('h2.product-miniature__title a')
                
                if not product_link_el or not product_link_el.get('href'):
                    failed.append({'Search Link': link, 'Reason': 'No product found'})
                    continue
                
                product_url = clean_url(product_link_el['href'])
                data = extract_product_data(product_url)
                
                if data:
                    data['Search Link'] = link
                    results.append(data)
                    
                # Update progress
                jobs[job_id]['processed_links'] = idx
                jobs[job_id]['progress'] = int((idx / len(search_links)) * 100)
                jobs[job_id]['failed_links'] = len(failed)
                
            except Exception as err:
                failed.append({'Search Link': link, 'Reason': str(err)})
                jobs[job_id]['failed_links'] = len(failed)
            
            time.sleep(SLEEP_BETWEEN)
        
        # Create results
        results_df = pd.DataFrame(results)
        merged_df = pd.merge(df, results_df, how='left', on='Search Link')
        
        # Save results
        output_file = os.path.join(results_folder, f"{job_id}_results.xlsx")
        merged_df.to_excel(output_file, index=False)
        
        if failed:
            failed_file = os.path.join(results_folder, f"{job_id}_failed.xlsx")
            pd.DataFrame(failed).to_excel(failed_file, index=False)
        
        # Update job status
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['error'] = str(e)
        print(f"Job failed: {str(e)}")
