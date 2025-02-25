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

def generate_edi_278(details):
    member = details.get("member", {})
    provider = details.get("provider", {})
    submitter = details.get("submitter", "SUBMITTER01")
    receiver = details.get("receiver", "RECEIVER01")
    payer = details.get("payer", "PAYER01")
    eligibility = details.get("eligibility", {})
    policy_benefits = details.get("policy_benefits", {})
    prior_auth = details.get("prior_auth", {})
    icd_codes = details.get("icd_codes", [])
    cpt_codes = details.get("cpt_codes", [])
    
    now = datetime.datetime.now()
    isa_date = now.strftime("%y%m%d")
    isa_time = now.strftime("%H%M")
    control_number = f"{random.randint(100000000, 999999999)}"
    gs_date = now.strftime("%Y%m%d")
    gs_time = now.strftime("%H%M")
    group_control = f"{random.randint(1000, 9999)}"
    transaction_set_control = f"{random.randint(1000, 9999)}"
    reference_number = f"REF{random.randint(10000, 99999)}"
    
    segments = []
    segments.append(f"ISA*00*          *00*          *ZZ*{submitter:<15}*ZZ*{receiver:<15}*{isa_date}*{isa_time}*U*00401*{control_number}*0*P*:~")
    segments.append(f"GS*HI*{submitter}*{receiver}*{gs_date}*{gs_time}*{group_control}*X*004010X278A1~")
    segments.append(f"ST*278*{transaction_set_control}~")
    segments.append(f"BHT*0007*13*{reference_number}*{gs_date}*{gs_time}~")
    
    segments.append("HL*1**20*1~")
    segments.append(f"NM1*82*2*{provider.get('name', 'Provider Name')}*****XX*{provider.get('npi', '0000000000')}~")
    segments.append(f"N3*{provider.get('address', 'Provider Address')}~")
    segments.append("N4*City*State*Zip~")
    segments.append(f"PRV*PE*PXC*{provider.get('taxonomy', '0000000000')}~")
    
    segments.append("HL*2*1*21*1~")
    member_name = member.get("name", "John Doe")
    if " " in member_name:
        first_name, last_name = member_name.split(" ", 1)
    else:
        first_name = member_name
        last_name = ""
    segments.append(f"NM1*IL*1*{last_name}*{first_name}****MI*{member.get('member_id', 'M0001')}~")
    #segments.append(f"NM1*IL*1*{last_name}*{first_name}****MI*{member.get('member_id', 'M0001')}~")
    mem_dob = eligibility.get("dob", "09011947")
    segments.append(f"DOB*{mem_dob}~")
    #sub_dob = eligibility.get("subscriber_dob", member.get("dob", "09011947"))
    #segments.append(f"DOB*{sub_dob}~")
    segments.append(f"N3*{member.get('address', 'Member Address')}~")
    
    segments.append("HL*3*2*22*0~")
    segments.append(f"EB*{eligibility.get('is_eligible', 'Yes')}*{eligibility.get('start_date', '01-01-2022')}*{eligibility.get('end_date', '12-31-2025')}~")
    segments.append(f"GRP*{eligibility.get('group_no', 'G0001')}~")
    sub_dob = eligibility.get("subscriber_dob", "01011980")
    segments.append(f"DOB*{sub_dob}~")
    segments.append(f"PB*{policy_benefits.get('PolicyName', 'Default Policy')}*{policy_benefits.get('Coverage', 'HMO')}~")
    for benefit in policy_benefits.get("details", []):
        segments.append(f"BEN*{benefit.get('type', 'General')}*{benefit.get('description', 'No Description')}~")
    
    segments.append(f"PA*{prior_auth.get('auth_status', 'Approved')}*{prior_auth.get('auth_number', 'AUTH12345')}*{prior_auth.get('auth_date', '01-01-2022')}*{prior_auth.get('auth_expiry_date', '12-31-2025')}~")
    
    for icd in icd_codes:
        segments.append(f"ICD*{icd}~")
    
    for cpt in cpt_codes:
        segments.append(f"CPT*{cpt}~")
    
    # Append SE segment with placeholders
    segments.append("SE*{seg_count}*{transaction_set_control}~")
    segments.append(f"GE*1*{group_control}~")
    segments.append(f"IEA*1*{control_number}~")
    
    edi_str = "\n".join(segments)
    edi_segments = edi_str.split("\n")
    st_index = None
    se_index = None
    for i, seg in enumerate(edi_segments):
        if seg.startswith("ST*"):
            st_index = i
        if seg.startswith("SE*"):
            se_index = i
            break
    if st_index is not None and se_index is not None:
        seg_count = se_index - st_index + 1
        edi_segments[se_index] = edi_segments[se_index].replace("{seg_count}", str(seg_count))\
                                                     .replace("{transaction_set_control}", transaction_set_control)
    edi_str = "\n".join(edi_segments)
    
    with open("edi278.txt", "w") as f:
        f.write(edi_str)
    
    return edi_str

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
    sample_input = claim_values["edi_features"]       
    
    if request.method == "POST":
        try:
            data = request.get_json()
            blob_url = data.get("blob_url")
        except Exception as e:
            return jsonify({"error": "Input JSON doesn't seem to exist", "details": str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        print("Blob URL from GET = ", blob_url)
        if not blob_url:
            return jsonify({"error": "blob_url is required"}), 400
        
    json_object = read_edi_from_blob(blob_url)
    obj = json.loads(json_object)
    print(obj)
    edi_content = generate_edi_278(obj)
    print("Generated EDI 278 File:")
    print(edi_content)
    response = {
        "message": "EDI Created based on given Member, Provider, Eligibility, Policy Benefits, ICD, CPT and PriorAuth",
        "data": edi_content
    }
    return (response)
