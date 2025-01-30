import os
import json

import pandas as pd
from openai import OpenAI
from anthropic import Anthropic

from db_utils import minio_utils
import invoice_utils as iu

# we need to ammend the llm extraction to inlude line items request.
def llm_key_extraction(input_text: str, model: str = 'gpt-4o') -> dict:
    # gpt-4o, gpt-4o-mini, gpt-3.5-turbo, claude-3-5-sonnet-20240620, claude-3-opus-20240229, claude-3-haiku-20240307
    # 
    """
    Extracts specific key fields from the given input text using a language model.

    Args:
        input_text (str): The text from which to extract the key fields.

    Returns:
        dict: A dictionary containing the extracted key fields in snake case as keys and their corresponding values as strings.
              The keys are:
              - vendor_invoice_id: The invoice number or document number or tax invoice number.
              - purchase_order_number: Your reference number or purchase order number or external order number.
              - vendor_tax_id: The vendor VAT or tax reference number.
              - vendor_registration_number: The vendor/company registration number.
              - invoice_date: The issue date as a date format.
              - total_amount: The total amount.
              - net_amount: The net amount.
              - tax_amount: The VAT or tax amount.
              - vendor_address: The address of the vendor (excluding city of Cape Town).
              - bank_name: The name of the bank.
              - bank_branch_code: The bank branch code.
              - bank_account_number: The bank account number.
              - sort_code: The bank sort code.
              - vendor_name: The company name or vendor name.
              - line_items: The line items of the invoice

              If the extraction fails, an empty dictionary is returned.

    Raises:
        Exception: If the JSON object creation fails.

    Note:
        The language model used is GPT-4o.
    """

    system_prompt = """
        You are a helpful assistant for the City of Cape Town with expert knowledge of the layout of invoice documents.
        Do not confuse City of Cape Town for the vendor informations. 
        Your task is to extract only the key fields specified by the user, from the invoice text, and only output these as a valid JSON object. 
        Return an empty string if the field is not present.
    """

    user_prompt =  f"""
    Question:
    Extract the following information as a JSON object with keys in snake case and extracted values as strings for an invoice text document:
        - Invoice number or document number or tax invoice number (vendor_invoice_id): [extracted value]
        - Your reference number or purchase order number or external order number (a 10 digit code that starts with a 450) (purchase_order_number): [extracted value]
        - Vendor VAT or tax reference number (a 10 digit code) (vendor_tax_id): [extracted value]
        - vendor/company registration number (vendor_registration_number): [extracted value]
        - Issue date (invoice_date) in formats MM/DD/YYYY or DD/MM/YYYY: [extracted value]
        - Total amount in currency format (total_amount): [extracted value]
        - Net amount in currency format (net_amount): [extracted value]
        - VAT or tax amount in currency format (tax_amount): [extracted value]
        - Vendor address (excluding city of Cape Town) (vendor_address): [extracted value]
        - Bank details (bank_details): [{{
            Bank name (e.g., ABSA, FNB, Standard Bank, Nedbank, Capitec) (bank_name): [extracted value],
            Bank branch code (6 digits) (bank_branch_code): [extracted value],
            Bank account number (8-12 digits) (bank_account_number): [extracted value]
            }}]
        - Vendor or company name (excluding city of Cape Town) (vendor_name): [extracted value]
        - Line items (line_items): [{{"item": "description", "quantity": "qty", "price": "price", "amount": "amount"}}]
    
    from the following invoice text: {input_text}
    """

    try:
        if model.startswith('gpt'):
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            client = OpenAI()
            #client = Anthropic() claude-3-5-sonnet-20240620
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=messages
            )

            response = response.choices[0].message.content

        elif model.startswith('claude'):
            messages = [
                {"role": "user", "content": user_prompt}
            ]
            client = Anthropic()
            response = client.messages.create(
                model=model,
                max_tokens=5000,
                temperature=0,
                messages=messages,
                system=system_prompt
            )
            response = response.content[0].text
        
        response = iu.find_brackets(response)
        response = json.loads(response)
        print("Text converted to JSON object")
        return response
    
    except Exception as e:
        print(f'Failed to create JSON object {e}')

df = pd.read_parquet('../tests/pdf.parquet')

data = []
for row in df[1:].itertuples():
    llm_raw = llm_key_extraction(row.extract)
    llm_clean = iu.val_clean(llm_raw)
    llm_clean['object_id'] = row.object_id
    llm_clean['invoice_quality'] = 'pdf'
    data.append(llm_clean)

data = pd.DataFrame(data)

data.to_parquet('../tests/line_item_test_gpt4o.parquet')