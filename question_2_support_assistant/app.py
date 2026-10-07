import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from assistant import DocumentAwareAssistant

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DOCS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'documents'))
assistant = DocumentAwareAssistant(DOCS_DIR)

# Pre-scripted 10-turn benchmark conversation
BENCHMARK_10_TURNS = [
    "What is your SLA response time for Critical P1 outages?",
    "What about Standard P3 severity issues?",
    "Can I get a refund if I cancel my annual subscription?",
    "How many days does it take for the refund money to reach my account?",
    "Could you remind me of the refund terms for annual plans?",
    "Is multi-factor authentication mandatory for admin accounts?",
    "What is the protocol if an administrator loses both password and 2FA recovery codes?",
    "What features and pricing are included in the Professional Plan?",
    "Does warranty cover physical drop damage or liquid spills?",
    "How long before a missing package is officially declared Lost in Transit?"
]

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        body = request.get_json() or {}
        query = body.get('message', '').strip()
        if not query:
            return jsonify({"success": False, "error": "Query cannot be empty"}), 400

        result = assistant.process_turn(query)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/run-10-turn-demo', methods=['POST'])
def run_demo():
    """Runs the 10-turn benchmark conversation in a fresh session and returns all turns."""
    try:
        demo_assistant = DocumentAwareAssistant(DOCS_DIR)
        turns_results = []
        for i, q in enumerate(BENCHMARK_10_TURNS, 1):
            turn_res = demo_assistant.process_turn(q)
            turns_results.append(turn_res)

        return jsonify({
            "success": True,
            "turns": turns_results,
            "final_session_state": demo_assistant.memory.get_summary_state()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/session-state', methods=['GET'])
def get_session_state():
    try:
        return jsonify({"success": True, "state": assistant.memory.get_summary_state()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/reset', methods=['POST'])
def reset_session():
    try:
        assistant.memory.reset()
        return jsonify({"success": True, "message": "Session memory reset."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/documents', methods=['GET'])
def get_documents():
    try:
        docs = []
        for f in sorted(os.listdir(DOCS_DIR)):
            if f.endswith(('.md', '.txt')):
                filepath = os.path.join(DOCS_DIR, f)
                with open(filepath, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                
                # Extract sections
                sec_list = [s for s in assistant.indexer.sections if s['doc_name'] == f]
                docs.append({
                    "filename": f,
                    "sections_count": len(sec_list),
                    "sections": sec_list,
                    "full_content": content
                })
        return jsonify({"success": True, "documents": docs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"Starting Question 2 Support Assistant on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
