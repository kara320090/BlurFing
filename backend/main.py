from fastapi import FastAPI

app = FastAPI(title="BlurFing Backend")


@app.get("/")
def health_check():
    return {"message": "BlurFing backend is running"}
