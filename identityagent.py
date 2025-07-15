from flask import Flask, request, jsonify
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, AutoConfig
from peft import PeftModel, PeftConfig
import logging
import mysql.connector
import pandas as pd
from typing import Optional
import warnings


########################################
####     Logging Configuration      ####
########################################
logging.basicConfig(
    level=logging.DEBUG,
    filename="error.log",
    format="%(asctime)s - %(levelname)s - %(message)s"
)


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
    full_name = CASE 
        WHEN full_name IS NULL 
             OR TRIM(full_name) = '' 
             OR TRIM(full_name) = "''" 
             OR LENGTH(full_name) - LENGTH(REPLACE(full_name, ' ', '')) < 1
        THEN %s 
        ELSE full_name 
    END,

    birth_day = CASE 
        WHEN birth_day IS NULL 
             OR TRIM(birth_day) = '' 
             OR TRIM(birth_day) = "''"
        THEN %s 
        ELSE birth_day 
    END,

    mobile_number = CASE 
        WHEN mobile_number IS NULL 
             OR TRIM(mobile_number) = '' 
             OR TRIM(mobile_number) = "''"
        THEN %s 
        ELSE mobile_number 
    END,

    address = CASE 
        WHEN address IS NULL 
             OR TRIM(address) = '' 
             OR TRIM(address) = "''" 
             OR LENGTH(address) - LENGTH(REPLACE(address, ' ', '')) < 2
        THEN %s 
        ELSE address 
    END,

    postal_code = CASE 
        WHEN postal_code IS NULL 
             OR TRIM(postal_code) = '' 
             OR TRIM(postal_code) = "''"
        THEN %s 
        ELSE postal_code 
    END,

    email_address = CASE 
        WHEN email_address IS NULL 
             OR TRIM(email_address) = '' 
             OR TRIM(email_address) = "''"
        THEN %s 
        ELSE email_address 
    END

WHERE email = %s AND start_time = %s;
"""
query_update_temp = """
UPDATE temp_ehr
SET
    full_name = CASE 
        WHEN full_name IS NULL 
             OR TRIM(full_name) = '' 
             OR TRIM(full_name) = "''" 
             OR LENGTH(full_name) - LENGTH(REPLACE(full_name, ' ', '')) < 1
        THEN %s 
        ELSE full_name 
    END,

    birth_day = CASE 
        WHEN birth_day IS NULL 
             OR TRIM(birth_day) = '' 
             OR TRIM(birth_day) = "''"
        THEN %s 
        ELSE birth_day 
    END,

    mobile_number = CASE 
        WHEN mobile_number IS NULL 
             OR TRIM(mobile_number) = '' 
             OR TRIM(mobile_number) = "''"
        THEN %s 
        ELSE mobile_number 
    END,

    address = CASE 
        WHEN address IS NULL 
             OR TRIM(address) = '' 
             OR TRIM(address) = "''" 
             OR LENGTH(address) - LENGTH(REPLACE(address, ' ', '')) < 2
        THEN %s 
        ELSE address 
    END,

    postal_code = CASE 
        WHEN postal_code IS NULL 
             OR TRIM(postal_code) = '' 
             OR TRIM(postal_code) = "''"
        THEN %s 
        ELSE postal_code 
    END,

    email_address = CASE 
        WHEN email_address IS NULL 
             OR TRIM(email_address) = '' 
             OR TRIM(email_address) = "''"
        THEN %s 
        ELSE email_address 
    END

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


def update_identity_ehr(data_identity_confirmed: tuple) -> bool:
    """
    Updates the EHR table with confirmed identity fields based on email and start_time.

    Parameters:
    - data_identity_confirmed (tuple): Should follow this order:
        (full_name, birth_day, mobile_number, address, postal_code, email_address, email, start_time)

    Returns:
    - bool: True if update is successful, False otherwise
    """
    try:
        connection = mysql.connector.connect(**db_config_speechtextst, autocommit=True)
        cursor = connection.cursor()
        cursor.execute(query_update, data_identity_confirmed)
        cursor.execute(query_update_temp, data_identity_confirmed)
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

########################################
####     Main Configuration      ####
########################################
adapter_path = "synthetic_identification_bio_20250710163055"
label_list = [
    'O',
    'B-per', 'I-per',
    'B-tim', 'I-tim',
    'B-geo', 'I-geo',
    'B-mobile',
    'B-email', 'I-email',
    'B-street', 'I-street',
    'B-post'
    ]

#########################################
###              MAIN APP             ###
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
        entity_types = ['per', 'tim', 'geo', 'mobile', 'email', 'street', 'post']
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
        full_name = " ".join(entities['per'][:2]) if len(entities['per']) >= 2 else ''
        address = " ".join(entities['street'][:2]) if len(entities['street']) >= 2 else ''
        city = " ".join(entities['geo']) if entities['geo'] else ''
        postal_code = " ".join(entities['post']) if entities['post'] else ''
        mobile_number = entities['mobile'][0] if entities['mobile'] else ''
        email_address = entities['email'][0] if entities['email'] else ''
        birth_day = " ".join(entities['tim'][:2]) if len(entities['tim']) >= 2 else ''
        address = ', '.join(part for part in [address, city] if part)

        data_identity = (
            email,
            start_time,
            full_name,
            birth_day,
            mobile_number,
            address,
            postal_code,
            email_address
        )
        email_start_time = (email, start_time)

        # Check if the row exists before inserting or updating
        ehr_exist, temp_ehr_exist = check_row_exists(email_start_time)
        if (ehr_exist and temp_ehr_exist):
            update_identity_ehr(data_identity)
            app.logger.info(f"✅ Identity info updated for {email_start_time} == {data_identity}")
        else:
            insert_initiate(email_start_time)
            update_identity_ehr(data_identity)
            app.logger.info(f"✅ Identity info inserted and updated for {email_start_time} == {data_identity}")

        return jsonify({"status": "success", "message": "Identity information processed successfully"}), 200

    except Exception as e:
        app.logger.exception("❌ Error while processing identity upload")
        return jsonify({"status": "error", "detail": str(e)}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0")