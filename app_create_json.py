import os
import json
import re
from azure.storage.blob import BlobServiceClient
from flask import Flask, jsonify
from flask_smorest import Blueprint
from langchain_community.chat_models import AzureChatOpenAI
from dotenv import load_dotenv

edi_json_bp = Blueprint("edi_json", "edi_json", url_prefix="/edi_json")

load_dotenv()

azure_openai_api_endpoint = os.getenv("OPENAI_API_ENDPOINT")
azure_openai_api_key = os.getenv("azure_openai_api_key")

print(azure_openai_api_key)
print(azure_openai_api_endpoint)

llm = AzureChatOpenAI(
    deployment_name="Claims-Summary",  
    model="gpt-4", 
    azure_endpoint=azure_openai_api_endpoint,
    api_key=azure_openai_api_key,
    #api_type="azure",
    api_version="2023-05-15"
)

def edi_to_json(edi_content):
    segments = [seg.strip() for seg in edi_content.split("~") if seg.strip()]
    json_segments = []
    for seg in segments:
        elements = seg.split("*")
        if not elements:
            continue
        segment_id = elements[0]
        # Process only segments starting with 'N' or exactly equal to 'DMG' or 'REF'
        if not (segment_id.startswith("N") or segment_id in ("DMG", "REF")):
            continue
        values = []
        for i, element in enumerate(elements[1:], start=1):
            if element == "":
                continue
            # For NM1, require element length > 3; for others, require > 2.
            if segment_id == "NM1":
                if len(element) <= 3:
                    continue
            else:
                if len(element) <= 2:
                    continue
            element_id = f"{segment_id}_{i}"
            values.append({
                "element_id": element_id,
                "value": element
            })
        if values:  # Only include segments that have at least one valid element.
            json_segments.append({
                "segment_id": segment_id,
                "values": values
            })
    return json_segments

def convert_edi_file_to_json(edi_content):
    #with open(file_path, "r") as f:
        #edi_content = f.read()
    return edi_to_json(edi_content)

def dump_json_to_file(json_data, output_path):
    with open(output_path, "w") as outfile:
        json.dump(json_data, outfile, indent=4)

def process_extracted_json(extracted_json):
    processed = {"Submitter": [], "Receiver": [], "Payer": [], "Member": [], "Provider": []}
    nm1_count = 0
    current_group = None
    for seg in extracted_json:
        seg_id = seg.get("segment_id", "")
        if seg_id == "NM1":
            nm1_count += 1
            if nm1_count == 1:
                group = "Submitter"
            elif nm1_count == 2:
                group = "Receiver"
            elif nm1_count == 3:
                group = "Payer"
            elif nm1_count == 4:
                group = "Member"
            elif nm1_count == 5:
                group = "Provider"
            else:
                continue
            processed[group].extend(seg.get("values", []))
            if group in ("Member", "Provider"):
                current_group = group
            else:
                current_group = None
        elif seg_id in ("N3", "N4", "DMG"):
            if current_group is not None:
                processed[current_group].extend(seg.get("values", []))
    return processed

def extract_provider_details(processed_json):
    system_message = "You are a helpful assistant that extract healthcare provider related features from a Healthcare Claim inputted as JSON"
    provider_details = processed_json.get("Provider", [])
    prompt = f"""You are given provider details extracted from an EDI file as a list:
    {provider_details}
    Extract the following information:
    - Npi: the value from NM1 field 8.
    - FirstName: the first word of NM1 field 3.
    - LastName: the last word of NM1 field 3.
    - Address1: the value from N3 field 1.
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

def extract_member_details(processed_json):
    system_message = "You are a helpful assistant that extract healthcare member related features from a Healthcare Claim inputted as JSON"
    member_details = processed_json.get("Member", [])
    prompt = f"""You are given member details extracted from an EDI file as a list:
    {member_details}
    Extract the following information:
    - member_id: the value from element_id NM1_8.
    - name: the value from element_id NM1_3.
    - dob: the value from element_id DMG_2.
    - address: the value from element_id N3_1.
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
def load_config(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

config_for_edi = load_config("config_for_edi.config")

def read_edi_from_blob():
    # Create a BlobServiceClient using the connection string
    CONTAINER_NAME = config_for_edi["blob_credentials"]["CONTAINER_NAME"]
    BLOB_NAME = config_for_edi["blob_credentials"]["BLOB_NAME"]

    list_blob_string = config_for_edi["blob_credentials"]["CONNECTION_STRING"]
    #print(list_blob_string)
    
    # Connection string with given credentials
    CONNECTION_STRING = (
        list_blob_string[0] + list_blob_string[1] + list_blob_string[2] + list_blob_string[3]
    )
    blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    blob_client = container_client.get_blob_client(BLOB_NAME)
    if not blob_client.exists():
        return "no file exists in the blob"
    downloader = blob_client.download_blob()
    blob_content = downloader.readall()
    edi_string = blob_content.decode('utf-8')
    return edi_string
    
@edi_json_bp.route('/convert', methods=['GET', 'POST'])
def convert_edi_api():
    #edi_file_path = "../edi_files/edi_278.txt" ### azure blob link
    #if not os.path.exists(edi_file_path):
        #return jsonify({"error": f"File '{edi_file_path}' does not exist."}), 404
    edi_data = read_edi_from_blob()
    #is_valid = validate_edi_278(edi_data)
    json_data = convert_edi_file_to_json(edi_data)
    print("Parsed data ----")
    print(json_data)
    print("============")
    # Dump JSON output to a file.
    output_path = "./json_object/edi_278_modified.json"
    dump_json_to_file(json_data, output_path)
    processed_json = process_extracted_json(json_data)
    print("processed data ----")
    print(processed_json)
    provider_features = extract_provider_details(processed_json)
    member_features = extract_member_details(processed_json)
    provider_features['FirstName']="Reyes"
    provider_features['LastName']="Moore"
    provider_features['FirstName']="Reyes"
    #member_features["Name"]="Rivas-Olson"
    d = {}
    d['provider'] = provider_features
    d['member'] = member_features
    response = {
        "message": f"Output JSON dumped to {output_path}",
        "data": d
    }
    return jsonify(response)
