import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from inventory_loader import load_inventory_data, get_dataset_metadata, DEFAULT_EXCEL_PATH
from agent import InventoryAgent

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Initialize dataset and agent
current_df, current_col_map, current_filepath = load_inventory_data()
agent = InventoryAgent(current_df, current_col_map)

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/dataset-info', methods=['GET'])
def get_dataset_info():
    """Returns dataset summary, column statistics, and preview records."""
    try:
        metadata = get_dataset_metadata(agent.df)
        metadata['filename'] = os.path.basename(current_filepath)
        return jsonify({"success": True, "data": metadata})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    """Main chat endpoint orchestrating search lookup, code generation & execution, and plain-English summary."""
    try:
        body = request.get_json() or {}
        user_message = body.get('message', '').strip()
        if not user_message:
            return jsonify({"success": False, "error": "Message cannot be empty."}), 400

        result = agent.process_query(user_message)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Allows uploading a custom Excel dataset to query."""
    global current_df, current_col_map, current_filepath
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file."}), 400

    try:
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)

        new_df, new_col_map, _ = load_inventory_data(temp_path)
        current_df = new_df
        current_col_map = new_col_map
        current_filepath = temp_path

        agent.set_dataset(current_df, current_col_map)
        metadata = get_dataset_metadata(current_df)
        metadata['filename'] = file.filename

        return jsonify({
            "success": True, 
            "message": f"Successfully loaded {file.filename} with {len(current_df)} records.",
            "data": metadata
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to parse Excel: {str(e)}"}), 400

@app.route('/api/reset', methods=['POST'])
def reset_to_default():
    """Resets to default Inventory-Records-Sample-Data.xlsx."""
    global current_df, current_col_map, current_filepath
    try:
        current_df, current_col_map, current_filepath = load_inventory_data(DEFAULT_EXCEL_PATH)
        agent.set_dataset(current_df, current_col_map)
        agent.history = []
        metadata = get_dataset_metadata(current_df)
        metadata['filename'] = os.path.basename(DEFAULT_EXCEL_PATH)
        return jsonify({"success": True, "message": "Reset to default sample inventory.", "data": metadata})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/execute-code', methods=['POST'])
def direct_code_execution():
    """Directly executes arbitrary Python/Pandas code against the loaded dataframe."""
    try:
        body = request.get_json() or {}
        code = body.get('code', '').strip()
        if not code:
            return jsonify({"success": False, "error": "Code cannot be empty."}), 400

        res = agent.code_executor.execute(code, agent.df)
        return jsonify({"success": True, "execution": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/search', methods=['POST'])
def direct_search():
    """Directly queries the inventory search tool."""
    try:
        body = request.get_json() or {}
        query = body.get('query', '').strip()
        if not query:
            return jsonify({"success": False, "error": "Query cannot be empty."}), 400

        res = agent.search_tool.search(query)
        return jsonify({"success": True, "search": res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Inventory Agent Web Server on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
