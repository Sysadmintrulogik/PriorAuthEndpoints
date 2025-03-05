import os, json
from flask import request, jsonify
from langchain.chat_models import AzureChatOpenAI
from dotenv import load_dotenv
from flask_smorest import Blueprint
from datetime import datetime

wfo_271_bp = Blueprint("wfo_271", "wfo_271", url_prefix="/wfo_271")

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

def load_config(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

claim_values = load_config("custom_edi.config")

def extract_features_271(edi_content):
    segments = [seg.strip() for seg in edi_content.split("~") if seg.strip()]
    result = {
        "member": {
            "member_id": "",
            "name": "",
            "address": "",
            "dob": ""
        },
        "provider": {
            "npi": "",
            "name": "",
            "address": "",
            "taxonomy": ""
        },
        "payer": {
            "payer_id": "",
            "name": ""
        },
        "icd_codes": [],
        "cpt_codes": [],
        "eligibility_benefit": {
            "service_type_code": "",
            "plan_coverage": "",
            "active_coverage": [],
            "copayment": [],
            "insurance_type_code": "",
            "monetory_value": "",
            "in_plan": ""
        }
    }
    nm1_tracker = ""
    i = 0
    while i < len(segments):
        seg = segments[i]
        fields = seg.split("*")
        seg_id = fields[0].strip()
        if seg_id == "NM1":
            nm1_tracker = fields[1].strip() if len(fields) > 1 else ""
            if nm1_tracker == "IL":
                if len(fields) > 3:
                    result["member"]["name"] = fields[3].strip()
                if len(fields) > 8:
                    result["member"]["member_id"] = fields[8].strip()
            elif nm1_tracker == "1P":
                if len(fields) > 3:
                    result["provider"]["name"] = fields[3].strip()
                if len(fields) > 8:
                    result["provider"]["npi"] = fields[8].strip()
            elif nm1_tracker == "PR":
                if len(fields) > 3:
                    result["payer"]["name"] = fields[3].strip()
                if len(fields) > 8:
                    result["payer"]["payer_id"] = fields[8].strip()
        elif seg_id == "N3":
            if nm1_tracker == "IL":
                if len(fields) > 1:
                    result["member"]["address"] = fields[1].strip()
            elif nm1_tracker == "1P":
                if len(fields) > 1:
                    result["provider"]["address"] = fields[1].strip()
        elif seg_id == "DMG":
            if nm1_tracker == "IL" and len(fields) > 2:
                result["member"]["dob"] = fields[2].strip()
        elif seg_id == "PRV":
            if nm1_tracker == "1P" and len(fields) > 3:
                result["provider"]["taxonomy"] = fields[3].strip()
        elif seg_id == "ICD":
            if len(fields) > 1:
                result["icd_codes"].append(fields[1].strip())
        elif seg_id == "CPT":
            if len(fields) > 1:
                result["cpt_codes"].append(fields[1].strip())
        #elif seg_id == "REF":
           # if len(fields) > 1 and fields[1].strip() in ["EA", "9F", "BB"]:
               # if len(fields) > 2:
                  #  result["authorization"]["cert_number"] = fields[2].strip()
        elif seg_id == "DTP":
            if len(fields) > 1 and fields[1].strip() in ["194", "198"]:
                if fields[1].strip() == "194" and len(fields) > 3:
                    result["authorization"]["start_date"] = fields[3].strip()
                if fields[1].strip() == "198" and len(fields) > 3:
                    result["authorization"]["end_date"] = fields[3].strip()
            elif len(fields) > 1 and fields[1].strip() == "AAH":
                if len(fields) > 3:
                    rcodes = fields[3].split(":")
                    for r in rcodes:
                        r = r.strip()
                        if r.isdigit():
                            result["authorization"]["reason_code"].append(int(r))
        elif seg_id == "EB":
            eb_fields = fields + [""] * 11
            if eb_fields[1].strip() == "1" and eb_fields[3].strip() == "30":
                result["eligibility_benefit"]["service_type_code"] = "30"
                if len(eb_fields) > 5 and eb_fields[5].strip():
                    result["eligibility_benefit"]["plan_coverage"] = eb_fields[5].strip()
            if eb_fields[1].strip() == "1" and ">" in eb_fields[3].strip() and result["eligibility_benefit"]["active_coverage"] == []:
                splitted = [s for s in eb_fields[3].split(">") if s.strip()]
                splitted = list(dict.fromkeys(splitted))
                result["eligibility_benefit"]["active_coverage"] = splitted
            if eb_fields[1].strip() == "B":
                multi = eb_fields[3].strip()
                splitted = [x for x in multi.split(">") if x.strip()]
                splitted = list(dict.fromkeys(splitted))
                result["eligibility_benefit"]["copayment"] = splitted
                if len(eb_fields) > 4:
                    result["eligibility_benefit"]["insurance_type_code"] = eb_fields[4].strip()
                if len(eb_fields) > 5:
                    result["eligibility_benefit"]["plan_coverage"] = eb_fields[5].strip()
                if len(eb_fields) > 6:
                    result["eligibility_benefit"]["monetory_value"] = eb_fields[6].strip()
                if len(eb_fields) > 10:
                    result["eligibility_benefit"]["in_plan"] = eb_fields[11].strip()
                
        i += 1
    return result

@wfo_271_bp.route('/authentication_flow', methods=['GET', 'POST'])
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

    if not blob_url:
        return jsonify({"error": "blob_url is required"}), 400

    print(f"Processing EDI from Blob URL: {blob_url}")
    start_time = time.time()
    edi_content = read_edi_from_blob(blob_url)
    if edi_content == "":
        d1 = "EDI Content not fetched",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        #print(response)
        return jsonify(response)
    edi_validity = validate_edi_278(edi_content)
    if edi_validity == False:
        d1 = "EDI Validation not Passed",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        #print(response)
        return jsonify(response)
    else:
        print("EDI Validated")
    #parsed = parse_edi_file(edi_content)
    extracted_json = extract_features_271(edi_content)
    print(extracted_json)
    if not list(extracted_json.keys()):
        d1 = "Feature Extraction Failed",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    else:
        d1 = "Feature Extraction Successful"
        d2 = extracted_json
        response = {"message":d1, "data":d2}
        return jsonify(response)

    
