import subprocess
import json
import sys  # Use sys.executable for correct Python path
import re
from flask import request, jsonify
from flask_smorest import Blueprint

edi_bp = Blueprint("edi", "edi", url_prefix="/edi")

def run_script(script_name, args=[]):
    try:
        print(f"\n Running {script_name} with args {args}")  # Debugging script call
        
        result = subprocess.run(
            [sys.executable, script_name] + args, 
            capture_output=True,
            text=True
        )

        stdout_output = result.stdout.strip()
        stderr_output = result.stderr.strip()

        print(f"STDOUT ({script_name}):\n{stdout_output}")
        print(f"STDERR ({script_name}):\n{stderr_output}")

        # If the script failed, return an error
        if result.returncode != 0:
            return {"error": f"Error in {script_name}", "details": stderr_output}

        
        json_str = stdout_output.split("\n")[-1].strip()

       
        json_str = re.sub(r"```json|```|'''", "", json_str).strip()

        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            return {
                "error": f"Invalid JSON from {script_name}",
                "details": str(e),
                "raw_output": stdout_output
            }

    except Exception as e:
        return {"error": f"Exception in {script_name}", "details": str(e)}

@edi_bp.route('/process_edi', methods=['POST'])
def process_edi():
    """ API to process EDI file from blob storage """
    data = request.json
    blob_url = data.get("blob_url")
    
    if not blob_url:
        return jsonify({"error": "blob_url is required"}), 400

    print(f"Processing EDI from Blob URL: {blob_url}")

    # Step 1: Validate EDI
    print("Running EDI Validation...")
    validation_result = run_script("app_validate.py", [blob_url])
    if "error" in validation_result:
        return jsonify({"error": "EDI validation failed", "details": validation_result}), 400
    
    # Step 2: Convert EDI to JSON
    print("Converting EDI to JSON...")
    json_result = run_script("app_create_json.py", [blob_url])
    if "error" in json_result:
        return jsonify({"error": "EDI to JSON conversion failed", "details": json_result}), 400
    
    # Step 3: Process Prior Authorization (Includes provider/member validation)
    print("Running Prior Authorization Workflow...")
    prior_auth_result = run_script("priorauth_workflow_2.py", [blob_url])
    if "error" in prior_auth_result:
        return jsonify({"error": "Prior authorization processing failed", "details": prior_auth_result}), 400
    
    # Step 4: Return consolidated response
    response = {
        "EDI Validation": validation_result,
        "Parsed JSON": json_result,
        "Prior Authorization": prior_auth_result
    }
    
    return jsonify(response)
