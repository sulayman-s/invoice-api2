import json
import logging
import os
import re
import typing
from dateutil.parser import parse
import base64

import cv2
import fitz
import pdfplumber
import pytesseract
import numpy as np
from openai import OpenAI
import requests
from anthropic import Anthropic
from fuzzywuzzy import fuzz, process

# SS mod
# from db_utils import minio_utils
# from invoice_regex import patterns

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Users\rvanwyk18\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
else:
    pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# Retrieve API key from environment variable
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise EnvironmentError("OPENAI_API_KEY environment variable not set.")

if "PROXY_USERNAME" in os.environ and "PROXY_PASSWORD" in os.environ:
    # Set the Proxy
    for proxy_env_var in ["HTTPS_PROXY", "HTTP_PROXY"]:
        proxy_str = f"http://{os.environ['PROXY_USERNAME']}:{os.environ['PROXY_PASSWORD']}@internet.capetown.gov.za:8080"
        os.environ[proxy_env_var] = proxy_str
        os.environ[proxy_env_var.lower()] = proxy_str
else:
    logger.warning("Not setting proxy variables")


TEMPERATURE = 0
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# SS mod
import re

patterns = {
    "issue_date": re.compile(
        r"((?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4})|(?:\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{2,4})|(?:\d{2,4}[-/]\d{1,2}[-/]\d{1,2}))",
        re.IGNORECASE,
    ),
    "amount": re.compile(r"[a-zA-Z£$R,\s/]", re.IGNORECASE),
    "vendor_registration_number": re.compile(r"[\d/]"),
    "vendor_tax_id": re.compile(r"([0-9]+)"),
    "bank_branch_code": re.compile(r"(\d{6})"),
    "purchase_order_number": re.compile(r"(\d{10})"),
    "bank_account_number": re.compile(r"(\d{8,16})"),
}


# Functions
def parse_date_with_regex(date_string):
    if re.match(r"^\d{4}/\d{1,2}/\d{1,2}$", date_string):  # Matches yyyy/mm/dd
        return parse(date_string, yearfirst=True)
    elif re.match(
        r"^\d{1,2}/\d{1,2}/\d{4}$", date_string
    ):  # Matches dd/mm/yyyy or mm/dd/yyyy
        return parse(date_string, dayfirst=True)
    elif re.match(
        r"^\d{1,2}/\d{1,2}/\d{1,2}$", date_string
    ):  # Matches dd/mm/yyyy or mm/dd/yyyy
        return parse(date_string, dayfirst=True)
    else:
        # Default fallback
        return parse(date_string)


def clean_json_string(messy_string: str) -> str:
    """
    Cleans a JSON string by removing newline characters and extra spaces.

    Args:
        messy_string (str): The JSON string to be cleaned.

    Returns:
        str: The cleaned JSON string.

    """
    cleaned_string = messy_string.replace("\n", "").replace("    ", "")
    return cleaned_string


def find_brackets(string: str) -> str:
    """
    Find the content enclosed in curly brackets ('{}') in the given string.

    Args:
        string (str): The input string.

    Returns:
        str: The content enclosed in brackets.
    """
    opening_bracket_index: int = string.find("{")
    closing_bracket_index: int = string.rfind("}")

    string: str = string[opening_bracket_index : closing_bracket_index + 1]
    string = clean_json_string(string)

    return string


def pull_invoice_pdf(inv_name, bucket):
    """
    Pulls an invoice PDF from a specified bucket and saves it locally.

    Args:
        inv_name (str): The name of the invoice file in the bucket.
        bucket (str): The name of the bucket where the invoice file is located.

    Returns:
        str: The local path where the invoice PDF was saved.
    """

    save_path = inv_name.split("/")[-1]
    save_path = os.path.join(SCRIPT_DIR, "pdfs", save_path)
    minio_utils.minio_to_file(
        filename=save_path,
        minio_filename_override=inv_name,
        minio_bucket=bucket,
    )

    return save_path


def pdf_to_text(path):
    """
    Extracts text from a PDF file located at the specified path.

    Args:
        path (str): The path to the PDF file.

    Returns:
        str: The extracted text from the PDF file.
    """
    with pdfplumber.open(path) as pdf:
        pages = pdf.pages
        text = ""
        for page in pages:
            text += page.extract_text(layout=True)
    return text


def convert_pdf_to_images(pdf_path: str) -> typing.List[str]:
    """
    Convert a PDF to a sequence of images and save them in the output directory.
    Returns a list of image file paths.

    Args:
        pdf_path (str): The path to the PDF file.
        output_dir (str): The output directory to save the images.

    Returns:
        List[str]: A list of image file paths.
    """
    dpi: int = 800  # choose desired dpi here
    zoom: float = dpi / 72  # zoom factor, standard: 72 dpi
    magnify: fitz.Matrix = fitz.Matrix(zoom, zoom)
    img_name_list: typing.List[str] = []

    doc: fitz.Document = fitz.open(pdf_path)
    for idx, page in enumerate(doc):
        pix: fitz.Pixmap = page.get_pixmap(matrix=magnify)
        img_name: str = (
            f"{SCRIPT_DIR}/img/{os.path.splitext(os.path.basename(pdf_path))[0]}_page_{idx+1}.png"
        )
        pix.save(img_name)
        img_name_list.append(img_name)

    return img_name_list


def extract_text_from_image(pdf_path: str) -> str:
    """
    Extract text from an image using Tesseract OCR.
    Returns the extracted text.

    Args:
        image_path (str): The path to the image file.

    Returns:
        str: The extracted text from the image.
    """
    img_name_list = convert_pdf_to_images(pdf_path)
    text = ""
    for image_path in img_name_list:
        img: np.ndarray = cv2.imread(image_path)
        os.remove(image_path)
        img_gray: np.ndarray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_thresh: np.ndarray = cv2.threshold(
            img_gray, 127, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]

        custom_config: str = r"-l eng --oem 1 --psm 6"
        text += pytesseract.image_to_string(img_thresh, config=custom_config)

    return text.strip()


# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# AI OCR
def ai_ocr(pdf_path: str, model: str) -> str:
    """
    Uses OpenAI's GPT-3 API to extract text from an image.

    Args:
    """
    client = OpenAI()
    img_name_list = convert_pdf_to_images(pdf_path)
    text = ""
    if model.startswith("gpt"):
        for image_path in img_name_list:

            # Getting the base64 string
            base64_image = encode_image(image_path)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all text from this image",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
            )
            text += response.choices[0] + "\n"

        return text.strip()
    elif model.startswith("claude"):
        client = Anthropic()
        pdf_data = base64.standard_b64encode(pdf_path).decode("utf-8")
        message = client.beta.messages.create(
            model="claude-3-5-sonnet-20241022",
            betas=["pdfs-2024-09-25"],
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "extract all text from these images",
                        },
                    ],
                }
            ],
        )

        return message.content


def text_checks(text: str, val_set: dict) -> list:
    """
    A function that checks the presence of purchase order number and vendor name in the given text.

    Args:
        text (str): The text to be checked.
        val_set (dict): A dictionary containing 'purchase_order_number' and 'vendor_name' keys.

    Returns:
        list: A list of error codes based on the text checks.
    """
    po_no = val_set["purchase_order_number"]
    vendor_name = val_set["vendor_name"]
    err_code = []
    if po_no in text:
        logger.info("Text PO check passed!")
        err_code.append("PO_RAW_PASS")
    else:
        logger.error("Text PO check failed!")
        err_code.append("PO_RAW_FAIL")
    if vendor_name in text:
        logger.info("Text Vendor name check passed!")
        err_code.append("VENDOR_RAW_PASS")
    else:
        logger.error("Text Vendor name check failed!")
        err_code.append("VENDOR_RAW_FAIL")
    return err_code


def text_extraction(invoice_path: str) -> str:
    """
    Extracts text from the provided invoice_path by first attempting to extract text from a PDF using pdf_to_text,
    then falling back to extract text from an image using extract_text_from_image if the PDF extraction fails.

    Args:
        invoice_path (str): The path to the invoice file.

    Returns:
        str: The extracted text from the invoice.
    """
    file_type = "pdf"
    text = pdf_to_text(invoice_path)
    if text == "":
        logger.info(
            f"Fialed to extracted pdf text from invoice {invoice_path} attempting OCR"
        )
        file_type = "img"
        text = extract_text_from_image(invoice_path)
        if text == "":
            file_type = "error"
            logger.error(
                f"Failed to extract text from invoice {invoice_path} for OCR"
            )
    elif text != "":
        logger.info(f"Extracted pdf text from invoice {invoice_path}")
    else:
        logger.error(f"Failed to extract text from invoice {invoice_path}")

    return text, file_type


# LLM
def llm_key_extraction(input_text: str, model: str = "gpt-4o") -> dict:
    # gpt-4o, gpt-4o-mini, gpt-3.5-turbo, claude-3-5-sonnet-20240620, claude-3-opus-20240229, claude-3-haiku-20240307
    #
    """
    Extracts specific key fields from the given input text using a language model.

    Args:
        input_text (str): The text from which to extract the key fields.

    Returns:
        dict: A dictionary containing the extracted key fields in snake case as keys and their corresponding values as strings.
    """

    system_prompt = """
        You are a helpful assistant for the City of Cape Town with expert knowledge of the layout of invoice documents.
        Do not confuse City of Cape Town for the vendor informations. 
        Your task is to extract only the key fields specified by the user, from the invoice text, and only output these as a valid JSON object. 
        Return an empty string if the field is not present.
        The expected dates will never start with month first. So no MM/DD/YYYY formats expected.
    """

    user_prompt = f"""
    Question:
    Extract the following information as a JSON object with keys in snake case and extracted values as strings for an invoice text document:
        - Invoice number or document number or tax invoice number (vendor_invoice_id): [extracted value]
        - Your reference number or purchase order number or external order number (a 10 digit code that starts with a 450) (purchase_order_number): [extracted value]
        - Vendor VAT or tax reference number (a 10 digit code) (vendor_tax_id): [extracted value]
        - vendor/company registration number (vendor_registration_number): [extracted value]
        - Issue date (invoice_date) in formats YYYY/MM/DD or DD/MM/YYYY of DD/MM/YY: [extracted value]
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

    logger.info("Starting LLM key extraction")

    try:
        if model.startswith("gpt"):

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            client = OpenAI()
            # client = Anthropic() claude-3-5-sonnet-20240620
            response = client.chat.completions.create(
                model=model, temperature=TEMPERATURE, messages=messages
            )

            response = response.choices[0].message.content

        elif model.startswith("claude"):
            messages = [{"role": "user", "content": user_prompt}]

            client = Anthropic()
            response = client.messages.create(
                model=model,
                max_tokens=5000,
                temperature=TEMPERATURE,
                messages=messages,
                system=system_prompt,
            )
            response = response.content[0].text

        elif model.startswith("local"):
            url = "https://datascience.capetown.gov.za/cptgpt-dev/v1/chat/completions"

            payload = {
                "model": "llama3-8b-it-q5",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            }
            headers = {"Content-Type": "application/json"}

            response = requests.request(
                "POST", url, json=payload, headers=headers
            )
            response = json.loads(response.content)
            response = response["choices"][0]["message"]["content"]

        response = find_brackets(response)
        response = json.loads(response)
        logger.info("Text converted to JSON object")
        return response

    except Exception as e:
        logger.error(f"Failed to create JSON object {e}")


# Key and val clean up
def key_clean(input_dict: dict) -> dict:
    """
    Cleans the keys of a dictionary by mapping the keys to a new dictionary with standardized keys.

    Args:
        input_dict (dict): The dictionary to clean.

    Returns:
        dict: The cleaned dictionary.

    """
    new_dict = {
        "vendor_name": "",
        "vendor_invoice_id": "",
        "invoice_date": "",
        "vendor_tax_id": "",
        "vendor_registration_number": "",
        "purchase_order_number": "",
        "bank_details": [
            {
                "bank_name": "",
                "bank_branch_code": "",
                "bank_account_number": "",
            }
        ],
        "vendor_address": "",
        "net_amount": None,
        "total_amount": None,
        "tax_amount": None,
        "address": "",
        "line_items": [],
    }

    for key, val in input_dict.items():
        match key:
            case _ if "vendor" in key and "name" in key:
                new_dict["vendor_name"] = val
            case _ if "invoice" in key and "id" in key:
                new_dict["vendor_invoice_id"] = val
            case _ if "date" in key:
                new_dict["invoice_date"] = val
            case _ if "vendor" in key and "tax" in key:
                new_dict["vendor_tax_id"] = val
            case _ if "vendor" in key and "registration" in key:
                new_dict["vendor_registration_number"] = val
            case _ if "purchase" in key or "order" in key:
                new_dict["purchase_order_number"] = val
            case _ if "bank" in key:
                bank_details = []
                for bank in val:
                    b = {}
                    for k, v in bank.items():
                        if "name" in k:
                            b["bank_name"] = v
                        elif "account" in k:
                            b["bank_account_number"] = v
                        elif "branch" in k:
                            b["bank_branch_code"] = v
                    bank_details.append(b)
                new_dict["bank_details"] = bank_details
            case _ if "net" in key and "amount" in key:
                new_dict["net_amount"] = val
            case _ if "total" in key and "amount" in key:
                new_dict["total_amount"] = val
            case _ if "tax" in key and "amount" in key:
                new_dict["tax_amount"] = val
            case _ if "address" in key:
                new_dict["vendor_address"] = val
            case _ if "items" in key:
                new_dict["line_items"] = val

    return new_dict


def val_clean(input_dict: dict) -> dict:
    """
    Cleans and standardizes the values in the input dictionary based on specific keys, returning a new dictionary with cleaned values.

    Args:
        input_dict (dict): The input dictionary to be cleaned.

    Returns:
        dict: A dictionary with cleaned and standardized values.
    """

    new_dict = key_clean(input_dict)

    for key, val in new_dict.items():
        match key:
            case "vendor_name":
                try:
                    new_dict[key] = val.strip().lower()
                except Exception as e:
                    new_dict[key] = val

            case "vendor_invoice_id":
                try:
                    val = val.replace(" ", "").upper()
                    new_dict[key] = val.strip()
                except Exception as e:
                    new_dict[key] = val

            case "invoice_date":
                try:
                    val = val.replace(".", "-")
                    match = re.search(patterns["issue_date"], val)
                    new_dict[key] = parse_date_with_regex(match.group(0))
                    new_dict[key] = new_dict[key].strftime("%Y-%m-%d")
                except Exception as e:
                    new_dict[key] = val

            case "vendor_tax_id":
                try:
                    val = val.replace(" ", "").replace("-", "")
                    match = re.search(patterns["vendor_tax_id"], val)
                    new_dict[key] = match.group(0)
                except Exception as e:
                    new_dict[key] = val

            case "vendor_registration_number":
                try:
                    val = val.replace(" ", "")
                    match = re.findall(
                        patterns["vendor_registration_number"], val
                    )
                    if match:
                        new_dict[key] = "".join(match)
                except Exception as e:
                    new_dict[key] = val

            case "purchase_order_number":
                try:
                    val = val.replace(" ", "")
                    match = re.search(patterns["purchase_order_number"], val)
                    new_dict[key] = match.group(0)
                except Exception as e:
                    new_dict[key] = val

            case "bank_details":
                for idx, bank in enumerate(val):
                    for b, v in bank.items():
                        match b:
                            case "bank_name":
                                try:
                                    new_dict[key][idx][b] = v.strip().lower()
                                except Exception as e:
                                    new_dict[key][idx][b] = v

                            case "bank_account_number":
                                try:
                                    v = v.replace(" ", "").replace("-", "")
                                    match = re.search(
                                        patterns["bank_account_number"], v
                                    )
                                    new_dict[key][idx][b] = match.group(0)
                                except Exception as e:
                                    new_dict[key][idx][b] = v

                            case "bank_branch_code":
                                try:
                                    v = v.replace(" ", "").replace("-", "")
                                    match = re.search(
                                        patterns["bank_branch_code"], v
                                    )
                                    new_dict[key][idx][b] = match.group(0)
                                except Exception as e:
                                    new_dict[key][idx][b] = v

            case "net_amount":
                try:
                    if "." not in val and "," in val:
                        # replace last comma index -3 with .
                        val = val[: len(val) - 3] + "." + val[len(val) - 2 :]
                    val = re.sub(patterns["amount"], "", val)
                    val = float(val)
                    new_dict[key] = val
                except Exception as e:
                    new_dict[key] = val

            case "total_amount":
                try:
                    if "." not in val and "," in val:
                        # replace last comma index -3 with .
                        val = val[: len(val) - 3] + "." + val[len(val) - 2 :]
                    val = re.sub(patterns["amount"], "", val)
                    val = float(val)
                    new_dict[key] = val
                except Exception as e:
                    new_dict[key] = val

            case "tax_amount":
                try:
                    if "." not in val and "," in val:
                        # replace last comma index -3 with .
                        val = val[: len(val) - 3] + "." + val[len(val) - 2 :]
                    val = re.sub(patterns["amount"], "", val)
                    val = float(val)
                    new_dict[key] = val
                except Exception as e:
                    new_dict[key] = val

            case "vendor_address":
                try:
                    new_dict[key] = val.strip().lower()
                except Exception as e:
                    new_dict[key] = val

            case "line_items":
                try:
                    new_dict[key] = val
                except Exception as e:
                    continue

    return new_dict


# Function to compare two strings and get the match score
def get_match(string1: str, string2: str, partial_ratio: float = 0.8) -> bool:
    """
    A function that compares two strings and returns a boolean based on the partial ratio comparison.

    Args:
        string1 (str): The first string for comparison.
        string2 (str): The second string for comparison.
        partial_ratio (float): The threshold for the partial ratio.

    Returns:
        bool: True if the partial ratio of string1 and string2 is greater than the provided threshold, False otherwise.
    """
    partial_match = fuzz.partial_ratio(string1, string2)

    if partial_match > partial_ratio:
        return True

    else:
        return False


if __name__ == "__main__":
    invoice = (
        r"invoice_data_processing\pdfs\ERASMUS TYRE SERVICES CC 5505769703.pdf"
    )
    text, file_type = text_extraction(invoice)
    llm_raw = llm_key_extraction(text)
    llm_clean = val_clean(llm_raw)
    print(llm_clean)
