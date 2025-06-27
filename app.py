from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
import os
from datetime import datetime
from scraping import start_scraping
import threading
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

# Create necessary folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Store scraping jobs status
jobs = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html', jobs=jobs)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and allowed_file(file.filename):
        # Generate unique job ID and save file
        job_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{filename}")
        file.save(input_path)
        
        # Setup job tracking
        jobs[job_id] = {
            'status': 'starting',
            'input_file': filename,
            'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'progress': 0,
            'total_links': 0,
            'processed_links': 0,
            'failed_links': 0
        }
        
        # Start scraping in background
        thread = threading.Thread(
            target=start_scraping,
            args=(job_id, input_path, RESULTS_FOLDER, jobs)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'job_id': job_id,
            'message': 'Scraping started'
        })
    
    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/status/<job_id>')
def get_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])

@app.route('/download/<job_id>')
def download_file(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Job not completed yet'}), 400
    
    result_file = os.path.join(RESULTS_FOLDER, f"{job_id}_results.xlsx")
    if not os.path.exists(result_file):
        return jsonify({'error': 'Result file not found'}), 404
    
    return send_file(
        result_file,
        as_attachment=True,
        download_name='stalco_scraped_results.xlsx'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
