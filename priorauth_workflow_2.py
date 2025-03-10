import random
import json, re
#from faker import Faker
import datetime
import os, sys
import requests
from collections import Counter

from flask import Flask, request, jsonify
app = Flask(__name__)

from azure.storage.blob import BlobServiceClient
from langchain.chat_models import AzureChatOpenAI

from dotenv import load_dotenv
import time

env_path = '/opt/conda/envs/indranilenv/.env'
load_dotenv(env_path)

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

def generate_edi_278(details, output_file="edi278.txt"):
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
    segments.append(f"GS*HI*{submitter}*{receiver}*{payer}*{gs_date}*{gs_time}*{group_control}*X*004010X278A1~")
    segments.append(f"ST*278*{transaction_set_control}~")
    segments.append(f"BHT*0007*13*{reference_number}*{gs_date}*{gs_time}~")
    
    # Provider Hierarchical Level
    segments.append("HL*1**20*1~")
    segments.append(f"NM1*82*2*{provider.get('name', 'Provider Name')}*****XX*{provider.get('npi', '0000000000')}~")
    segments.append(f"N3*{provider.get('address', 'Provider Address')}~")
    segments.append("N4*City*State*Zip~")
    segments.append(f"PRV*PE*PXC*{provider.get('taxonomy', '0000000000')}~")
    
    # Subscriber (Member) Hierarchical Level
    segments.append("HL*2*1*21*1~")
    member_name = member.get("name", "John Doe")
    if " " in member_name:
        first_name, last_name = member_name.split(" ", 1)
    else:
        first_name = member_name
        last_name = ""
    segments.append(f"NM1*IL*1*{last_name}*{first_name}****MI*{member.get('member_id', 'M0001')}~")
    # Member's DOB from member details
    segments.append(f"DOB*{member.get('dob', '12-12-1980')}~")
    segments.append(f"N3*{member.get('address', 'Member Address')}~")
    
    # Eligibility / Benefits Hierarchical Level
    segments.append("HL*3*2*22*0~")
    segments.append(f"EB*{eligibility.get('is_eligible', 'Yes')}*{eligibility.get('start_date', '01-01-2022')}*{eligibility.get('end_date', '12-31-2023')}~")
    # Subscriber's DOB from eligibility (kept separate)
    if 'subscriber_dob' in eligibility:
        segments.append(f"DMG*D8*{eligibility['subscriber_dob']}~")
    segments.append(f"GRP*{eligibility.get('group_no', 'G0001')}~")
    segments.append(f"PB*{policy_benefits.get('PolicyName', 'Default Policy')}*{policy_benefits.get('Coverage', 'HMO')}~")
    for benefit in policy_benefits.get("details", []):
        segments.append(f"BEN*{benefit.get('type', 'General')}*{benefit.get('description', 'No Description')}~")
    
    # Prior Authorization Details segment (PA)
    segments.append(f"PA*{prior_auth.get('auth_status', 'Approved')}*{prior_auth.get('auth_number', 'AUTH12345')}*{prior_auth.get('auth_date', '01-01-2022')}*{prior_auth.get('auth_expiry_date', '12-31-2023')}~")
    
    for icd in icd_codes:
        segments.append(f"ICD*{icd}~")
    
    for cpt in cpt_codes:
        segments.append(f"CPT*{cpt}~")
    
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
    
    directory = os.path.dirname(output_file)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    
    with open(output_file, "w") as f:
        f.write(edi_str)
    
    return edi_str

def create_edi(sample_input, output_file):
    edi_content = generate_edi_278(sample_input, output_file)
    return edi_content

def validate_edi_278(content):
    segments = [seg.strip() for seg in content.split("~") if seg.strip()]

    if not segments or not segments[0].startswith("ISA"):
        print("Error: Missing or invalid ISA segment.")
        return False
    if not any(seg.startswith("GS") for seg in segments):
        print("Error: Missing GS segment.")
        return False

    try:
        st_index = next(i for i, seg in enumerate(segments) if seg.startswith("ST"))
    except StopIteration:
        print("Error: Missing ST segment.")
        return False

    try:
        se_index = next(i for i, seg in enumerate(segments[st_index:], start=st_index) if seg.startswith("SE"))
    except StopIteration:
        print("Error: Missing SE segment.")
        return False

    transaction_count = se_index - st_index + 1
    se_fields = segments[se_index].split("*")
    try:
        expected_count = int(se_fields[1])
    except (IndexError, ValueError):
        print("Error: Invalid SE segment count.")
        return False
    print("Transaction Count = ",transaction_count)
    print("Expected Count = ",expected_count)
    #if transaction_count != expected_count:
        #print("Error: Transaction segment count mismatch.")
        #return False
    if not any(seg.startswith("GE") for seg in segments):
        print("Error: Missing GE segment.")
        return False
    if not segments[-1].startswith("IEA"):
        print("Error: Missing IEA segment.")
        return False
    return True

def parse_edi_file(edi_content, output_file):
    edi_text = edi_content.strip()
    segments = [seg.strip() for seg in edi_text.split("~") if seg.strip()]
    parsed_segments = []
    for seg in segments:
        # Split the segment into elements using "*" and filter out elements that are empty or one character long.
        elements = [elem.strip() for elem in seg.split("*")]
        filtered_elements = [elem for elem in elements if len(elem) > 1]
        if filtered_elements:
            parsed_segments.append({
                "tag": filtered_elements[0],
                "elements": filtered_elements[1:]
            })
    directory = os.path.dirname(output_file)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(output_file, "w") as f:
        json.dump(parsed_segments, f, indent=4)
    return parsed_segments
    
def is_name(s):
    # True if s contains 2-4 words and no digits.
    words = s.split()
    return len(words) in [2, 3, 4] and not any(char.isdigit() for char in s)

def is_npi(s):
    # True if s is all digits and length between 7 and 11.
    return s.isdigit() and 7 <= len(s) <= 11

def is_taxonomy(s):
    # True if s is alphanumeric, 7-11 characters long, containing at least one digit and one letter.
    if not s.isalnum():
        return False
    if not (7 <= len(s) <= 11):
        return False
    return any(char.isdigit() for char in s) and any(char.isalpha() for char in s)

def extract_edi_fields(parsed_segments):
    output = {
        "member": {},
        "provider": {},
        "submitter": "",
        "receiver": "",
        "payer": "",
        "eligibility": {},
        "policy_benefits": {"details": []},
        "basic_auth": {},
        "icd_codes": [],
        "cpt_codes": []
    }
    
    for seg in parsed_segments:
        tag = seg.get("tag")
        elems = seg.get("elements", [])
        
        if tag == "GS":
            # GS: [HI, Submitter Sanders, Receiver Roberts, Payer Paddington, ...]
            if len(elems) >= 4:
                output["submitter"] = elems[1]
                output["receiver"] = elems[2]
                output["payer"] = elems[3]
        elif tag == "NM1":
            # Provider NM1: first element "82"
            if elems and elems[0] == "82":
                for element in elems:
                    if not output["provider"].get("name") and is_name(element):
                        output["provider"]["name"] = element
                    if not output["provider"].get("npi") and is_npi(element):
                        output["provider"]["npi"] = element
            # Member NM1: first element "IL"
            elif elems and elems[0] == "IL":
                if len(elems) >= 5:
                    # For member, we assume first name is at index 2 and last name is at index 1.
                    first_name = elems[2]
                    last_name = elems[1]
                    output["member"]["name"] = f"{first_name} {last_name}"
                    output["member"]["member_id"] = elems[4]
        elif tag == "DOB":
            if elems:
                output["member"]["dob"] = elems[0]
        elif tag == "N3":
            # If provider already has a name and no address, assign provider address.
            if "name" in output["provider"] and "address" not in output["provider"]:
                output["provider"]["address"] = elems[0]
            elif "name" in output["member"] and "address" not in output["member"]:
                output["member"]["address"] = elems[0]
        elif tag == "PRV":
            for element in elems:
                if not output["provider"].get("taxonomy") and is_taxonomy(element):
                    output["provider"]["taxonomy"] = element
        elif tag == "EB":
            if len(elems) >= 3:
                output["eligibility"]["is_eligible"] = elems[0]
                output["eligibility"]["start_date"] = elems[1]
                output["eligibility"]["end_date"] = elems[2]
        elif tag == "DMG":
            if len(elems) >= 2:
                output["eligibility"]["subscriber_dob"] = elems[1]
        elif tag == "GRP":
            if elems:
                output["eligibility"]["group_no"] = elems[0]
        elif tag == "PB":
            if len(elems) >= 2:
                output["policy_benefits"]["PolicyName"] = elems[0]
                output["policy_benefits"]["Coverage"] = elems[1]
        elif tag == "BEN":
            if len(elems) >= 2:
                benefit = {"type": elems[0], "description": elems[1]}
                output["policy_benefits"]["details"].append(benefit)
        elif tag == "PA":
            if len(elems) >= 4:
                output["basic_auth"]["auth_status"] = elems[0]
                output["basic_auth"]["auth_number"] = elems[1]
                output["basic_auth"]["auth_date"] = elems[2]
                output["basic_auth"]["auth_expiry_date"] = elems[3]
        elif tag == "ICD":
            if elems:
                output["icd_codes"].append(elems[0])
        elif tag == "CPT":
            if elems:
                output["cpt_codes"].append(elems[0])  
    return output

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
    print("Response 1 = ", response, " ", type(response))
    response = response.replace('json','').replace("```","")
    res = (m := re.search(r'({.*})', response, re.DOTALL)) and m.group(1)
    print("Response 2 = ", res)
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
    b = json.dumps(a, indent=2)
    return b

def fetch_provider_score(provider_features, providers_db):
    retries = 3
    delay = 2
    for attempt in range(retries):
        try:
            #payload = {"Npi": str(provider_npi)}
            payload = provider_features
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
    text = "Provider Validation Result"
    if result and result[0]['SCORE']:
        score = ((result[0])['SCORE']['Final_Score'])
        score1 = str(result[0]['SCORE'])    
        response = {
            "message": text,
            "data": score1
        }
        if int(score)>=85:
            text = "Provider Validated"
            return (response, True)
        else:
            text = "Provider Not Validated due to Less Score"
            return (response, False)
    else:
        print("Invalid provider ID because Provider Not Present")
        text = "Provider Not Validated because Provider Not Present"
        return (response, False)

def fetch_member_score(member_features, members_db):
    retries = 3
    delay = 2
    for attempt in range(retries):
        try:
            payload = json.loads(member_features)
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
    if result and result[0]['SCORE']:
        score = ((result[0])['SCORE']['Final_Score'])
        print("Score obtained = ", score)
        score1 = str(result[0]['SCORE'])    
        response = {
            "message": text,
            "data": score1
        }
        if int(score)>=65:
            text = "Member Validated"
            return (response, True)
        else:
            text = "Member Not Validated due to Less Score"
            return (response, False)
    else:
        print("Invalid Member ID because Member Not Present")
        text = "Member Not Validated because Member Not Present"
        return (response, False)

def validate_eligibility(eligibility_features):
    valid = False
    elig = eligibility_features["is_eligible"].lower()
    #print("eligibility = ",elig, type(elig))
    if elig in ["yes", "true", "valid"]:
        today = datetime.datetime.today()
        print("Today's Date = ", today)
        start = datetime.datetime.strptime(eligibility_features["start_date"], "%m-%d-%Y")
        end = datetime.datetime.strptime(eligibility_features["end_date"], "%m-%d-%Y")
        if start <= today <= end:
            valid = True
        else:
            valid = False
    return valid

def validate_auth(auth_basics):
    valid = False
    elig = auth_basics["auth_status"].lower()
    #print("eligibility = ",elig, type(elig))
    if elig in ["approved", "true", "valid"]:
        today = datetime.datetime.today()
        print("Today's Date = ", today)
        start = datetime.datetime.strptime(auth_basics["auth_date"], "%m-%d-%Y")
        end = datetime.datetime.strptime(auth_basics["auth_expiry_date"], "%m-%d-%Y")
        if start <= today <= end:
            valid = True
        else:
            valid = False
    return valid

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
    
@app.route('/authentication_flow', methods=['GET', 'POST'])
def authentication_flow():
    claim_values = load_config("custom_edi.config")
    blob_url = request.args.get("blob_url")
    #print("Request = ", blob_url)
    if not blob_url:
        return jsonify({"error": "blob_url is required"}), 400

    print(f"Processing EDI from Blob URL: {blob_url}")
    
    list_fields_1 = (claim_values["fields_need_to_check"])
    """
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Blob URL required"}))
        sys.exit(1)
    blob_url = sys.argv[1]
    
    sample_input = claim_values["edi_features"]
    list_text = list()
    list_message = list()
    print("Features Present in the Input EDI ....... ")
    print(list(sample_input.keys()))
    output_file = claim_values["output_edi"]
    """
    
    list_text = list()
    list_message = list()
    start_time = time.time()
    edi_content = read_edi_from_blob(blob_url)
    #print(edi_content)
    flag = False
    edi_validity = validate_edi_278(edi_content)
    if edi_validity == False:
        print("EDI Validation Failed .......... ")
        list_text.append("EDI Validation Failed ..........")
        list_message.append("No Further Prior Authorization ......")
        flag = True
        response = {
        "message": "EDI Validation Failure",
        "data": {},
        "status":"fail"}
        return jsonify(response)
    else:
        print("EDI Validity = ", edi_validity)
        list_text.append("EDI Validation Done")
        list_message.append("Proceeding after EDI Validation .....")
    #json_segments = edi_to_json(edi_content)
    if flag == False:
        #edi_file_path = claim_values["output_edi"]
        json_output_path = claim_values["output_extracted_json"]
        #parsed = parse_edi_file(edi_file_path, json_output_path) 
        parsed = parse_edi_file(edi_content, json_output_path)
        extracted_json = extract_edi_fields(parsed)
        if not list(extracted_json.keys()):
            response = {
                    "message": "Fail due to No Extraction",
                    "data": {},
                    "status":"fail"}
            return jsonify(response)
        list_fields_2 = list(extracted_json.keys())
        print("List Match are ",list_fields_1)
        print("List Match are ",list_fields_2)
        valid_extraction = (all(x in list_fields_2 for x in list_fields_1))
        print("All Fields Extraction Validation = ",valid_extraction)
        if valid_extraction==False:
            print("Extraction Validation Failed .......... ")
            list_text.append("Extraction Validation Failed ..........")
            list_message.append("No Further Prior Authorization ......")
            flag = True
            response = {
                    "message": "Fail due to Invalid or Incomplete Extraction",
                    "data": {"member":{}, "provider":{}},
                    "status":"fail"}
            return jsonify(response)
        else:
            print("Extraction Validity = ", valid_extraction)
            list_text.append("Extraction Validation Done")
            list_message.append("Proceeding after Extraction Validation .....")
        if flag == False:
            x1 = (bool(extracted_json["provider"]))
            x2 = (bool(extracted_json["member"]))
            print("Keys in extracted_json = ", (list(extracted_json.keys())))
            if x1 == False or x2 == False:
                print("Provider or Member are not Extracted")
                flag = True
                response = {
                    "message": "Fail due to Member or Provider details not extracted",
                    "data": {"member":extracted_json["member"], "provider":extracted_json["provider"]},
                    "status":"fail"}
                return jsonify(response)
            else:
                provider_features = extract_provider_details(extracted_json)
                member_features = extract_member_details(extracted_json)
                print(provider_features)
                print(member_features)
                providers_db = claim_values["providers_db"]
                members_db = claim_values["members_db"]
                valid_provider = validate_provider_api(provider_features, providers_db)
                print(valid_provider)
                if(valid_provider[1] == "False"):
                    print("Authentication not approved because of Provider Validation Fail")
                    list_text.append("Authentication not approved because of Provider Validation Fail")
                    list_message.append("No Further Prior Authorization ......")
                    flag = True
                    response = {
                        "message": "Provider Validation Failed",
                        "data": {"member":member_features, "provider":valid_provider[0]},
                        "status":"fail"}
                    return jsonify(response)
                else:
                    list_text.append(str(provider_features))
                    list_message.append("Proceeding after Provider Validation .....")
                valid_member = validate_member_api(member_features, members_db)
                print(valid_member)
                if(valid_member[1] == "False"):
                    print("Authentication not approved because of Member Validation Fail")
                    list_text.append("Authentication not approved because of Member Validation Fail")
                    list_message.append("No Further Prior Authorization ......")
                    flag = True
                    response = {
                        "message": "Member Validation Failed",
                        "data": {"member":valid_member[0], "provider":provider_features},
                        "status":"fail"}
                    return jsonify(response)
                else:
                    s = str(member_features)
                    s = s.replace("\\","")
                    list_text.append(s)
                    list_message.append("Proceeding after Member Validation .....")
                if flag == False:
                    eligibility_features = extracted_json["eligibility"]
                    valid = validate_eligibility(eligibility_features)
                    print("Validation for Eligibility = ",valid)
                    if valid=="False":
                        list_text.append("Authentication not approved because of Eligibility Fail")
                        list_message.append("No Further Prior Authorization ......")
                        response = {
                            "message": "Eligibity Validation Failed",
                            "data": {"member":valid_member[0], "provider":valid_provider[0]},
                            "status":"fail"}
                        return jsonify(response)
                    else:
                        list_text.append("Eligibility Validation Done")
                        list_message.append("Proceeding After Eligibility Validation .....")
                    auth_basics = extracted_json["basic_auth"]
                    valid = validate_auth(auth_basics)
                    if valid=="False":
                        list_text.append("Authentication not approved because of Basic Prior Auth doesn't match")
                        list_message.append("No Further Prior Authorization ......")
                        response = {
                            "message": "Basic Auth Validation Failed",
                            "data": {"member":valid_member[0], "provider":valid_provider[0]},
                            "status":"fail"}
                        return jsonify(response)
                    else:
                        list_text.append("Basic Prior Auth Match Done")
                        list_message.append("Closing the Loop post Basic Prior Auth Validation .....")
                    print("Validation for Authentication Basics = ",valid)
        
    response = {
            "message": "All Validation Passed",
            "data": {"member":valid_member[0], "provider":valid_provider[0]},
            "status":"pass"}
    end_time = time.time()
    print(f"Execution Time: {end_time - start_time:.2f} seconds for Complete Workflow Processing ")
    return jsonify(response)
    
#authentication_flow()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5007, debug=True)
