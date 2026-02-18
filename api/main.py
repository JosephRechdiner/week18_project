from fastapi import Depends, FastAPI, File, Request, UploadFile, HTTPException
from contextlib import asynccontextmanager
from pymongo import MongoClient
from schemas import Order
from mongo_handler import save_to_mongo, MongoManger, get_order_by_id_mongo
from producer_handler import KafkaProducer
from redis_handler import RedisManager
import json

# ========================================================================
# UTILS
# ========================================================================

def convert_to_python_obj(orders):
    return [Order(**order) for order in orders]

# ========================================================================
# DEPENDENCIES
# ========================================================================

def get_client(request: Request):
    return request.app.state.client

def get_kafka_producer(request: Request):
    return request.app.state.producer

def get_redis(request: Request):
    return request.app.state.r

# ========================================================================
# APP
# ========================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mongo_manager = MongoManger()
    app.state.client = app.state.mongo_manager.get_client()
    app.state.producer = KafkaProducer()
    app.state.r = RedisManager()
    yield
    app.state.client.close()

app = FastAPI(lifespan=lifespan)

# ========================================================================
# ROUTES
# ========================================================================

@app.post("/uploadfile")
def upload_file(
    file: UploadFile = File(...),
    client: MongoClient = Depends(get_client),
    producer: KafkaProducer = Depends(get_kafka_producer)
):
    # getting data from file
    try:
        orders = json.loads(file.file.read())
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read file, Error: {str(e)}")

    # convert data to python objs
    python_orders = convert_to_python_obj(orders)

    # saving to mongo
    try:
        mongo_msg, inserted_orders = save_to_mongo(python_orders, client)
    except Exception as e:
        raise HTTPException(status_code=409, detail=e)

    # sending to kafka
    kafka_msg = producer.send_orders_to_kafka(inserted_orders)

    return {"mongo msg": mongo_msg, "kafka msg": kafka_msg}


@app.get("/order/{order_id}")
def get_order_by_id(
    order_id: str,
    client: MongoClient = Depends(get_client),
    r: RedisManager = Depends(get_redis)
):
    # checking if data in redis cache
    order = r.r.get(order_id)
    if order:
        return {"source": "redis_cache", "order": json.loads(order)}
    
    # loading from mongo if does not exist in redis
    order = get_order_by_id_mongo(order_id, client) 
    r.r.set(order_id, json.dumps(order))
    
    return {"source": "mongodb", "order": order}
