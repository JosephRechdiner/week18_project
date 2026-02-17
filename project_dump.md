# PROJECT TREE

```
__pycache__/ [subfolders: 0, files: 3, total files: 3]
    api.cpython-314.pyc
    mongo.cpython-314.pyc
    schemans.cpython-314.pyc
api/ [subfolders: 0, files: 8, total files: 8]
    __init__.py
    Dockerfile
    main.py
    mongo_handler.py
    producer_handler.py
    redis_handler.py
    requirements.txt
    schemas.py
docker-compose.yaml
enricher/ [subfolders: 1, files: 7, total files: 8]
    __init__.py
    Dockerfile
    jsons/ [subfolders: 0, files: 1, total files: 1]
        pizza_analysis_lists.json
    main.py
    mongo_handler.py
    redis_handler.py
    requirements.txt
    text_handler.py
kitchen_worker/ [subfolders: 0, files: 6, total files: 6]
    __init__.py
    Dockerfile
    main.py
    mongo_handler.py
    redis_handler.py
    requirements.txt
preprocessor/ [subfolders: 1, files: 5, total files: 6]
    Dockerfile
    jsons/ [subfolders: 0, files: 1, total files: 1]
        pizza_prep.json
    main.py
    producer_handler.py
    requirements.txt
    text_handler.py
text_worker/ [subfolders: 0, files: 6, total files: 6]
    __init__.py
    Dockerfile
    main.py
    mongo_handler.py
    requirements.txt
    text_handler.py
```

# PROJECT STATS

- Total folders: 8
- Total files  : 38

## File types

| Extension | Files | Lines (utf-8 text only) |
|---|---:|---:|
| `.json` | 2 | 122 |
| `.py` | 22 | 625 |
| `.pyc` | 3 | 0 |
| `.txt` | 5 | 100 |
| `.yaml` | 1 | 168 |
| `no_ext` | 5 | 31 |

---

# FILE CONTENTS

## __pycache__/api.cpython-314.pyc

**SKIPPED (binary or non-UTF8 text)**

## __pycache__/mongo.cpython-314.pyc

**SKIPPED (binary or non-UTF8 text)**

## __pycache__/schemans.cpython-314.pyc

**SKIPPED (binary or non-UTF8 text)**

## api/Dockerfile

```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD [ "uvicorn" , "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## api/__init__.py

```python

```

## api/main.py

```python
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
    
    # loading from mongo if not in redis
    order = get_order_by_id_mongo(order_id, client) 
    r.r.set(order_id, json.dumps(order))
    return {"source": "mongodb", "order": order}
```

## api/mongo_handler.py

```python
from pymongo import MongoClient
from schemas import Order
import os

MONGO_URI = os.getenv("MONGO_URI") 

class MongoManger:
    client = None
    def __init__(self):
        try:
            if not MongoManger.client:
                MongoManger.client = MongoClient(MONGO_URI)
                self.client = MongoManger.client
        except Exception as e:
            raise Exception(f"Could not connect to mongo db, Error: {str(e)}")

    def get_client(self):
        return self.client  

def save_to_mongo(orders: list[Order], client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    
    new_orders = []
    for order in orders:
        new_order = order.model_dump()
        new_order["status"] = "PREPARING"
        try:
            collection.insert_one(new_order)
            new_order.pop("_id")
            new_orders.append(new_order)
        except Exception as e:
            raise Exception(f"Could not insert orders to mongo db, Error: {str(e)}")
    return f"Saved to mongo", new_orders

def get_order_by_id_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    return collection.find_one({"order_id": order_id}, {"_id": 0})
```

## api/producer_handler.py

```python
from confluent_kafka import Producer
import json
import os

BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")

producer_config = {"bootstrap.servers": BOOTSTRAP_SERVERS}

class KafkaProducer:
    producer = None
    def __init__(self):
        try:
            if not KafkaProducer.producer:
                KafkaProducer.producer = Producer(producer_config)
            self.producer = KafkaProducer.producer
        except Exception as e:
            raise Exception(f"Could not init kafka producer, Error: {str(e)}")
        
    def send_orders_to_kafka(self, orders: list[dict], topic: str = KAFKA_TOPIC): 
        for order in orders:
            try:
                self.producer.produce(topic, value=json.dumps(order).encode("utf-8"))
            except Exception as e:
                raise Exception(f"Could not send {order} to kafka, Error: {str(e)}")
        self.producer.flush()
        return f"All data sent to kafka"



```

## api/redis_handler.py

```python
from redis import Redis
import os

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_DB = os.getenv("REDIS_DB")

class RedisManager:
    r = None
    def __init__(self):
        try:
            if not RedisManager.r:
                RedisManager.r = Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    decode_responses=True)
            self.r = RedisManager.r
        except Exception as e:
            raise Exception(f"Could not init redis, Error: {str(e)}")
```

## api/requirements.txt

```
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
click==8.3.1
colorama==0.4.6
confluent-kafka==2.13.0
dnspython==2.8.0
fastapi==0.129.0
h11==0.16.0
idna==3.11
pydantic==2.12.5
pydantic_core==2.41.5
pymongo==4.16.0
python-multipart==0.0.22
redis==7.1.1
starlette==0.52.1
typing-inspection==0.4.2
typing_extensions==4.15.0
uvicorn==0.40.0
```

## api/schemas.py

```python
from pydantic import BaseModel, Field
from typing import Literal

class Order(BaseModel):
    order_id: str = Field(..., description="Special order id")
    pizza_type: str = Field(..., description="The type of the pizza")
    size: Literal["Small", "Medium", "Large", "Family"] = Field(..., description="The size of the pizza")
    quantity: int = Field(..., gt=0, description="The quantity of the pizza in the order")
    is_delivery: bool = Field(..., description="Has the pizza delivered")
    special_instructions: str = Field("", description="Any special instructions")
```

## docker-compose.yaml

```yaml
version: '3.8'

services:
  kafka:
    image: confluentinc/cp-kafka:7.8.3
    container_name: kafka
    ports:
      - "9092:9092"

    environment:
      KAFKA_KRAFT_MODE: 'true'

      CLUSTER_ID: '1L6g7nGhU-eAKfL--X25wo'
      KAFKA_NODE_ID: 1

      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER

      KAFKA_LOG_DIRS: /tmp/kraft-combined-logs

    healthcheck:
      test: ["CMD", "bash", "-c", "kafka-topics --bootstrap-server kafka:9092 --list"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 40s

    volumes:
      - kafka_kraft:/var/lib/kafka/data


  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8085:8080"
    environment:
      DYNAMIC_CONFIG_ENABLED: "true"
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
    depends_on:
      - kafka
  mongo:
    image: mongo
    ports:
      - '27017:27017'
    volumes:
      - dbdata:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval" ,"db.adminCommand('ping')"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 40s

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - cache:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      interval: 1s
      timeout: 3s
      retries: 5

  api:
    build: ./api
    restart: always
    ports:
      - "8000:8000"
    environment:
      MONGO_URI: "mongodb://mongo:27017"

      BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_TOPIC: pizza-orders

      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_DB: 0
      
    depends_on:
      mongo:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy

  kitchen-worker:
    build: ./kitchen_worker
    restart: always
    ports:
      - "8090:8090"
    environment:
      MONGO_URI: "mongodb://mongo:27017"

      BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_TOPIC: pizza-orders
      KAFKA_GROUP_ID: kitchen-team

      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_DB: 0
      
    depends_on:
      mongo:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy


  preprocessor:
    build: ./preprocessor
    restart: always
    ports:
      - "8070:8070"
    environment:
      BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_LISTEN_TOPIC: pizza-orders
      KAFKA_SEND_TOPIC: cleaned-instructions
      KAFKA_GROUP_ID: preprocessor-team
      
    depends_on:
      mongo:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy

  enricher:
    build: ./enricher
    restart: always
    ports:
      - "8060:8060"
    environment:
      MONGO_URI: "mongodb://mongo:27017"
      
      BOOTSTRAP_SERVERS: kafka:9092
      KAFKA_LISTEN_TOPIC: cleaned-instructions
      KAFKA_GROUP_ID: enricher-team

      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_DB: 0

    depends_on:
      mongo:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  kafka_kraft:
  dbdata:
  cache:
    driver: local
```

## enricher/Dockerfile

```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python" , "main.py"]
```

## enricher/__init__.py

```python

```

## enricher/jsons/pizza_analysis_lists.json

```json
{
  "common_allergens": [
    "milk",
    "dairy",
    "wheat",
    "gluten",
    "eggs",
    "soy",
    "fish",
    "shellfish",
    "shrimp",
    "clams",
    "tree nuts",
    "peanuts",
    "pine nuts",
    "walnuts",
    "sesame",
    "mustard",
    "celery",
    "sulfites"
  ],
  "forbidden_non_kosher": [
    "pork",
    "ham",
    "bacon",
    "pepperoni",
    "prosciutto",
    "salami",
    "shrimp",
    "clams",
    "lobster",
    "seafood",
    "shellfish",
    "pancetta",
    "lard"
  ],
  "meat_ingredients": [
    "chicken",
    "beef",
    "steak",
    "meatball",
    "sausage",
    "pepperoni",
    "ham",
    "bacon",
    "prosciutto",
    "salami",
    "pork",
    "meat",
    "pancetta",
    "sirloin",
    "ribeye"
  ],
  "dairy_ingredients": [
    "cheese",
    "mozzarella",
    "parmesan",
    "ricotta",
    "feta",
    "gorgonzola",
    "provolone",
    "cheddar",
    "butter",
    "cream",
    "alfredo",
    "milk",
    "dairy",
    "goat cheese"
  ]
}
```

## enricher/main.py

```python
from confluent_kafka import Consumer
import os
import json
import logging
from mongo_handler import MongoManger, add_prep_instructions_mongo, add_special_instructions_mongo, update_burnt_status_mongo
from text_handler import get_hits, get_analysis
from redis_handler import RedisManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_LISTEN_TOPIC = os.getenv("KAFKA_LISTEN_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_LISTEN_TOPIC])

mongo_manager = MongoManger()
redis_manager = RedisManager()

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)

    # insert to mongo
    client = mongo_manager.get_client()
    add_special_instructions_mongo(order["order_id"], order["special_instructions"], client)
    add_prep_instructions_mongo(order["order_id"], order["prep_instructions"], client)

    # checking for redis hits
    analysis = get_analysis()
    hits = redis_manager.r.get(order["pizza_type"])
    if not hits:
        hits = {}

        hits["allergens_hits"] = get_hits(order["prep_instructions"], analysis["common_allergens"])
        hits["meat_hits"] = get_hits(order["prep_instructions"], analysis["meat_ingredients"])
        hits["dairy_hits"] = get_hits(order["prep_instructions"], analysis["dairy_ingredients"])
        hits["kisher_hits"] = get_hits(order["prep_instructions"], analysis["forbidden_non_kosher"])

        redis_manager.r.set(order["pizza_type"], json.dumps(hits))

    if (hits["meat_hits"] and hits["dairy_hits"]) or not hits["kosher_hits"]:
        update_burnt_status_mongo(order["order_id"], client)
```

## enricher/mongo_handler.py

```python
from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI") 

class MongoManger:
    client = None
    def __init__(self):
        try:
            if not MongoManger.client:
                MongoManger.client = MongoClient(MONGO_URI)
            self.client = MongoManger.client
        except Exception as e:
            raise Exception(f"Could not connect to mongo db, Error: {str(e)}")

    def get_client(self):
        return self.client 


def update_burnt_status_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"status": "BURNT"}})
    except Exception as e:
        raise Exception(f"Could not update order status, Error: {str(e)}") 

def add_special_instructions_mongo(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"special_instructions": text}})
    except Exception as e:
        raise Exception(f"Could not set special instructions field, Error: {str(e)}")
    
def add_prep_instructions_mongo(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"prep_instructions": text}})
    except Exception as e:
        raise Exception(f"Could not set prep instructions field, Error: {str(e)}")
```

## enricher/redis_handler.py

```python
from redis import Redis
import os

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_DB = os.getenv("REDIS_DB")

class RedisManager:
    r = None
    def __init__(self):
        try:
            if not RedisManager.r:
                RedisManager.r = Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    decode_responses=True)
            self.r = RedisManager.r
        except Exception as e:
            raise Exception(f"Could not init redis, Error: {str(e)}")
```

## enricher/requirements.txt

```
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
click==8.3.1
colorama==0.4.6
confluent-kafka==2.13.0
dnspython==2.8.0
fastapi==0.129.0
h11==0.16.0
idna==3.11
pydantic==2.12.5
pydantic_core==2.41.5
pymongo==4.16.0
python-multipart==0.0.22
redis==7.1.1
starlette==0.52.1
typing-inspection==0.4.2
typing_extensions==4.15.0
uvicorn==0.40.0
```

## enricher/text_handler.py

```python
import json

def get_analysis():
    with open("./jsons/pizza_analysis_lists.json") as file:
        data = json.load(file)
    return data

def get_hits(instructions, words):
    res = []
    for word in words:
        if word.upper() in instructions:
            res.append(word)
    return res
```

## kitchen_worker/Dockerfile

```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python" , "main.py"]
```

## kitchen_worker/__init__.py

```python

```

## kitchen_worker/main.py

```python
from confluent_kafka import Consumer
from mongo_handler import MongoManger, update_order_in_mongo
from redis_handler import RedisManager
import os
import json
import time

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_TOPIC])

mongo_manager = MongoManger()
redis_manager = RedisManager()


while True:
    # getting data from kafka
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)
    
    try:
        # update status in mongo
        client = mongo_manager.get_client()
        update_order_in_mongo(order["order_id"], client)

        # deleting from redis
        redis_manager.r.delete(order["order_id"])

        # waiting...
        time.sleep(6)

    except Exception as e:
        raise Exception(f"Error: {str(e)}")
```

## kitchen_worker/mongo_handler.py

```python
from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI") 

class MongoManger:
    client = None
    def __init__(self):
        try:
            if not MongoManger.client:
                MongoManger.client = MongoClient(MONGO_URI)
            self.client = MongoManger.client
        except Exception as e:
            raise Exception(f"Could not connect to mongo db, Error: {str(e)}")

    def get_client(self):
        return self.client  

def update_order_in_mongo(order_id: str, client: MongoClient):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id, "status": { "$ne": "BURNT" }}, {"$set": {"status": "DELIVERED"}})
    except Exception as e:
        raise Exception(f"Could not update order status, Error: {str(e)}")
```

## kitchen_worker/redis_handler.py

```python
from redis import Redis
import os

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_DB = os.getenv("REDIS_DB")

class RedisManager:
    r = None
    def __init__(self):
        try:
            if not RedisManager.r:
                RedisManager.r = Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    decode_responses=True)
            self.r = RedisManager.r
            
        except Exception as e:
            raise Exception(f"Could not init redis, Error: {str(e)}")
```

## kitchen_worker/requirements.txt

```
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
click==8.3.1
colorama==0.4.6
confluent-kafka==2.13.0
dnspython==2.8.0
fastapi==0.129.0
h11==0.16.0
idna==3.11
pydantic==2.12.5
pydantic_core==2.41.5
pymongo==4.16.0
python-multipart==0.0.22
redis==7.1.1
starlette==0.52.1
typing-inspection==0.4.2
typing_extensions==4.15.0
uvicorn==0.40.0
```

## preprocessor/Dockerfile

```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python" , "main.py"]
```

## preprocessor/jsons/pizza_prep.json

```json
{
  "Margherita": "Preheat oven to 230°C (450°F) or wood-fired oven to 485°C (905°F). Bake for 8-12 minutes in conventional oven or 60-90 seconds in wood-fired oven until crust is golden and cheese is melted and bubbling. Allow fresh mozzarella to come to room temperature for best melt. Add fresh basil leaves in the last minute of baking or immediately after removing from oven. Drizzle with extra virgin olive oil before serving. Keep refrigerated until ready to bake. Wash hands before and after handling fresh ingredients. Use clean utensils for slicing.",
  "Pepperoni": "Preheat oven to 220°C (425°F). Bake for 12-15 minutes until cheese is melted and pepperoni edges are slightly crispy. For frozen pizza: do not thaw, bake directly from frozen for 15-18 minutes. Place directly on oven rack or use a pizza stone for crispier crust. Rotate pizza halfway through baking for even cooking. Let rest for 2-3 minutes before slicing to allow cheese to set. Keep refrigerated or frozen until ready to cook. Wash hands after handling raw dough or packaging. Clean cutting board and pizza cutter after use.",
  "Hawaiian": "Preheat oven to 220°C (425°F). Bake for 12-15 minutes until cheese is golden and pineapple begins to caramelize. Ensure ham is heated through to at least 60°C (140°F) internal temperature. Pat pineapple chunks dry with paper towel before adding to reduce excess moisture. Use a pizza stone or perforated pan to help achieve a crispy crust despite moisture from pineapple. Let cool for 3-4 minutes before slicing to prevent toppings from sliding. Keep refrigerated until baking. Wash hands after handling ham and before touching other ingredients. Ensure all surfaces are clean to prevent cross-contamination with pork products.",
  "BBQ Chicken": "Preheat oven to 220°C (425°F). Ensure chicken is pre-cooked to 74°C (165°F) before adding to pizza. Bake for 12-14 minutes until cheese is melted and BBQ sauce is bubbling. If using raw chicken, cook chicken thoroughly before assembly. Brush crust edges with olive oil for golden finish. Add fresh cilantro after baking to preserve its bright flavor. Let pizza rest 2-3 minutes before cutting. For extra flavor, brush additional BBQ sauce on crust edges. If using raw chicken, use separate cutting board and utensils. Wash hands thoroughly with soap after handling raw chicken. Clean all surfaces that contacted raw chicken with hot soapy water. Ensure chicken reaches safe internal temperature.",
  "Meat Lovers": "Preheat oven to 220°C (425°F). Bake for 14-18 minutes until all meats are thoroughly heated and cheese is golden brown. Ensure internal temperature reaches at least 74°C (165°F) for food safety. For frozen pizza, bake 18-22 minutes without thawing. Use a pizza stone or dark pan to support the weight of heavy toppings. Rotate pizza halfway through baking for even cooking. Let rest for 3-5 minutes before slicing to allow fats to settle. Blot excess grease with paper towel if desired. Keep refrigerated or frozen until ready to cook. Wash hands after handling raw or processed meats. Use clean utensils for serving. Wipe down preparation surfaces after handling meat products.",
  "Veggie Supreme": "Preheat oven to 220°C (425°F). Bake for 12-15 minutes until vegetables are tender and cheese is melted and lightly browned. If vegetables are raw, may require additional 2-3 minutes for proper cooking. Pre-cook high-moisture vegetables like zucchini to prevent soggy crust. Arrange vegetables evenly for consistent cooking. Use perforated pizza pan for crispier bottom despite vegetable moisture. Let cool for 2-3 minutes before slicing. Wash all fresh vegetables thoroughly before use. Keep refrigerated until ready to bake. Wash hands before and after handling fresh produce. Use clean cutting boards for vegetables.",
  "Four Cheese": "Preheat oven to 220°C (425°F). Bake for 10-12 minutes until all cheeses are melted and bubbling. Watch carefully to prevent burning; cheese can brown quickly. Remove when golden spots appear on surface. Bring cheeses to room temperature before baking for even melting. Finish with fresh herbs (basil, oregano) immediately after baking. Let rest 3-4 minutes before slicing as cheese will be very hot. Use pizza stone for crispy crust to balance rich topping. Keep refrigerated until ready to bake. Wash hands after handling different cheese varieties. Use clean utensils for each cheese type if assembling. Wipe down surfaces after handling dairy products.",
  "Buffalo Chicken": "Preheat oven to 220°C (425°F). Ensure chicken is pre-cooked to 74°C (165°F) before adding to pizza. Bake for 12-14 minutes until cheese is melted and buffalo sauce is bubbling. Add ranch or blue cheese drizzle after baking. Toss chicken in buffalo sauce just before adding to pizza. Don't over-sauce or crust will become soggy. Add celery garnish after baking for fresh crunch. Let cool 2-3 minutes before slicing. Use separate utensils for raw and cooked chicken. Wash hands thoroughly after handling chicken. Keep refrigerated until ready to bake. Clean all surfaces that contacted raw poultry.",
  "White Pizza": "Preheat oven to 230°C (450°F). Bake for 10-12 minutes until ricotta is set and mozzarella is golden brown. Garlic should be fragrant and lightly golden, not burnt. Remove when cheese begins to brown on edges. Spread ricotta evenly, leaving 1-inch border for crust. Use roasted garlic for sweeter, mellower flavor. Drizzle with olive oil before and after baking. Add fresh herbs after baking. Let rest 3-4 minutes before slicing. Keep all dairy products refrigerated until use. Wash hands before and after handling cheeses. Use clean utensils for spreading ricotta. Ensure workspace is clean and sanitized.",
  "Mushroom & Truffle": "Preheat oven to 230°C (450°F). Sauté mushrooms in butter or olive oil before adding to pizza to remove moisture. Bake for 10-12 minutes until cheese is melted and mushrooms are golden. Add truffle oil after baking, not before, to preserve aroma. Use variety of mushrooms for complex flavor. Don't wash mushrooms; wipe with damp cloth to prevent excess moisture. Add fresh thyme during last minute of baking. Drizzle truffle oil sparingly (2-3 teaspoons) immediately before serving. Let rest 2 minutes before slicing. Clean mushrooms properly before cooking. Wash hands after handling raw mushrooms. Keep refrigerated until ready to prepare. Use clean utensils for sautéing and assembly.",
  "Prosciutto & Arugula": "Preheat oven to 230°C (450°F). Bake pizza base (without prosciutto and arugula) for 10-12 minutes until cheese is melted and crust is golden. Add fresh arugula and prosciutto immediately after removing from oven. Do not bake prosciutto or arugula as they should remain fresh. Toss arugula lightly with olive oil and lemon juice before adding. Arrange prosciutto in delicate folds, not flat. Add shaved parmesan on top of arugula. Drizzle with balsamic glaze in thin lines. Serve immediately; do not let sit or arugula will wilt. Wash arugula thoroughly and pat dry. Keep prosciutto refrigerated until ready to use. Wash hands after handling cured meats. Use clean utensils for assembly.",
  "Capricciosa": "Preheat oven to 220°C (425°F). Arrange toppings in sections if following traditional preparation. Bake for 12-15 minutes until cheese is melted and ham is heated through. Artichokes and mushrooms should be tender. Pre-cook mushrooms to remove excess moisture. Drain artichokes thoroughly before adding. Arrange ingredients in quadrants for visual appeal. Let rest 2-3 minutes before slicing. Wash hands after handling ham and before touching other ingredients. Keep refrigerated until baking. Drain jarred ingredients (artichokes, olives) before use. Clean utensils between handling different ingredients.",
  "Quattro Stagioni": "Preheat oven to 220°C (425°F). Divide pizza into 4 sections, arranging each season's ingredients in separate quadrants. Bake for 12-15 minutes until cheese is melted and all toppings are heated through. Ensure ingredients don't mix between sections. Use dividers or careful placement to keep sections distinct. Pre-cook mushrooms to prevent excess moisture. Drain artichokes and olives thoroughly. Visual presentation is important for this pizza. Let rest 3 minutes before carefully slicing. Wash hands after handling ham. Keep all ingredients refrigerated until assembly. Use separate utensils for each ingredient type to maintain distinct flavors. Clean workspace between ingredient groups.",
  "Diavola": "Preheat oven to 220°C (425°F). Bake for 12-14 minutes until cheese is melted and spicy salami is crispy on edges. Chili peppers should be fragrant but not burnt. Remove when crust is golden brown. Adjust amount of chili peppers based on desired heat level. Add fresh chilies after baking for extra heat if desired. Drizzle with chili oil for additional spiciness. Let rest 2-3 minutes before slicing. Have cooling beverages ready. Wash hands thoroughly after handling chili peppers. Avoid touching face or eyes after handling peppers. Keep refrigerated until baking. Clean cutting board and utensils after handling spicy ingredients.",
  "Marinara": "Preheat oven to 240°C (475°F) for high-heat baking. Bake for 8-10 minutes until crust is crispy and golden with slight charring. Garlic should be fragrant and golden, not burnt. No cheese means shorter baking time. Use high-quality tomato sauce as it's the star ingredient. Slice garlic thinly for even distribution. Brush crust edges with olive oil for golden color. Add fresh oregano in last minute of baking. Drizzle with extra virgin olive oil immediately after baking. Wash hands before handling fresh ingredients. Use clean utensils for sauce and toppings. Keep ingredients at appropriate temperature. Maintain clean workspace.",
  "Napoletana": "Preheat oven to 220°C (425°F). Bake for 10-12 minutes until cheese is melted and anchovies are heated through. Capers should remain intact, not burnt. Remove when cheese is bubbling. Rinse anchovies if packed in salt to reduce saltiness. Distribute anchovies and capers evenly. Don't add extra salt; anchovies and capers are very salty. Let rest 2 minutes before slicing. Fresh oregano can be added after baking. Wash hands after handling anchovies (fish). Keep refrigerated until baking. Use separate utensils for fish products. Clean workspace thoroughly after handling anchovies.",
  "Sicilian": "Preheat oven to 230°C (450°F). Bake in oiled rectangular pan for 15-20 minutes until bottom is golden and crispy. Cheese should be melted and bubbly. Thick crust requires longer baking than thin crust. Oil the pan generously for crispy bottom. Let dough rise in pan before adding toppings for airy texture. Some versions put sauce on top of cheese; follow recipe preference. Let rest 5 minutes before slicing to allow structure to set. Keep refrigerated until ready to bake. Wash hands before handling dough. Use clean utensils and pans. Ensure pan is properly cleaned and oiled.",
  "Detroit Style": "Preheat oven to 260°C (500°F). Use blue steel or heavy-duty rectangular pan. Bake for 12-15 minutes until cheese on edges is crispy and caramelized. Bottom should be very crispy, interior airy. Apply sauce in stripes on top after cheese. Oil pan heavily, especially edges, for signature crispy cheese. Press cheese all the way to pan edges. Use brick cheese or similar for authentic flavor. Let cool 3-5 minutes before removing from pan. Run spatula around edges to release crispy cheese. Keep refrigerated until baking. Wash hands before handling ingredients. Use oven mitts when handling hot pan. Clean pan thoroughly after use.",
  "Chicago Deep Dish": "Preheat oven to 220°C (425°F). Build in reverse order: dough, cheese, toppings, sauce on top. Bake for 30-45 minutes until crust is golden brown and filling is bubbling. Internal temperature should reach 74°C (165°F). Much longer baking time than regular pizza. Use deep round pan (2-3 inches deep). Brush pan with butter or oil for flaky crust. Cover with foil for first 20 minutes, then uncover to brown. Let rest 10 minutes before slicing; very hot inside. Use fork and knife to eat; too thick to fold. Keep refrigerated until baking. Wash hands before handling ingredients. Use oven mitts for deep, heavy pan. Be careful of hot cheese and sauce when cutting.",
  "New York Style": "Preheat oven to 260°C (500°F) or use deck oven. Bake for 8-12 minutes until bottom is crispy and cheese has slight brown spots. Crust should be crispy enough to support a fold but still pliable. Remove when cheese is bubbling. Use pizza stone or steel for authentic texture. High heat is essential for proper crust. Don't overload with toppings; keep it simple. Brush crust edges with garlic oil for extra flavor. Let cool 1-2 minutes before slicing. Keep refrigerated until baking. Wash hands before handling dough. Use clean pizza peel and cutter. Maintain clean workspace.",
  "Pesto Chicken": "Preheat oven to 220°C (425°F). Ensure chicken is pre-cooked to 74°C (165°F). Bake for 12-14 minutes until cheese is melted and pesto is fragrant. Watch carefully; pesto can darken if overcooked. Spread pesto in thin layer; it's concentrated flavor. Use grilled chicken for smoky depth. Add sun-dried tomatoes before baking. Fresh cherry tomatoes can be added halfway through. Let rest 2 minutes before slicing. Wash hands after handling raw chicken if cooking from scratch. Keep pesto refrigerated until use. Use separate utensils for chicken. Clean surfaces that contacted raw poultry.",
  "Spinach & Feta": "Preheat oven to 220°C (425°F). If using fresh spinach, sauté and drain well before adding to prevent soggy crust. Bake for 12-14 minutes until feta is slightly golden and mozzarella is melted. Remove when cheese is bubbling. Squeeze excess moisture from spinach thoroughly. Crumble feta evenly across pizza. Add garlic for extra flavor. Don't over-bake feta or it will become dry. Let rest 2-3 minutes before slicing. Wash fresh spinach thoroughly in multiple rinses. Keep dairy products refrigerated until use. Wash hands before handling fresh greens. Use clean utensils for assembly.",
  "Greek Pizza": "Preheat oven to 220°C (425°F). Use slightly thicker, oilier crust for authentic Greek style. Bake for 13-15 minutes until feta is softened and olives are heated. Remove when crust is golden. Brush crust with olive oil before and after baking. Use generous oregano; it's essential for Greek flavor. Don't over-bake feta; it should stay creamy. Add cucumber or tomatoes after baking for fresh version. Let rest 2-3 minutes. Wash fresh vegetables thoroughly. Keep feta refrigerated until use. Wash hands before handling ingredients. Drain olives before adding.",
  "Mexican Pizza": "Preheat oven to 220°C (425°F). Cook ground beef with taco seasoning until fully cooked (71°C/160°F internal temperature). Bake pizza base with beef and cheese for 12-14 minutes. Add fresh toppings (lettuce, tomatoes) immediately after removing from oven. Drain excess fat from cooked beef before adding to pizza. Use mix of cheddar and mozzarella for best melt and flavor. Keep fresh toppings cold until ready to add. Add sour cream, salsa, guacamole as table condiments. Let rest 2 minutes before adding fresh toppings. Wash hands after handling raw ground beef. Use separate cutting board for raw meat. Clean all surfaces that contacted raw beef. Wash fresh vegetables before using. Keep cold toppings refrigerated until serving.",
  "Taco Pizza": "Preheat oven to 220°C (425°F). Cook ground beef with taco seasoning until fully cooked (71°C/160°F). Spread refried beans on crust, add beef and cheese. Bake for 12-14 minutes until cheese is melted. Add fresh toppings and crushed tortilla chips immediately after baking. Warm refried beans slightly for easier spreading. Drain beef well to prevent soggy crust. Crush tortilla chips just before adding for maximum crunch. Keep fresh ingredients refrigerated until serving. Add sour cream and salsa at table. Wash hands after handling raw beef. Use separate cutting board for meat. Wash fresh vegetables before use. Clean all surfaces that contacted raw meat. Keep fresh toppings cold.",
  "Philly Cheesesteak": "Preheat oven to 220°C (425°F). Sauté thinly sliced steak, peppers, and onions until steak is cooked through and vegetables are tender. Assemble on pizza with white sauce and provolone. Bake for 12-14 minutes until cheese is melted and bubbling. Use ribeye or sirloin for best flavor. Slice steak paper-thin across the grain. Pre-cook vegetables to remove moisture. Season steak with salt and pepper while cooking. Let rest 2-3 minutes before slicing. Wash hands after handling raw beef. Use separate cutting board and utensils for raw meat. Clean all surfaces after handling raw steak. Ensure steak reaches safe temperature. Keep refrigerated until cooking.",
  "Bacon Cheeseburger": "Preheat oven to 220°C (425°F). Cook ground beef like burger patties, seasoned with salt and pepper, until fully cooked (71°C/160°F). Cook bacon until crispy. Bake pizza with beef, bacon, and cheese for 12-14 minutes. Add fresh toppings (lettuce, tomatoes, pickles) after baking. Drain beef and bacon thoroughly. Make burger sauce (ketchup, mayo, mustard) fresh. Keep fresh toppings cold until serving. Add pickles after baking; they can be warm or cold. Drizzle with burger sauce just before serving. Wash hands after handling raw beef. Use separate cutting board for raw meat. Clean surfaces after handling raw meat. Wash fresh vegetables before use. Keep cold toppings refrigerated.",
  "Pulled Pork BBQ": "Preheat oven to 220°C (425°F). Ensure pulled pork is pre-cooked and heated to at least 74°C (165°F). Bake pizza with BBQ sauce, pork, onions, and cheese for 12-14 minutes. Add coleslaw immediately after baking, if using. Don't over-sauce; excess BBQ sauce makes crust soggy. Shred pork into bite-sized pieces. Caramelize onions slightly before adding for sweetness. Keep coleslaw cold and crisp until topping. Let rest 2-3 minutes before adding coleslaw. Ensure pork is heated to safe temperature. Wash hands after handling meat. Keep coleslaw refrigerated until serving. Use clean utensils for assembly.",
  "Breakfast Pizza": "Preheat oven to 200°C (400°F) - lower than typical pizza to prevent overcooking eggs. Cook bacon and sausage until fully cooked. Scramble eggs until just set. Assemble pizza with cream sauce, meats, eggs, cheese, and hash browns. Bake for 10-12 minutes until cheese is melted; don't over-bake eggs. Pre-cook all proteins thoroughly. Scramble eggs to soft stage; they'll cook more in oven. Use par-cooked or frozen hash browns. Work quickly; eggs don't hold well. Serve immediately after baking. Wash hands after handling raw eggs and meat. Use separate utensils for raw and cooked ingredients. Clean all surfaces after handling raw eggs. Ensure all meats reach safe temperature. Keep refrigerated until baking.",
  "Meatball Parmesan": "Preheat oven to 220°C (425°F). Ensure meatballs are pre-cooked to 74°C (165°F) internal temperature. Slice or break meatballs into smaller pieces. Bake pizza with sauce, meatballs, and cheeses for 14-16 minutes until cheese is golden and bubbly. Make meatballs ahead and refrigerate or use store-bought. Slice meatballs to ensure even cooking and easier eating. Use generous parmesan for authentic flavor. Add fresh basil after baking. Let rest 3-4 minutes before slicing. Wash hands after handling raw meat if making meatballs from scratch. Ensure meatballs are fully cooked before adding. Keep refrigerated until baking. Use clean utensils for assembly.",
  "Chicken Alfredo": "Preheat oven to 200°C (400°F) - lower temp to prevent cream sauce from separating. Ensure chicken is pre-cooked to 74°C (165°F). Spread alfredo sauce, add chicken, top with cheeses. Bake for 12-14 minutes until cheese is melted; watch carefully to prevent burning cream sauce. Make alfredo sauce fresh if possible. Don't over-sauce; cream sauce is rich. Use grilled or roasted chicken for flavor. Add garlic to sauce for depth. Let rest 3-4 minutes before slicing. Finish with fresh parsley. Wash hands after handling raw chicken if cooking from scratch. Keep cream sauce refrigerated until use. Use clean utensils for assembly. Ensure chicken reaches safe temperature.",
  "Shrimp Scampi": "Preheat oven to 220°C (425°F). Sauté shrimp with garlic in butter until just cooked through (pink and opaque). Assemble pizza with garlic butter sauce, shrimp, and cheese. Bake for 10-12 minutes until cheese is melted. Add lemon zest and parsley immediately after baking. Don't overcook shrimp; they cook quickly. Use fresh or properly thawed frozen shrimp. Mince garlic finely for even distribution. Add lemon zest after baking to preserve brightness. Fresh parsley is essential. Serve immediately. Wash hands after handling raw shrimp. Use separate cutting board for seafood. Clean all surfaces after handling shellfish. Ensure shrimp are properly deveined. Keep refrigerated until cooking.",
  "Clam Casino": "Preheat oven to 220°C (425°F). Cook bacon until crispy; set aside. If using fresh clams, steam until opened; chop meat. If using canned, drain well. Assemble pizza with white sauce, clams, bacon, cheese, and breadcrumbs. Bake for 12-14 minutes until golden. Drain clams thoroughly to prevent soggy crust. Crumble bacon into small pieces. Mix breadcrumbs with butter for golden topping. Add parsley and garlic for authentic flavor. Let rest 2 minutes before slicing. Wash hands after handling raw shellfish. Use separate utensils for seafood. Ensure clams are from safe, approved sources. Clean all surfaces after handling shellfish. Keep refrigerated until cooking.",
  "Smoked Salmon": "Preheat oven to 200°C (400°F). Bake crust with cream cheese base only for 8-10 minutes until just golden. Remove from oven and let cool 5-10 minutes. Add smoked salmon, capers, red onions, and dill to cooled crust. Do not bake salmon; it should remain cold and silky. Use high-quality smoked salmon (lox). Slice red onions paper-thin. Fresh dill is essential; dried is not suitable. Can be served cold or at room temperature. This is essentially a cold pizza. Keep salmon refrigerated until ready to assemble. Wash hands after handling fish. Use clean utensils for assembly. Maintain cold chain for salmon. Prepare just before serving.",
  "Mediterranean": "Preheat oven to 220°C (425°F). Drain all jarred/preserved ingredients (artichokes, olives, sun-dried tomatoes) thoroughly. Bake for 12-14 minutes until feta is softened and mozzarella is melted. Remove when crust is golden. Chop sun-dried tomatoes into smaller pieces. Crumble feta evenly. Don't over-bake feta; keep it creamy. Finish with fresh oregano and olive oil drizzle. Let rest 2-3 minutes before slicing. Wash hands before handling ingredients. Drain preserved items completely. Keep dairy refrigerated until use. Use clean utensils for assembly.",
  "Caprese": "Preheat oven to 220°C (425°F). Bake crust with light sauce and mozzarella for 8-10 minutes. Add fresh mozzarella slices and tomato slices for final 2-3 minutes just to warm. Remove from oven. Top with fresh basil, balsamic glaze, and olive oil immediately. Use highest quality fresh mozzarella (buffalo if possible). Slice tomatoes thinly and pat dry to remove excess moisture. Add fresh ingredients at end to preserve texture. Drizzle generously with extra virgin olive oil. Serve immediately while still warm. Wash tomatoes and basil thoroughly. Keep fresh mozzarella refrigerated until use. Use clean cutting board for vegetables. Wash hands before handling fresh ingredients.",
  "Pear & Gorgonzola": "Preheat oven to 200°C (400°F) - lower temp to prevent burning honey/pears. Caramelize pears in butter and honey before adding if using fresh pears. Assemble with white sauce, pears, gorgonzola, mozzarella, and walnuts. Bake for 10-12 minutes until cheese is melted. Drizzle with honey or balsamic immediately after baking. Use ripe but firm pears. Toast walnuts before adding for enhanced flavor. Balance sweet pears with pungent gorgonzola. Don't over-bake; pears should hold shape. Let rest 2-3 minutes before slicing. Wash pears thoroughly. Keep dairy refrigerated until use. Check walnuts for freshness (no rancid smell). Use clean utensils for assembly.",
  "Fig & Prosciutto": "Preheat oven to 220°C (425°F). Bake crust with white sauce and cheese for 10-12 minutes until golden. Remove from oven. Add fresh figs (or warm caramelized figs), prosciutto, and arugula immediately after baking. Drizzle with balsamic reduction or honey. Do not bake prosciutto or arugula. Use fresh figs when in season; otherwise use preserved. Arrange prosciutto in delicate folds. Fresh arugula adds peppery contrast. Balance sweet figs with salty prosciutto. Serve immediately. Wash fresh figs and arugula thoroughly. Keep prosciutto refrigerated until use. Use clean utensils for assembly. Wash hands after handling cured meats.",
  "Caramelized Onion & Goat Cheese": "Preheat oven to 220°C (425°F). Caramelize onions slowly in butter and oil over medium-low heat for 30-40 minutes until deeply golden and sweet. Assemble pizza with white sauce or olive oil, caramelized onions, goat cheese, mozzarella, and fresh thyme. Bake for 10-12 minutes until cheese is melted. Don't rush caramelizing onions; low and slow is key. Use sweet onions (Vidalia, Walla Walla) for best results. Crumble goat cheese evenly. Add fresh thyme before or after baking. Optional: drizzle with honey or balsamic after baking. Let rest 2-3 minutes. Wash hands before handling ingredients. Keep dairy products refrigerated until use. Use clean pan for caramelizing onions. Maintain clean workspace.",
  "Roasted Garlic & Ricotta": "Preheat oven to 220°C (425°F). Roast whole garlic heads at 200°C (400°F) for 30-40 minutes until soft and caramelized (can be done ahead). Squeeze roasted garlic cloves from skins. Assemble pizza with olive oil, ricotta, roasted garlic, mozzarella, and herbs. Bake for 10-12 minutes until cheese is golden. Roast garlic ahead of time for convenience. Roasted garlic is sweet and mild, not sharp. Spread ricotta evenly, leaving border for crust. Use fresh herbs (rosemary, thyme, or basil). Drizzle with olive oil before and after baking. Let rest 3-4 minutes. Wash hands before handling ingredients. Keep ricotta refrigerated until use. Use clean utensils for spreading cheese. Maintain clean workspace.",
  "Sun-Dried Tomato & Basil": "Preheat oven to 220°C (425°F). Drain sun-dried tomatoes and pat dry; chop if whole. Assemble pizza with tomato sauce, sun-dried tomatoes, mozzarella, and garlic. Bake for 12-14 minutes until cheese is melted. Add fresh basil immediately after baking. Oil-packed sun-dried tomatoes have better flavor than dry-packed. Reserve some tomato oil for drizzling on crust. Mince garlic finely or use roasted garlic. Fresh basil is essential; add after baking. Optional: add pine nuts or parmesan. Let rest 2 minutes. Wash hands before handling ingredients. Keep ingredients at appropriate temperature. Use clean utensils for assembly. Wash fresh basil before use.",
  "Artichoke & Olive": "Preheat oven to 220°C (425°F). Drain marinated artichokes and olives thoroughly; pat dry. Assemble pizza with white sauce or olive oil, artichokes, olives, mozzarella, and feta. Bake for 12-14 minutes until cheese is melted and edges are golden. Quarter artichoke hearts if large. Mix different olive varieties for complexity. Don't over-bake feta; keep it creamy. Add fresh herbs (oregano, basil) after baking. Drizzle with olive oil before serving. Let rest 2-3 minutes. Drain jarred ingredients thoroughly. Keep dairy refrigerated until use. Wash hands before handling ingredients. Use clean utensils for assembly.",
  "Eggplant Parmesan": "Preheat oven to 220°C (425°F). Slice eggplant, bread with flour, egg, and breadcrumbs. Fry breaded eggplant until golden (can be done ahead). Assemble pizza with tomato sauce, fried eggplant, mozzarella, and parmesan. Bake for 12-14 minutes until cheese is golden and bubbling. Salt eggplant slices and let sit 30 minutes to remove bitterness; rinse and pat dry. Fry eggplant until golden and crispy. Drain on paper towels to remove excess oil. Layer eggplant slices without overlapping too much. Add fresh basil after baking. Let rest 3-4 minutes. Wash eggplant thoroughly. Use separate bowls for flour, egg, and breadcrumbs (breading station). Keep egg refrigerated until use. Clean surfaces after handling raw egg. Wash hands after breading process.",
  "Ratatouille": "Preheat oven to 220°C (425°F). Slice vegetables (zucchini, eggplant, peppers, tomatoes) thinly. Sauté or roast vegetables separately to remove moisture and develop flavor. Assemble pizza with tomato sauce, cooked vegetables, herbs, and cheese if using. Bake for 12-14 minutes until vegetables are tender and cheese (if using) is melted. Pre-cook vegetables to prevent soggy crust. Slice vegetables uniformly for even cooking. Season vegetables with herbs de Provence or Italian herbs. Arrange vegetables in decorative pattern for beautiful presentation. Can be made vegan by omitting cheese. Let rest 2-3 minutes. Wash all vegetables thoroughly. Use clean cutting board for vegetables. Wash hands before handling fresh produce. Keep ingredients at appropriate temperature.",
  "Carbonara": "Preheat oven to 200°C (400°F) - lower temp to prevent scrambling eggs. Cook bacon or pancetta until crispy. Beat eggs with parmesan cheese. Assemble pizza with cream sauce base (if using), bacon, and some cheese. Bake for 8-10 minutes. Drizzle egg mixture over hot pizza immediately after removing from oven. Return to oven for 2-3 minutes until eggs are just set. Work quickly with eggs; they set fast. Use freshly grated parmesan for best results. Crumble bacon into small pieces. Add generous black pepper (signature carbonara ingredient). Don't overcook eggs or they'll become rubbery. Serve immediately. Wash hands after handling raw eggs. Keep eggs refrigerated until use. Use pasteurized eggs if concerned about safety. Clean surfaces after handling raw eggs. Wash hands after handling bacon.",
  "Bolognese": "Preheat oven to 220°C (425°F). Prepare Bolognese meat sauce with ground beef, tomatoes, onions, carrots, celery, and herbs; simmer for at least 1-2 hours (can be made ahead). Assemble pizza with Bolognese sauce and cheeses. Bake for 14-16 minutes until cheese is golden and sauce is bubbling. Thick sauce requires slightly longer baking. Make Bolognese sauce ahead; flavors improve overnight. Don't over-sauce; too much liquid makes crust soggy. Use mix of mozzarella and parmesan for best flavor. Add fresh basil or parsley after baking. Let rest 3-5 minutes before slicing. Wash hands after handling raw beef if making sauce from scratch. Wash and chop vegetables on clean cutting board. Cook meat to safe temperature (71°C/160°F). Store sauce properly if making ahead. Keep refrigerated until use.",
  "Funghi (Mushroom)": "Preheat oven to 230°C (450°F). Sauté mushrooms in butter or olive oil with garlic until golden and moisture is evaporated. Assemble pizza with tomato sauce, sautéed mushrooms, mozzarella, and fresh parsley. Bake for 10-12 minutes until cheese is melted and mushrooms are golden. Use variety of mushrooms for complex flavor (cremini, button, shiitake, oyster). Don't wash mushrooms; wipe with damp cloth. Cook mushrooms until golden; don't crowd pan. Add fresh parsley and garlic after baking for brightness. Optional: finish with truffle oil or parmesan. Let rest 2 minutes. Clean mushrooms properly before cooking. Wash hands after handling raw mushrooms. Use clean cutting board and knife. Keep refrigerated until cooking.",
  "Sausage & Peppers": "Preheat oven to 220°C (425°F). Cook Italian sausage until fully cooked (74°C/165°F internal temperature); slice or crumble. Roast or sauté peppers and onions until tender and slightly charred. Assemble pizza with tomato sauce, sausage, peppers, onions, and mozzarella. Bake for 12-14 minutes until cheese is golden. Use mix of red, yellow, and green peppers for color and flavor. Fennel seeds in sausage provide signature flavor. Caramelize onions for sweetness. Use hot or sweet Italian sausage based on preference. Let rest 2-3 minutes before slicing. Wash hands after handling raw sausage. Cook sausage to safe temperature. Wash vegetables before roasting. Clean surfaces after handling raw meat. Keep refrigerated until cooking.",
  "Anchovy & Caper": "Preheat oven to 220°C (425°F). Rinse anchovies to reduce saltiness if desired (optional). Assemble pizza with tomato sauce, anchovies, capers, mozzarella, and oregano. Bake for 10-12 minutes until cheese is melted and anchovies are heated. Capers should remain intact. Distribute anchovies and capers evenly. Use high-quality anchovies packed in olive oil for best flavor. Don't add extra salt; both ingredients are very salty. Add fresh oregano after baking. Drizzle with olive oil before serving. Let rest 2 minutes. Wash hands after handling anchovies (fish). Use separate utensils for fish products. Keep refrigerated until baking. Clean workspace after handling fish.",
  "Spicy Salami": "Preheat oven to 220°C (425°F). Arrange spicy salami slices on pizza. Bake for 12-14 minutes until cheese is melted and salami edges are crispy. Add hot peppers (fresh or pickled) during or after baking based on preference. Drizzle with chili oil if desired. Use high-quality spicy salami (soppressata, calabrese, ventriciana). Don't overlap salami too much or it won't crisp. Adjust pepper amount for desired heat level. Fresh chilies can be added before or after baking. Chili oil is optional but enhances spice. Let rest 2-3 minutes. Wash hands after handling chili peppers. Avoid touching face or eyes after handling peppers. Keep refrigerated until baking. Use gloves when handling very hot peppers."
}
```

## preprocessor/main.py

```python
from confluent_kafka import Consumer
import os
import json
import logging
from producer_handler import KafkaProducer
from text_handler import get_instructions, clean_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_LISTEN_TOPIC = os.getenv("KAFKA_LISTEN_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_LISTEN_TOPIC])

producer = KafkaProducer()

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)

    #
    cleaned_instruction = clean_text(order["special_instructions"])
    cleaned_prep_instructions = clean_text(get_instructions(order["pizza_type"]))

    logger.info(cleaned_instruction)
    logger.info(cleaned_prep_instructions)

    cleaned_instruction = {
        "order_id": order["order_id"],
        "pizza_type": order["pizza_type"],
        "special_instructions": cleaned_instruction,
        "prep_instructions": cleaned_prep_instructions
    }
    producer.send_orders_to_kafka(cleaned_instruction)
```

## preprocessor/producer_handler.py

```python
from confluent_kafka import Producer
import json
import os

BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_SEND_TOPIC = os.getenv("KAFKA_SEND_TOPIC")

producer_config = {"bootstrap.servers": BOOTSTRAP_SERVERS}

class KafkaProducer:
    producer = None
    def __init__(self):
        try:
            if not KafkaProducer.producer:
                KafkaProducer.producer = Producer(producer_config)
            self.producer = KafkaProducer.producer
        except Exception as e:
            raise Exception(f"Could not init kafka producer, Error: {str(e)}")
        
    def send_orders_to_kafka(self, order_details, topic: str = KAFKA_SEND_TOPIC): 
        try:
            self.producer.produce(topic, value=json.dumps(order_details).encode("utf-8"))
            self.producer.flush()
        except Exception as e:
            raise Exception(f"Could not send {order_details} to kafka, Error: {str(e)}")
        return f"All data sent to kafka"
```

## preprocessor/requirements.txt

```
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
click==8.3.1
colorama==0.4.6
confluent-kafka==2.13.0
dnspython==2.8.0
fastapi==0.129.0
h11==0.16.0
idna==3.11
pydantic==2.12.5
pydantic_core==2.41.5
pymongo==4.16.0
python-multipart==0.0.22
redis==7.1.1
starlette==0.52.1
typing-inspection==0.4.2
typing_extensions==4.15.0
uvicorn==0.40.0
```

## preprocessor/text_handler.py

```python
import re
import json

def get_instructions(pizza_type):
    with open("./jsons/pizza_prep.json") as file:
        data = json.load(file)

    for key, value in data.items():
        if pizza_type in key:
            return value

def clean_text(text):
    final_txt = re.sub(r'[^a-zA-Z ]', '', text)
    final_txt = re.sub(r'\s+', ' ', final_txt).strip()
    return final_txt.upper()
```

## text_worker/Dockerfile

```
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD [ "python" , "main.py"]
```

## text_worker/__init__.py

```python

```

## text_worker/main.py

```python
from confluent_kafka import Consumer
from mongo_handler import MongoManger, add_cleaned_protocol, add_danger_field
import os
import json
import logging
from text_handler import check_for_danger, clean_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC")
BOOTSTRAP_SERVERS = os.getenv("BOOTSTRAP_SERVERS")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID")

consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": KAFKA_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
}

consumer = Consumer(consumer_config)
consumer.subscribe([KAFKA_TOPIC])

mongo_manager = MongoManger()


while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Error:", msg.error())
        continue
    value = msg.value().decode("utf-8")
    order = json.loads(value)
    logger.info(order)

    try:
        text = order["special_instructions"]
        client = mongo_manager.get_client()

        cleaned_text = clean_text(text)
        add_cleaned_protocol(order["order_id"], cleaned_text, client)

        danger_words = ["GLUTEN","PEANUT","ALLERGY"]
        danger_order = check_for_danger(cleaned_text, danger_words)

        if danger_order:
            add_danger_field(order["order_id"], client)

    except Exception as e:
        raise Exception(f"Error: {str(e)}")
```

## text_worker/mongo_handler.py

```python
from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI") 

class MongoManger:
    client = None
    def __init__(self):
        try:
            if not MongoManger.client:
                MongoManger.client = MongoClient(MONGO_URI)
            self.client = MongoManger.client
        except Exception as e:
            raise Exception(f"Could not connect to mongo db, Error: {str(e)}")

    def get_client(self):
        return self.client  

def add_danger_field(order_id, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"allergies_flaged": True}})
    except Exception as e:
        raise Exception(f"Could not set danger field, Error: {str(e)}")
    
def add_cleaned_protocol(order_id, text, client):
    database = client["orders_database"]
    collection = database["orders_collection"]
    try:
        collection.update_one({"order_id": order_id}, {"$set": {"protocol_cleaned": text}})
    except Exception as e:
        raise Exception(f"Could not set danger field, Error: {str(e)}")
    
```

## text_worker/requirements.txt

```
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.12.1
click==8.3.1
colorama==0.4.6
confluent-kafka==2.13.0
dnspython==2.8.0
fastapi==0.129.0
h11==0.16.0
idna==3.11
pydantic==2.12.5
pydantic_core==2.41.5
pymongo==4.16.0
python-multipart==0.0.22
redis==7.1.1
starlette==0.52.1
typing-inspection==0.4.2
typing_extensions==4.15.0
uvicorn==0.40.0
```

## text_worker/text_handler.py

```python
import re

def check_for_danger(text, danger_words):
    for word in danger_words:
        if word in text:
            return True
    return False

def clean_text(text):
    final_txt = re.sub(r'[^a-zA-Z ]', '', text)
    final_txt = re.sub(r'\s+', ' ', final_txt).strip()
    return final_txt.upper()
```

