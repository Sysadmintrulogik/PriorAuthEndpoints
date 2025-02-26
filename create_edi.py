import random
import json
import datetime
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
    
    # ISA - Interchange Control Header
    # Remove the ">" at the end and end with ":~"
    isa_segment = (
        'ISA*00*          *00*          *ZZ*' + 
        json_obj['submitter'].ljust(15) + 
        '*ZZ*' + json_obj['receiver'].ljust(15) + 
        '*' + current_date_yy + '*' + current_time + 
        '*U*00401*000000001*0*P*:'
    )
    segments.append(isa_segment + '~')
    
    # GS - Functional Group Header
    gs_segment = f'GS*HC*{json_obj["submitter"][:2]}*{json_obj["receiver"][:2]}*{current_date_yyyy}*{current_time}*1*X*004010X096A1'
    segments.append(gs_segment + '~')
    
    # ST - Transaction Set Header
    st_control = now.strftime("%Y%m%d%H%M%S")
    st_segment = f'ST*278*{st_control}*00'
    segments.append(st_segment + '~')
    
    # BHT - Beginning of Hierarchical Transaction
    segments.append('BHT*0007*13*REF47517*' + '~')
    
    # HL segments: first for the subscriber (member), second for the provider.
    segments.append('HL*1**20*1' + '~')  # HL for Member (Subscriber)
    segments.append('HL*2*1*21*1' + '~')  # HL for Provider (child of the subscriber)
    
    # --- Member (Subscriber) Information ---
    member = json_obj['member']
    segments.append(f'NM1*IL*1*{member["name"]}*****34*{member["member_id"]}' + '~')
    segments.append(f'N3*{member["address"]}' + '~')
    try:
        dob_dt = datetime.strptime(member["dob"], "%m-%d-%Y")
        dob_formatted = dob_dt.strftime("%m-%d-%Y")
    except Exception:
        dob_formatted = member["dob"]
    segments.append(f'DMG*D8*{dob_formatted}' + '~')
    
    # --- Provider Information ---
    provider = json_obj['provider']
    segments.append(f'NM1*85*2*{provider["name"]}****46*{provider["npi"]}' + '~')
    segments.append(f'N3*{provider["address"]}' + '~')
    segments.append(f'PRV*BI*PXC*{provider["taxonomy"]}' + '~')
    
    # --- Submitter Information ---
    segments.append(f'NM1*41*2*{json_obj["submitter"]}****46*{json_obj["submitter"][:10]}' + '~')
    
    # --- Receiver Information ---
    segments.append(f'NM1*40*2*{json_obj["receiver"]}****46*{json_obj["receiver"][:10]}' + '~')

    # --- ICD Codes ---
    for icd in json_obj['icd_codes']:
        segments.append(f'ICD*{icd}' + '~')
    
    # --- CPT Codes ---
    for cpt in json_obj['cpt_codes']:
        segments.append(f'CPT*{cpt}' + '~')
    
    # --- Trailer Segments ---
    segments.append(f'SE*{len(segments)+1}*0001' + '~')
    segments.append('GE*1*1' + '~')
    segments.append('IEA*1*000000001' + '~')
    
    return '\n'.join(segments)

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
            data = request.get_json()
            #print(data)
            obj = json.loads(data)
            print(obj)
            edi_content = generate_edi_278_new(obj)
            #blob_url = data.get("blob_url")
            #member = data.get("member")
            #print("Blob URL = ", blob_url)
            #print("Member  = ", member)
        except Exception as e:
            return jsonify({"error": "No Input JSON Found", "details": str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        print("Blob URL from GET = ", blob_url)
        if not blob_url:
            return jsonify({"error": "blob_url is required"}), 400
            
    #json_object = read_edi_from_blob(blob_url)
    #obj = json.loads(data)
    #print(obj)
    #edi_content = generate_edi_278_new(obj)
    print("Generated EDI 278 File:")
    print(edi_content)
    response = {
        "message": "EDI Created based on given Member, Provider, Eligibility, Policy Benefits, ICD, CPT Codes",
        "data": edi_content
    }
    return jsonify(response)
