from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel
import os
import json
import tempfile
import logging
from openai import OpenAI
from . import invoice_utils as iu  # Uncomment for Docker

# import invoice_utils as iu  # Comment out for Docker

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add a test log message to verify output
logger.info("Logging is configured and working at INFO level.")

app = FastAPI(root_path="/invoice-api-backend-dev")


class Item(BaseModel):
    name: str
    description: str = None


# Simple GET endpoint for health check
@app.get("/")
async def root():
    return {"message": "API is running"}


# Basic POST endpoint to echo back data
@app.post("/echo/")
async def echo(item: Item):
    return {"message": "Received data", "data": item}


# Endpoint to upload a PDF file and return the filename
@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted.",
        )
    return {"filename": file.filename}


# Endpoint to upload any file and return the filename
@app.post("/upload-any-file/")
async def upload_any_file(file: UploadFile = File(...)):
    return {"filename": file.filename}


# Original endpoint to upload PDF and extract invoice data
def extract_data(file_path: str) -> dict:
    try:
        text = iu.text_extraction(file_path)
        logger.info("text extraction successful")
        llm_raw = iu.llm_key_extraction(text)
        logger.info("llm key extraction successful")
        llm_clean = iu.val_clean(llm_raw)
        logger.info("val clean successful")
        output = json.dumps(llm_clean)
        logger.info("json dump successful")
        return json.loads(output)
    except Exception as e:
        logger.error(f"Error extracting data from {file_path}: {e}")
        raise HTTPException(status_code=500, detail="Error processing file")


def process_file(file: UploadFile):
    """Process the file and return the extracted data."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(file.file.read())
        temp_file_path = temp_file.name

    try:
        filename_data = extract_data(temp_file_path)
        return filename_data
    finally:
        os.remove(temp_file_path)


@app.post("/upload-pdf-return-invoice-data/")
async def upload_pdf_return_invoice_data(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted.",
        )

    output = process_file(file)
    return output


# New endpoint to test loading a file in /tmp and checking its existence
@app.post("/test-tmp-file/")
async def test_tmp_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only PDF files are accepted.",
        )

    # Save the file temporarily in /tmp
    with tempfile.NamedTemporaryFile(delete=False, dir="/tmp") as temp_file:
        temp_file.write(file.file.read())
        temp_file_path = temp_file.name

    # Check if the file exists and can be accessed
    file_exists = os.path.exists(temp_file_path)
    file_accessible = os.access(temp_file_path, os.R_OK)

    return {
        "tmp_file_path": temp_file_path,
        "file_exists": file_exists,
        "file_accessible": file_accessible,
        "filename": os.path.basename(temp_file_path),
    }


# Endpoint to test connection to OpenAI API
@app.get("/test-openai-connection/")
async def test_openai_connection():
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

    # Initialize OpenAI client
    client = OpenAI(api_key=openai_api_key)
    model_use = "gpt-4o"  # Example model name

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": "Say this is a test",
                }
            ],
            model=model_use,
        )
        # Attempt a simple request to test the connection
        response = chat_completion.choices[0].message.content
        return {
            "status": "Connection to OpenAI successful",
            "response": response,
        }
    except Exception as e:
        logger.error(f"Failed to connect to OpenAI: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to connect to OpenAI"
        )
