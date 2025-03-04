import os
from flask import request, jsonify
from langchain.chat_models import AzureChatOpenAI
from dotenv import load_dotenv
from flask_smorest import Blueprint
from datetime import datetime

wfo_270_bp = Blueprint("wfo_270", "wfo_270", url_prefix="/wfo_270")

load_dotenv()

azure_openai_api_endpoint = os.getenv("OPENAI_API_ENDPOINT")
azure_openai_api_key = os.getenv("azure_openai_api_key")

llm = AzureChatOpenAI(
    deployment_name="Claims-Summary",  
    model="gpt-4", 
    azure_endpoint=azure_openai_api_endpoint,
    api_key=azure_openai_api_key,
    #api_type="azure",
    api_version="2023-05-15"
)

@wfo_270_bp.route('/authentication_flow', methods=['GET', 'POST'])
def authentication_flow():
    if request.method == "GET":
        try:
            data = request.get_json()
            blob_url = data.get("blob_url")
        except Exception as e:
            return jsonify({"error": "Input EDI File not available", "details": str(e)}), 400
    else:
        if not request.form.get('blob_url'):
            return jsonify({"error": "blob_url is required"}), 400
        blob_url = request.form.get('blob_url')

    return jsonify({"message": "Authentication Flow Completed"})

    
