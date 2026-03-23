FROM python:3.8-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -f https://download.pytorch.org/whl/torch_stable.html

# Copy shared model module (copied into build context by build-project.sh)
COPY shared/ ./shared/

COPY aggregation_confirmation_tp.py .

CMD ["python", "aggregation_confirmation_tp.py"]