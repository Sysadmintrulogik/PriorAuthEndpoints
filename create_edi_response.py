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
    if request.method == "POST":
        try:
            obj = request.get_json()
        except Exception as e:
            return jsonify({"error":  str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        if not blob_url:
            return jsonify({"error": "blob_url is required"}), 400
    
    return jsonify({"message": "Success"}), 200
