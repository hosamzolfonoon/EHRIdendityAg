# Use the latest Ubuntu image with Python 3.10
FROM python:3.10

# Set working directory
WORKDIR /ehridentityag

RUN apt-get update && \
    apt-get install -y nginx zip nano bash curl net-tools iputils-ping libgl1 telnet default-mysql-client && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/

# Copy necessary files into Docker container
COPY ehridentityag.py .
COPY requirements.txt .
COPY start.sh .
COPY default .
COPY synthetic_identification_bio_20250723162236 /ehridentityag/synthetic_identification_bio_20250723162236

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# Grant execute permissions to the script
RUN chmod +x start.sh

# Run the script
CMD ["bash", "start.sh"]