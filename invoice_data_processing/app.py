import json
import os
import random
import sys
import streamlit as st
import fitz  # PyMuPDF
import openai
import pandas as pd
from db_utils import minio_utils
import invoice_utils as iu

openai.api_key = st.secrets["OPENAI_API_KEY"]

BUCKET_APPROVED="rvanwyk18.invoice-extract-approved"
BUCKET_RAW="rvanwyk18.invoice-extract-raw"
BUCKET_COMARED="rvanwyk18.invoice-extract-compared"


# Directory containing the PDF files
files = os.listdir('invoice_data_processing/pdfs')
random.shuffle(files)

# Initialize the current file index in session state if it doesn't exist
if 'current_file_index' not in st.session_state:
    st.session_state.current_file_index = 0

def pdf_preview(file_path, zoom=8):  # Adjust zoom level as needed (e.g., 2 for higher resolution)
    with fitz.open(file_path) as pdf:
        for page_num in range(len(pdf)):
            page = pdf.load_page(page_num)
            # Apply zoom to increase resolution (2x = 200% size)
            mat = fitz.Matrix(zoom, zoom)
            img = page.get_pixmap(matrix=mat)
            st.image(img.tobytes(), caption=f'Page {page_num + 1}', width=800)

def process_file(file_path):
    # Extract data only once per file
    if 'auto_fill_data' not in st.session_state or st.session_state.get("current_file_path") != file_path:
        text, file_type = iu.text_extraction(file_path)
        llm_raw = iu.llm_key_extraction(text)
        llm_clean = iu.val_clean(llm_raw)
        st.session_state.file_type = file_type
        st.session_state.auto_fill_data = llm_clean  # Save data to session state
        st.session_state.current_file_path = file_path
        st.session_state.bank_details = llm_clean.get('bank_details', [])
        st.session_state.line_items = llm_clean.get('line_items', [])

def main():
    st.title("PDF Preview and Auto-Fill Approval")

    # Check if there are files to process
    if st.session_state.current_file_index < len(files):
        current_file = files[st.session_state.current_file_index]
        file_path = os.path.join('invoice_data_processing/pdfs', current_file)

        # Display the current file name
        st.write(f"Processing file: {current_file}")

        # Get the auto-fill data from session state
        process_file(file_path)

        if st.session_state.file_type != 'pdf':
            st.warning("Image file. Skipping")
            os.remove(file_path)
            st.session_state.current_file_index += 1
            st.experimental_rerun()  # Rerun to load the next file with cleared data 

        pdf_preview(file_path)

        auto_fill_data = st.session_state.auto_fill_data
        approvals = {}

        # Display JSON fields in the sidebar
        st.sidebar.title("Auto-Fill Values")
        approvals["purchase_order_number"] = st.sidebar.text_input("purchase_order_number:", value=auto_fill_data.get('purchase_order_number', ''))
        approvals["invoice_date"] = st.sidebar.text_input("invoice_date:", value=auto_fill_data.get('invoice_date', ''))
        approvals["vendor_name"] = st.sidebar.text_input("vendor_name:", value=auto_fill_data.get('vendor_name', ''))
        approvals["vendor_invoice_id"] = st.sidebar.text_input("vendor_invoice_id:", value=auto_fill_data.get('vendor_invoice_id', ''))
        approvals["vendor_tax_id"] = st.sidebar.text_input("vendor_tax_id:", value=auto_fill_data.get('vendor_tax_id', ''))
        approvals["vendor_registration_number"] = st.sidebar.text_input("vendor_registration_number:", value=auto_fill_data.get('vendor_registration_number', ''))
        approvals["vendor_address"] = st.sidebar.text_input("vendor_address:", value=auto_fill_data.get('vendor_address', ''))
        approvals["net_amount"] = st.sidebar.text_input("net_amount:", value=str(auto_fill_data.get('net_amount', '')))
        approvals["total_amount"] = st.sidebar.text_input("total_amount:", value=str(auto_fill_data.get('total_amount', '')))
        approvals["tax_amount"] = st.sidebar.text_input("tax_amount:", value=str(auto_fill_data.get('tax_amount', '')))

        # Handle bank details with dynamic add/remove functionality
        st.sidebar.subheader("Bank Details")
        for idx, bank in enumerate(st.session_state.bank_details):
            bank_info = {}
            bank_info['bank_name'] = st.sidebar.text_input(f"bank_name[{idx}]:", value=bank.get('bank_name', ''))
            bank_info['bank_branch_code'] = st.sidebar.text_input(f"bank_branch_code[{idx}]:", value=bank.get('bank_branch_code', ''))
            bank_info['bank_account_number'] = st.sidebar.text_input(f"bank_account_number[{idx}]:", value=bank.get('bank_account_number', ''))
            approvals.setdefault("bank_details", []).append(bank_info)
            
            # Remove button for each bank entry
            if st.sidebar.button(f"Remove Bank {idx}"):
                st.session_state.bank_details.pop(idx)
                st.experimental_rerun()  # Rerun to reflect changes immediately

        if st.sidebar.button("Add Bank"):
            st.session_state.bank_details.append({'bank_name': '', 'bank_branch_code': '', 'bank_account_number': ''})

        # Handle line items with dynamic add/remove functionality
        st.sidebar.subheader("Line Items")
        for idx, item in enumerate(st.session_state.line_items):
            item_info = {}
            item_info['item'] = st.sidebar.text_input(f"item[{idx}]:", value=item.get('item', ''))
            item_info['quantity'] = st.sidebar.text_input(f"quantity[{idx}]:", value=item.get('quantity', ''))
            item_info['price'] = st.sidebar.text_input(f"price[{idx}]:", value=str(item.get('price', '')))
            item_info['amount'] = st.sidebar.text_input(f"amount[{idx}]:", value=str(item.get('amount', '')))
            approvals.setdefault("line_items", []).append(item_info)

            # Remove button for each line item entry
            if st.sidebar.button(f"Remove Line Item {idx}"):
                st.session_state.line_items.pop(idx)
                st.experimental_rerun()  # Rerun to reflect changes immediately

        if st.sidebar.button("Add Line Item"):
            st.session_state.line_items.append({'item': '', 'quantity': '', 'price': '', 'amount': ''})

        # Submit button to save and move to the next file
        if st.sidebar.button("Submit"):
            # Perform additional processing as needed here
            # For example, saving approval data to a file or database

            approvals['net_amount'] = float(approvals['net_amount'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
            approvals['total_amount'] = float(approvals['total_amount'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
            approvals['tax_amount'] = float(approvals['tax_amount'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
            for item in approvals['line_items']:
                item['amount'] = float(item['amount'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
                item['price'] = float(item['price'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
            st.sidebar.write("Approval statuses:")
            # same for auto_fill_data line items
            for item in auto_fill_data['line_items']:
                item['amount'] = float(item['amount'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)
                item['price'] = float(item['price'].replace(',', '').replace('$', '').replace(' ', '').replace('R', '') or 0)

            # we need to write to bucket
            approvals['file_type'] = st.session_state.file_type
            auto_fill_data['file_type'] = st.session_state.file_type

            # compare the approvals dict with the auto_fill_data dict use true or false
            compare = {}
            for approval_key in approvals.keys():
                if approval_key in auto_fill_data:
                    # Handle nested keys for lists like bank_details and line_items
                    if isinstance(approvals[approval_key], list):
                        compare[approval_key] = []  # Initialize list for this key in compare
                        for item_idx, item in enumerate(approvals[approval_key]):
                            compare[approval_key].append({})  # Initialize a new dictionary for each item
                            for item_key in item.keys():
                                # Check if the value matches with auto_fill_data
                                if approvals[approval_key][item_idx][item_key] == auto_fill_data[approval_key][item_idx][item_key]:
                                    compare[approval_key][item_idx][item_key] = True
                                else:
                                    compare[approval_key][item_idx][item_key] = False

                    # Non-list value comparison
                    elif approvals[approval_key] == auto_fill_data[approval_key]:
                        compare[approval_key] = True
                    else:
                        compare[approval_key] = False

            compare['file_type'] = st.session_state.file_type

            # Store them
            #write json files for each to ./json 
            with open(f'invoice_data_processing/jsons/{current_file}_aaprovals.json', 'w') as f:
                json.dump(approvals, f, indent=4)
            with open(f'invoice_data_processing/jsons/{current_file}_extracted.json', 'w') as f:
                json.dump(auto_fill_data, f, indent=4)
            with open(f'invoice_data_processing/jsons/{current_file}_compare.json', 'w') as f:
                json.dump(compare, f, indent=4)
            
            #approval_data.append(approvals_df.to_dict(orient='records'))
            #extracted_data.append(extracted_df.to_dict(orient='records'))
            #compared_data.append(compare_df.to_dict(orient='records'))
            
            #minio_utils.dataframe_to_minio(approvals_df, BUCKET_APPROVED, partition_cols=["shard_key"], data_versioning=False, file_format="parquet")
            #minio_utils.dataframe_to_minio(extracted_df, BUCKET_RAW, partition_cols=["shard_key"], data_versioning=False, file_format="parquet")
            #minio_utils.dataframe_to_minio(compare_df, BUCKET_COMARED, partition_cols=["shard_key"], data_versioning=False, file_format="parquet")

            print(f"Finished writing file {current_file}.")
            os.remove(file_path)

            # Move to the next file and trigger rerun
            st.session_state.current_file_index += 1
            st.experimental_rerun()  # Rerun to load the next file with cleared data     

    else:
        st.write("All files have been processed.")

if __name__ == "__main__":
    main()
