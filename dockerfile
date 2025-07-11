# Use the latest Ubuntu image with Python 3.10
FROM python:3.10

# Set environment variable for Node.js major version
ENV NODE_MAJOR=22

# Set working directory
WORKDIR /ehridentityst

RUN apt-get update && \
    apt-get install -y nginx zip nano bash curl default-mysql-client && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/

# Copy necessary files into Docker container
COPY ehridentityst.py /ehridentityst
COPY requirements.txt /ehridentityst
COPY start.sh /ehridentityst
COPY default /ehridentityst
COPY synthetic_identification_bio_20250710163055 /ehridentityst/synthetic_identification_bio_20250710163055


# White Pages
RUN mkdir .streamlit
COPY config.toml /ehridentityst/.streamlit

# Verify installation
RUN node -v && npm -v

# Install PM2 globally
RUN npm install -g npm@11.1.0
RUN npm install -g pm2@latest

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Grant execute permissions to the script
RUN chmod +x start.sh

# Run the script
CMD ["bash", "start.sh"]
