import boto3
from botocore.config import Config
from urllib.parse import urlparse
import os
import json

timeout_config = Config(read_timeout=300)
s3Client = boto3.client('s3', config=timeout_config)
bedrock_agent = boto3.client("bedrock-agent", config=timeout_config)
sts = boto3.client("sts", config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()["Account"]


def parse_s3_uri(s3_uri: str): 
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    s3_path = s3_uri[5:]  # strip off 's3://'
    bucket, key = s3_path.split("/", 1)
    return bucket, key


def s3upload(bucket, key, content):
    response = s3Client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType="text/markdown",
        ExpectedBucketOwner=ACCOUNT_ID
    )
    print(f"s3 put object response - {bucket} - {key} : ", response)


def lambda_handler(event, context):

    print("event is: ", json.dumps(event))

    # ==============================================================
    # CASE 1 — STATUS CHECK (re-invoked by Step Function to poll)
    # ==============================================================
    if isinstance(event, dict) and "ingestionJobId" in event:
        ingestion_job_id = event["ingestionJobId"]
        knowledge_base_id = event["knowledge_base_id"]
        data_source_id = event["data_source_id"]
        print(f"Checking status for job {ingestion_job_id}")

        response = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=ingestion_job_id
        )

        job = response["ingestionJob"]

        return {
            "action": "STATUS_CHECK",
            "ingestionJobId": job["ingestionJobId"],
            "knowledge_base_id": knowledge_base_id,
            "data_source_id": data_source_id,
            "status": job["status"],  # STARTING | IN_PROGRESS | COMPLETE | FAILED | STOPPED
            "statistics": job.get("statistics", {}),
            "failureReasons": job.get("failureReasons", [])
        }

    # ==============================================================
    # CASE 2 — EXTRACT + UPLOAD + START INGESTION (initial invoke)
    # ==============================================================
    source_bucket = event["detail"]["bucket"]["name"]
    source_key = event["detail"]["object"]["key"]
    target_bucket = event["output_bucket"]
    knowledge_base_id = event["knowledge_base_id"]
    data_source_id = event["data_source_id"]

    print(f"Processing file s3://{source_bucket}/{source_key}")
    print(f"Target bucket: {target_bucket}, KB: {knowledge_base_id}, DS: {data_source_id}")

    presigned_source_url = s3Client.generate_presigned_url(
        'get_object',
        Params={'Bucket': source_bucket, 'Key': source_key},
        ExpiresIn=3600
    ) 

    try:
        print("Importing docling")
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TesseractOcrOptions
        )
        from docling.datamodel.base_models import InputFormat

        # Check if file is PDF
        file_extension = os.path.splitext(source_key)[1].lower()
        
        if file_extension == '.pdf':
            # PASS 1: Try without OCR first (works for born-digital PDFs
            # like those converted from EML/MSG, and regular digital PDFs).
            # This avoids Tesseract OSD errors on non-scanned content.
            print("Pass 1: Converting PDF without OCR")
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options.do_cell_matching = True

            doc_converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            result = doc_converter.convert(source=presigned_source_url)
            md_content = result.document.export_to_markdown()

            # PASS 2: If no text was extracted at all, the PDF is likely
            # a scanned document (no text layer) — retry with OCR enabled.
            if len(md_content.strip()) == 0:
                print("Pass 1 produced no content (likely scanned PDF), retrying with OCR")
                pipeline_options_ocr = PdfPipelineOptions()
                pipeline_options_ocr.do_ocr = True
                pipeline_options_ocr.do_table_structure = True
                pipeline_options_ocr.table_structure_options.do_cell_matching = True
                pipeline_options_ocr.ocr_options = TesseractOcrOptions()

                doc_converter_ocr = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options_ocr)
                    }
                )
                result = doc_converter_ocr.convert(source=presigned_source_url)
                md_content = result.document.export_to_markdown()
            else:
                print(f"Pass 1 succeeded ({len(md_content.strip())} chars extracted without OCR)")
        else:
            doc_converter = DocumentConverter()
            result = doc_converter.convert(source=presigned_source_url)
            md_content = result.document.export_to_markdown()

        print("Import done")

        target_key = f"{os.path.splitext(source_key)[0].lower()}.md"
        print("target_key: ", target_key)
        s3upload(target_bucket, target_key, md_content)

        # Start KB ingestion job after uploading
        print(f"Starting ingestion job for KB: {knowledge_base_id}, DS: {data_source_id}")
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id
        )

        job = response["ingestionJob"]

        return {
            "action": "STARTED",
            "ingestionJobId": job["ingestionJobId"],
            "knowledge_base_id": knowledge_base_id,
            "data_source_id": data_source_id,
            "status": job["status"]  # STARTING
        }

    except Exception as e:
        print("Error:", str(e))
        return {"error": f"Unexpected error: {str(e)}"}
