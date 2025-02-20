#!/usr/bin/env python
# coding: utf-8

# In[1]:


import os, json
from flask import Flask, request, jsonify
from azure.storage.blob import BlobServiceClient

app = Flask(__name__)

def validate_edi_278(content):
    """
    if not os.path.exists(edi_file_path):
        print(f"Error: File '{edi_file_path}' does not exist.")
        return False
    try:
        with open(edi_file_path, "r") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return False
    """

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

    print(transaction_count, expected_count)
    #if transaction_count != expected_count:
       #print("Error: Transaction segment count mismatch.")
     #   return False
    if not any(seg.startswith("GE") for seg in segments):
        print("Error: Missing GE segment.")
        return False
    if not segments[-1].startswith("IEA"):
        print("Error: Missing IEA segment.")
        return False

    return True

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
    
@app.route('/validate', methods=['GET'])
def validate_edi_api():
    #file_path = "../edi_files/edi_278.txt"
    #if not os.path.exists(file_path):
        #return jsonify({"error": f"File '{file_path}' does not exist."}), 404
    edi_data = read_edi_from_blob()
    is_valid = validate_edi_278(edi_data)
    message = f"EDI file Validity: {is_valid}"
    return jsonify({"message": message})

app_validate = app
#print(validate_edi_api())

if __name__ == '__main__':
    app_validate.run(host='0.0.0.0', port=5001, debug=True)
    app_validate.run(debug=True)


# In[ ]:




