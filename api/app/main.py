from fastapi import FastAPI
from api.app.data_identity.routes import auth, activities, core_data

app = FastAPI(title="CarbonLens API", version="1.0.0")

app.include_router(auth.router)
app.include_router(activities.router)
app.include_router(core_data.router)

@app.get("/")
def root():
    return {"message": "Welcome to CarbonLens API"}