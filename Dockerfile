# Step 1: Use Python base image
FROM python:3.11-slim

# Step 2: Set working directory
WORKDIR /app

# Step 3: Install system packages (FFmpeg)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean

# Step 4: Copy requirements
COPY requirements.txt .

# Step 5: Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Step 6: Copy app files
COPY . .

# Step 7: Expose port
EXPOSE 8080

# Step 8: Run the app
CMD ["python", "app.py"]
