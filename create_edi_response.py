import json
from datetime import datetime
from flask import request, jsonify
from flask_smorest import Blueprint

edi_resp_bp = Blueprint("edi-resp", "edi-resp", url_prefix="/edi-resp")

def load_config(file_path="custom_edi.config"):
    with open(file_path, 'r') as file:
        return json.load(file)

claim_values = load_config("custom_edi.config")    

@edi_resp_bp.route('/response', methods=['GET', 'POST'])
def create_edi():
    claim_values = load_config("custom_edi.config")

    edi_content = ""
    if request.method == "POST":
        try:
            obj = request.get_json()
            edi_content = generate_edi_278_new(obj)
        except Exception as e:
            return jsonify({"error":  str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        print("Blob URL from GET = ", blob_url)
        if not blob_url:
            return jsonify({"error": "blob_url is required"}), 400
        
    print("Generated EDI 278 File:")
    print(edi_content)
    response = {
        "message": "DI Response Created based on given Member, Provider, ICD, CPT and Authorization",
        "data": edi_content
    }
    return jsonify(response)
