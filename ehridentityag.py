from flask import Flask, request, jsonify
import logging
import mysql.connector
from peft import PeftModel, PeftConfig
import requests
import re
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, AutoConfig
import warnings


########################################
####     Logging Configuration      ####
########################################
logging.basicConfig(level=logging.INFO)

# Disable all warnings
warnings.filterwarnings("ignore")
########################################
### MySQL Database Configuration ###
########################################

db_config_speechtextst = {
    'host': 'speechtextfast-mysql',
    'user': 'speechtextfast',
    'password': 'SpeechTextFast1234',
    'database': 'speechtextfast',
    'port': 3306
}

########################################
###            SQL QUERY             ###
########################################

query_update = """
UPDATE ehr
SET
    full_name = %s,
    birth_day = %s,
    mobile_number = %s,
    address = %s,
    postal_code = %s
WHERE email = %s AND start_time = %s;
"""
query_update_temp = """
UPDATE temp_ehr
SET
    full_name = %s,
    birth_day = %s,
    mobile_number = %s,
    address = %s,
    postal_code = %s
WHERE email = %s AND start_time = %s;
"""

query_check_row_exists_ehr = """
SELECT 1 FROM ehr
WHERE email = %s AND start_time = %s
LIMIT 1;
"""

query_check_row_exists_temp_ehr = """
SELECT 1 FROM temp_ehr
WHERE email = %s AND start_time = %s
LIMIT 1;
"""

query_insert_initiate = """
INSERT INTO ehr (
    email,
    start_time
) VALUES (%s, %s);
"""

query_insert_initiate_temp = """
INSERT INTO temp_ehr (
    email,
    start_time
) VALUES (%s, %s);
"""

########################################
####          Functions             ####
########################################
def insert_initiate(email_start_time):
    try:
        connection = mysql.connector.connect(**db_config_speechtextst, autocommit=True)
        cursor = connection.cursor()
        cursor.execute(query_insert_initiate, email_start_time)
        cursor.execute(query_insert_initiate_temp, email_start_time)
    except mysql.connector.Error as db_err:
        logging.error(f"❌ MySQL InsertToMySQL: {str(db_err)}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()

def check_row_exists(email_start_time):
    try:
        connection = mysql.connector.connect(**db_config_speechtextst)
        cursor = connection.cursor()

        # Check in ehr
        cursor.execute(query_check_row_exists_ehr, email_start_time)
        ehr_exists = cursor.fetchone() is not None

        # Check in temp_ehr
        cursor.execute(query_check_row_exists_temp_ehr, email_start_time)
        temp_exists = cursor.fetchone() is not None

        return ehr_exists, temp_exists

    except Exception as e:
        logging.exception("❌ Error in check_row_exists")
        return False, False

    finally:
        if 'cursor' in locals(): cursor.close()
        if 'connection' in locals() and connection.is_connected(): connection.close()


def update_identity_ehr(data_identity_dic_: dict) -> bool:
    """
    Updates the EHR table with confirmed identity fields based on email and start_time.

    Parameters:
    - data_identity_confirmed (tuple): Should follow this order:
        (full_name, birth_day, mobile_number, address, postal_code, email, start_time)

    Returns:
    - bool: True if update is successful, False otherwise
    """
    try:
        connection = mysql.connector.connect(**db_config_speechtextst, autocommit=True)
        cursor = connection.cursor()
        # Fetch current row from DB
        cursor.execute("SELECT full_name, birth_day, mobile_number, address, postal_code FROM temp_ehr WHERE email = %s AND start_time = %s;", (input_data['email'], input_data['start_time']))
        existing_row = cursor.fetchone()
        if existing_row:
            # Prepare new values with fallback
            updated_values = [
                validate_field(data_identity_dic_['full_name']) or existing_row[0],
                validate_field(data_identity_dic_['birth_day']) or existing_row[1],
                validate_field(data_identity_dic_['mobile_number']) or existing_row[2],
                validate_field(data_identity_dic_['address']) or existing_row[3],
                validate_field(data_identity_dic_['postal_code']) or existing_row[4],
                data_identity_dic_['email'],
                data_identity_dic_['start_time'],
            ]
        cursor.execute(query_update, updated_values)
        cursor.execute(query_update_temp, updated_values)
        logging.info("✅ Confirmed identity data updated in EHR successfully.")
        return True

    except mysql.connector.Error as db_err:
        logging.exception("❌ MySQL update error")
        return False

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()

def load_model():
    peft_config = PeftConfig.from_pretrained(adapter_path)
    base_config = AutoConfig.from_pretrained(peft_config.base_model_name_or_path, num_labels=len(label_list))
    base_model = AutoModelForTokenClassification.from_pretrained(peft_config.base_model_name_or_path, config=base_config)
    model = PeftModel.from_pretrained(base_model, adapter_path)
    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    return model, tokenizer, device

def infer_entities(text, model, tokenizer, device):
    tokens = text.split()
    tokenized_input = tokenizer(tokens, return_tensors="pt", is_split_into_words=True, truncation=True, padding=True)
    word_ids = tokenized_input.word_ids()
    tokenized_input = {k: v.to(device) for k, v in tokenized_input.items()}
    
    model.eval()
    with torch.no_grad():
        outputs = model(**tokenized_input)
        predictions = torch.argmax(outputs.logits, dim=2)

    aligned_labels = []
    prev_word_idx = None
    for idx, word_idx in enumerate(word_ids):
        if word_idx is None or word_idx == prev_word_idx:
            continue
        label_id = predictions[0][idx].item()
        aligned_labels.append(label_list[label_id])
        prev_word_idx = word_idx

    return list(zip(tokens, aligned_labels))

def postcod_to_address(postal_code):
    postal_code = str(postal_code)
    try:
        response = requests.post("https://dataanalyst.pt/ehrptaddsqlag/", json={'postal_code': postal_code})
        response.raise_for_status()
        # Get predicted sentiment
        address = response.json().get('address', 'not_detected')
        logging.info(f"✅ Address agent response: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        logging.error(f"❌ Failed to send data to chronic agent: {e}")
    return address

def extract_valid_portugal_postal_code(postal_code: str) -> str | None:
    """
    Return the postal code if it matches the Portuguese format NNNN-NNN,
    otherwise return None.
    """
    pattern = r"^\d{4}-\d{3}$"
    return postal_code if re.match(pattern, postal_code) else None

def validate_field(value):
    return value if value and len(str(value)) >= 6 else None

########################################
####      Main Configuration        ####
########################################
adapter_path = "synthetic_identification_bio_20250723162236"
label_list = [
    'O',
    'B-per', 'I-per',
    'B-tim', 'I-tim',
    'B-geo', 'I-geo',
    'B-mobile',
    'B-post'
    ]

#########################################
###              Main Body           ###
#########################################
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/', methods=['POST'])
def upload():
    try:
        # Parse JSON from request
        received_message = request.json

        # Required fields
        required_fields = ['email', 'start_time', 'dialouge_post']
        missing_fields = [field for field in required_fields if field not in received_message]

        if missing_fields:
            app.logger.error(f"Invalid request format. Missing fields: {missing_fields}")
            return jsonify({"error": f"Missing fields: {missing_fields}"}), 400

        # Extract values
        email = received_message['email']
        start_time = received_message['start_time']
        dialouge_post = received_message['dialouge_post']

        # Combine prompt and transcription
        model, tokenizer, device = load_model()
        result = infer_entities(dialouge_post, model, tokenizer, device)
        app.logger.info(f"✅ contenet ========  {result}")

        # Handle empty result
        if not result:
            return jsonify({"status": "error", "message": "No entities found in the dialogue"}), 400

        # Group tokens by entity types
        entity_types = ['per', 'tim', 'geo', 'mobile', 'post']
        entities = {key: [] for key in entity_types}

        current_entity = []
        current_type = None

        for token, label in result:
            if label.startswith("B-"):
                if current_entity and current_type:
                    entities[current_type].append(" ".join(current_entity))
                current_type = label[2:]
                current_entity = [token]
            elif label.startswith("I-") and current_type == label[2:]:
                current_entity.append(token)
            else:
                if current_entity and current_type:
                    entities[current_type].append(" ".join(current_entity))
                current_entity = []
                current_type = None

        if current_entity and current_type:
            entities[current_type].append(" ".join(current_entity))

        # Construct output fields
        address = 'not_detected'
        full_name = " ".join(entities['per'][:2]) if len(entities['per']) >= 1 else ''
        birth_day = " ".join(entities['tim'][:2]) if len(entities['tim']) >= 1 else ''
        mobile_number = entities['mobile'][0] if entities['mobile'] else ''
        postal_code = " ".join(entities['post']) if entities['post'] else ''
        #postal_code = extract_valid_portugal_postal_code(postal_code)
        if postal_code:
            address = postcod_to_address(postal_code)
            
        app.logger.info(f"✅✅✅ address ========  {address}")

        data_identity_dic = {
            "full_name": full_name,
            "birth_day": birth_day,
            "mobile_number": mobile_number,
            "address": address,
            "postal_code": postal_code,
            "email": email,
            "start_time": start_time,
            }

        email_start_time = (email, start_time)

        # Check if the row exists before inserting or updating
        ehr_exist, temp_ehr_exist = check_row_exists(email_start_time)
        if (ehr_exist and temp_ehr_exist):
            update_identity_ehr(data_identity_dic)
            app.logger.info(f"✅ Identity info updated for {email_start_time} == {data_identity_dic.values}")
        else:
            insert_initiate(email_start_time)
            update_identity_ehr(data_identity_dic)
            app.logger.info(f"✅ Identity info inserted and updated for {email_start_time} == {data_identity_dic.values}")

        return jsonify({"status": "success", "message": "Identity information processed successfully"}), 200

    except Exception as e:
        app.logger.exception("❌ Error while processing identity upload")
        return jsonify({"status": "error", "detail": str(e)}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0")