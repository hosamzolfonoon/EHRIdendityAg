import streamlit as st
import torch
from transformers import AutoTokenizer, AutoModelForTokenClassification, AutoConfig
from peft import PeftModel, PeftConfig
import logging
import mysql.connector
import pandas as pd
import time
import streamlit.components.v1 as components
from typing import Optional
import logging
import warnings


########################################
####     Logging Configuration      ####
########################################
logging.basicConfig(
    level=logging.DEBUG,
    filename="error.log",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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

last_row_conversation = f"""
SELECT email, start_time, text_client, text_response
FROM temp_results_speechtextfast
WHERE text_response IS NOT NULL
  AND text_client IS NOT NULL
  AND TRIM(text_client) != ''
ORDER BY audio_saved_time DESC
LIMIT 1;
"""

insert_query_identity = """
INSERT IGNORE INTO ehr (
    email, start_time, full_name, address, postal_code,
    mobile_number, email_address, birth_day
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
"""

update_query = """
UPDATE ehr
SET full_name = %s,
    birth_day = %s,
    mobile_number = %s,
    address = %s,
    postal_code = %s,
    email_address = %s
WHERE email = %s AND start_time = %s;
"""

########################################
####          Functions             ####
########################################

def get_last_conversation_pair() -> Optional[list]:
    """
    Retrieves the most recent user and system message pair from the database as a list.
    
    Returns:
        List of [email, start_time, text_client, text_response] if found,
        else None.
    """
    try:
        conn = mysql.connector.connect(**db_config_speechtextst)
        cursor = conn.cursor()
        cursor.execute(last_row_conversation)
        result = cursor.fetchone()

        return list(result) if result else None

    except mysql.connector.Error as err:
        logging.error(f"MySQL error while fetching last conversation pair: {err}")
        return None

    finally:
        try:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
        except NameError:
            pass

def InsertToEHR(data_identity: tuple) -> bool:
    """
    Inserts a row into the `ehr` table using provided data.

    Parameters:
    - data_row (tuple): A tuple of values matching the INSERT query.

    Returns:
    - True if successful, False if an error occurred
    """
    try:
        connection = mysql.connector.connect(**db_config_speechtextst, autocommit=True)
        cursor = connection.cursor()
        cursor.execute(insert_query_identity, data_identity)
        logging.info("✅ Data inserted into EHR successfully.")
        return True

    except mysql.connector.Error as db_err:
        logging.exception("❌ MySQL insert error")
        return False

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()

def confirm_identity_ehr(data_identity_confirmed: tuple) -> bool:
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
        cursor.execute(update_query, data_identity_confirmed)
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

@st.cache_resource

#########################################
###              MAIN APP             ###
#########################################

def main():
    st.title("🔍 Personal Information Extractor")

    last_conversation = get_last_conversation_pair()
    logging.info(f'================= {last_conversation}')
    if not last_conversation:
        st.info("📭 No messages yet — waiting for FastAPI to insert data...")
    else:
        input_text = ' '.join(last_conversation[2:])
        model, tokenizer, device = load_model()
        result = infer_entities(input_text, model, tokenizer, device)

        st.success("✅ Inference complete!")

        # === Group tokens by entity types ===
        entity_types = ['per', 'tim', 'geo', 'mobile', 'email', 'street', '', 'post', '', 'email', '']
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

        # === Construct Form-Like Output ===
        full_name = " ".join(entities['per'][:2]) if len(entities['per']) >= 2 else '' # " ".join(entities['per'])
        address = " ".join(entities['street'][:2]) if len(entities['street']) >= 2 else ''
        city = " ".join(entities['geo']) if entities['geo'] else ""
        postal_code = " ".join(entities['post']) if entities['post'] else ""
        mobile_number = entities['mobile'][0] if entities['mobile'] else ""
        email_address = entities['email'][0] if entities['email'] else ""
        birth_day = " ".join(entities['tim'][:2]) if len(entities['street']) >= 2 else ''
        address = ', '.join(part for part in [address, city] if part)

        data_identity = (
            last_conversation[0],
            last_conversation[1],
            full_name,
            birth_day,
            mobile_number,
            address,
            postal_code,
            email_address
        )
        InsertToEHR(data_identity)


main()
