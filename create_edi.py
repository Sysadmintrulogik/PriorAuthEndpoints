import random
import json
import datetime
from datetime import datetime
import os
from flask import request, jsonify
from azure.storage.blob import BlobServiceClient
from flask_smorest import Blueprint

edi_bp = Blueprint("edi", "edi", url_prefix="/edi")

def load_config(file_path="custom_edi.config"):
    with open(file_path, 'r') as file:
        return json.load(file)

def generate_edi_278_new(json_obj):
    segments = []
    now = datetime.now()
    current_date_yy = now.strftime('%y%m%d')
    current_date_yyyy = now.strftime('%Y%m%d')
    current_time = now.strftime('%H%M')

    # ISA Segment
    isa = ('ISA*00*          *00*          *ZZ*' +
           json_obj["submitter"].ljust(15) +
           '*ZZ*' + json_obj["receiver"].ljust(15) +
           '*' + current_date_yy +
           '*' + current_time +
           '*U*00401*000000001*0*P*:')  
    segments.append(isa + '~')

    # GS Segment
    gs = f'GS*HC*{json_obj["submitter"][:2]}*{json_obj["receiver"][:2]}*{current_date_yyyy}*{current_time}*1*X*004010X096A1'
    segments.append(gs + '~')

    # ST Segment
    st_control = now.strftime("%Y%m%d%H%M%S")
    segments.append(f'ST*278*{st_control}*00' + '~')

    # BHT Segment
    segments.append('BHT*0007*13*REF47517*' + '~')

    # HL Segments
    segments.append("HL*1**20*1~")  # Subscriber HL
    segments.append("HL*2*1*21*1~")  # Provider HL

    if "trace_no" in json_obj:
        segments.append(f'TRN*1*{json_obj["trace_no"]}*9012345678' + '~')
    else:
        segments.append('TRN*1*111099*9012345678~')

    # Member Information (NM1, N3, DMG segments)
    member = json_obj["member"]
    segments.append(f'NM1*IL*1*{member["name"]}*****34*{member["member_id"]}' + '~')
    segments.append(f'N3*{member["address"]}' + '~')
    try:
        dob_dt = datetime.strptime(member["dob"], "%m-%d-%Y")
        dob_formatted = dob_dt.strftime("%Y%m%d")
    except Exception:
        dob_formatted = member["dob"]
    segments.append(f'DMG*D8*{dob_formatted}' + '~')

    # Provider Information (NM1, N3, PRV segments)
    provider = json_obj["provider"]
    segments.append(f'NM1*85*2*{provider["name"]}****46*{provider["npi"]}' + '~')
    segments.append(f'N3*{provider["address"]}' + '~')
    segments.append(f'PRV*BI*PXC*{provider["taxonomy"]}' + '~')

    # PA Requests (PA request segments)
    if "paRequesets" in json_obj:
        for pa_request in json_obj["paRequesets"]:
            if pa_request["serviceCodeType"]:
                segments.append(f'SVC*{pa_request["serviceCodeType"]}*{pa_request["cptProcedureCode"]}~')
            if pa_request["icdProcedureCode"]:
                segments.append(f'ICD*{pa_request["icdProcedureCode"]}~')
            if pa_request["dateOfService"]:
                segments.append(f'DTP*291*D8*{pa_request["dateOfService"]}~')
            if pa_request["placeOfService"]:
                segments.append(f'POS*{pa_request["placeOfService"]}~')
            if pa_request["diagnosis"]:
                segments.append(f'DX*{pa_request["diagnosis"]}~')

    # SE Segment
    segment_count = len(segments) - 2  # Excluding SE and IEA segments
    segments.append(f'SE*{segment_count}*0001' + '~')

    # GE Segment
    segments.append('GE*1*1' + '~')

    # IEA Segment
    segments.append('IEA*1*000000001' + '~')

    return "\n".join(segments)

def read_edi_from_blob(blob_url):
    """Read EDI content from the given blob URL"""
    config_for_edi = load_config("custom_edi.config")
    
    # Create a BlobServiceClient using the connection string
    CONNECTION_STRING = "".join(config_for_edi["blob_credentials"]["CONNECTION_STRING"])
    
    blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    container_name = config_for_edi["blob_credentials"]["CONTAINER_NAME"]
    blob_name = os.path.basename(blob_url)  # Extract filename from URL
    
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    
    if not blob_client.exists():
        return {"error": "File does not exist in blob storage"}
    
    blob_data = blob_client.download_blob().readall()
    return blob_data.decode('utf-8')
    
@edi_bp.route('/create_edi', methods=['GET', 'POST'])
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
        "message": "EDI 278 Created based on given Member, Provider, ICD, CPT, Submitter Receiver",
        "data": edi_content
    }
    return jsonify(response)

@edi_bp.route('/create_edi_278_new', methods=['GET', 'POST'])
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
        "message": "EDI 278 Created based on given Member, Provider, ICD, CPT, Submitter Receiver",
        "data": edi_content
    }
    return jsonify(response)

