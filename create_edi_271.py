import json
from flask import request, jsonify
from flask_smorest import Blueprint
from datetime import datetime

edi_271_bp = Blueprint("edi_271", "edi_271", url_prefix="/edi_271")

def load_config(file_path="custom_edi.config"):
    with open(file_path, 'r') as file:
        return json.load(file)
    
@edi_271_bp.route('/create_edi', methods=['GET', 'POST'])
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
        
    return jsonify({"message": "EDI Created based on given Member, Provider, Eligibility, Policy Benefits, ICD, CPT Codes"})
