import os
import json
from flask import Flask, jsonify, send_from_directory, send_file, request
from flask_cors import CORS
from pipeline import DocumentPipeline, CONFIDENCE_THRESHOLD, THRESHOLD_RATIONALE

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

pipeline = DocumentPipeline("question_3_document_pipeline/ground_truth.json")
cached_results = pipeline.run_pipeline()

DOC_IMG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Question 1 & 3 (Files to use)', 'Question 3'))

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/documents', methods=['GET'])
def get_documents():
    """Returns all 10 classified documents with their extracted fields and confidences."""
    return jsonify({
        "success": True,
        "data": cached_results["documents"],
        "threshold": CONFIDENCE_THRESHOLD,
        "rationale": THRESHOLD_RATIONALE
    })

@app.route('/api/flagging-report', methods=['GET'])
def get_flagging_report():
    """Returns the human review flagging report."""
    return jsonify({
        "success": True,
        "report": cached_results["flagging_report"]
    })

@app.route('/api/image/<path:filename>')
def serve_image(filename):
    """Serves document images from Question 3 folder."""
    return send_from_directory(DOC_IMG_DIR, filename)

@app.route('/api/export/extractions', methods=['GET'])
def export_extractions():
    path = os.path.join(os.path.dirname(__file__), 'outputs', 'extractions.json')
    return send_file(path, as_attachment=True, download_name='extractions.json')

@app.route('/api/export/flagging-report', methods=['GET'])
def export_flagging_report():
    path = os.path.join(os.path.dirname(__file__), 'outputs', 'flagging_report.json')
    return send_file(path, as_attachment=True, download_name='flagging_report.json')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f"Starting Question 3 Pipeline Dashboard on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
