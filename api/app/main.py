from fastapi import FastAPI
from api.app.data_identity.routes import auth, activities, core_data, assets, users
from api.app.engine import routes as engine_routes

app = FastAPI(title="CarbonLens API", version="1.0.0")

app.include_router(auth.router)
app.include_router(activities.router)
app.include_router(core_data.router)
app.include_router(assets.router)
app.include_router(users.router) # <-- Add this line
app.include_router(engine_routes.router)  # S2 Emission Engine

@app.get("/")
def root():
    return {"message": "Welcome to CarbonLens API"}