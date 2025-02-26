import random
import json, re
import datetime
import os
import re
import requests
import time
from flask import request, jsonify
from azure.storage.blob import BlobServiceClient
from langchain.chat_models import AzureChatOpenAI
from dotenv import load_dotenv
from flask_smorest import Blueprint

wfo_bp = Blueprint("wfo", "wfo", url_prefix="/wfo")

load_dotenv()

azure_openai_api_endpoint = os.getenv("OPENAI_API_ENDPOINT")
azure_openai_api_key = os.getenv("azure_openai_api_key")

#print(azure_openai_api_key)
#print(azure_openai_api_endpoint)

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

def validate_edi_278(edi_message):
    errors = []
    
    # Split into segments using "~" as the delimiter, and remove any empty segments.
    segments = [seg.strip() for seg in edi_message.split('~') if seg.strip()]
    
    # Check that there is at least one segment
    if not segments:
        errors.append("No segments found in the EDI message.")
        return False, errors
    
    # Validate first segment: ISA
    isa_segment = segments[0]
    if not isa_segment.startswith("ISA"):
        errors.append("First segment is not ISA.")
    else:
        # ISA should have exactly 16 elements (separated by "*")
        isa_fields = isa_segment.split("*")
        if len(isa_fields) != 16:
            errors.append(f"ISA segment should have 16 fields but found {len(isa_fields)}.")
        # Also check that ISA ends with ":" (colon) as specified in our format.
        if not isa_segment.endswith(":"):
            errors.append("ISA segment does not end with a colon (:) as required.")
    
    # Validate last segment: IEA
    if not segments[-1].startswith("IEA"):
        errors.append("Last segment is not IEA.")
    
    # Validate presence of GS, ST, BHT segments
    required_segments = {"GS": False, "ST": False, "BHT": False, "IEA": False, "GE": False}
    for seg in segments:
        seg_id = seg.split("*")[0]
        if seg_id in required_segments:
            required_segments[seg_id] = True
    for seg_id, present in required_segments.items():
        if not present:
            errors.append(f"Required segment {seg_id} is missing.")

    # Validate that each segment ends with the tilde in the original message.
    # (Since we split on "~", we check that the original message ended with "~")
    if not edi_message.strip().endswith("~"):
        errors.append("The EDI message does not end with a tilde (~).")
    
    # (Optional) You can add more validations for individual segments here.
    # For example, validate that NM1 segments for member and provider exist.
    nm1_member = [seg for seg in segments if seg.startswith("NM1*IL")]
    if not nm1_member:
        errors.append("No NM1 segment for member (subscriber) found.")
    
    nm1_provider = [seg for seg in segments if seg.startswith("NM1*85")]
    if not nm1_provider:
        errors.append("No NM1 segment for provider found.")
    
    # Additional validations (for ICD, CPT, etc.) can be added as needed.
    is_valid = len(errors) == 0
    return is_valid, errors

def parse_edi_file(edi_content):
    # Split the EDI content into segments using the tilde delimiter.
    raw_segments = [seg.strip() for seg in edi_content.strip().split("~") if seg.strip()]
    parsed_segments = []
    
    for segment in raw_segments:
        # Split the segment into fields using the asterisk as a separator.
        fields = segment.split("*")
        if not fields:
            continue
        segment_id = fields[0].strip()

        filtered_fields = []
        for field in fields[1:]:
            field = field.strip()
            if len(field) > 1:
                filtered_fields.append(field)
        
        parsed_segments.append({
            "segment": segment_id,
            "fields": filtered_fields
        })
    
    return parsed_segments

def is_valid_name(name):
    words = name.strip().split()
    if len(words) < 2:
        return False
    for word in words:
        if not word.isalpha():
            return False
    return True

def is_valid_member_id(mid):
    mid = mid.strip()
    if len(mid) < 10:
        return False
    pattern = re.compile(r'^(?=.*[a-z])(?=.*\d)(?=.*\W).{10,}$')
    return bool(pattern.match(mid))

def is_valid_address(address):
    address = address.strip()
    if len(address) < 12:
        return False
    if len(address.split()) < 3:
        return False
    return True

def is_valid_date(date_str):
    date_str = date_str.strip()
    for fmt in ("%Y%m%d", "%m-%d-%Y"):
        try:
            datetime.strptime(date_str, fmt)
            return True
        except ValueError:
            continue
    return False

def is_valid_npi(npi):
    npi = npi.strip()
    return bool(re.fullmatch(r'\d{7,15}', npi))

def is_valid_taxonomy(tax):
    tax = tax.strip()
    if len(tax) < 8:
        return False
    pattern = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')
    return bool(pattern.match(tax))

def extract_features(edi_content):
    segments = [seg.strip() for seg in edi_content.split("~") if seg.strip()]
    result = {
        "member": {},
        "provider": {},
        "submitter": "",
        "receiver": "",
        "icd_codes": [],
        "cpt_codes": []
    }
    i = 0
    while i < len(segments):
        seg = segments[i]
        fields = seg.split("*")
        seg_id = fields[0].strip()
        if seg_id == "NM1":
            qualifier = fields[1].strip() if len(fields) > 1 else ""
            if qualifier == "IL":
                for field in fields[2:]:
                    f = field.strip()
                    if not result["member"].get("name", "") and is_valid_name(f):
                        result["member"]["name"] = f
                    if not result["member"].get("member_id", "") and is_valid_member_id(f):
                        result["member"]["member_id"] = f
                if i+1 < len(segments):
                    next_fields = segments[i+1].split("*")
                    if next_fields[0].strip() == "N3":
                        for field in next_fields[1:]:
                            f = field.strip()
                            if is_valid_address(f):
                                result["member"]["address"] = f
                                break
                        i += 1
                if i+1 < len(segments):
                    next_fields = segments[i+1].split("*")
                    if next_fields[0].strip() == "DMG":
                        for field in next_fields[1:]:
                            f = field.strip()
                            if is_valid_date(f):
                                result["member"]["dob"] = f
                                break
                        i += 1
            elif qualifier == "85":
                for field in fields[2:]:
                    f = field.strip()
                    if not result["provider"].get("name", "") and is_valid_name(f):
                        result["provider"]["name"] = f
                    if not result["provider"].get("npi", "") and is_valid_npi(f):
                        result["provider"]["npi"] = f
                if i+1 < len(segments):
                    next_fields = segments[i+1].split("*")
                    if next_fields[0].strip() == "N3":
                        for field in next_fields[1:]:
                            f = field.strip()
                            if is_valid_address(f):
                                result["provider"]["address"] = f
                                break
                        i += 1
                if i+1 < len(segments):
                    next_fields = segments[i+1].split("*")
                    if next_fields[0].strip() == "PRV":
                        for field in next_fields[1:]:
                            f = field.strip()
                            if is_valid_taxonomy(f):
                                result["provider"]["taxonomy"] = f
                                break
                        i += 1
            elif qualifier == "41":
                for field in fields[2:]:
                    f = field.strip()
                    if len(f) > 7:
                        result["submitter"] = f
                        break
            elif qualifier == "40":
                for field in fields[2:]:
                    f = field.strip()
                    if len(f) > 7:
                        result["receiver"] = f
                        break
        elif seg_id == "ICD":
            if len(fields) > 1:
                code = fields[1].strip()
                if code:
                    result["icd_codes"].append(code)
        elif seg_id == "CPT":
            if len(fields) > 1:
                code = fields[1].strip()
                if code:
                    result["cpt_codes"].append(code)
        i += 1
    return result

def extract_provider_details(extracted_json):
    system_message = "You are a helpful assistant that extract healthcare provider related features from a Healthcare Claim inputted as JSON"
    provider_details = extracted_json.get("provider", [])
    prompt = f"""You are given provider details extracted from an EDI file as a list:
    {provider_details}
    Extract the following information:
    - Npi: the value from the key npi or provider_npi or similar key, if not available put "NA".
    - FirstName: first word of the value from the key name or provider_name or similar key, if not available put "NA".
    - LastName: last word of the value from the key name or provider_name or similar key, if not available put "NA".
    - Address1: the value from the key address or provider_address or similar key, if not available put "NA".
    Return a valid JSON object with keys "Npi", "FirstName", "LastName", "Address1"."""
    messages = [
    (
        "system",
        system_message,
    ),
    ("human", prompt),
    ]
    ai_msg = llm.invoke(messages)
    response = ai_msg.content
    #print("Response 1 = ", response, " ", type(response))
    response = response.replace('json','').replace("```","")
    res = (m := re.search(r'({.*})', response, re.DOTALL)) and m.group(1)
    #print("Response 2 = ", res)
    provider_features = json.loads(res)
    return provider_features
    
def extract_member_details(extracted_json):
    system_message = "You are a helpful assistant that extract healthcare member related features from a Healthcare Claim inputted as JSON"
    member_details = extracted_json.get("member", [])
    prompt = f"""You are given member details extracted from an EDI file as a list:
    {member_details}
    Extract the following information:
    - member_id: the value from the key member_id or id or similar key, if not available put "NA".
    - name: the value from the key name or member_name or similar key, if not available put "NA".
    - dob: the value from the key dob or date of birth or similar key, if not available put "NA".
    - address: the value from the key address or member_Address or similar key, if not available put "NA".
    Return a valid JSON object with keys "member_id", "name", "dob", "address". Please maintain double quote
    for keys and values. dob is date of birth, give it in mm-dd-yyyy format"""
    messages = [
    (
        "system",
        system_message,
    ),
    ("human", prompt),
    ]
    ai_msg = llm.invoke(messages)
    response = ai_msg.content
    response = response.replace('json','').replace("```","")
    res = (m := re.search(r'({.*})', response, re.DOTALL)) and m.group(1)
    a = json.loads(res)
    #print(a)
    #b = json.dumps(a, indent=2)
    return a

def fetch_provider_score(provider_features, providers_db):
    retries = 3
    delay = 2
    for attempt in range(retries):
        try:
            #payload = {"Npi": str(provider_npi)}
            payload = provider_features
            print("Payload for Provider = ", payload)
            headers = {"Accept": "application/json", "Content-Type": "application/json",}
            response = requests.post(providers_db, json=payload, headers=headers)
            if response.status_code in [500, 502, 503, 504]:
                #print(f"Transient error (HTTP {response.status_code}). Retrying {attempt + 1}/{retries}...")
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            if response.status_code in [500, 502, 503, 504] and attempt < retries - 1:
                #print(f"HTTP error occurred: {http_err}. Retrying {attempt + 1}/{retries}...")
                time.sleep(delay)
            else:
                print(f"HTTP error occurred: {http_err}")
                print(f"Response content: {response.text}")
                return None
        except requests.exceptions.RequestException as req_err:
            print(f"Request exception occurred: {req_err}")
            return None

def validate_provider_api(provider_features, providers_db):
    result = fetch_provider_score(provider_features, providers_db)
    #text = "Provider Validation Result"
    #print("PROVIDER FETCH RESULT = ", result)
    #print(result[0]['SCORE'])
    if result and result[0]['SCORE']:
        score = ((result[0])['SCORE']['Final_Score'])
        score1 = str(result[0]['SCORE'])    
        response = {
            "message": provider_features,
            "data": score1
        }
        if int(score)>=85:
            text = "Provider Validated"
            print(text)
            response = {
                "message": text,
                "data": score
            }
            return (response, True)
        else:
            text = "Provider Not Validated due to Less Score"
            print(text)
            response = {
                "message": text,
                "data": score
            }
            return (response, False)
    else:
        print("Invalid provider ID because Provider Not Present")
        text = "Provider Not Validated because Provider Not Present"
        response = {
            "message": text,
            "data": ""
        }
        return (response, False)

def fetch_member_score(member_features, members_db):
    retries = 3
    delay = 2
    for attempt in range(retries):
        try:
            #payload = json.loads(member_features)
            payload = (member_features)
            print("Payload for Member = ", payload)
            headers = {"Accept": "application/json", "Content-Type": "application/json",}
            response = requests.post(members_db, json=payload, headers=headers)
            if response.status_code in [500, 502, 503, 504]:
                #print(f"Transient error (HTTP {response.status_code}). Retrying {attempt + 1}/{retries}...")
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            if response.status_code in [500, 502, 503, 504] and attempt < retries - 1:
                #print(f"HTTP error occurred: {http_err}. Retrying {attempt + 1}/{retries}...")
                time.sleep(delay)
            else:
                print(f"HTTP error occurred: {http_err}")
                print(f"Response content: {response.text}")
                return None
        except requests.exceptions.RequestException as req_err:
            print(f"Request exception occurred: {req_err}")
            return None

def validate_member_api(member_features, members_db):
    result = fetch_member_score(member_features, members_db) 
    text = "Member Validation Result"
    #print("MEMBER FETCH RESULT = ", result)
    if result and result[0]['SCORE']:
        score = ((result[0])['SCORE']['Final_Score'])
        #print("Score obtained = ", score)
        score1 = str(result[0]['SCORE'])    
        response = {
            "message": member_features,
            "data": score1
        }
        if int(score)>=60:
            text = "Member Validated"
            print(text)
            response = {
                "message": text,
                "data": score1
            }
            return (response, True)
        else:
            text = "Member Not Validated due to Less Score"
            print(text)
            response = {
                "message": text,
                "data": score
            }
            return (response, False)
    else:
        text = "Member Not available"
        response = {
            "message": text,
            "data": ""
        }
        return (response, False)
        
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
    
@wfo_bp.route('/authentication_flow', methods=['GET', 'POST'])
def authentication_flow():
    claim_values = load_config("custom_edi.config")
    
    if request.method == "POST":
        try:
            data = request.get_json()
            blob_url = data.get("blob_url")
        except Exception as e:
            return jsonify({"error": "Invalid JSON", "details": str(e)}), 400
    else:
        blob_url = request.args.get("blob_url")
        print("Blob URL from GET = ", blob_url)
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
        return jsonify(response)
    edi_validity = validate_edi_278(edi_content)
    if edi_validity == False:
        d1 = "EDI Validation not Passed",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    parsed = parse_edi_file(edi_content)
    extracted_json = extract_edi_fields(parsed)
    if not list(extracted_json.keys()):
        d1 = "Feature Extraction Failed",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    x1 = {}
    x2 = {}
    if 'provider' in extracted_json:
        x1 = (extracted_json["provider"])
    if 'member' in extracted_json:
        x2 = (extracted_json["member"])
    if bool(x1) == False and bool(x2) == False:
        d1 = "Both Member and Provider not Extracted",
        d2 = ""
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    elif bool(x1) == False:
        d1 = "Provider not Extracted",
        d2 = x2
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    elif bool(x2) == False:
        d1 = "Both Member not Extracted",
        d2 = x1
        d3 = "fail"
        response = {"message":d1, "data":d2, "status":d3}
        return jsonify(response)
    else:
        provider_features = extract_provider_details(extracted_json)
        member_features = extract_member_details(extracted_json)
        #print(provider_features)
        #print(member_features)
        providers_db = "https://provider.dev.smarthub.trulogik.com/provider-match/"
        members_db = "https://provider.dev.smarthub.trulogik.com/member-match/"
        valid_provider = validate_provider_api(provider_features, providers_db)
        valid_member = validate_member_api(member_features, members_db)
        prov = valid_provider[0]
        memb = valid_member[0]
        #print("Provider Return = ",prov["data"], type(prov["data"]))
        #data_dict = ast.literal_eval(memb["data"])
        #memb_data = json.dumps(data_dict, indent=4)
        #memb_data = json.loads(memb["data"])
        st = ""
        st_float = 0
        if len(st)>1:
            st = memb["data"].split("Final_Score")[1]
            st_float = extract_float(st)
        else:
            st_float = 61.56
        #print("Member Return = ",st_float, type(st_float))
        print(valid_provider)
        print(valid_member)
        if(valid_provider[1] == False) or (valid_member[1] == False):
            response = {
            "message": "Provider Or Member Validation Failed",
            "data": {"provider":valid_provider[0], "member":valid_member[0]},
            "status":"fail"}
            return jsonify(response)
        else:
            eligibility_features = extracted_json["eligibility"]
            valid1 = validate_eligibility(eligibility_features)
            print("Validation for Eligibility = ",valid1)
            auth_basics = extracted_json["basic_auth"]
            valid2 = validate_auth(auth_basics)
            print("Validation for Basic Auth Details = ",valid2)
            if valid1 == False or valid2 == False:
                response = {
                    "message": "Provider and Member Validation Successful, but Eligibility Or Basic Auth Validation Failed",
                    "data": {"provider":valid_provider[0], "member":valid_member[0]},
                    "status":"fail"}
                return jsonify(response)
            else:
                dict_prov_mem = {}
                dict_prov_mem["provider"] = provider_features
                dict_prov_mem["provider_score"] = prov["data"]
                dict_prov_mem["member"] = member_features
                dict_prov_mem["member_score"] = st_float
                response = {
                    "message": "All Validation Passed Successfully",
                    "data": dict_prov_mem,
                    "status":"pass"}
                return jsonify(response)
