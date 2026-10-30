FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m src.gerar_dados && python -m src.treinar
EXPOSE 8501
CMD ["streamlit", "run", "app/demo.py", "--server.address=0.0.0.0", "--server.port=8501"]