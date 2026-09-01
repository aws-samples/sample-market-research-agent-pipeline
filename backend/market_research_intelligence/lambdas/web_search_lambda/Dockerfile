FROM public.ecr.aws/lambda/python:3.11

# Copy requirements first (better caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy lambda code
COPY lambda_function.py .

RUN yum install -y shadow-utils && \
    /usr/sbin/groupadd -r appuser && \
    /usr/sbin/useradd -r -g appuser appuser && \
    yum remove -y shadow-utils && \
    yum clean all && \
    rm -rf /var/cache/yum
 
USER appuser

# Set handler
CMD ["lambda_function.lambda_handler"]
