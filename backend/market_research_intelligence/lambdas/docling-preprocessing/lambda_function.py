import os
import io
import boto3
from botocore.config import Config
import extract_msg
import base64
import re
from email import policy
from email.parser import BytesParser
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from weasyprint import HTML

timeout_config = Config(read_timeout=300)
s3 = boto3.client("s3", config=timeout_config)
sts = boto3.client("sts", config=timeout_config)
ACCOUNT_ID = sts.get_caller_identity()["Account"]


def extract_msg_content(file_bytes):
    msg = extract_msg.Message(file_bytes)

    html = msg.htmlBody or ""
    if isinstance(html, bytes):
        html = html.decode('utf-8', errors='replace')

    image_map = {}
    for att in msg.attachments:
        if att.data and att.mimetype and att.mimetype.startswith('image/'):
            cid = att.cid or att.longFilename or att.shortFilename
            if cid:
                cid = cid.strip('<>')
                b64 = base64.b64encode(att.data).decode()
                image_map[cid] = f"data:{att.mimetype};base64,{b64}"
                print(f"[MSG] Embedded image: {cid}, type: {att.mimetype}, size: {len(att.data)}")

    for cid, data_uri in image_map.items():
        html = html.replace(f"cid:{cid}", data_uri)

    if html:
        return html, True
    return msg.body or "", False


def image_processing(part, ctype, image_map):
    """To get the images from the email and store it in image_map."""
    data = part.get_payload(decode=True)
    if not data:
        return

    cid = part.get("Content-Id", "").strip("<>")
    if cid:
        image_map[cid] = f"data:{ctype};base64,{base64.b64encode(data).decode()}"
        print(f"Embedded image with CID: {cid}, with type: {ctype}, with size: {len(data)}")

    filename = part.get_filename()
    if filename and filename not in image_map:
        image_map[filename] = f"data:{ctype};base64,{base64.b64encode(data).decode()}"
        print(f"Embedded image without CID: {filename}, with type: {ctype}, with size: {len(data)}")


def replace_image(html, image_map):
    """To replace cid: and src refs in HTML with base64 data URIs."""
    for cid, data_uri in image_map.items():
        html = html.replace(f"cid:{cid}", data_uri)
        html = html.replace(f'src="{cid}"', f'src="{data_uri}"')
    print(f"Replaced {len(image_map)} image references")
    return html


def extract_eml_content(file_bytes):
    msg = BytesParser(policy=policy.default).parsebytes(file_bytes)

    html = None
    text = None
    image_map = {}

    for part in msg.walk():
        ctype = part.get_content_type()
        disposition = part.get_content_disposition() or ""

        if ctype == "text/html" and "attachment" not in disposition and not html:
            html = part.get_content()
        elif ctype == "text/plain" and "attachment" not in disposition and not text:
            text = part.get_content()
        elif ctype.startswith("image/"):
            image_processing(part, ctype, image_map)

    if html:
        return replace_image(html, image_map), True

    return text or "", False


def text_to_pdf_bytes(text):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    t = c.beginText(40, 750)
    for line in text.splitlines():
        t.textLine(line)
    c.drawText(t)
    c.save()
    buffer.seek(0)
    return buffer


def html_to_pdf_bytes(html_content):
    fix_css = """
    <style>
        @page {
            size: A4 landscape;
            margin: 1cm;
        }
        body {
            font-size: 10px !important;
            font-family: Arial, sans-serif;
        }
        table {
            width: 100% !important;
            table-layout: fixed !important;
            word-wrap: break-word !important;
            border-collapse: collapse !important;
        }
        td, th {
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            white-space: normal !important;
            width: auto !important;
            max-width: 200px !important;
            padding: 4px !important;
            font-size: 10px !important;
        }
        img {
            max-width: 100% !important;
            height: auto !important;
            display: block !important;
            margin: 10px 0 !important;
        }
        * {
            max-width: 100% !important;
            box-sizing: border-box !important;
        }
    </style>
    """

    html_content = re.sub(r'(<t[dh][^>]*?)width\s*:\s*[\d]+px', r'\1', html_content)
    html_content = re.sub(r'(<t[dh][^>]*?)width\s*=\s*["\'][\d]+["\']', r'\1', html_content)

    if '<head>' in html_content.lower():
        html_content = html_content.replace('</head>', fix_css + '</head>', 1)
    else:
        html_content = fix_css + html_content

    buffer = io.BytesIO()
    HTML(string=html_content).write_pdf(buffer)
    buffer.seek(0)
    return buffer


def convert_email_to_pdf_bytes(file_bytes, ext):
    if ext == ".msg":
        content, is_html = extract_msg_content(file_bytes)
    else:
        content, is_html = extract_eml_content(file_bytes)

    if is_html:
        return html_to_pdf_bytes(content)
    return text_to_pdf_bytes(content)


def lambda_handler(event, context):
    detail = event.get("detail", {})

    bucket = detail.get("bucket", {}).get("name")
    key = detail.get("object", {}).get("key")

    if not bucket or not key:
        print('Missing bucket or key')
        raise ValueError("Missing bucket or key in event detail")

    ext = os.path.splitext(key)[1].lower()
    if ext not in {".eml", ".msg"}:
        return event

    response = s3.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=ACCOUNT_ID)

    content_length = response.get('ContentLength', 0)
    if content_length > 10 * 1024 * 1024:
        return {'statusCode': 400, 'body': 'File too large'}

    file_bytes = response['Body'].read()

    pdf_buffer = convert_email_to_pdf_bytes(file_bytes, ext)

    base, _ = os.path.splitext(key)
    output_key = base + ".pdf"

    s3.upload_fileobj(pdf_buffer, bucket, output_key, ExtraArgs={'ExpectedBucketOwner': ACCOUNT_ID})


    return {
        'status': 'preprocessed',
        'body': f'Converted: {output_key}'
    }
