import random
import json
import datetime
from datetime import datetime
import os
from flask import request, jsonify
from azure.storage.blob import BlobServiceClient
from flask_smorest import Blueprint

edi_271_bp = Blueprint("edi_271", "edi_271", url_prefix="/edi_271")

def load_config(file_path="custom_edi.config"):
    with open(file_path, 'r') as file:
        return json.load(file)

def check_invalid(obj):
    if not isinstance(obj, list):
        return True
    return any(item is None for item in obj)
    
def generate_edi_271(json_obj):
    segments = []
    
    now = datetime.now()
    current_date_yy = now.strftime('%y%m%d')
    current_date_yyyy = now.strftime('%Y%m%d')
    current_time = now.strftime('%H%M')
    
    # ISA - Interchange Control Header
    # Remove the ">" at the end and end with ":~"
    if 'submitter' in json_obj and 'receiver' in json_obj:
        isa_segment = (
            'ISA*00*          *00*          *ZZ*' + 
            json_obj['submitter'].ljust(15) + 
            '*ZZ*' + json_obj['receiver'].ljust(15) + 
            '*' + current_date_yy + '*' + current_time + 
            '*U*00401*000000001*0*P*:'
        )
        segments.append(isa_segment + '~')
        gs_segment = f'GS*HC*{json_obj["submitter"][:2]}*{json_obj["receiver"][:2]}*{current_date_yyyy}*{current_time}*1*X*004010X096A1'
        segments.append(gs_segment + '~')
    else:
        isa_segment = (
            'ISA*00*          *00*          *ZZ*' + 
            current_date_yy + '*' + current_time + 
            '*U*00401*000000001*0*P*:'
        )
        segments.append(isa_segment + '~')
        gs_segment = f'GS*HC*{current_date_yyyy}*{current_time}*1*X*004010X096A1'
        segments.append(gs_segment + '~')
    #segments.append(isa_segment + '~')
       
    # ST - Transaction Set Header
    st_control = now.strftime("%Y%m%d%H%M%S")
    st_segment = f'ST*271*{st_control}*005010X279A1'
    segments.append(st_segment + '~')
    
    # BHT - Beginning of Hierarchical Transaction
    purpose_code = '22'
    segments.append('BHT*0022*11*REF47517*20250303*1319' + '~') ##CHANGE
    
    # HL segments: first for the subscriber (member), second for the provider.
    segments.append('HL*1**20*1' + '~')  # HL for Member (Subscriber)
    segments.append('HL*2*1*21*1' + '~')  # HL for Provider (child of the subscriber)
    
    # --- Member (Subscriber) Information ---
    member = json_obj['member']
    segments.append(f'NM1*IL*1*{member["name"]}*****MI*{member["member_id"]}' + '~')
    segments.append(f'N3*{member["address"]}' + '~')
    try:
        dob_dt = datetime.strptime(member["dob"], "%m-%d-%Y")
        dob_formatted = dob_dt.strftime("%m-%d-%Y")
    except Exception:
        dob_formatted = member["dob"]
    #segments.append(f'N3*{member["address"]}' + '~')
    segments.append(f'DTP*291*D8*20250303~')
    segments.append(f'EQ*30~')     
    segments.append(f'DMG*D8*{dob_formatted}' + '~')
    
    # --- Provider Information ---
    provider = json_obj['provider']
    segments.append(f'HL*1**20*1' + '~')
    segments.append(f'NM1*1P*2*{provider["name"]}****46*{provider["npi"]}' + '~')
    segments.append(f'N3*{provider["address"]}' + '~')
    segments.append(f'PRV*BI*PXC*{provider["taxonomy"]}' + '~')
    # Extra Line - Not present in EDI 278 Review Request
    #segments.append(f'HCR*A1*PXC*{provider["auth_number"]}' + '~')#HCR*A1*AUTH0001~

    # --- Payer Information ---
    payer = json_obj['payer']
    segments.append(f'HL*2*1*21*1' + '~')
    segments.append(f'NM1*PR*2*{payer["name"]}****PI*{payer["payer_id"]}' + '~')
    #segments.append(f'N3*{provider["address"]}' + '~')
    #segments.append(f'PRV*BI*PXC*{provider["taxonomy"]}' + '~')

  # --- ICD Codes ---
    icd_list = json_obj['icd_codes']
    if check_invalid(icd_list) == False:
        for icd in json_obj['icd_codes']:
            segments.append(f'ICD*{icd}' + '~')
    else:
        segments.append(f'ICD*Null' + '~')
    
    # --- CPT Codes ---
    cpt_list = json_obj['cpt_codes']
    if check_invalid(cpt_list) == False:
        for cpt in json_obj['cpt_codes']:
            segments.append(f'CPT*{cpt}' + '~')
    else:
        segments.append(f'CPT*Null' + '~')

    # ----- Benefits Information --------- #
    #EB*1**30**GOLD 123 PLAN~ #EB*1**1>33>35>47>86>88>98>AL>MH>UC~ #EB*B**1>33>35>47>86>88>98>AL>MH>UC*HM*GOLD 123 PLAN*27*10*****Y~ #LS*2120~ #LE*2120~#
    benefits = json_obj['eligibility_benefit']
    if 'service_type_code' in benefits and 'plan_coverage' in benefits:
        service_type_code = benefits['service_type_code']
        plan_coverage = benefits['plan_coverage']
        segments.append(f'EB*1**{service_type_code}**{plan_coverage}' + '~')
    segments.append('EB*L' + '~')
    
    if 'active_coverage' in benefits:
        list_active_coverage = benefits['active_coverage']
        st = ""
        for l in list_active_coverage:
            st = st+(">")
            st = st + str(l)
        segments.append(f'EB*1**1{st}~')
        
    if 'copayment' in benefits:
        list_copayment = benefits['copayment']
        st = ""
        for l in list_copayment:
            st = st+(">")
            st = st + str(l)
        st = st+"*"
        if "insurance_type_code" in benefits:
            insurance_type_code = benefits["insurance_type_code"]
            st = st+str(insurance_type_code)
        
        if 'plan_coverage' in benefits:
            plan_coverage = benefits['plan_coverage']
            st = st+"*"
            st = st+str(plan_coverage)
        st = st+"27"
        if "monetory_value" in benefits:
            st = st+"*"
            monetory = benefits["monetory_value"]
            st = st+str(monetory)
        st = st+"****"
        if "in_plan" in benefits:
            in_plan = benefits["in_plan"]
            st = st+"*"
            st = st+str(in_plan)
        #st.append("~")
        segments.append(f'EB*B**1{st}~')

    segments.append('LS*2120' + '~')
    segments.append('LE*2120' + '~')
    # --- Trailer Segments ---
    segments.append(f'SE*{len(segments)+1}*{st_control}~')
    #segments.append('GE*1*1' + '~')
    segments.append('IEA*1*000000001' + '~')
    
    return '\n'.join(segments)

@edi_271_bp.route('/create_edi', methods=['GET', 'POST'])
def create_edi():
    claim_values = load_config("custom_edi.config")

    edi_content = ""
    if request.method == "POST":
        try:
            obj = request.get_json()
            edi_content = generate_edi_271(obj)
        except Exception as e:
            return jsonify({"error":  str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        print("Blob URL from GET = ", blob_url)
        if not blob_url:
            return jsonify({"error": "blob_url is required"}), 400

    print("Generated EDI 271 File:")
    print(edi_content)
    response = {
        "message": "EDI 271 Created based on given Member, Provider, ICD, CPT, Payer, Benefits Details",
        "data": edi_content
    }   
    return jsonify(response)
