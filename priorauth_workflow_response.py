import ast
import json
from datetime import datetime
import os
from flask import request, jsonify
from langchain.chat_models import AzureChatOpenAI
from dotenv import load_dotenv
from flask_smorest import Blueprint

wfo_resp_bp = Blueprint("wfo-resp", "wfo-resp", url_prefix="/wfo-resp")

load_dotenv()

azure_openai_api_endpoint = os.getenv("OPENAI_API_ENDPOINT")
azure_openai_api_key = os.getenv("azure_openai_api_key")

def load_config(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

claim_values = load_config("custom_edi.config")
   
@wfo_resp_bp.route('/response', methods=['GET', 'POST'])
def authentication_flow():    
    if request.method == "GET":
        try:
            blob_url = request.args.get("blob_url")
            if not blob_url:
                return jsonify({"error": "blob_url is required"}), 400
        except Exception as e:
            return jsonify({"error":  str(e)}), 400
    else:
        if not request.form.get('blob_url'):
            return jsonify({"error": "blob_url is required"}), 400
        blob_url = request.form.get('blob_url')

    return jsonify({"message": "Success"}), 200
