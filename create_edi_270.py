import random
import json
import datetime
import os
from flask import request, jsonify
from azure.storage.blob import BlobServiceClient
from flask_smorest import Blueprint

edi_270_bp = Blueprint("edi_270", "edi_270", url_prefix="/edi_270")

def load_config(file_path="custom_edi.config"):
    with open(file_path, 'r') as file:
        return json.load(file)
    
@edi_270_bp.route('/create_edi', methods=['GET', 'POST'])
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
