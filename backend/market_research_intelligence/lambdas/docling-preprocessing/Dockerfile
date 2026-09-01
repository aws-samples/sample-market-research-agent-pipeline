FROM public.ecr.aws/lambda/python:3.12
 
# Install system dependencies for WeasyPrint and create non-root user
RUN dnf install -y \
    cairo \
    cairo-devel \
    pango \
    pango-devel \
    glib2 \
    glib2-devel \
    harfbuzz \
    harfbuzz-devel \
    gobject-introspection \
    shadow-utils \
    && /usr/sbin/groupadd -r appuser \
    && /usr/sbin/useradd -r -g appuser appuser \
    && dnf remove -y shadow-utils \
    && dnf clean all
 
# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt
 
# Copy function code
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
 
# Switch to non-root user for security compliance
USER appuser
 
CMD ["lambda_function.lambda_handler"]