from db_utils import minio_utils
import invoice_utils as iu

BUCKET='fleet-data-pipeline.invoice-examples'

files = minio_utils.list_objects_in_bucket(BUCKET)

for file in files:
    iu.pull_invoice_pdf(file,BUCKET)
    