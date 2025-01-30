from dataclasses import dataclass
from datetime import datetime
from airflow.utils.task_group import TaskGroup
from pipeline_utils.kubernetes_dag import (
    airflowK8sDAG, DagOwner, LIGHT_RESOURCES, MEDIUM_RESOURCES, HEAVY_RESOURCES
)

@dataclass
class OperatorSettings:
    task_name: str
    cmd_args: str


PROJECT_NAME = 'invoice-data-processing'
DAG_IMAGE = "cityofcapetown/datascience:python@sha256:d127af40a3002e0c3569856fe2cf4683e8ff81a525eac47ce48b6707391bc5da"
DAG_NAME = PROJECT_NAME
CODE_LOCATION = f"https://lake.capetown.gov.za/{PROJECT_NAME}.deploy/{PROJECT_NAME}.zip"
OWNER = "canthony3"
OWNER_EMAIL = "colinscott.anthony@capetown.gov.za"
DAG_STARTDATE = datetime(2022, 1, 12)

DAG_INTERVAL = "30 */6 * * 1-5"


# tasks
INVOICE_TEXT_EXTRACTION_TASK = "invoice-text-extraction"
INVOICE_OCR_TASK = "invoice-ocr-extraction"
INVOICE_VALIDATION_STEP_1_TASK = "invoice-validation-primary"
INVOICE_VALIDATION_STEP_2_TASK = "invoice-validation-secondary"
INVOICE_TRINO_TASK = "data_to_trino"

# task operator object settings
processing_tasks = [
    OperatorSettings(INVOICE_TEXT_EXTRACTION_TASK, ""),
    OperatorSettings(INVOICE_OCR_TASK, "")
]

validation_tasks = [
    OperatorSettings(INVOICE_VALIDATION_STEP_1_TASK, ""),
    OperatorSettings(INVOICE_VALIDATION_STEP_2_TASK, "")
]

# build operators
with airflowK8sDAG(
    dag_name=DAG_NAME,
    dag_owner=DagOwner(OWNER, OWNER_EMAIL),
    start_date=DAG_STARTDATE,
    schedule_interval=DAG_INTERVAL,
    dag_image=DAG_IMAGE,
    secret_name=f"{PROJECT_NAME}-secrets",
    code_location=CODE_LOCATION,
    concurrency=3
) as dag:

    # Defining tasks
    with TaskGroup("invoice-data-extraction") as processing_operators_group:
        processing_operators = [
            dag.get_dag_operator(
                resources=LIGHT_RESOURCES,
                task_name=task.task_name,
                task_cmd=f"python3 ./invoice_data_processing/{task.task_name}.py"
            ) for task in processing_tasks
        ]

    with TaskGroup("invoice-data-validation") as validation_operators_group:
        validation_1_operator = dag.get_dag_operator(
                resources=LIGHT_RESOURCES,
                task_name=INVOICE_VALIDATION_STEP_1_TASK,
                task_cmd=f"python3 ./invoice_data_processing/{INVOICE_VALIDATION_STEP_1_TASK}.py"
            )
        validation_2_operator = dag.get_dag_operator(
            resources=LIGHT_RESOURCES,
            task_name=INVOICE_VALIDATION_STEP_2_TASK,
            task_cmd=f"python3 ./invoice_data_processing/{INVOICE_VALIDATION_STEP_2_TASK}.py"
        )
        # validation dependencies
        validation_1_operator >> validation_2_operator

    invoice_data_to_trino_operator = dag.get_dag_operator(
        resources=MEDIUM_RESOURCES,
        task_name=INVOICE_TRINO_TASK,
        task_cmd=f"python3 ./fleet_data_pipeline/processing/{INVOICE_TRINO_TASK}.py",
    )

    # Dependencies
    processing_operators_group >> validation_operators_group >> invoice_data_to_trino_operator
